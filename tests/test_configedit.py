import unittest
from pathlib import Path

from xampp_panel import configedit
from xampp_panel.sites import Site

HTTPD = 'ServerRoot "/opt/lampp"\n\nListen 80\n\nUser daemon\n'
SSL = "Listen 443\n<VirtualHost _default_:443>\n</VirtualHost>\n"
MYCNF = "[client]\nport=3306\n\n[mysqld]\nport=3306\nsocket=/opt/lampp/var/mysql/mysql.sock\n"


class SetBlockTest(unittest.TestCase):
    def test_add_replace_remove(self):
        text = "a\nb"
        added = configedit.set_block(text, "x", "one")
        self.assertEqual(added, "a\nb\n# BEGIN xampp-panel x\none\n# END xampp-panel x\n")
        replaced = configedit.set_block(added, "x", "two\n")
        self.assertEqual(replaced, "a\nb\n# BEGIN xampp-panel x\ntwo\n# END xampp-panel x\n")
        self.assertEqual(configedit.set_block(replaced, "x", None), "a\nb\n")

    def test_blocks_are_independent(self):
        text = configedit.set_block(configedit.set_block("", "a", "1"), "b", "2")
        text = configedit.set_block(text, "a", None)
        self.assertEqual(text, "# BEGIN xampp-panel b\n2\n# END xampp-panel b\n")
        self.assertTrue(configedit.has_block(text, "b"))
        self.assertFalse(configedit.has_block(text, "a"))


class ApacheLocalhostTest(unittest.TestCase):
    def test_round_trip(self):
        on = configedit.apache_localhost(HTTPD, True)
        self.assertIn("\nListen 127.0.0.1:80\n", on)
        self.assertNotIn("\nListen 80\n", on)
        self.assertEqual(configedit.apache_localhost(on, True), on)
        self.assertEqual(configedit.apache_localhost(on, False), HTTPD)

    def test_ssl_listen(self):
        on = configedit.apache_localhost(SSL, True)
        self.assertIn("Listen 127.0.0.1:443", on)
        self.assertEqual(configedit.apache_localhost(on, False), SSL)


class MysqlLocalhostTest(unittest.TestCase):
    def test_round_trip(self):
        on = configedit.mysql_localhost(MYCNF, True)
        self.assertIn("[mysqld]\n# xampp-panel: localhost only\nbind-address=127.0.0.1\nport=3306", on)
        self.assertEqual(configedit.mysql_localhost(on, True), on)
        self.assertEqual(configedit.mysql_localhost(on, False), MYCNF)

    def test_adds_section_when_missing(self):
        on = configedit.mysql_localhost("[client]\nport=3306\n", True)
        self.assertTrue(on.endswith("[mysqld]\n# xampp-panel: localhost only\nbind-address=127.0.0.1\n"))

    def test_disables_skip_networking_for_good(self):
        text = MYCNF + "#skip-networking\nskip-networking\n"
        on = configedit.mysql_localhost(text, True)
        self.assertNotRegex(on, r"(?m)^skip-networking")
        self.assertNotIn("xampp-panel: was", on)
        self.assertEqual(configedit.mysql_localhost(on, True), on)
        off = configedit.mysql_localhost(on, False)  # harden off (--allow-lan) keeps TCP on
        self.assertEqual(off, MYCNF + "#skip-networking\n#skip-networking\n")
        self.assertFalse(configedit.mysql_networking_off(off))

    def test_old_restore_marker_is_dropped(self):
        old = configedit.mysql_localhost(MYCNF, True) + '# xampp-panel: was "skip_networking"\n#skip-networking\n'
        for on in (True, False):
            with self.subTest(on=on):
                new = configedit.mysql_localhost(old, on)
                self.assertNotIn("xampp-panel: was", new)
                self.assertTrue(new.endswith("port=3306\nsocket=/opt/lampp/var/mysql/mysql.sock\n#skip-networking\n"))
                self.assertFalse(configedit.mysql_networking_off(new))


HASH = "$6$abcdefgh12345678$" + "A" * 86
BROKEN_FTP = """ServerName "ProFTPD"
UserPassword daemon <?
function ftp_password() {
  return crypt("x");
}
?>
DefaultRoot ~
"""


class ProftpdPasswordTest(unittest.TestCase):
    def test_detects_php_written_by_lampp_security(self):
        self.assertTrue(configedit.proftpd_password_broken(BROKEN_FTP))
        self.assertFalse(configedit.proftpd_password_broken(f"UserPassword daemon {HASH}\n"))

    def test_replaces_broken_block(self):
        new = configedit.proftpd_set_password(BROKEN_FTP, HASH)
        self.assertEqual(new, f'ServerName "ProFTPD"\nUserPassword daemon {HASH}\nDefaultRoot ~\n')

    def test_replaces_existing_password_line(self):
        self.assertEqual(configedit.proftpd_set_password("A\nUserPassword daemon old\nB\n", HASH),
                         f"A\nUserPassword daemon {HASH}\nB\n")

    def test_appends_when_missing(self):
        self.assertEqual(configedit.proftpd_set_password("A", HASH), f"A\nUserPassword daemon {HASH}\n")

    def test_rejects_anything_but_a_sha512_hash(self):
        for bad in ("plain", "$1$abc$def", HASH + "\nUser root"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                configedit.proftpd_set_password(BROKEN_FTP, bad)


class MysqlNetworkingTest(unittest.TestCase):
    def test_networking_off(self):
        self.assertTrue(configedit.mysql_networking_off("[mysqld]\nskip-networking\n"))
        self.assertFalse(configedit.mysql_networking_off("[mysqld]\n#skip-networking\n"))
        fixed = configedit.mysql_localhost("[mysqld]\nskip-networking\n", True)
        self.assertFalse(configedit.mysql_networking_off(fixed))

    def test_networking_on_only_removes_skip_networking(self):
        text = "[mysqld]\nport=3306\nskip-networking\n"
        on = configedit.mysql_networking_on(text)
        self.assertFalse(configedit.mysql_networking_off(on))
        self.assertFalse(configedit.mysql_hardened(on))  # bind-address is harden's business
        self.assertEqual(configedit.mysql_localhost(on, False), on)  # harden off does not bring it back
        self.assertEqual(configedit.mysql_networking_on(on), on)

    def test_networking_on_keeps_bind_address(self):
        hardened = configedit.mysql_localhost("[mysqld]\nport=3306\n", True) + "skip_networking\n"
        on = configedit.mysql_networking_on(hardened)
        self.assertFalse(configedit.mysql_networking_off(on))
        self.assertTrue(configedit.mysql_hardened(on))
        self.assertFalse(configedit.mysql_networking_off(configedit.mysql_localhost(on, False)))

    def test_hardened(self):
        self.assertFalse(configedit.mysql_hardened("[mysqld]\nport=3306\n"))
        self.assertTrue(configedit.mysql_hardened(configedit.mysql_localhost("[mysqld]\nport=3306\n", True)))


class RenderTest(unittest.TestCase):
    def test_vhosts_start_with_localhost_default(self):
        out = configedit.render_vhosts([Site("blog", "/home/u/Sites/blog", 1000)], Path("/opt/lampp/htdocs"))
        first, second = out.index("ServerName localhost"), out.index("ServerName blog.local")
        self.assertLess(first, second)
        self.assertIn('DocumentRoot "/opt/lampp/htdocs"', out)
        self.assertIn('<Directory "/home/u/Sites/blog">', out)
        self.assertIn("Require local", out)
        self.assertIn("Options -Indexes +FollowSymLinks", out)

    def test_hosts(self):
        self.assertIsNone(configedit.render_hosts([]))
        self.assertEqual(
            configedit.render_hosts([Site("a", "/x", 1), Site("b", "/y", 1)]),
            "127.0.0.1\ta.local\n127.0.0.1\tb.local",
        )


class MysqlInitFileTest(unittest.TestCase):
    def test_add_replace_remove(self):
        on = configedit.mysql_init_file(MYCNF, "/tmp/xampp-reset-ab_1/reset.sql")
        self.assertIn("[mysqld]\n# xampp-panel: one-time root password reset (removed right after)\n"
                      "init-file=/tmp/xampp-reset-ab_1/reset.sql\nport=3306", on)
        self.assertEqual(configedit.mysql_init_file_path(on), "/tmp/xampp-reset-ab_1/reset.sql")
        again = configedit.mysql_init_file(on, "/tmp/xampp-reset-cd/reset.sql")
        self.assertEqual(again.count("init-file="), 1)
        self.assertIn("init-file=/tmp/xampp-reset-cd/reset.sql", again)
        self.assertEqual(configedit.mysql_init_file(again, None), MYCNF)
        self.assertIsNone(configedit.mysql_init_file_path(MYCNF))

    def test_adds_section_when_missing(self):
        on = configedit.mysql_init_file("[client]\nport=3306", "/tmp/x/reset.sql")
        self.assertTrue(on.endswith("[mysqld]\n# xampp-panel: one-time root password reset (removed right after)\n"
                                    "init-file=/tmp/x/reset.sql\n"))

    def test_leaves_an_init_file_line_it_did_not_write(self):
        text = MYCNF + "init-file=/etc/mysql/mine.sql\n"
        self.assertIsNone(configedit.mysql_init_file_path(text))
        self.assertEqual(configedit.mysql_init_file(text, None), text)

    def test_refuses_paths_that_could_break_the_option_file(self):
        for bad in ("relative/reset.sql", "/tmp/a b/reset.sql", "/tmp/x\n[client]/r.sql", "/tmp/x#y/r.sql"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                configedit.mysql_init_file(MYCNF, bad)
