import unittest

import rules

# Anna-style week: Mon 8-16, Tue 8-16, Thu 8-16 (24 h)
WEEK = [("2026-11-02 08:00", "2026-11-02 16:00"),
        ("2026-11-03 08:00", "2026-11-03 16:00"),
        ("2026-11-05 08:00", "2026-11-05 16:00")]


class RulesTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(rules.check_shift(WEEK, ("2026-11-06 08:00", "2026-11-06 16:00")), rules.OK)

    def test_overlap(self):
        self.assertEqual(rules.check_shift(WEEK, ("2026-11-02 12:00", "2026-11-02 20:00")), rules.OVERLAP)

    def test_rest_after_a_late_shift(self):
        # Wed 14-22, then Thu 8:00 is only 10 hours later
        self.assertEqual(rules.check_shift(WEEK, ("2026-11-04 14:00", "2026-11-04 22:00")), rules.TOO_LITTLE_REST)

    def test_weekly_limit(self):
        busy = [(f"2026-11-0{d} 08:00", f"2026-11-0{d} 16:00") for d in (2, 3, 4, 5, 6)]   # 40 h
        self.assertEqual(rules.check_shift(busy, ("2026-11-07 08:00", "2026-11-07 16:00")), rules.OVER_WEEKLY_LIMIT)

    def test_exactly_40_hours_is_allowed(self):
        four_days = [(f"2026-11-0{d} 08:00", f"2026-11-0{d} 16:00") for d in (2, 3, 4, 5)]  # 32 h
        self.assertEqual(rules.check_shift(four_days, ("2026-11-06 08:00", "2026-11-06 16:00")), rules.OK)

    def test_hours_in_another_week_do_not_count(self):
        next_week = [(f"2026-11-0{d} 08:00", f"2026-11-0{d} 16:00") for d in (2, 3, 4, 5, 6)]
        self.assertEqual(rules.check_shift(next_week, ("2026-11-09 08:00", "2026-11-09 16:00")), rules.OK)

    def test_cpp_and_python_give_the_same_answers(self):
        if rules.BACKEND != "C++":
            self.skipTest("C++ library not built")
        cases = [("2026-11-06 08:00", "2026-11-06 16:00"), ("2026-11-02 12:00", "2026-11-02 20:00"),
                 ("2026-11-04 14:00", "2026-11-04 22:00"), ("2026-11-08 06:00", "2026-11-08 14:00")]
        for candidate in cases:
            cpp = rules.check_shift(WEEK, candidate)
            library, rules._lib = rules._lib, None          # switch to the Python version
            try:
                python = rules.check_shift(WEEK, candidate)
            finally:
                rules._lib = library
            self.assertEqual(cpp, python, candidate)


if __name__ == "__main__":
    unittest.main()