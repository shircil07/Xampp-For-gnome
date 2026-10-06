import subprocess
import unittest

from xampp_panel.dialogs import Dialogs


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

    def test_msgbox_scrolls(self):
        run = Run()
        Dialogs(run).msgbox("Hello")
        self.assertEqual(run.calls[0][0][3:], ["--scrolltext", "--msgbox", "Hello", "20", "74"])
