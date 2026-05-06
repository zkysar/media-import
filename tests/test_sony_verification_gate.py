import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _load_module import load
m = load()


class GateTest(unittest.TestCase):
    def test_gate_blocks_when_sentinel_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "sony-verified.json"
            with patch.object(m, "SONY_VERIFICATION_PATH", fake):
                with self.assertRaises(SystemExit) as cm:
                    m._check_sony_verification()
            msg = str(cm.exception)
            self.assertIn("verify-sony", msg)

    def test_gate_passes_when_sentinel_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "sony-verified.json"
            fake.write_text("{}")
            with patch.object(m, "SONY_VERIFICATION_PATH", fake):
                m._check_sony_verification()  # must not raise


if __name__ == "__main__":
    unittest.main()
