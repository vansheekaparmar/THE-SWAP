CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('employee', 'manager'))
);

CREATE TABLE IF NOT EXISTS shifts (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id  INTEGER NOT NULL REFERENCES users(id),
  start_ts TEXT NOT NULL,          -- 'YYYY-MM-DD HH:MM'
  end_ts   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS swaps (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  shift_id   INTEGER NOT NULL REFERENCES shifts(id),
  giver_id   INTEGER NOT NULL REFERENCES users(id),
  taker_id   INTEGER REFERENCES users(id),
  return_shift_id INTEGER REFERENCES shifts(id),   -- the shift the taker gives back (NULL = normal swap)
  status     TEXT NOT NULL CHECK (status IN ('open', 'pending', 'approved', 'declined', 'cancelled')),
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  decided_at TEXT
);

-- a shift can have only one live swap at a time
CREATE UNIQUE INDEX IF NOT EXISTS one_live_swap_per_shift
  ON swaps(shift_id) WHERE status IN ('open', 'pending');

CREATE TABLE IF NOT EXISTS notifications (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  is_read    INTEGER NOT NULL DEFAULT 0
);