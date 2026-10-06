import os
import tempfile
import unittest
from pathlib import Path

import fakes
from xampp_panel import health
from xampp_panel.paths import Paths
from xampp_panel.services import State

GOOD_PMA = ("<?php\n$cfg['Servers'][$i]['controluser'] = 'pma';\n"
            "$cfg['Servers'][$i]['controlpass'] = 'pw';\n$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';\n")


class HealthCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc")
        for d in ("lampp/etc", "lampp/phpmyadmin", "lampp/sbin", "app/state"):
            (root / d).mkdir(parents=True)
        self.paths.my_cnf.write_text("[mysqld]\nport=3306\n")
        self.paths.httpd_conf.write_text("# BEGIN xampp-panel vhosts\nInclude x\n# END xampp-panel vhosts\n")
        self.paths.proftpd_conf.write_text("UserPassword daemon $6$x$y\n")
        self.paths.proftpd_bin.write_text("")
        self.paths.phpmyadmin_conf.write_text(GOOD_PMA)
        self.paths.hosts.write_text("127.0.0.1\tlocalhost\n")
        self.admin = fakes.FakeAdmin(root_password="secret1!")
        self.admin.anonymous = []
        self.run = fakes.FakeRun()
        self.states = {"apache": State.RUNNING, "mysql": State.RUNNING, "ftp": State.STOPPED}

    def check(self, root_password="secret1!"):
        hc = health.HealthCheck(self.admin, self.paths, self.run, snapshot=lambda paths: self.states)
        return hc.run_checks(root_password)

    def problems(self, findings):
        return [(f.text, f.fix) for f in findings if not f.ok]


class HealthCheckTest(HealthCase):
    def test_healthy_install_has_no_problems(self):
        findings = self.check()
        self.assertEqual(self.problems(findings), [])
        self.assertIn("No problems found.", health.render(findings))

    def test_mysql_networking_off(self):
        self.paths.my_cnf.write_text("[mysqld]\nskip-networking\n")
        self.assertIn(health.FIX_NETWORK, [fix for _, fix in self.problems(self.check())])

    def test_mysql_starting_points_to_networking_fix(self):
        self.states["mysql"] = State.STARTING
        self.assertIn(health.FIX_NETWORK, [fix for _, fix in self.problems(self.check())])

    def test_broken_ftp_config(self):
        self.paths.proftpd_conf.write_text("UserPassword daemon <?\nphp\n?>\n")
        self.assertIn(health.FIX_FTP, [fix for _, fix in self.problems(self.check())])

    def test_config_test_failure_is_reported(self):
        self.run.answers["apachectl"] = (1, "", "Syntax error on line 3\n")
        texts = [text for text, _ in self.problems(self.check())]
        self.assertTrue(any("Syntax error on line 3" in t for t in texts), texts)

    def test_root_without_password_and_anonymous_accounts(self):
        self.admin.root_password = ""
        self.admin.anonymous = ["''@'localhost'"]
        fixes = [fix for _, fix in self.problems(self.check(root_password=None))]
        self.assertEqual(fixes.count(health.FIX_ROOT), 2)

    def test_anonymous_check_skipped_without_root_password(self):
        self.admin.anonymous = ["''@'localhost'"]
        self.assertEqual(self.problems(self.check(root_password=None)), [])

    def test_pma_not_set_up_or_cannot_log_in(self):
        self.paths.phpmyadmin_conf.write_text("<?php\n")
        self.assertIn(health.FIX_PMA, [fix for _, fix in self.problems(self.check())])
        self.paths.phpmyadmin_conf.write_text(GOOD_PMA)
        self.admin.pma_login = False
        self.assertIn(health.FIX_PMA, [fix for _, fix in self.problems(self.check())])

    def test_mysql_stopped_skips_account_checks(self):
        self.states["mysql"] = State.STOPPED
        self.admin.root_password = ""
        self.assertEqual(self.problems(self.check()), [])

    def test_site_missing_from_hosts(self):
        self.paths.state_file.write_text('[{"name": "demo", "path": "/home/u/Sites/demo", "uid": 1000}]')
        self.assertIn(health.FIX_REAPPLY, [fix for _, fix in self.problems(self.check())])
        self.paths.hosts.write_text("127.0.0.1\tdemo.local\n")
        self.assertEqual(self.problems(self.check()), [])

    def test_render_counts_problems(self):
        text = health.render([health.Finding(True, "fine"), health.Finding(False, "broken", health.FIX_FTP)])
        self.assertIn("OK   fine", text)
        self.assertIn("FIX  broken", text)
        self.assertIn(f"→ {health.FIX_FTP}", text)
        self.assertIn("1 problem(s) found.", text)
