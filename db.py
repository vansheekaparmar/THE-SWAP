import os
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = Path(os.environ.get("SWAP_DB") or HERE / "swap.db")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row            # rows can be read like dictionaries
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect()
    conn.executescript((HERE / "schema.sql").read_text())
    conn.commit()
    conn.close()