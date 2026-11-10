"""Create the database with demo people and shifts for next week.  Run:  python seed.py"""
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

import db

DEMO_PASSWORD = "swap1234"          # demo only. Real users choose their own.

PEOPLE = [
    ("Mary", "mary@example.com", "manager"),
    ("Ami", "ami@example.com", "employee"),
    ("Bora", "bora@example.com", "employee"),
    ("Canie", "canie@example.com", "employee"),
    ("Danny", "danny@example.com", "employee"),
]

# (person, weekday 0=Mon, start, end)
SHIFTS = [
    ("Ami", 0, "08:00", "16:00"), ("Ami", 2, "14:00", "22:00"), ("Ami", 4, "08:00", "16:00"),
    ("Bora", 1, "08:00", "16:00"), ("Bora", 3, "08:00", "16:00"),
    ("Bora", 5, "08:00", "16:00"), ("Bora", 6, "08:00", "16:00"),
    ("Canie", 0, "08:00", "16:00"), ("Canie", 1, "08:00", "16:00"), ("Canie", 2, "08:00", "16:00"),
    ("Canie", 3, "08:00", "16:00"), ("Canie", 4, "08:00", "16:00"),
    ("Danny", 1, "14:00", "22:00"), ("Danny", 3, "14:00", "22:00"),
]


def main():
    db.DB_PATH.unlink(missing_ok=True)          # start from an empty database
    db.init_db()
    conn = db.connect()

    ids = {}
    for name, email, role in PEOPLE:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(DEMO_PASSWORD), role),
        )
        ids[name] = cur.lastrowid

    today = date.today()
    next_monday = today + timedelta(days=7 - today.weekday())
    for name, weekday, start, end in SHIFTS:
        day = next_monday + timedelta(days=weekday)
        conn.execute("INSERT INTO shifts (user_id, start_ts, end_ts) VALUES (?, ?, ?)",
                     (ids[name], f"{day} {start}", f"{day} {end}"))
    conn.commit()
    conn.close()

    print(f"Created {db.DB_PATH.name} with shifts for the week of {next_monday}.")
    print(f"Log in with any of these emails and the password '{DEMO_PASSWORD}':")
    for name, email, role in PEOPLE:
        print(f"  {email:<18} {role}")


if __name__ == "__main__":
    main()