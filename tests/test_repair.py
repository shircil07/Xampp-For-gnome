import contextlib
import io
import re
import stat
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fakes
from xampp_panel import configedit, health, pmaconfig, repair
from xampp_panel.mysqladmin import native_password_hash
from xampp_panel.paths import Paths
from xampp_panel.services import State

PMA_XAMPP = ("<?php\n$i = 0;\n$i++;\n$cfg['Servers'][$i]['auth_type'] = 'config';\n"
             "$cfg['Servers'][$i]['user'] = 'root';\n$cfg['Servers'][$i]['controluser'] = 'pma';\n"
             "#$cfg['Servers'][$i]['controlpass'] = '';\n")
HASH = "$6$abcdefgh12345678$" + "B" * 86
NEW = "new-pass 1"
CONNECT = "ERROR 2002 (HY000): Can't connect to local server through socket 'mysql.sock' (2)"


class RepairCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc",
                           runtime=root / "run")
        for d in ("lampp/etc", "lampp/phpmyadmin/sql", "lampp/sbin", "app/state"):
            (root / d).mkdir(parents=True)
        self.paths.phpmyadmin_conf.write_text(PMA_XAMPP)
        self.paths.pma_tables_sql.write_text("CREATE DATABASE IF NOT EXISTS phpmyadmin;\n")
        self.paths.my_cnf.write_text("[mysqld]\nport=3306\n")
        self.paths.httpd_conf.write_text("Listen 80\n")
        self.paths.proftpd_conf.write_text("A\nUserPassword daemon <?\nphp\n?>\nB\n")
        self.admin = fakes.FakeAdmin(root_password="")
        self.helper = fakes.FakeHelper()
        self.run = fakes.FakeRun({"openssl": (0, HASH + "\n", "")})
        self.running = True
        self.now = 0.0  # the fake monotonic clock; the fake sleep advances it
        self.chowns = []

    def advance(self, seconds):
        self.now += seconds

    def app(self, *answers, token="generated-token", real_mysql_check=False):
        """real_mysql_check: use RepairApp's own /proc-based check instead of self.running."""
        self.dialogs = fakes.FakeDialogs(answers)
        running = None if real_mysql_check else (lambda: self.running)
        return repair.RepairApp(self.dialogs, self.admin, self.helper, self.paths, self.run,
                                token=lambda n: token, mysql_running=running, sleep=self.advance,
                                clock=lambda: self.now, mysql_account=lambda: (1234, 1235),
                                chown=lambda target, uid, gid: self.chowns.append((target, uid, gid)))

    def mysqld_without_port(self):
        """A live XAMPP mysqld in the fake /proc, with no port listening (what skip-networking does)."""
        d = self.paths.proc / "500"
        d.mkdir(parents=True)
        (d / "comm").write_text("mysqld\n")
        (d / "cmdline").write_bytes(f"{self.paths.lampp}/sbin/mysqld\0--skip-networking\0".encode())

    def pma(self, key):
        return pmaconfig.get_value(self.paths.phpmyadmin_conf.read_text(), key)


class ChangeRootPasswordTest(RepairCase):
    def test_sets_password_drops_anonymous_then_switches_login_page(self):
        self.app(NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertTrue(Path(str(self.paths.phpmyadmin_conf) + ".xampp-panel.bak").exists())

    def test_failure_leaves_phpmyadmin_alone(self):
        self.admin.fail = "ERROR 1064 syntax"
        app = self.app(NEW, NEW)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertEqual(self.pma("auth_type"), "config")
        self.assertIn("ERROR 1064 syntax", self.dialogs.messages()[-1])

    def test_asks_current_password_until_right(self):
        self.admin.root_password = "old-pass 1"
        self.app("wrong", "old-pass 1", NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertIn("not right", self.dialogs.messages()[0])

    def test_rejects_short_and_mismatched_passwords(self):
        self.app("short", NEW, "other-pass", NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(len(self.dialogs.messages()), 3)  # too short, mismatch, done

    def test_cancel_changes_nothing(self):
        app = self.app(None)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertEqual(self.admin.executed, [])

    def test_cancel_on_repeat_is_a_cancel_not_a_mismatch(self):
        app = self.app(NEW, None)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertEqual(self.admin.executed, [])
        self.assertEqual(self.dialogs.messages(), [])

    def test_mysqld_without_port_counts_as_running(self):
        self.mysqld_without_port()
        self.assertFalse(self.app(real_mysql_check=True)._ensure_mysql())
        self.assertEqual(self.helper.calls, [])

    def test_starts_mysql_when_stopped(self):
        self.running = False
        app = self.app()
        with self.assertRaises(repair.RepairError), contextlib.redirect_stderr(io.StringIO()):
            app._ensure_mysql()
        self.assertEqual(self.helper.calls[0], ("lampp", ["startmysql"]))

    def test_waits_until_mysql_answers(self):
        self.admin.unready_pings = 3  # process up, server still starting
        sleeps = []
        app = self.app()
        app.sleep = sleeps.append
        self.assertFalse(app._ensure_mysql())
        self.assertEqual(self.admin.pings, 4)
        self.assertEqual(sleeps, [1, 1, 1])

    def test_mysql_that_never_answers_is_an_error(self):
        self.admin.connect_error = CONNECT
        with self.assertRaisesRegex(repair.RepairError, "does not answer"):
            self.app()._ensure_mysql()
        self.assertEqual(self.admin.pings, repair.MYSQL_WAIT_SECONDS + 1)  # polls at 0, 1, ... 20 s
        self.assertEqual(self.now, repair.MYSQL_WAIT_SECONDS)

    def test_wait_is_bounded_in_real_time_even_when_pings_hang(self):
        app = self.app()
        pings = []

        def slow_ping():
            pings.append(self.now)
            self.advance(15)  # each attempt runs into the client's timeout
            return False
        app.admin.ping = slow_ping
        with self.assertRaisesRegex(repair.RepairError, "does not answer"):
            app._ensure_mysql()
        self.assertEqual(pings, [0, 16])  # no sleep after the last poll once the deadline passed
        self.assertEqual(self.now, 31)

    def test_connection_error_is_shown_not_taken_as_a_wrong_password(self):
        app = self.app()
        app.admin.ping = lambda: True  # answered once, then went away
        self.admin.connect_error = CONNECT
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertIn("Can't connect", self.dialogs.messages()[-1])
        self.assertEqual(self.dialogs.shown, [("msgbox", self.dialogs.messages()[-1])])  # no password prompt


class PmaTest(RepairCase):
    def test_fix_generates_password_writes_config_and_account(self):
        self.app().fix_pma()
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.pma("pmadb"), "phpmyadmin")
        self.assertIn("CREATE DATABASE IF NOT EXISTS phpmyadmin;", self.admin.executed[0])
        self.assertIn("IDENTIFIED BY 'generated-token'", self.admin.executed[0])

    def test_fix_keeps_existing_password(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "kept"))
        self.app(token="unused").fix_pma()
        self.assertEqual(self.pma("controlpass"), "kept")

    def test_sql_failure_leaves_config_untouched(self):
        self.admin.fail = "ERROR"
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertEqual(self.paths.phpmyadmin_conf.read_text(), PMA_XAMPP)

    def test_other_pmadb_refused(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "pmadb", "custom"))
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertEqual(self.admin.executed, [])

    def test_controluser_root_is_refused(self):
        for user in ("root", "ROOT"):
            with self.subTest(user=user):
                self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controluser", user))
                app = self.app()
                self.assertFalse(app._attempt(app.fix_pma))
                self.assertEqual(self.admin.executed, [])
                self.assertIn(f"controluser is '{user}'", self.dialogs.messages()[-1])

    def test_odd_controluser_is_refused(self):
        for user in ("pma'@'%", "a" * 33, "pma user"):
            with self.subTest(user=user):
                self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controluser", user))
                app = self.app()
                self.assertFalse(app._attempt(app.fix_pma))
                self.assertEqual(self.admin.executed, [])

    def test_login_still_failing_is_reported(self):
        self.admin.pma_login = False
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertIn("cannot log in", self.dialogs.messages()[-1])

    def test_show_password_only_after_yes(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "s3cret"))
        self.app(False).show_pma_password()
        self.assertEqual(self.dialogs.messages(), [])
        self.assertEqual(self.dialogs.secrets(), [])
        self.app(True).show_pma_password()
        self.assertEqual(self.dialogs.messages(), [])
        self.assertIn("s3cret", self.dialogs.secrets()[0])

    def test_show_password_escape_shows_nothing(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "s3cret"))
        app = self.app(None)
        self.assertFalse(app._attempt(app.show_pma_password))
        self.assertEqual(self.dialogs.secrets(), [])


class FtpTest(RepairCase):
    def test_replaces_broken_block_with_hash(self):
        self.app("ftp-pass 1", "ftp-pass 1").fix_ftp()
        self.assertEqual(self.paths.proftpd_conf.read_text(), f"A\nUserPassword daemon {HASH}\nB\n")
        openssl = [c for c in self.run.calls if c[0][0] == "openssl"][0]
        self.assertEqual(openssl[0], ["openssl", "passwd", "-6", "-stdin"])
        self.assertEqual(openssl[1]["input"], "ftp-pass 1\n")

    def test_rolls_back_when_proftpd_rejects_it(self):
        self.run.answers["proftpd"] = (1, "", "Fatal: bad config\n")
        before = self.paths.proftpd_conf.read_text()
        app = self.app("ftp-pass 1", "ftp-pass 1")
        self.assertFalse(app._attempt(app.fix_ftp))
        self.assertEqual(self.paths.proftpd_conf.read_text(), before)
        self.assertIn("Fatal: bad config", self.dialogs.messages()[-1])

    def test_openssl_timeout_is_reported(self):
        self.run.answers["openssl"] = subprocess.TimeoutExpired(["openssl"], 30)
        before = self.paths.proftpd_conf.read_text()
        app = self.app("ftp-pass 1", "ftp-pass 1")
        self.assertFalse(app._attempt(app.fix_ftp))
        self.assertIn("timed out", self.dialogs.messages()[-1])
        self.assertEqual(self.paths.proftpd_conf.read_text(), before)


class OtherActionsTest(RepairCase):
    def test_networking_fix_comments_out_skip_networking(self):
        self.paths.my_cnf.write_text("[mysqld]\nskip-networking\n")
        self.mysqld_without_port()
        self.app(True, real_mysql_check=True).fix_networking()
        text = self.paths.my_cnf.read_text()
        self.assertFalse(configedit.mysql_networking_off(text))
        self.assertFalse(configedit.mysql_hardened(text))  # localhost-only is harden's job, not this fix's
        self.assertEqual(self.helper.calls, [("lampp", ["stopmysql", "startmysql"])])

    def test_networking_fix_when_mysql_stopped_says_start_it(self):
        self.paths.my_cnf.write_text("[mysqld]\nskip-networking\n")
        self.app(real_mysql_check=True).fix_networking()
        self.assertEqual(self.helper.calls, [])
        self.assertIn("Start MySQL", self.dialogs.messages()[0])

    def test_mysql_upgrade_shows_output(self):
        self.app().mysql_upgrade()
        self.assertIn("OK", self.dialogs.messages()[0])

    def test_reapply_asks_and_applies(self):
        self.app(True, False).reapply()
        self.assertEqual(self.helper.calls, [("integrate", True), ("harden", True), ("lean", False), ("apply", [])])

    def test_reapply_escape_on_either_question_changes_nothing(self):
        for answers in ((None,), (True, None), (False, None)):
            with self.subTest(answers=answers):
                app = self.app(*answers)
                self.assertFalse(app._attempt(app.reapply))
                self.assertEqual(self.helper.calls, [])
                self.assertEqual(self.dialogs.messages(), [])

    def test_reapply_no_means_no(self):
        self.app(False, False).reapply()
        self.assertEqual(self.helper.calls, [("integrate", True), ("harden", False), ("lean", False), ("apply", [])])

    def test_health_check_shows_report(self):
        app = self.app()
        app.check.snapshot = lambda paths: {"apache": State.STOPPED, "mysql": State.STOPPED,
                                            "ftp": State.STOPPED}
        app.health_check()
        report = self.dialogs.messages()[0]
        # Fixture: damaged proftpd.conf and no vhosts block in httpd.conf; MySQL stopped (checks skipped).
        self.assertIn("FIX  FTP config was damaged by 'lampp security'", report)
        self.assertIn("FIX  The panel's sites setup is missing from httpd.conf", report)
        self.assertIn("MySQL is not running: account checks skipped", report)
        self.assertTrue(report.endswith("2 problem(s) found."), report)


class FirstInstallTest(RepairCase):
    def first_install(self, app):
        """Runs first_install; returns (exit code, what it printed to stdout and stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = app.first_install()
        return code, out.getvalue() + err.getvalue()

    def passwordboxes(self):
        return [text for kind, text in self.dialogs.shown if kind == "passwordbox"]

    def working_pma(self, password="kept-token"):
        text = pmaconfig.set_value(PMA_XAMPP, "controlpass", password)
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(text, "pmadb", "phpmyadmin"))

    def test_fresh_install_sets_everything_up_and_stops_mysql_it_started(self):
        self.running = False
        states = iter([False, True])
        app = self.app(NEW, NEW)
        app.mysql_running = lambda: next(states, True)
        code, printed = self.first_install(app)
        self.assertEqual(code, 0)
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertEqual(self.helper.calls, [("lampp", ["startmysql"]), ("lampp", ["stopmysql"])])
        self.assertIn("Starting MySQL", printed)

    def test_skipping_password_still_drops_anonymous(self):
        self.assertEqual(self.first_install(self.app(""))[0], 0)
        self.assertEqual(self.admin.root_password, "")
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "config")
        self.assertEqual(self.helper.calls, [])  # MySQL was already running: left running

    def test_cancel_on_repeat_skips_the_password(self):
        self.assertEqual(self.first_install(self.app(NEW, None))[0], 0)
        self.assertEqual(self.admin.root_password, "")
        self.assertEqual(self.admin.anonymous, [])
        self.assertFalse(any("don't match" in m for m in self.dialogs.messages()))

    def test_rerun_keeps_working_pma(self):
        self.working_pma()
        code, printed = self.first_install(self.app("", token="unused"))
        self.assertEqual(code, 0)
        self.assertEqual(self.pma("controlpass"), "kept-token")
        self.assertFalse(any("CREATE USER" in sql for sql in self.admin.executed))
        self.assertIn("already working", printed)

    def test_rerun_resets_pma_that_cannot_log_in(self):
        self.working_pma("stale")
        logins = iter([False])  # the first login check fails; after the reset it works
        can_login = self.admin.can_login
        self.admin.can_login = lambda u, p, d=None: next(logins, True) if u == "pma" else can_login(u, p, d)
        self.assertEqual(self.first_install(self.app(""))[0], 0)
        self.assertEqual(self.pma("controlpass"), "generated-token")

    def test_rerun_sets_up_pma_without_pmadb(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "kept-token"))
        self.assertEqual(self.first_install(self.app(""))[0], 0)
        self.assertEqual(self.pma("pmadb"), "phpmyadmin")
        self.assertEqual(self.pma("controlpass"), "generated-token")

    def test_rerun_with_root_password_asks_nothing(self):
        self.admin.root_password = "old-pass 1"
        self.working_pma()
        code, printed = self.first_install(self.app())  # no scripted answers: any dialog would fail
        self.assertEqual(code, 0)
        self.assertEqual(self.admin.root_password, "old-pass 1")
        self.assertIn(health.FIX_ROOT, printed)
        self.assertNotIn("anonymous accounts removed", printed)  # the password is not known here

    def test_root_password_is_asked_once_when_pma_needs_it(self):
        self.admin.root_password = "old-pass 1"
        code, printed = self.first_install(self.app("old-pass 1"))
        self.assertEqual(code, 0)
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.admin.root_password, "old-pass 1")
        self.assertEqual(len(self.passwordboxes()), 1)
        self.assertIn(health.FIX_ROOT, printed)
        self.assertEqual(self.admin.anonymous, [])  # the known password was used to drop them
        self.assertTrue(self.admin.executed[-1].startswith(repair.drop_anonymous_sql()))
        self.assertIn("anonymous accounts removed", printed)

    def test_cancelled_root_prompt_is_not_repeated(self):
        self.admin.root_password = "old-pass 1"
        code, _ = self.first_install(self.app(None))
        self.assertEqual(code, 1)  # pma was skipped
        self.assertEqual(len(self.passwordboxes()), 1)
        self.assertEqual(self.admin.executed, [])

    def test_connection_error_is_not_taken_as_a_root_password(self):
        self.admin.ping = lambda: True  # answered once, then went away
        self.admin.connect_error = CONNECT
        code, printed = self.first_install(self.app())
        self.assertEqual(code, 1)
        self.assertNotIn("already has a password", printed)
        messages = self.dialogs.messages()
        self.assertTrue(any(m.startswith("MySQL root password did not work") and "Can't connect" in m
                            for m in messages), messages)
        self.assertEqual(self.admin.executed, [])

    def test_mysql_that_never_answers_stops_first_install(self):
        self.admin.connect_error = CONNECT
        code, printed = self.first_install(self.app())
        self.assertEqual(code, 1)
        self.assertIn("does not answer", printed)
        self.assertNotIn("already has a password", printed)

    def test_failed_step_returns_1_and_names_the_fix(self):
        self.admin.fail = "ERROR 2002"
        self.assertEqual(self.first_install(self.app(""))[0], 1)
        self.assertIn(health.FIX_PMA, self.dialogs.messages()[0])


class FakeMysqlServer(fakes.FakeHelper):
    """lampp stop/start flip the running flag. A start reads my.cnf's init-file the way MariaDB does:
    a hash it recognises (one of `passwords`) becomes root's password. start_fails: a start with an
    init-file never comes up. exit_on_init_start: the program is killed during that start."""

    def __init__(self, case, passwords=(), start_fails=False, exit_on_init_start=False, normal_start_fails=False):
        super().__init__()
        self.case = case
        self.hashes = {native_password_hash(pw): pw for pw in passwords}
        self.start_fails = start_fails
        self.exit_on_init_start = exit_on_init_start
        self.normal_start_fails = normal_start_fails
        self.init_files = []  # (folder mode, file mode, contents) of every init-file a start saw

    def lampp(self, actions):
        super().lampp(actions)
        for action in actions:
            if action == "stopmysql":
                self.case.running = False
            elif action == "startmysql":
                m = re.search(r"(?m)^init-file=(.*)$", self.case.paths.my_cnf.read_text())
                if not m:
                    self.case.running = not self.normal_start_fails
                    continue
                path = Path(m[1])
                self.init_files.append((stat.S_IMODE(path.parent.stat().st_mode),
                                        stat.S_IMODE(path.stat().st_mode), path.read_text()))
                if self.exit_on_init_start:
                    raise SystemExit(143)
                if self.start_fails:
                    continue
                digest = re.search(r"IDENTIFIED BY PASSWORD '(\*[0-9A-F]{40})';", path.read_text())
                if digest and digest[1] in self.hashes:
                    self.case.admin.root_password = self.hashes[digest[1]]  # what MariaDB would now accept
                self.case.running = True


class ResetRootPasswordTest(RepairCase):
    def setUp(self):
        super().setUp()
        self.admin.root_password = "forgotten 1"
        self.original_cnf = self.paths.my_cnf.read_text()

    def server(self, passwords=(NEW,), **kw):
        self.helper = FakeMysqlServer(self, passwords, **kw)
        return self.helper

    def lampp_calls(self):
        return [actions for kind, actions in self.helper.calls if kind == "lampp"]

    def leftovers(self):
        return list(self.paths.runtime.iterdir()) if self.paths.runtime.exists() else []

    def assert_cleaned_up(self):
        self.assertEqual(self.paths.my_cnf.read_text(), self.original_cnf)
        self.assertEqual(self.leftovers(), [])

    def test_resets_through_an_init_file_then_finishes_like_a_password_change(self):
        server = self.server()
        app = self.app(True, NEW, NEW)
        app.reset_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.lampp_calls(), [["stopmysql"], ["startmysql"], ["stopmysql"], ["startmysql"]])
        self.assertEqual(len(server.init_files), 1)  # the normal restart no longer sees the file
        folder_mode, file_mode, sql = server.init_files[0]
        self.assertEqual((folder_mode, file_mode), (0o710, 0o640))
        self.assertIn("IDENTIFIED BY PASSWORD '*", sql)
        self.assertNotIn(NEW, sql)
        folder, fd = self.chowns[0][0], self.chowns[1][0]
        self.assertEqual(self.chowns, [(folder, 0, 1235), (fd, 0, 1235)])  # root:mysql, never the mysql uid
        self.assertEqual(Path(folder).parent, self.paths.runtime)
        self.assertIsInstance(fd, int)  # the file is changed through its open handle, not its path
        self.assert_cleaned_up()
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertEqual(app.root_password, NEW)
        self.assertEqual(self.dialogs.messages()[-1], "Done. Log in to phpMyAdmin as 'root' with the new password.")

    def test_mysql_stopped_at_the_start_is_stopped_again_at_the_end(self):
        self.server()
        self.running = False
        self.app(True, NEW, NEW).reset_root_password()
        self.assertEqual(self.lampp_calls(), [["startmysql"], ["stopmysql"], ["startmysql"], ["stopmysql"]])
        self.assertFalse(self.running)
        self.assertEqual(self.admin.root_password, NEW)

    def test_no_or_escape_changes_nothing(self):
        for answers in ((False,), (None,), (True, None)):
            with self.subTest(answers=answers):
                self.server()
                app = self.app(*answers)
                app._attempt(app.reset_root_password)
                self.assertEqual(self.lampp_calls(), [])
                self.assertEqual(self.admin.root_password, "forgotten 1")
                self.assert_cleaned_up()

    def test_missing_mysql_user_is_found_before_asking_for_a_password(self):
        self.server()
        app = self.app(True)
        app.mysql_account = mock.Mock(side_effect=KeyError("mysql"))
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("There is no 'mysql' user, so the reset cannot work. Nothing was changed.",
                      self.dialogs.messages()[-1])
        self.assertEqual(self.lampp_calls(), [])

    def test_a_runtime_folder_that_is_not_private_is_refused_before_stopping_mysql(self):
        self.server()
        self.paths.runtime.mkdir(mode=0o777)
        self.paths.runtime.chmod(0o777)
        app = self.app(True, NEW, NEW)
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("not a private", self.dialogs.messages()[-1])
        self.assertEqual(self.lampp_calls(), [])

    def test_mysql_not_coming_up_with_the_file_is_cleaned_up_and_started_normally(self):
        self.server(start_fails=True)
        app = self.app(True, NEW, NEW)
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("The reset did not work: MySQL did not start with the reset file.", self.dialogs.messages()[-1])
        self.assertEqual(self.lampp_calls()[-1], ["startmysql"])
        self.assertTrue(self.running)
        self.assertEqual(self.admin.root_password, "forgotten 1")
        self.assert_cleaned_up()

    def test_a_failing_lampp_start_is_cleaned_up_too(self):
        self.server()
        app = self.app(True, NEW, NEW)
        original = self.helper.lampp

        def lampp(actions):
            if actions == ["startmysql"] and "init-file=" in self.paths.my_cnf.read_text():
                raise repair.HelperFailure("lampp startmysql failed")
            original(actions)
        self.helper.lampp = lampp
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("The reset did not work: lampp startmysql failed", self.dialogs.messages()[-1])
        self.assertTrue(self.running)
        self.assert_cleaned_up()

    def test_a_failing_reset_file_write_is_cleaned_up_and_started_normally(self):
        self.server()
        app = self.app(True, NEW, NEW)
        app.chown = mock.Mock(side_effect=PermissionError(1, "Operation not permitted"))
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("The reset did not work: [Errno 1] Operation not permitted", self.dialogs.messages()[-1])
        self.assertEqual(self.lampp_calls(), [["stopmysql"], ["startmysql"]])  # never started with a file
        self.assert_cleaned_up()

    def test_mysql_that_does_not_stop_is_reported_before_any_file_exists(self):
        self.server()
        self.helper.lampp = lambda actions: self.helper.calls.append(("lampp", list(actions)))  # stop does nothing
        app = self.app(True, NEW, NEW)
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("MySQL did not stop", self.dialogs.messages()[-1])
        self.assertEqual(self.lampp_calls(), [["stopmysql"]])
        self.assert_cleaned_up()

    def test_new_password_not_taking_effect_is_reported(self):
        self.server(passwords=())
        app = self.app(True, NEW, NEW)
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertIn("MySQL started, but the new password does not work", self.dialogs.messages()[-1])
        self.assertEqual(self.pma("auth_type"), "config")
        self.assert_cleaned_up()

    def test_a_failed_normal_restart_says_what_happened(self):
        for start_fails, expected in ((False, "running this again is safe"),
                                      (True, "The reset itself did not work either: MySQL did not start with")):
            with self.subTest(start_fails=start_fails):
                self.setUp()
                self.server(start_fails=start_fails, normal_start_fails=True)
                app = self.app(True, NEW, NEW)
                self.assertFalse(app._attempt(app.reset_root_password))
                message = self.dialogs.messages()[-1]
                self.assertIn("MySQL could not be started normally again: MySQL did not start.", message)
                self.assertIn(expected, message)
                self.assert_cleaned_up()

    def test_root_password_is_remembered_even_if_the_last_steps_fail(self):
        self.server()
        app = self.app(True, NEW, NEW)
        app.root_password = "forgotten 1"
        original = self.admin.execute

        def execute(sql, root_password):
            if "DROP USER" in sql:
                raise repair.MysqlError("ERROR 1064 boom")
            return original(sql, root_password)
        self.admin.execute = execute
        self.assertFalse(app._attempt(app.reset_root_password))
        self.assertEqual(app.root_password, NEW)

    def test_my_cnf_that_cannot_be_cleaned_is_named_and_mysql_is_not_restarted(self):
        self.server()
        app = self.app(True, NEW, NEW)
        writes = []
        real_write = repair.fsutil.atomic_write

        def atomic_write(path, text):
            if path == self.paths.my_cnf and "init-file=" not in text:
                raise OSError(28, "No space left on device")
            writes.append(path)
            real_write(path, text)
        with mock.patch.object(repair.fsutil, "atomic_write", atomic_write):
            self.assertFalse(app._attempt(app.reset_root_password))
        message = self.dialogs.messages()[-1]
        self.assertIn(str(self.paths.my_cnf), message)
        self.assertIn("init-file=", message)
        self.assertEqual(self.leftovers(), [])  # the reset file itself is gone first
        self.assertEqual(self.lampp_calls(), [["stopmysql"], ["startmysql"]])  # no normal restart

    def test_cleanup_happens_even_when_the_program_is_killed_midway(self):
        self.server(exit_on_init_start=True)
        app = self.app(True, NEW, NEW)
        with self.assertRaises(SystemExit):
            app.reset_root_password()
        self.assert_cleaned_up()

    def test_a_reset_left_by_a_killed_run_is_removed_on_start(self):
        self.server()
        folder = self.paths.runtime / "reset-old"
        folder.mkdir(parents=True)
        (folder / "reset.sql").write_text("ALTER USER ...;\n")
        self.paths.my_cnf.write_text(configedit.mysql_init_file(self.original_cnf, str(folder / "reset.sql")))
        note = self.app().remove_stale_reset()
        self.assertIn("Removed a root password reset left over", note)
        self.assert_cleaned_up()
        self.assertIsNone(self.app().remove_stale_reset())

    def test_a_stale_line_pointing_elsewhere_keeps_that_file(self):
        self.server()
        elsewhere = self.paths.lampp / "mine.sql"
        elsewhere.write_text("x")
        self.paths.my_cnf.write_text(configedit.mysql_init_file(self.original_cnf, str(elsewhere)))
        self.app().remove_stale_reset()
        self.assertEqual(self.paths.my_cnf.read_text(), self.original_cnf)
        self.assertTrue(elsewhere.exists())

    def test_wrong_current_password_points_to_the_reset(self):
        app = self.app("wrong one", None)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertIn(f"use “{health.FIX_RESET}” in sudo xampp-repair", self.dialogs.messages()[0])

    def test_is_in_the_menu(self):
        self.assertIn(health.FIX_RESET, [label for _, label, _ in self.app().menu_items()])


class MenuAndMainTest(RepairCase):
    def test_menu_runs_action_reports_errors_and_quits(self):
        self.admin.fail = "boom"
        app = self.app("5", "q")
        self.assertEqual(app.main_menu(), 0)
        self.assertIn("boom", self.dialogs.messages()[0])

    def test_escape_quits(self):
        self.assertEqual(self.app(None).main_menu(), 0)

    def test_hangup_and_terminate_exit_so_finally_blocks_run(self):
        for sig in (signal.SIGHUP, signal.SIGTERM):
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))
        repair.exit_on_signals()
        for sig, code in ((signal.SIGHUP, 129), (signal.SIGTERM, 143)):
            with self.subTest(sig=sig), self.assertRaises(SystemExit) as cm:
                signal.getsignal(sig)(sig, None)
            self.assertEqual(cm.exception.code, code)

    def test_main_rejects_bad_usage_and_non_root(self):
        self.assertEqual(repair.main(["bogus"]), 2)
        with mock.patch("os.geteuid", return_value=1000):
            self.assertEqual(repair.main([]), 1)
