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

    def test_disables_skip_networking(self):
        text = MYCNF + "#skip-networking\nskip-networking\n"
        on = configedit.mysql_localhost(text, True)
        self.assertNotRegex(on, r"(?m)^skip-networking")
        self.assertIn('# xampp-panel: was "skip-networking"\n#skip-networking\n', on)
        self.assertIn("#skip-networking\n# xampp-panel", on)  # XAMPP's own commented line is untouched
        self.assertEqual(configedit.mysql_localhost(on, True), on)
        self.assertEqual(configedit.mysql_localhost(on, False), text)


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
