import unittest

from xampp_panel import pmaconfig

CONFIG = """<?php
$i = 0;
$i++;
/* Authentication type */
#$cfg['Servers'][$i]['auth_type'] = 'cookie';
$cfg['Servers'][$i]['auth_type'] = 'config';   // XAMPP default
$cfg['Servers'][$i]['user'] = 'root';
// $cfg['Servers'][$i]['controlpass'] = 'commented';
$cfg['Servers'][$i]['controluser'] = 'pma';
$cfg['Servers'][$i]['controlpass'] = 'it\\'s \\\\ x';
$cfg['UploadDir'] = '';
"""


class GetValueTest(unittest.TestCase):
    def test_reads_active_line_and_ignores_comments(self):
        self.assertEqual(pmaconfig.get_value(CONFIG, "auth_type"), "config")
        self.assertEqual(pmaconfig.get_value(CONFIG, "controluser"), "pma")

    def test_unescapes_php_single_quotes(self):
        self.assertEqual(pmaconfig.get_value(CONFIG, "controlpass"), "it's \\ x")

    def test_missing_key_is_none(self):
        self.assertIsNone(pmaconfig.get_value(CONFIG, "pmadb"))

    def test_last_active_assignment_wins(self):
        text = "$cfg['Servers'][$i]['pmadb'] = 'a';\n$cfg['Servers'][$i]['pmadb'] = 'b';\n"
        self.assertEqual(pmaconfig.get_value(text, "pmadb"), "b")

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            pmaconfig.get_value(CONFIG, "password")


class SetValueTest(unittest.TestCase):
    def test_replaces_value_and_keeps_trailing_comment(self):
        new = pmaconfig.set_value(CONFIG, "auth_type", "cookie")
        self.assertIn("$cfg['Servers'][$i]['auth_type'] = 'cookie';   // XAMPP default\n", new)
        self.assertIn("#$cfg['Servers'][$i]['auth_type'] = 'cookie';\n", new)
        self.assertEqual(new.count("auth_type"), 2)

    def test_round_trips_quotes_and_backslashes(self):
        for value in ("a'b", "c\\d", "\\'", "plain-_09"):
            with self.subTest(value=value):
                self.assertEqual(pmaconfig.get_value(pmaconfig.set_value(CONFIG, "controlpass", value), "controlpass"), value)

    def test_adds_missing_key_after_last_server_line(self):
        new = pmaconfig.set_value(CONFIG, "pmadb", "phpmyadmin")
        lines = new.splitlines()
        self.assertEqual(lines[lines.index("$cfg['Servers'][$i]['controlpass'] = 'it\\'s \\\\ x';") + 1],
                         "$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';")

    def test_adds_at_end_without_server_lines(self):
        self.assertEqual(pmaconfig.set_value("<?php", "pmadb", "x"), "<?php\n$cfg['Servers'][$i]['pmadb'] = 'x';\n")

    def test_rejects_line_breaks_and_nul(self):
        for bad in ("a\nb", "a\rb", "a\0b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pmaconfig.set_value(CONFIG, "controlpass", bad)
