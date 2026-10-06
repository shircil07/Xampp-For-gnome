import os
import stat
import subprocess
import unittest
from pathlib import Path

from xampp_panel import mysqladmin
from xampp_panel.paths import Paths

GUARD = "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');"


class SqlTest(unittest.TestCase):
    def test_sql_quote(self):
        self.assertEqual(mysqladmin.sql_quote("a'b\\c"), "'a''b\\\\c'")
        with self.assertRaises(ValueError):
            mysqladmin.sql_quote("a\0b")

    def test_password_problem(self):
        self.assertIsNone(mysqladmin.password_problem("  pass word  "))
        self.assertIsNotNone(mysqladmin.password_problem("short"))
        self.assertIsNotNone(mysqladmin.password_problem("x" * 129))

    def test_password_length_boundaries(self):
        for length, ok in ((7, False), (8, True), (128, True), (129, False)):
            with self.subTest(length=length):
                self.assertEqual(mysqladmin.password_problem("x" * length) is None, ok)
        self.assertIsNotNone(mysqladmin.password_problem("tab\there1"))
        self.assertIsNotNone(mysqladmin.password_problem("del\x7fhere1"))

    def test_drop_anonymous_lets_mariadb_list_accounts(self):
        sql = mysqladmin.drop_anonymous_sql()
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("FROM mysql.user WHERE user = '';", sql)
        self.assertIn("EXECUTE IMMEDIATE IF(@accounts IS NULL, 'DO 0', CONCAT('DROP USER ', @accounts));", sql)

    def test_set_root_password_escapes_once(self):
        sql = mysqladmin.set_root_password_sql("a'b\\c$x`y")
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("SET @pw = 'a''b\\\\c$x`y';", sql)
        self.assertEqual(sql.count("a''b"), 1)
        self.assertIn("FROM mysql.user WHERE user = 'root';", sql)
        self.assertTrue(sql.rstrip().endswith("SET @pw = NULL, @accounts = NULL;"))

    def test_pma_account_sql(self):
        sql = mysqladmin.pma_account_sql("p'ma", "s3cret")
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("CREATE USER IF NOT EXISTS 'p''ma'@'localhost';", sql)
        self.assertIn("ALTER USER 'p''ma'@'localhost' IDENTIFIED BY 's3cret';", sql)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON `phpmyadmin`.* TO 'p''ma'@'localhost';", sql)


class RecordingRun:
    """Fake subprocess.run that captures the option file while it still exists."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.calls = []

    def __call__(self, argv, **kwargs):
        option_file = argv[1].split("=", 1)[1]
        mode = stat.S_IMODE(os.stat(option_file).st_mode)
        self.calls.append({"argv": argv, "kwargs": kwargs, "option_file": option_file,
                           "options": Path(option_file).read_text(), "mode": mode})
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


class MysqlAdminTest(unittest.TestCase):
    def setUp(self):
        self.paths = Paths(lampp=Path("/l"))

    def test_execute_keeps_secrets_off_argv_and_env(self):
        run = RecordingRun(stdout="ok\n")
        out = mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", 'pa"ss\\word')
        self.assertEqual(out, "ok\n")
        call = run.calls[0]
        self.assertEqual(call["argv"][0], "/l/bin/mysql")
        self.assertTrue(call["argv"][1].startswith("--defaults-extra-file="))
        self.assertNotIn("pa", " ".join(call["argv"][2:]))
        self.assertEqual(call["kwargs"]["input"], "SELECT 1;")
        self.assertNotIn("MYSQL_PWD", call["kwargs"]["env"])
        self.assertEqual(call["mode"], 0o600)
        self.assertEqual(call["options"], '[client]\nuser="root"\npassword="pa\\"ss\\\\word"\n')
        self.assertFalse(os.path.exists(call["option_file"]))

    def test_empty_password_writes_no_password_line(self):
        run = RecordingRun()
        mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "")
        self.assertEqual(run.calls[0]["options"], '[client]\nuser="root"\n')

    def test_failure_raises_last_error_line_and_still_removes_file(self):
        run = RecordingRun(returncode=1, stderr="warning\nERROR 1045: Access denied\n")
        with self.assertRaisesRegex(mysqladmin.MysqlError, "ERROR 1045: Access denied"):
            mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "x")
        self.assertFalse(os.path.exists(run.calls[0]["option_file"]))

    def test_timeout_becomes_mysql_error(self):
        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaises(mysqladmin.MysqlError):
            mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "")

    def test_can_login(self):
        ok = RecordingRun()
        self.assertTrue(mysqladmin.MysqlAdmin(self.paths, ok).can_login("pma", "pw", "phpmyadmin"))
        self.assertEqual(ok.calls[0]["argv"][-1], "phpmyadmin")
        self.assertIn('user="pma"', ok.calls[0]["options"])
        self.assertFalse(mysqladmin.MysqlAdmin(self.paths, RecordingRun(returncode=1)).can_login("pma", "pw"))

    def test_anonymous_accounts(self):
        run = RecordingRun(stdout="''@'localhost'\n''@'zbook'\n")
        self.assertEqual(mysqladmin.MysqlAdmin(self.paths, run).anonymous_accounts(""),
                         ["''@'localhost'", "''@'zbook'"])

    def test_upgrade_uses_mysql_upgrade(self):
        run = RecordingRun(stdout="Phase 1/7\nOK\n")
        self.assertIn("OK", mysqladmin.MysqlAdmin(self.paths, run).upgrade("pw"))
        self.assertEqual(run.calls[0]["argv"][0], "/l/bin/mysql_upgrade")
