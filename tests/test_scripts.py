import os
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
        if os.geteuid() == 0:
            self.skipTest("running as root")
        proc = subprocess.run(["bash", str(ROOT / "setup.sh")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sudo", proc.stderr)

    def test_setup_uses_xampp_repair_not_lampp_security(self):
        text = (ROOT / "setup.sh").read_text()
        self.assertNotIn('lampp" security', text)
        self.assertIn('"$APP_DIR/bin/xampp-repair" first-install', text)
        self.assertIn("whiptail", text)
        self.assertIn('"$SRC_DIR/bin/xampp-repair"', text)
        self.assertIn("/usr/local/bin/xampp-repair", text)

    def test_setup_downloads_and_verifies_the_installer(self):
        text = (ROOT / "setup.sh").read_text()
        self.assertIn('source "$SRC_DIR/lib/xampp-download.sh"', text)
        self.assertIn("xampp_download ", text)
        self.assertIn("xampp_verified_copy ", text)
        self.assertRegex(text, r"packages=\([^)]*\bcurl\b[^)]*\bca-certificates\b")
