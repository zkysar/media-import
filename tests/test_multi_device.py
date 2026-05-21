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


if __name__ == "__main__":
    unittest.main()
