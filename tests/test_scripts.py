import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ScriptsTest(unittest.TestCase):
    def test_syntax(self):
        for name in ("setup.sh", "uninstall.sh", "tools/fix-pma.sh", "tools/secure-mysql.sh"):
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


class FixPmaSqlTest(unittest.TestCase):
    """tools/fix-pma.php needs a PHP CLI: set XAMPP_TEST_PHP or have php on PATH."""

    def setUp(self):
        self.php = os.environ.get("XAMPP_TEST_PHP") or shutil.which("php")
        if not self.php:
            self.skipTest("no PHP CLI")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_php(self, mode, config_body):
        """Runs fix-pma.php the way fix-pma.sh does: script on stdin, config path as argument."""
        cfg = Path(self.tmp.name) / "config.inc.php"
        cfg.write_text("<?php\n$i = 0;\n$i++;\n" + config_body)
        with open(ROOT / "tools/fix-pma.php", "rb") as src:
            return subprocess.run([self.php, "-d", "display_errors=stderr", "--", mode, str(cfg)],
                                  stdin=src, capture_output=True, text=True)

    def test_values_are_escaped(self):
        proc = self.run_php("sql", r"""$cfg['Servers'][$i]['controluser'] = 'p\'ma';
$cfg['Servers'][$i]['controlpass'] = 'a\'b\\c"d`e';
$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';
""")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');")
        self.assertIn("CREATE USER IF NOT EXISTS 'p''ma'@'localhost';", lines)
        self.assertIn(r"""ALTER USER 'p''ma'@'localhost' IDENTIFIED BY 'a''b\\c"d`e';""", lines)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON `phpmyadmin`.* TO 'p''ma'@'localhost';", lines)

    def test_config_output_stays_out_of_the_sql(self):
        proc = self.run_php("sql", """echo $undefined;
$cfg['Servers'][$i]['controluser'] = 'pma';
$cfg['Servers'][$i]['controlpass'] = 'x';
$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';
?>
trailing text
""")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.startswith("SET SESSION"), proc.stdout)
        self.assertNotIn("trailing", proc.stdout)

    def test_refused_configs(self):
        cases = {
            "no password": "$cfg['Servers'][$i]['controluser'] = 'pma';\n"
                           "$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';\n",
            "no user": "$cfg['Servers'][$i]['controlpass'] = 'x';\n"
                       "$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';\n",
            "no pmadb": "$cfg['Servers'][$i]['controluser'] = 'pma';\n"
                        "$cfg['Servers'][$i]['controlpass'] = 'x';\n",
            "other pmadb": "$cfg['Servers'][$i]['controluser'] = 'pma';\n"
                           "$cfg['Servers'][$i]['controlpass'] = 'x';\n"
                           "$cfg['Servers'][$i]['pmadb'] = 'my`db';\n",
            "NUL byte": "$cfg['Servers'][$i]['controluser'] = 'pma';\n"
                        "$cfg['Servers'][$i]['controlpass'] = \"a\\0b\";\n"
                        "$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';\n",
        }
        for name, body in cases.items():
            with self.subTest(name):
                proc = self.run_php("sql", body)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_bad_usage(self):
        proc = self.run_php("drop", "")
        self.assertEqual(proc.returncode, 2)


class SecureMysqlTest(unittest.TestCase):
    def bash(self, script, *args):
        """Runs `script` after sourcing secure-mysql.sh, with as_root running commands directly."""
        prelude = 'source "$1"; shift; as_root() { "$@"; }; '
        proc = subprocess.run(["bash", "-c", prelude + script, "bash", str(ROOT / "tools/secure-mysql.sh"), *args],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_password_is_escaped_and_not_expanded(self):
        lines = self.bash('build_sql "$1"', "a'b\\c$HOME%s`id`&e").splitlines()
        self.assertEqual(lines[0], "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');")
        self.assertIn("SET @pw = 'a''b\\\\c$HOME%s`id`&e';", lines)
        self.assertEqual(sum("a''b" in line for line in lines), 1, "password must appear only once")
        self.assertEqual(lines[-1], "SET @pw = NULL, @accounts = NULL;")

    def test_accounts_come_from_mysql_user(self):
        sql = self.bash('build_sql password1')
        self.assertIn("FROM mysql.user WHERE user = '';", sql)
        self.assertIn("FROM mysql.user WHERE user = 'root';", sql)
        self.assertIn("EXECUTE IMMEDIATE IF(@accounts IS NULL, 'DO 0', CONCAT('DROP USER ', @accounts));", sql)

    def write_config(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "config.inc.php"
        cfg.write_text(body)
        return cfg

    def test_auth_type_config_switches_to_cookie_with_backup(self):
        original = ("<?php\n#$cfg['Servers'][$i]['auth_type'] = 'cookie';\n"
                    "$cfg['Servers'][$i]['auth_type'] = 'config'; // XAMPP default\n"
                    "$cfg['Servers'][$i]['user'] = 'root';\n")
        cfg = self.write_config(original)
        self.assertEqual(self.bash('pma_auth_type "$1"', str(cfg)), "config\n")
        self.bash('pma_backup "$1"; pma_use_login_page "$1"', str(cfg))
        self.assertEqual(self.bash('pma_auth_type "$1"', str(cfg)), "cookie\n")
        self.assertEqual(cfg.read_text(), original.replace("= 'config';", "= 'cookie';"))
        self.assertIn("#$cfg['Servers'][$i]['auth_type'] = 'cookie';", cfg.read_text())
        self.assertEqual(Path(str(cfg) + ".xampp-panel.bak").read_text(), original)

    def test_backup_is_made_only_once(self):
        cfg = self.write_config("<?php\n$cfg['Servers'][$i]['auth_type'] = 'config';\n")
        backup = Path(str(cfg) + ".xampp-panel.bak")
        backup.write_text("older backup")
        self.bash('pma_backup "$1"', str(cfg))
        self.assertEqual(backup.read_text(), "older backup")

    def test_password_keeps_surrounding_spaces(self):
        proc = subprocess.run(["bash", "-c", 'source "$1"; read_new_password; printf "[%s]" "$NEW_PASSWORD"',
                               "bash", str(ROOT / "tools/secure-mysql.sh")],
                              input="  pass word  \n  pass word  \n", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.endswith("[  pass word  ]"), proc.stdout)

    def test_commented_auth_type_is_ignored(self):
        cfg = self.write_config("<?php\n// $cfg['Servers'][$i]['auth_type'] = 'config';\n")
        self.assertEqual(self.bash('pma_auth_type "$1"', str(cfg)), "")
