"""Entry point for the web server:  gunicorn wsgi:app"""
import db
from app import app


def needs_demo_data():
    conn = db.connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    finally:
        conn.close()


if needs_demo_data():          # empty database (first start, or the host wiped the disk)
    import seed
    seed.main()