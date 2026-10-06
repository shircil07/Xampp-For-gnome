import unittest
from pathlib import Path

from xampp_panel import terminal
from xampp_panel.paths import Paths


class TerminalTest(unittest.TestCase):
    def test_first_installed_terminal_wins(self):
        which = {"kgx": "/usr/bin/kgx", "x-terminal-emulator": "/usr/bin/x-terminal-emulator"}.get
        self.assertEqual(terminal.terminal_argv(["sh", "-c", "x"], which), ["/usr/bin/kgx", "--", "sh", "-c", "x"])

    def test_x_terminal_emulator_uses_e(self):
        which = {"x-terminal-emulator": "/usr/bin/x-terminal-emulator"}.get
        self.assertEqual(terminal.terminal_argv(["sh"], which), ["/usr/bin/x-terminal-emulator", "-e", "sh"])

    def test_none_found(self):
        self.assertIsNone(terminal.terminal_argv(["sh"], lambda name: None))

    def test_repair_command_waits_before_closing(self):
        argv = terminal.repair_command(Paths(app=Path("/a")))
        self.assertEqual(argv[:2], ["sh", "-c"])
        self.assertIn("sudo /a/bin/xampp-repair", argv[2])
        self.assertIn("read", argv[2])
