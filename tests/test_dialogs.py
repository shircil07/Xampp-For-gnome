import os
import stat
import subprocess
import unittest

from xampp_panel.dialogs import Cancelled, Dialogs


class Run:
    def __init__(self, returncode=0, stderr=""):
        self.returncode, self.stderr, self.calls = returncode, stderr, []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, None, self.stderr)


class DialogsTest(unittest.TestCase):
    def test_menu_returns_tag_from_stderr(self):
        run = Run(stderr="2")
        self.assertEqual(Dialogs(run).menu("Pick:", [("1", "One"), ("2", "Two")]), "2")
        argv, kwargs = run.calls[0]
        self.assertEqual(argv[:3], ["whiptail", "--title", "XAMPP repair & configure"])
        self.assertEqual(argv[3:], ["--menu", "Pick:", "20", "74", "2", "1", "One", "2", "Two"])
        self.assertEqual(kwargs["stderr"], subprocess.PIPE)
        self.assertNotIn("stdout", kwargs)  # whiptail draws on the terminal

    def test_cancel_returns_none(self):
        self.assertIsNone(Dialogs(Run(returncode=1)).menu("Pick:", [("1", "One")]))
        self.assertIsNone(Dialogs(Run(returncode=255)).passwordbox("Password:"))

    def test_passwordbox_keeps_spaces(self):
        self.assertEqual(Dialogs(Run(stderr="  pass word  ")).passwordbox("Password:"), "  pass word  ")

    def test_yesno(self):
        self.assertTrue(Dialogs(Run(0)).yesno("Sure?"))
        self.assertFalse(Dialogs(Run(1)).yesno("Sure?"))

    def test_yesno_escape_cancels(self):
        with self.assertRaises(Cancelled):
            Dialogs(Run(255)).yesno("Sure?")

    def test_msgbox_scrolls(self):
        run = Run()
        Dialogs(run).msgbox("Hello")
        self.assertEqual(run.calls[0][0][3:], ["--scrolltext", "--msgbox", "Hello", "20", "74"])

    def test_secret_keeps_text_off_argv_uses_a_0600_file_and_removes_it(self):
        seen = {}

        def run(argv, **kwargs):
            self.assertNotIn("s3cret-text", argv)
            self.assertEqual(argv[:5], ["whiptail", "--title", "Title", "--scrolltext", "--textbox"])
            path = argv[5]
            self.assertEqual(argv[6:], ["20", "74"])
            self.assertEqual(kwargs["stderr"], subprocess.PIPE)
            self.assertTrue(kwargs["text"])
            seen["path"] = path
            self.assertTrue(os.path.exists(path))
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "s3cret-text")
            return subprocess.CompletedProcess(argv, 0, None, "")

        Dialogs(run).secret("Title", "s3cret-text")
        self.assertFalse(os.path.exists(seen["path"]))
