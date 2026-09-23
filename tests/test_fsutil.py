import os
import tempfile
import unittest
from pathlib import Path

from xampp_panel import fsutil


class FsutilCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class AtomicWriteTest(FsutilCase):
    def test_creates_file_with_default_mode(self):
        p = self.dir / "a.txt"
        fsutil.atomic_write(p, "hi\n")
        self.assertEqual(p.read_text(), "hi\n")
        self.assertEqual(p.stat().st_mode & 0o777, 0o644)

    def test_preserves_existing_mode(self):
        p = self.dir / "a.txt"
        p.write_text("old")
        p.chmod(0o600)
        fsutil.atomic_write(p, "new")
        self.assertEqual(p.read_text(), "new")
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_explicit_mode_wins(self):
        p = self.dir / "a.txt"
        fsutil.atomic_write(p, "x", mode=0o600)
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_leaves_no_temp_files(self):
        fsutil.atomic_write(self.dir / "a.txt", "x")
        self.assertEqual(os.listdir(self.dir), ["a.txt"])


class BackupOnceTest(FsutilCase):
    def test_backs_up_only_the_first_time(self):
        p = self.dir / "httpd.conf"
        p.write_text("original")
        bak = fsutil.backup_once(p)
        p.write_text("changed")
        fsutil.backup_once(p)
        self.assertEqual(bak, self.dir / "httpd.conf.xampp-panel.bak")
        self.assertEqual(bak.read_text(), "original")

    def test_missing_file_is_ignored(self):
        bak = fsutil.backup_once(self.dir / "nope")
        self.assertFalse(bak.exists())


class TailTest(FsutilCase):
    def test_short_file_is_returned_whole(self):
        p = self.dir / "log"
        p.write_text("a\nb\n")
        self.assertEqual(fsutil.tail(p), "a\nb\n")

    def test_long_file_keeps_last_whole_lines(self):
        p = self.dir / "log"
        p.write_text("".join(f"line {i}\n" for i in range(1000)))
        out = fsutil.tail(p, max_bytes=100)
        self.assertTrue(out.endswith("line 999\n"))
        self.assertTrue(out.startswith("line "))
        self.assertLessEqual(len(out), 100)
