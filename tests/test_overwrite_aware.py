import os
import tempfile
import unittest
from pathlib import Path

from _load_module import load
m = load()


class ClassifyDstTest(unittest.TestCase):
    def test_missing_dst_returns_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = m.classify_dst(Path(tmp) / "absent.bin", expected_size=100)
            self.assertEqual(result, (False, 0))

    def test_same_size_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "exact.bin"
            p.write_bytes(b"x" * 100)
            self.assertIsNone(m.classify_dst(p, expected_size=100))

    def test_different_size_returns_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "stale.bin"
            p.write_bytes(b"x" * 50)
            result = m.classify_dst(p, expected_size=100)
            self.assertEqual(result, (True, 50))


class CopyOpFlagTest(unittest.TestCase):
    def test_copyop_default_overwrite_existing_is_false(self):
        op = m.CopyOp(src=Path("/tmp/x"), dst=Path("/tmp/y"), size_bytes=10)
        self.assertFalse(op.overwrite_existing)
        self.assertEqual(op.existing_size_bytes, 0)

    def test_plan_overwrites_property(self):
        plan = m.Plan()
        plan.singleton_moves = [
            m.CopyOp(src=Path("/a"), dst=Path("/b"), size_bytes=10),
            m.CopyOp(src=Path("/c"), dst=Path("/d"), size_bytes=20,
                     overwrite_existing=True, existing_size_bytes=15),
        ]
        self.assertEqual(len(plan.overwrites), 1)
        self.assertEqual(plan.overwrites[0].existing_size_bytes, 15)


class RunSingletonMovesTest(unittest.TestCase):
    def test_overwrite_flag_replaces_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "staged" / "f.bin"
            src.parent.mkdir()
            src.write_bytes(b"new content (long-er)")
            dst = tmp / "final" / "f.bin"
            dst.parent.mkdir()
            dst.write_bytes(b"old")

            plan = m.Plan(dest=tmp)
            plan.singleton_moves = [m.CopyOp(
                src=src, dst=dst, size_bytes=len(b"new content (long-er)"),
                overwrite_existing=True, existing_size_bytes=3,
            )]
            stats = m.run_singleton_moves(plan)
            self.assertEqual(stats["overwritten"], 1)
            self.assertEqual(dst.read_bytes(), b"new content (long-er)")

    def test_unflagged_size_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "staged" / "f.bin"
            src.parent.mkdir()
            src.write_bytes(b"new")
            dst = tmp / "final" / "f.bin"
            dst.parent.mkdir()
            dst.write_bytes(b"different size old")

            plan = m.Plan(dest=tmp)
            plan.singleton_moves = [m.CopyOp(
                src=src, dst=dst, size_bytes=3,
                overwrite_existing=False,   # surprise mismatch
            )]
            with self.assertRaises(RuntimeError):
                m.run_singleton_moves(plan)


if __name__ == "__main__":
    unittest.main()
