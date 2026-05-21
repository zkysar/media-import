import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, date
from pathlib import Path

from _load_module import load
m = load()


class SonyVerifiedPredicateTest(unittest.TestCase):
    def test_returns_false_when_marker_absent(self):
        orig = m.SONY_VERIFICATION_PATH
        try:
            m.SONY_VERIFICATION_PATH = Path("/nonexistent/sony-verified.json")
            self.assertFalse(m._sony_is_verified())
        finally:
            m.SONY_VERIFICATION_PATH = orig

    def test_returns_true_when_marker_present(self):
        orig = m.SONY_VERIFICATION_PATH
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                marker = Path(f.name)
            m.SONY_VERIFICATION_PATH = marker
            self.assertTrue(m._sony_is_verified())
        finally:
            m.SONY_VERIFICATION_PATH = orig
            marker.unlink(missing_ok=True)


class ResolveDateRangeTest(unittest.TestCase):
    def _args(self, **kw):
        base = dict(days=None, from_date=None, to_date=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_days_sets_window_ignoring_default_dates(self):
        args = self._args(days=2)
        m.resolve_date_range(args, [date(2000, 1, 1)])
        self.assertEqual(args.to_date, date.today())
        self.assertEqual((args.to_date - args.from_date).days, 2)

    def test_no_flags_infers_from_earliest_default_date(self):
        args = self._args()
        m.resolve_date_range(args, [date(2026, 5, 3), date(2026, 5, 1), date(2026, 5, 7)])
        self.assertEqual(args.from_date, date(2026, 5, 1))
        self.assertEqual(args.to_date, date.today())

    def test_no_flags_no_dates_raises(self):
        args = self._args()
        with self.assertRaises(SystemExit):
            m.resolve_date_range(args, [])


if __name__ == "__main__":
    unittest.main()
