"""Scheduling rules.

The checking is done by C++ (cpp/rules.cpp) when the library has been built.
An identical pure-Python version is used as a fallback, so the app always runs.
"""
import ctypes
import sys
from datetime import datetime, timedelta
from pathlib import Path

FMT = "%Y-%m-%d %H:%M"                 # how shift times are stored, e.g. 2026-11-02 08:00
EPOCH = datetime(1970, 1, 1)
MAX_WEEK_MINUTES = 40 * 60             # weekly limit
MIN_REST_MINUTES = 11 * 60             # rest between two shifts

OK, OVER_WEEKLY_LIMIT, OVERLAP, TOO_LITTLE_REST = 0, 1, 2, 3
MESSAGES = {
    OVER_WEEKLY_LIMIT: "That would put you over 40 hours this week.",
    OVERLAP: "That shift overlaps with one of your shifts.",
    TOO_LITTLE_REST: "You need at least 11 hours of rest between shifts.",
}


# ---------- time helpers ----------
def to_minutes(ts):
    return int((datetime.strptime(ts, FMT) - EPOCH).total_seconds() // 60)


def week_bounds(ts):
    """Start (Monday 00:00) and end of the week that contains ts, in minutes."""
    d = datetime.strptime(ts, FMT)
    monday = datetime(d.year, d.month, d.day) - timedelta(days=d.weekday())
    start = int((monday - EPOCH).total_seconds() // 60)
    return start, start + 7 * 24 * 60


def week_label(ts):
    d = datetime.strptime(ts, FMT)
    monday = d - timedelta(days=d.weekday())
    return f"Week of {monday:%a %d %b}"


def _overlap(a_start, a_end, b_start, b_end):
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def week_minutes(shifts, week_start, week_end):
    """Minutes worked inside one week. shifts is a list of (start_ts, end_ts)."""
    return sum(_overlap(to_minutes(s), to_minutes(e), week_start, week_end) for s, e in shifts)


# ---------- the C++ library ----------
def _load_library():
    names = {"win32": "swaprules.dll", "darwin": "libswaprules.dylib"}
    path = Path(__file__).parent / names.get(sys.platform, "libswaprules.so")
    try:
        lib = ctypes.CDLL(str(path))
    except OSError:
        return None
    ll = ctypes.c_longlong
    lib.check_shift.argtypes = [ctypes.POINTER(ll), ctypes.POINTER(ll), ctypes.c_int,
                                ll, ll, ll, ll, ctypes.c_int, ctypes.c_int]
    lib.check_shift.restype = ctypes.c_int
    return lib


_lib = _load_library()
BACKEND = "C++" if _lib else "Python fallback"


# ---------- the same rules in Python (fallback, and used to test the C++ version) ----------
def _check_shift_python(starts, ends, c_start, c_end, w_start, w_end):
    pairs = list(zip(starts, ends))
    if any(_overlap(s, e, c_start, c_end) > 0 for s, e in pairs):
        return OVERLAP
    for s, e in pairs:
        gap = c_start - e if c_start >= e else s - c_end
        if gap < MIN_REST_MINUTES:
            return TOO_LITTLE_REST
    total = _overlap(c_start, c_end, w_start, w_end) + sum(_overlap(s, e, w_start, w_end) for s, e in pairs)
    return OVER_WEEKLY_LIMIT if total > MAX_WEEK_MINUTES else OK


def check_shift(existing, candidate):
    """existing: list of (start_ts, end_ts) the person already works.
    candidate: (start_ts, end_ts) of the shift they might take. Returns OK or a problem code."""
    starts = [to_minutes(s) for s, _ in existing]
    ends = [to_minutes(e) for _, e in existing]
    c_start, c_end = to_minutes(candidate[0]), to_minutes(candidate[1])
    w_start, w_end = week_bounds(candidate[0])
    if _lib is None:
        return _check_shift_python(starts, ends, c_start, c_end, w_start, w_end)
    n = len(starts)
    ll = ctypes.c_longlong
    return _lib.check_shift((ll * n)(*starts), (ll * n)(*ends), n, c_start, c_end,
                            w_start, w_end, MAX_WEEK_MINUTES, MIN_REST_MINUTES)