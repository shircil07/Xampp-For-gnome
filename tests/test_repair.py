import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fakes
from xampp_panel import configedit, health, pmaconfig, repair
from xampp_panel.paths import Paths
from xampp_panel.services import State

PMA_XAMPP = ("<?php\n$i = 0;\n$i++;\n$cfg['Servers'][$i]['auth_type'] = 'config';\n"
             "$cfg['Servers'][$i]['user'] = 'root';\n$cfg['Servers'][$i]['controluser'] = 'pma';\n"
             "#$cfg['Servers'][$i]['controlpass'] = '';\n")
HASH = "$6$abcdefgh12345678$" + "B" * 86
NEW = "new-pass 1"


class RepairCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc")
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

    def app(self, *answers, token="generated-token", real_mysql_check=False):
        """real_mysql_check: use RepairApp's own /proc-based check instead of self.running."""
        self.dialogs = fakes.FakeDialogs(answers)
        running = None if real_mysql_check else (lambda: self.running)
        return repair.RepairApp(self.dialogs, self.admin, self.helper, self.paths, self.run,
                                token=lambda n: token, mysql_running=running, sleep=lambda s: None)

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

    def test_mysqld_without_port_counts_as_running(self):
        self.mysqld_without_port()
        self.assertFalse(self.app(real_mysql_check=True)._ensure_mysql())
        self.assertEqual(self.helper.calls, [])

    def test_starts_mysql_when_stopped(self):
        self.running = False
        app = self.app()
        with self.assertRaises(repair.RepairError):
            app._ensure_mysql()
        self.assertEqual(self.helper.calls[0], ("lampp", ["startmysql"]))


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

    def test_health_check_shows_report(self):
        app = self.app()
        app.check.snapshot = lambda paths: {"apache": State.STOPPED, "mysql": State.STOPPED,
                                            "ftp": State.STOPPED}
        app.health_check()
        self.assertRegex(self.dialogs.messages()[0], r"problem\(s\) found\.|No problems found\.")


class FirstInstallTest(RepairCase):
    def test_sets_everything_up_and_stops_mysql_it_started(self):
        self.running = False
        states = iter([False, True])
        app = self.app(NEW, NEW)
        app.mysql_running = lambda: next(states, True)
        self.assertEqual(app.first_install(), 0)
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertEqual(self.helper.calls, [("lampp", ["startmysql"]), ("lampp", ["stopmysql"])])

    def test_skipping_password_still_drops_anonymous(self):
        self.assertEqual(self.app("").first_install(), 0)
        self.assertEqual(self.admin.root_password, "")
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "config")
        self.assertEqual(self.helper.calls, [])  # MySQL was already running: left running

    def test_existing_root_password_is_kept(self):
        self.admin.root_password = "old-pass 1"
        self.assertEqual(self.app("old-pass 1").first_install(), 0)
        self.assertEqual(self.admin.root_password, "old-pass 1")

    def test_failed_step_returns_1_and_names_the_fix(self):
        self.admin.fail = "ERROR 2002"
        self.assertEqual(self.app("").first_install(), 1)
        self.assertIn(health.FIX_PMA, self.dialogs.messages()[0])


class MenuAndMainTest(RepairCase):
    def test_menu_runs_action_reports_errors_and_quits(self):
        self.admin.fail = "boom"
        app = self.app("4", "q")
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
