# THE SWAP

A shift-swapping app for teams. An employee opens a shift, a colleague accepts it (or trades one of their own shifts for it), the manager approves, and both schedules update automatically.

Built with **Python, JavaScript, HTML, CSS and C++** as a student project.

## What it does

1. An employee opens one of their upcoming shifts for a swap.
2. Only colleagues who can really take it are notified. The app checks hours, overlaps and rest time first.
3. A colleague accepts the shift. If they can't take it outright (for example because they are already at 40 hours), they can **trade** one of their own shifts for it instead.
4. The manager is notified and approves or declines, seeing everyone's weekly hours before and after.
5. On approval, both schedules update and everyone involved gets an alert.

## Features

- Login with roles (employee and manager)
- Open, cancel, accept, trade, approve and decline swaps
- **Two-way swaps:** the colleague gives a shift back, and both people's hours are checked after the exchange
- Only eligible colleagues are notified or shown the shift
- First accept wins: two people can't take the same shift
- In-app alerts, with live updates every 3 seconds
- The rules are re-checked at the moment of approval

## Scheduling rules

| Rule | Value |
|---|---|
| Maximum hours per week | 40 h |
| Overlapping shifts | not allowed |
| Minimum rest between shifts | 11 h |

The rules are written in C++ (`cpp/rules.cpp`) and called from Python through `ctypes`. An identical pure-Python version is used automatically if the C++ library hasn't been compiled, so the app always runs. The header of the app shows which one is active (`Rules: C++` or `Rules: Python fallback`).

## Tech stack

| Part | Technology | Job |
|---|---|---|
| Rules engine | C++ | Checks hours, overlap and rest |
| Server | Python + Flask | Login, actions, JSON API |
| Database | SQLite | Users, shifts, swaps, alerts |
| Front end | HTML, CSS, JavaScript | The screens, no framework |

## Project structure

```
THE-SWAP/
├── app.py            Flask server: login, actions and API
├── rules.py          Loads the C++ library, Python fallback
├── db.py             Database connection and setup
├── schema.sql        Tables and constraints
├── seed.py           Creates demo people and shifts
├── cpp/
│   └── rules.cpp     The scheduling rules in C++
├── static/
│   ├── index.html    The page
│   ├── style.css     The look
│   └── app.js        The screens and clicks
├── test_rules.py     Tests for the rules
├── test_app.py       Tests for the whole swap flow
└── requirements.txt
```

## Getting started

You need Python 3.10 or newer. A C++ compiler (g++) is optional.

```bash
# 1. Get the code
git clone https://github.com/vansheekaparmar/THE-SWAP.git
cd THE-SWAP

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install Flask
pip install -r requirements.txt

# 4. (Optional) compile the C++ rules engine
g++ -O2 -shared -fPIC -o libswaprules.so cpp/rules.cpp

# 5. Create the demo database
python seed.py

# 6. Start the app
python app.py
```

Open http://127.0.0.1:5000 in your browser. In GitHub Codespaces, open the **Ports** tab and click the globe icon next to port 5000.

### Compiling the C++ library on other systems

| System | Command |
|---|---|
| Linux | `g++ -O2 -shared -fPIC -o libswaprules.so cpp/rules.cpp` |
| macOS | `g++ -O2 -shared -fPIC -o libswaprules.dylib cpp/rules.cpp` |
| Windows (MinGW) | `g++ -O2 -shared -static-libgcc -static-libstdc++ -o swaprules.dll cpp/rules.cpp` |
| Windows (MSVC) | `cl /LD /EHsc cpp\rules.cpp /Fe:swaprules.dll` |

## Demo logins

All demo accounts use the password `swap1234`. These are for local testing only.

| Name | Email | Role |
|---|---|---|
| Mary | mary@example.com | manager |
| Ami | ami@example.com | employee |
| Bora | bora@example.com | employee |
| Canie | canie@example.com | employee |
| Danny | danny@example.com | employee |

**Try it:** open two browser windows, log in as Ami in one and Mary in the other. Ami opens a shift, a colleague accepts or trades for it in a third window, and Mary approves it. Both schedules update.

## Tests

```bash
python -m unittest
```

The tests cover the rules (including the Python fallback), login, a full swap, the first-accept-wins race, the rest rule, two-way trades and the permission checks.

## Security notes

- Passwords are stored as salted hashes, never as plain text
- The login cookie is signed, `HttpOnly` and `SameSite=Lax`
- Roles are checked on the server, not just in the browser
- The server only accepts JSON for actions, which blocks forged form posts
- Everything a user can type is HTML-escaped before it is shown
- The database refuses a second live swap for the same shift
- Set the `SWAP_SECRET` environment variable for a real deployment

## Ideas for next steps

- Email or push notifications
- Shift swap requests aimed at one specific colleague
- Manager tools to create and edit schedules
- Deploy online (for example on Render or Fly.io)

## Author

Vansheeka Parmar, BSc Computer Science, Berlin.

## License

MIT
