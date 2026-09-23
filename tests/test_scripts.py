import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ScriptsTest(unittest.TestCase):
    def test_syntax(self):
        for name in ("setup.sh", "uninstall.sh"):
            subprocess.run(["bash", "-n", str(ROOT / name)], check=True)

    def test_help_works_without_root(self):
        for name, needle in (("setup.sh", "--allow-lan"), ("uninstall.sh", "--remove-xampp")):
            proc = subprocess.run(["bash", str(ROOT / name), "--help"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(needle, proc.stdout)

    def test_unknown_option_fails(self):
        proc = subprocess.run(["bash", str(ROOT / "setup.sh"), "--bogus"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_non_root_is_refused(self):
        import os
        if os.geteuid() == 0:
            self.skipTest("running as root")
        proc = subprocess.run(["bash", str(ROOT / "setup.sh")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sudo", proc.stderr)
