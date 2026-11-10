// rules.cpp - the scheduling rules, compiled into a shared library that Python calls.
// All times are "minutes since 1 Jan 1970", so the maths is just whole-number comparisons.
#include <algorithm>

static long long overlap_minutes(long long a_start, long long a_end,
                                 long long b_start, long long b_end) {
    long long lo = std::max(a_start, b_start);
    long long hi = std::min(a_end, b_end);
    return hi > lo ? hi - lo : 0;
}

#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif

// Can a person who already works the shifts (starts[i], ends[i]) also take the candidate shift?
// Returns 0 = OK, 1 = over the weekly limit, 2 = overlaps a shift, 3 = not enough rest.
EXPORT int check_shift(const long long* starts, const long long* ends, int n,
                       long long cand_start, long long cand_end,
                       long long week_start, long long week_end,
                       int max_week_minutes, int min_rest_minutes) {
    // 1. overlap with an existing shift
    for (int i = 0; i < n; ++i) {
        if (overlap_minutes(starts[i], ends[i], cand_start, cand_end) > 0) return 2;
    }
    // 2. rest between the candidate and every other shift
    for (int i = 0; i < n; ++i) {
        long long gap = (cand_start >= ends[i]) ? cand_start - ends[i] : starts[i] - cand_end;
        if (gap < min_rest_minutes) return 3;
    }
    // 3. total minutes inside the candidate's week
    long long week_total = overlap_minutes(cand_start, cand_end, week_start, week_end);
    for (int i = 0; i < n; ++i) {
        week_total += overlap_minutes(starts[i], ends[i], week_start, week_end);
    }
    return week_total > max_week_minutes ? 1 : 0;
}