import tempfile
import unittest
from pathlib import Path

from xampp_panel import services
from xampp_panel.paths import Paths
from xampp_panel.services import State

HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"


def _rows(ports, addr, state="0A"):
    return "".join(
        f"   {i}: {addr}:{p:04X} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000     0        0 {1000 + i} 1 0 100 0 0 10 0\n"
        for i, p in enumerate(ports)
    )


def make_proc(root: Path, procs=None, tcp=(), tcp6=(), established=()):
    for pid, (comm, cmdline) in (procs or {}).items():
        d = root / str(pid)
        d.mkdir(parents=True)
        (d / "comm").write_text(comm + "\n")
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in cmdline.split(" ")) + b"\0")
    (root / "net").mkdir(parents=True, exist_ok=True)
    (root / "net/tcp").write_text(HEADER + _rows(tcp, "0100007F") + _rows(established, "0100007F", state="01"))
    (root / "net/tcp6").write_text(HEADER + _rows(tcp6, "00000000000000000000000000000000"))


class ServicesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self._tmp.name) / "proc"
        self.proc.mkdir()
        self.paths = Paths(proc=self.proc)

    def tearDown(self):
        self._tmp.cleanup()


class ListeningPortsTest(ServicesCase):
    def test_reads_listening_ports_from_tcp_and_tcp6_only(self):
        make_proc(self.proc, tcp=(80, 3306), tcp6=(21,), established=(8080,))
        self.assertEqual(services.listening_ports(self.paths), {80, 3306, 21})

    def test_missing_proc_files_give_empty_set(self):
        self.assertEqual(services.listening_ports(Paths(proc=self.proc / "missing")), set())


class RunningServicesTest(ServicesCase):
    def test_detects_xampp_processes_and_ignores_system_ones(self):
        make_proc(self.proc, procs={
            100: ("httpd", "/opt/lampp/bin/httpd -k start -E /opt/lampp/logs/error_log"),
            200: ("mysqld", "/usr/sbin/mysqld --basedir=/usr"),
            300: ("proftpd", "proftpd: (accepting connections)"),
            400: ("bash", "/bin/bash"),
        })
        self.assertEqual(services.running_services(self.paths), {"apache", "ftp"})

    def test_detects_processes_whose_comm_is_a_truncated_path(self):
        # Seen on Zorin: XAMPP's httpd reports comm "/opt/lampp/bin/" (15-char cut of its path).
        make_proc(self.proc, procs={
            100: ("/opt/lampp/bin/", "/opt/lampp/bin/httpd -k start -E /opt/lampp/logs/error_log"),
            200: ("/opt/lampp/sbin", "/opt/lampp/sbin/mysqld --basedir=/opt/lampp"),
        })
        self.assertEqual(services.running_services(self.paths), {"apache", "mysql"})

    def test_detects_xampp_mysql(self):
        make_proc(self.proc, procs={500: ("mysqld", "/opt/lampp/sbin/mysqld --basedir=/opt/lampp")})
        self.assertEqual(services.running_services(self.paths), {"mysql"})

    def test_missing_proc_dir_gives_empty_set(self):
        self.assertEqual(services.running_services(Paths(proc=self.proc / "missing")), set())


class SnapshotTest(ServicesCase):
    def test_states(self):
        make_proc(
            self.proc,
            procs={
                100: ("httpd", "/opt/lampp/bin/httpd -k start"),
                200: ("mysqld", "/opt/lampp/sbin/mysqld"),
            },
            tcp=(80, 21),
        )
        self.assertEqual(services.snapshot(self.paths), {
            "apache": State.RUNNING,    # process + port
            "mysql": State.STARTING,    # process, port not open yet
            "ftp": State.CONFLICT,      # port 21 used by something that isn't XAMPP
        })

    def test_all_stopped(self):
        make_proc(self.proc)
        self.assertEqual(set(services.snapshot(self.paths).values()), {State.STOPPED})


class LogPathTest(unittest.TestCase):
    def test_log_paths(self):
        p = Paths()
        self.assertEqual(services.log_path("apache", p), Path("/opt/lampp/logs/error_log"))
        self.assertEqual(services.log_path("mysql", p, hostname="zbook"), Path("/opt/lampp/var/mysql/zbook.err"))
        self.assertIsNone(services.log_path("ftp", p))
