import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class AtomicWriteOwnerTest(unittest.TestCase):
    def test_same_owner_no_chown_needed(self):
        """When rewriting own file (same owner), fchown is not called."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            path.write_text("old")
            with mock.patch("os.fchown") as fchown:
                fsutil.atomic_write(path, "new")
            fchown.assert_not_called()
            self.assertEqual(path.read_text(), "new")

    def test_different_owner_calls_chown(self):
        """When rewriting daemon-owned file, fchown is called."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.inc.php"
            path.write_text("original")
            st = path.stat()
            fstat_calls = []
            # Mock os.fstat to return different owner for temp file
            def mock_fstat(fd):
                fstat_calls.append(fd)
                # Simulate temp file owned by root, original owned by daemon
                from types import SimpleNamespace
                return SimpleNamespace(st_uid=0, st_gid=0)
            fchown_calls = []
            with mock.patch("xampp_panel.fsutil.os.fstat", side_effect=mock_fstat):
                with mock.patch("os.fchown", side_effect=lambda fd, uid, gid: fchown_calls.append((uid, gid))):
                    fsutil.atomic_write(path, "new")
            # Verify fchown was called with the original (daemon) owner
            self.assertEqual(fchown_calls, [(st.st_uid, st.st_gid)])
            self.assertEqual(path.read_text(), "new")

    def test_new_file_is_not_chowned(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("os.fchown") as fchown:
                fsutil.atomic_write(Path(d) / "new.conf", "x")
            fchown.assert_not_called()

    def test_fchown_failure_aborts_write_and_preserves_original(self):
        """When fchown fails, the write is aborted and original file preserved."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.inc.php"
            path.write_text("original")
            st = path.stat()
            # Mock os.fstat to return different owner for temp file, triggering fchown
            def mock_fstat(fd):
                from types import SimpleNamespace
                return SimpleNamespace(st_uid=0, st_gid=0)  # Different owner
            with mock.patch("xampp_panel.fsutil.os.fstat", side_effect=mock_fstat):
                with mock.patch("os.fchown", side_effect=PermissionError("Operation not permitted")):
                    with self.assertRaises(PermissionError):
                        fsutil.atomic_write(path, "new content")
            # Original file unchanged
            self.assertEqual(path.read_text(), "original")
            # No temp file left behind
            temp_files = [f for f in os.listdir(d) if f.startswith(f".{path.name}.")]
            self.assertEqual(temp_files, [])
