import unittest
from pathlib import Path

from xampp_panel.paths import DEFAULT, Paths


class PathsTest(unittest.TestCase):
    def test_defaults_point_at_real_install_locations(self):
        self.assertEqual(DEFAULT.lampp_script, Path("/opt/lampp/lampp"))
        self.assertEqual(DEFAULT.helper, Path("/opt/xampp-panel/bin/xampp-helper"))
        self.assertEqual(DEFAULT.state_file, Path("/opt/xampp-panel/state/sites.json"))
        self.assertEqual(DEFAULT.vhosts_conf, Path("/opt/lampp/etc/extra/xampp-panel-vhosts.conf"))
        self.assertEqual(DEFAULT.hosts, Path("/etc/hosts"))

    def test_overrides_flow_into_derived_paths(self):
        p = Paths(lampp=Path("/tmp/l"), app=Path("/tmp/a"))
        self.assertEqual(p.httpd_conf, Path("/tmp/l/etc/httpd.conf"))
        self.assertEqual(p.launcher, Path("/tmp/a/bin/xampp-panel"))


class RepairPathsTest(unittest.TestCase):
    def test_repair_paths(self):
        p = Paths(lampp=Path("/l"), app=Path("/a"))
        self.assertEqual(p.phpmyadmin_conf, Path("/l/phpmyadmin/config.inc.php"))
        self.assertEqual(p.pma_tables_sql, Path("/l/phpmyadmin/sql/create_tables.sql"))
        self.assertEqual(p.mysql_upgrade, Path("/l/bin/mysql_upgrade"))
        self.assertEqual(p.proftpd_bin, Path("/l/sbin/proftpd"))
        self.assertEqual(p.repair, Path("/a/bin/xampp-repair"))
