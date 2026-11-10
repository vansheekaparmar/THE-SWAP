"""THE SWAP - the real-life version. Run:  python app.py"""
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash

import db
import rules


def load_secret_key():
    """Signs the login cookie. Production: set the SWAP_SECRET environment variable."""
    if os.environ.get("SWAP_SECRET"):
        return os.environ["SWAP_SECRET"]
    path = Path(__file__).parent / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,        # JavaScript can't read the login cookie
    SESSION_COOKIE_SAMESITE="Lax",       # other websites can't make the browser send it
)
db.init_db()


class SwapError(Exception):
    """An action that is not allowed. The message is shown to the user."""


# ---------- database connection and login ----------
def get_conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(_error):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_conn().execute(
        "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify(ok=False, message="Please log in."), 401
        return view(user, *args, **kwargs)
    return wrapper


# ---------- small helpers ----------
def now_ts():
    return datetime.now().strftime(rules.FMT)


def label(shift):
    start = datetime.strptime(shift["start_ts"], rules.FMT)
    end = datetime.strptime(shift["end_ts"], rules.FMT)
    return f"{start:%a %d %b} {start:%H:%M}-{end:%H:%M}"


def shift_minutes(shift):
    return rules.to_minutes(shift["end_ts"]) - rules.to_minutes(shift["start_ts"])


def shift_json(shift):
    return {"id": shift["id"], "label": label(shift), "hours": shift_minutes(shift) / 60}


def get_shift(conn, shift_id):
    return conn.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()


def get_swap(conn, swap_id):
    swap = conn.execute("SELECT * FROM swaps WHERE id = ?", (swap_id,)).fetchone()
    if swap is None:
        raise SwapError("Request not found.")
    return swap


def times_of(conn, user_id, skip_id=None):
    """The (start, end) of every shift a person works. skip_id leaves one shift out
    (used for a two-way swap: the shift the person is about to hand over)."""
    rows = conn.execute("SELECT start_ts, end_ts FROM shifts WHERE user_id = ? AND id IS NOT ?",
                        (user_id, skip_id))
    return [(r["start_ts"], r["end_ts"]) for r in rows]


def notify(conn, user_id, text):
    conn.execute("INSERT INTO notifications (user_id, text) VALUES (?, ?)", (user_id, text))


def name_of(conn, user_id):
    return conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()["name"]


def can_take(conn, user_id, shift, skip_id=None):
    """The rules engine (C++) decides whether this person may take the shift."""
    return rules.check_shift(times_of(conn, user_id, skip_id), (shift["start_ts"], shift["end_ts"]))


def is_locked(conn, shift_id):
    """A shift that is already part of a live swap can't be used in another one."""
    return conn.execute(
        "SELECT 1 FROM swaps WHERE (shift_id = ? AND status IN ('open', 'pending')) "
        "OR (return_shift_id = ? AND status = 'pending')", (shift_id, shift_id)).fetchone() is not None


def trade_options(conn, user_id, giver_id, shift):
    """Two-way swap: which of this person's own shifts could they give back in return?
    Both people are checked AFTER the exchange."""
    options = []
    rows = conn.execute("SELECT * FROM shifts WHERE user_id = ? AND start_ts > ? ORDER BY start_ts",
                        (user_id, now_ts())).fetchall()
    for mine in rows:
        if is_locked(conn, mine["id"]):
            continue
        if can_take(conn, user_id, shift, skip_id=mine["id"]) != rules.OK:
            continue                                   # I could not take their shift
        if can_take(conn, giver_id, mine, skip_id=shift["id"]) != rules.OK:
            continue                                   # they could not take mine
        options.append(mine)
    return options


# ---------- actions: each one checks, changes the data, returns a message ----------
def open_swap(conn, user, shift_id):
    shift = get_shift(conn, shift_id)
    if shift is None or shift["user_id"] != user["id"]:
        raise SwapError("That is not your shift.")
    if shift["start_ts"] <= now_ts():
        raise SwapError("This shift has already started.")
    if is_locked(conn, shift_id):
        raise SwapError("This shift is already part of a swap.")
    try:
        conn.execute("INSERT INTO swaps (shift_id, giver_id, status) VALUES (?, ?, 'open')",
                     (shift_id, user["id"]))
    except sqlite3.IntegrityError:
        raise SwapError("This shift is already open.")
    # only colleagues who can really take the shift are notified
    colleagues = conn.execute(
        "SELECT id FROM users WHERE role = 'employee' AND id != ?", (user["id"],)).fetchall()
    for colleague in colleagues:
        if can_take(conn, colleague["id"], shift) == rules.OK or trade_options(conn, colleague["id"], user["id"], shift):
            notify(conn, colleague["id"], f"{user['name']} opened {label(shift)} for a swap.")
    return "Shift is open. Colleagues who can take it were notified."


def cancel_swap(conn, user, swap_id):
    swap = get_swap(conn, swap_id)
    if swap["giver_id"] != user["id"] or swap["status"] != "open":
        raise SwapError("You can only cancel your own open shift.")
    conn.execute("UPDATE swaps SET status = 'cancelled' WHERE id = ?", (swap_id,))
    return "Request cancelled."


def accept_swap(conn, user, swap_id):
    if user["role"] != "employee":
        raise SwapError("Only employees can take shifts.")
    swap = get_swap(conn, swap_id)
    if swap["giver_id"] == user["id"]:
        raise SwapError("You can't accept your own shift.")
    if swap["status"] != "open":
        raise SwapError("Sorry, this shift was just taken.")
    shift = get_shift(conn, swap["shift_id"])
    problem = can_take(conn, user["id"], shift)
    if problem != rules.OK:
        raise SwapError(rules.MESSAGES[problem])
    # first one wins: this only changes the row if it is STILL open
    cursor = conn.execute(
        "UPDATE swaps SET status = 'pending', taker_id = ? WHERE id = ? AND status = 'open'",
        (user["id"], swap_id))
    if cursor.rowcount != 1:
        raise SwapError("Sorry, this shift was just taken.")
    giver = name_of(conn, swap["giver_id"])
    for manager in conn.execute("SELECT id FROM users WHERE role = 'manager'").fetchall():
        notify(conn, manager["id"], f"{user['name']} wants {giver}'s {label(shift)}. Approval needed.")
    notify(conn, swap["giver_id"], f"{user['name']} accepted your {label(shift)}. Waiting for the manager.")
    return "Sent to the manager. Waiting for approval."


def trade_swap(conn, user, swap_id, give_id):
    """Two-way swap: take the open shift AND give one of my own shifts back."""
    if user["role"] != "employee":
        raise SwapError("Only employees can take shifts.")
    swap = get_swap(conn, swap_id)
    if swap["giver_id"] == user["id"]:
        raise SwapError("You can't accept your own shift.")
    if swap["status"] != "open":
        raise SwapError("Sorry, this shift was just taken.")
    shift = get_shift(conn, swap["shift_id"])
    mine = get_shift(conn, give_id)
    if mine is None or mine["user_id"] != user["id"]:
        raise SwapError("That is not your shift.")
    if mine["start_ts"] <= now_ts():
        raise SwapError("That shift has already started.")
    if is_locked(conn, give_id):
        raise SwapError("That shift is already part of a swap.")
    problem = can_take(conn, user["id"], shift, skip_id=give_id)
    if problem != rules.OK:
        raise SwapError(rules.MESSAGES[problem])
    if can_take(conn, swap["giver_id"], mine, skip_id=shift["id"]) != rules.OK:
        raise SwapError(f"{name_of(conn, swap['giver_id'])} could not take that shift (hours, overlap or rest).")
    cursor = conn.execute(
        "UPDATE swaps SET status = 'pending', taker_id = ?, return_shift_id = ? WHERE id = ? AND status = 'open'",
        (user["id"], give_id, swap_id))
    if cursor.rowcount != 1:
        raise SwapError("Sorry, this shift was just taken.")
    giver = name_of(conn, swap["giver_id"])
    for manager in conn.execute("SELECT id FROM users WHERE role = 'manager'").fetchall():
        notify(conn, manager["id"],
               f"{user['name']} offers {label(mine)} for {giver}'s {label(shift)}. Approval needed.")
    notify(conn, swap["giver_id"],
           f"{user['name']} offers a trade: your {label(shift)} for their {label(mine)}. Waiting for the manager.")
    return "Trade sent to the manager. Waiting for approval."


def approve_swap(conn, user, swap_id):
    if user["role"] != "manager":
        raise SwapError("Only a manager can approve.")
    swap = get_swap(conn, swap_id)
    if swap["status"] != "pending":
        raise SwapError("This request is no longer waiting for approval.")
    shift = get_shift(conn, swap["shift_id"])
    if shift["user_id"] != swap["giver_id"]:
        raise SwapError("This shift has changed hands since it was requested.")
    back = None                                            # check again at the moment of approval
    if swap["return_shift_id"] is not None:                # two-way swap: check the other direction too
        back = get_shift(conn, swap["return_shift_id"])
        if back["user_id"] != swap["taker_id"]:
            raise SwapError("The shift being given back has changed hands.")
        problem = can_take(conn, swap["taker_id"], shift, skip_id=back["id"])
        if problem == rules.OK:
            problem = can_take(conn, swap["giver_id"], back, skip_id=shift["id"])
        if problem != rules.OK:
            raise SwapError("This trade is no longer possible. " + rules.MESSAGES[problem])
    else:                                                  # one-way swap
        problem = can_take(conn, swap["taker_id"], shift)
        if problem != rules.OK:
            raise SwapError("This swap is no longer possible. " + rules.MESSAGES[problem])
    conn.execute("UPDATE shifts SET user_id = ? WHERE id = ?", (swap["taker_id"], shift["id"]))
    if back is not None:
        conn.execute("UPDATE shifts SET user_id = ? WHERE id = ?", (swap["giver_id"], back["id"]))
    conn.execute("UPDATE swaps SET status = 'approved', decided_at = datetime('now', 'localtime') WHERE id = ?",
                 (swap_id,))
    for person in (swap["giver_id"], swap["taker_id"]):
        text = f"Approved: {label(shift)} now belongs to {name_of(conn, swap['taker_id'])}."
        if back is not None:
            text += f" {label(back)} now belongs to {name_of(conn, swap['giver_id'])}."
        notify(conn, person, text)
    return "Approved. Both schedules are updated."


def decline_swap(conn, user, swap_id):
    if user["role"] != "manager":
        raise SwapError("Only a manager can decline.")
    swap = get_swap(conn, swap_id)
    if swap["status"] != "pending":
        raise SwapError("This request is no longer waiting for approval.")
    shift = get_shift(conn, swap["shift_id"])
    conn.execute("UPDATE swaps SET status = 'declined', decided_at = datetime('now', 'localtime') WHERE id = ?",
                 (swap_id,))
    for person in (swap["giver_id"], swap["taker_id"]):
        notify(conn, person, f"Declined: {label(shift)} stays with {name_of(conn, swap['giver_id'])}.")
    return "Declined. Shifts stay as they were."


ACTIONS = {"open": open_swap, "cancel": cancel_swap, "accept": accept_swap,
           "approve": approve_swap, "decline": decline_swap}


# ---------- routes ----------
@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/login")
def api_login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(ok=False, message="Bad request."), 400
    email = str(body.get("email", "")).strip().lower()
    user = get_conn().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], str(body.get("password", ""))):
        return jsonify(ok=False, message="Wrong email or password."), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(ok=True, message=f"Welcome, {user['name']}.")


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True, message="Logged out.")


@app.get("/api/state")
@login_required
def api_state(user):
    """Everything the screen needs for the logged-in person."""
    conn = get_conn()
    now = now_ts()
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM users")}

    # my upcoming shifts, grouped by week, with the hours of each week
    my_shifts = conn.execute("SELECT * FROM shifts WHERE user_id = ? ORDER BY start_ts", (user["id"],)).fetchall()
    my_times = [(s["start_ts"], s["end_ts"]) for s in my_shifts]
    weeks = {}
    for s in my_shifts:
        if s["start_ts"] <= now:
            continue
        w_start, w_end = rules.week_bounds(s["start_ts"])
        week = weeks.setdefault(w_start, {
            "label": rules.week_label(s["start_ts"]),
            "hours": rules.week_minutes(my_times, w_start, w_end) / 60,
            "shifts": []})
        swap = conn.execute("SELECT id, status, taker_id, return_shift_id FROM swaps WHERE shift_id = ? "
                            "AND status IN ('open', 'pending')", (s["id"],)).fetchone()
        # a shift I promised to give back in a pending trade is locked too
        trade = conn.execute("SELECT id FROM swaps WHERE return_shift_id = ? AND status = 'pending'",
                             (s["id"],)).fetchone()
        info = None
        if swap is not None:
            back = None if swap["return_shift_id"] is None else label(get_shift(conn, swap["return_shift_id"]))
            info = {"id": swap["id"], "status": swap["status"], "taker": names.get(swap["taker_id"]), "give": back}
        week["shifts"].append({**shift_json(s), "swap": info, "inTrade": trade is not None})

    available, waiting, approvals = [], [], []
    if user["role"] == "employee":
        for swap in conn.execute("SELECT * FROM swaps WHERE status = 'open' AND giver_id != ? ORDER BY id",
                                 (user["id"],)):
            s = get_shift(conn, swap["shift_id"])
            if s["start_ts"] <= now:
                continue
            outright = can_take(conn, user["id"], s) == rules.OK
            trades = trade_options(conn, user["id"], swap["giver_id"], s)
            if not outright and not trades:
                continue                                   # only shifts this person can really take
            w_start, w_end = rules.week_bounds(s["start_ts"])
            after = rules.week_minutes(my_times + [(s["start_ts"], s["end_ts"])], w_start, w_end) / 60
            available.append({"id": swap["id"], "shift": shift_json(s),
                              "giver": names[swap["giver_id"]], "weekHoursAfter": after,
                              "canTake": outright, "tradeOptions": [shift_json(t) for t in trades]})
        for swap in conn.execute("SELECT * FROM swaps WHERE status = 'pending' AND taker_id = ?", (user["id"],)):
            back = None if swap["return_shift_id"] is None else get_shift(conn, swap["return_shift_id"])
            waiting.append({"shift": shift_json(get_shift(conn, swap["shift_id"])),
                            "giver": names[swap["giver_id"]],
                            "give": None if back is None else label(back)})
    else:
        for swap in conn.execute("SELECT * FROM swaps WHERE status = 'pending' ORDER BY id"):
            s = get_shift(conn, swap["shift_id"])
            w_start, w_end = rules.week_bounds(s["start_ts"])
            moved = rules.week_minutes([(s["start_ts"], s["end_ts"])], w_start, w_end)
            g_before = rules.week_minutes(times_of(conn, swap["giver_id"]), w_start, w_end)
            t_before = rules.week_minutes(times_of(conn, swap["taker_id"]), w_start, w_end)
            back = None if swap["return_shift_id"] is None else get_shift(conn, swap["return_shift_id"])
            returned = 0 if back is None else rules.week_minutes([(back["start_ts"], back["end_ts"])], w_start, w_end)
            approvals.append({"id": swap["id"], "shift": shift_json(s),
                              "giver": names[swap["giver_id"]], "taker": names[swap["taker_id"]],
                              "give": None if back is None else label(back),
                              "giverBefore": g_before / 60, "giverAfter": (g_before - moved + returned) / 60,
                              "takerBefore": t_before / 60, "takerAfter": (t_before + moved - returned) / 60})

    notes = conn.execute("SELECT text, created_at, is_read FROM notifications WHERE user_id = ? "
                         "ORDER BY id DESC LIMIT 20", (user["id"],)).fetchall()
    return jsonify({
        "user": {"name": user["name"], "role": user["role"]},
        "engine": rules.BACKEND,
        "maxHours": rules.MAX_WEEK_MINUTES / 60,
        "weeks": list(weeks.values()),
        "available": available, "waiting": waiting, "approvals": approvals,
        "notifications": [{"text": n["text"], "time": n["created_at"][:16], "unread": not n["is_read"]} for n in notes],
        "unread": sum(1 for n in notes if not n["is_read"]),
    })


@app.post("/api/action/<name>")
@login_required
def api_action(user, name):
    if name not in ACTIONS and name != "trade":
        return jsonify(ok=False, message="Unknown action."), 404
    body = request.get_json(silent=True)        # only JSON is accepted, which also blocks forged form posts
    if not isinstance(body, dict) or not isinstance(body.get("id"), int):
        return jsonify(ok=False, message="Bad request."), 400
    conn = get_conn()
    try:
        if name == "trade":                         # the one action that also needs the shift I give back
            if not isinstance(body.get("give"), int):
                raise SwapError("Choose which of your shifts you give back.")
            message = trade_swap(conn, user, body["id"], body["give"])
        else:
            message = ACTIONS[name](conn, user, body["id"])
        conn.commit()
    except SwapError as error:
        conn.rollback()
        return jsonify(ok=False, message=str(error)), 409
    return jsonify(ok=True, message=message)


@app.post("/api/notifications/read")
@login_required
def api_read(user):
    if request.get_json(silent=True) is None:
        return jsonify(ok=False, message="Bad request."), 400
    conn = get_conn()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
    conn.commit()
    return jsonify(ok=True, message="Marked as read.")


if __name__ == "__main__":
    app.run(debug=True)