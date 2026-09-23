import unittest

from xampp_panel import privileged


class PrivilegedTest(unittest.TestCase):
    def test_argv(self):
        self.assertEqual(privileged.argv_for("start", "apache"),
                         ["pkexec", "/opt/xampp-panel/bin/xampp-helper", "start", "apache"])

    def test_success_returns_stdout(self):
        self.assertEqual(privileged.interpret(0, "ok\n", ""), "ok\n")

    def test_cancelled_auth(self):
        with self.assertRaises(privileged.Cancelled):
            privileged.interpret(126, "", "Not authorized")

    def test_not_authorized_or_missing_helper(self):
        with self.assertRaises(privileged.HelperError) as ctx:
            privileged.interpret(127, "", "Not authorized")
        self.assertNotIsInstance(ctx.exception, privileged.Cancelled)
        self.assertEqual(str(ctx.exception), "Not authorized, or the XAMPP Panel helper is missing")

    def test_error_uses_last_stderr_line(self):
        with self.assertRaises(privileged.HelperError) as ctx:
            privileged.interpret(1, "", "details\nport 80 in use\n")
        self.assertEqual(str(ctx.exception), "port 80 in use")

    def test_error_without_output(self):
        with self.assertRaises(privileged.HelperError) as ctx:
            privileged.interpret(3, "", "")
        self.assertEqual(str(ctx.exception), "the helper failed (exit code 3)")
