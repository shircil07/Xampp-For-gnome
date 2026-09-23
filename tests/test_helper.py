import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from xampp_panel import configedit, helper, sites
from xampp_panel.paths import Paths

HTTPD = 'ServerRoot "/opt/lampp"\nListen 80\nUser daemon\n'
SSL = "Listen 443\n"
MYCNF = "[client]\nport=3306\n\n[mysqld]\nport=3306\n"
HOSTS = "127.0.0.1\tlocalhost\n"


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.fail = set()

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        name = Path(argv[0]).name
        code = 1 if name in self.fail else 0
        return subprocess.CompletedProcess(argv, code, stdout=f"{name} ok\n", stderr=f"{name} failed\n" if code else "")

    def argvs(self):
        return [argv for argv, _ in self.calls]


class HelperCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(os.path.realpath(self._tmp.name))
        self.root = root
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc")
        (root / "lampp/etc/extra").mkdir(parents=True)
        (root / "lampp/htdocs").mkdir()
        (root / "lampp/logs").mkdir()
        (root / "proc").mkdir()
        (root / "app/state").mkdir(parents=True)
        self.paths.httpd_conf.write_text(HTTPD)
        self.paths.ssl_conf.write_text(SSL)
        self.paths.my_cnf.write_text(MYCNF)
        self.paths.hosts.write_text(HOSTS)
        self.home = root / "home"
        self.site_dir = self.home / "Sites/blog"
        self.site_dir.mkdir(parents=True)
        self.uid = os.getuid()
        self.pw = SimpleNamespace(pw_uid=self.uid, pw_gid=os.getgid(), pw_dir=str(self.home))
        self.run = FakeRunner()
        self.out = io.StringIO()

    def tearDown(self):
        self._tmp.cleanup()

    def helper(self, env=None):
        env = {"PKEXEC_UID": str(self.uid)} if env is None else env
        return helper.Helper(paths=self.paths, run=self.run, env=env, getpw=lambda uid: self.pw, out=self.out)

    def call(self, *argv, env=None):
        return helper.main(list(argv), helper=self.helper(env))


class DispatchTest(HelperCase):
    def test_unknown_commands_are_rejected(self):
        for argv in (["rm", "-rf", "/"], [], ["start"], ["start", "nginx"], ["lean", "maybe"], ["log", "ftp"]):
            self.assertEqual(self.call(*argv), 2, argv)
        self.assertEqual(self.run.calls, [])

    def test_start_all_starts_apache_and_mysql_only(self):
        self.assertEqual(self.call("start", "all"), 0)
        lampp = str(self.paths.lampp_script)
        self.assertEqual(self.run.argvs(), [[lampp, "startapache"], [lampp, "startmysql"]])

    def test_stop_all(self):
        self.assertEqual(self.call("stop", "all"), 0)
        self.assertEqual(self.run.argvs(), [[str(self.paths.lampp_script), "stop"]])

    def test_subprocesses_get_a_clean_environment_and_no_shell(self):
        self.call("start", "apache")
        kwargs = self.run.calls[0][1]
        self.assertEqual(kwargs["env"], helper.SAFE_ENV)
        self.assertNotIn("shell", kwargs)

    def test_failures_return_1(self):
        self.run.fail.add("lampp")
        self.assertEqual(self.call("start", "mysql"), 1)


class HardenAndLeanTest(HelperCase):
    def test_harden_round_trip_with_backup(self):
        self.assertEqual(self.call("harden", "on"), 0)
        self.assertIn("Listen 127.0.0.1:80", self.paths.httpd_conf.read_text())
        self.assertIn("Listen 127.0.0.1:443", self.paths.ssl_conf.read_text())
        self.assertIn("bind-address=127.0.0.1", self.paths.my_cnf.read_text())
        self.assertTrue((self.paths.lampp / "etc/httpd.conf.xampp-panel.bak").exists())
        self.assertEqual(self.call("harden", "off"), 0)
        self.assertEqual(self.paths.httpd_conf.read_text(), HTTPD)
        self.assertEqual(self.paths.ssl_conf.read_text(), SSL)
        self.assertEqual(self.paths.my_cnf.read_text(), MYCNF)

    def test_lean_round_trip(self):
        self.assertEqual(self.call("lean", "on"), 0)
        self.assertEqual(self.paths.lean_httpd.read_text(), configedit.LEAN_HTTPD)
        self.assertIn(f"Include {self.paths.lean_httpd}", self.paths.httpd_conf.read_text())
        self.assertIn(f"!include {self.paths.lean_mysql}", self.paths.my_cnf.read_text())
        self.assertEqual(self.call("lean", "off"), 0)
        self.assertEqual(self.paths.httpd_conf.read_text(), HTTPD)
        self.assertEqual(self.paths.my_cnf.read_text(), MYCNF)
        self.assertFalse(self.paths.lean_httpd.exists())


class SitesTest(HelperCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.call("integrate", "on"), 0)
        self.run.calls.clear()

    def test_integrate_on_adds_include_and_default_vhost(self):
        self.assertIn(f"Include {self.paths.vhosts_conf}", self.paths.httpd_conf.read_text())
        self.assertIn("ServerName localhost", self.paths.vhosts_conf.read_text())

    def test_site_add(self):
        self.assertEqual(self.call("site-add", "blog", str(self.site_dir)), 0)
        self.assertIn("ServerName blog.local", self.paths.vhosts_conf.read_text())
        self.assertIn("127.0.0.1\tblog.local", self.paths.hosts.read_text())
        self.assertEqual(sites.load(self.paths.state_file), [sites.Site("blog", str(self.site_dir), self.uid)])
        self.assertIn([str(self.paths.apachectl), "-t"], self.run.argvs())
        setfacl = [(argv, kw) for argv, kw in self.run.calls if argv[0] == "setfacl"]
        self.assertEqual([a[-1] for a, _ in setfacl], [str(self.home), str(self.home / "Sites"), str(self.site_dir)])
        for _, kw in setfacl:
            self.assertEqual(kw["user"], self.uid)   # ACLs are set as the user, never as root
        self.assertEqual(self.out.getvalue().strip(), "http://blog.local/")

    def test_site_add_validation(self):
        outside = self.root / "elsewhere"
        outside.mkdir()
        link = self.home / "Sites/link"
        link.symlink_to(outside)
        weird = self.home / "Sites/we$ird"
        weird.mkdir()
        cases = [
            ("Bad_Name", self.site_dir),
            ("ok", outside),
            ("ok", link),
            ("ok", weird),
            ("ok", self.home),
            ("ok", self.home / "Sites/missing"),
        ]
        for name, folder in cases:
            self.assertEqual(self.call("site-add", name, str(folder)), 2, (name, folder))
        self.assertEqual(sites.load(self.paths.state_file), [])

    def test_site_add_requires_pkexec_uid(self):
        self.assertEqual(self.call("site-add", "blog", str(self.site_dir), env={}), 2)

    def test_duplicate_and_nested_sites_rejected(self):
        self.assertEqual(self.call("site-add", "blog", str(self.site_dir)), 0)
        inner = self.site_dir / "inner"
        inner.mkdir()
        self.assertEqual(self.call("site-add", "blog", str(inner)), 2)
        self.assertEqual(self.call("site-add", "inner", str(inner)), 2)

    def test_config_test_failure_rolls_back(self):
        before = self.paths.vhosts_conf.read_text()
        self.run.fail.add("apachectl")
        self.assertEqual(self.call("site-add", "blog", str(self.site_dir)), 1)
        self.assertEqual(self.paths.vhosts_conf.read_text(), before)
        self.assertEqual(self.paths.hosts.read_text(), HOSTS)
        self.assertEqual(sites.load(self.paths.state_file), [])
        self.assertTrue(any(a[0] == "setfacl" and "-x" in a for a in self.run.argvs()))

    def test_site_remove(self):
        self.call("site-add", "blog", str(self.site_dir))
        self.run.calls.clear()
        self.assertEqual(self.call("site-remove", "blog"), 0)
        self.assertNotIn("blog.local", self.paths.vhosts_conf.read_text())
        self.assertEqual(self.paths.hosts.read_text(), HOSTS)
        self.assertEqual(sites.load(self.paths.state_file), [])
        self.assertTrue(any(a[0] == "setfacl" and "-x" in a for a in self.run.argvs()))

    def test_cannot_remove_other_users_site(self):
        sites.save(self.paths.state_file, [sites.Site("theirs", "/home/other/x", self.uid + 1)])
        self.assertEqual(self.call("site-remove", "theirs"), 2)

    def test_integrate_off_removes_everything(self):
        self.call("site-add", "blog", str(self.site_dir))
        self.assertEqual(self.call("integrate", "off"), 0)
        self.assertEqual(self.paths.httpd_conf.read_text(), HTTPD)
        self.assertEqual(self.paths.hosts.read_text(), HOSTS)
        self.assertFalse(self.paths.vhosts_conf.exists())
        self.assertFalse(self.paths.state_file.exists())


class LogTest(HelperCase):
    def test_log_prints_tail(self):
        (self.paths.lampp / "logs/error_log").write_text("boom\n")
        self.assertEqual(self.call("log", "apache"), 0)
        self.assertEqual(self.out.getvalue(), "boom\n")


class TraversalDirsTest(unittest.TestCase):
    def test_dirs_between_home_and_site(self):
        self.assertEqual(
            helper.traversal_dirs(Path("/home/u"), Path("/home/u/Sites/blog")),
            [Path("/home/u"), Path("/home/u/Sites")],
        )
