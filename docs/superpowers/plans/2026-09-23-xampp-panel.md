# XAMPP Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-command installer plus a native GNOME (GTK4/libadwaita) control panel, optional tray icon and polkit-guarded root helper that make XAMPP 8.2.12 secure, lightweight and pleasant on Zorin OS.

**Architecture:** Pure-Python, stdlib-only logic modules (`services`, `configedit`, `sites`, `fsutil`, `settings`, `privileged`) that are fully unit-tested. There's a root helper (`helper.py`) with a whitelisted command set, run through `pkexec`. Two thin UIs sit on top: a GTK4 panel and a GTK3 AppIndicator tray, each in its own process. Bash `setup.sh`/`uninstall.sh` install and reverse everything.

**Tech Stack:** Python ≥ 3.10 (stdlib only), PyGObject, GTK 4 + libadwaita ≥ 1.1, GTK 3 + AyatanaAppIndicator3, polkit/pkexec, bash, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-23-xampp-panel-design.md` (read the "Plan-time refinements" section; it overrides earlier sections).

## Global Constraints

- Python ≥ 3.10, **stdlib only** at runtime and in tests (no pip). Tests: `unittest`.
- Minimum desktop: Zorin OS 17 / Ubuntu 22.04: GTK 4.6, libadwaita 1.1, GLib 2.72. Any API newer than that (`Adw.Banner`, `Gtk.FileDialog`, `Gio.ApplicationFlags.DEFAULT_FLAGS`, `Adw.ViewStack.add_titled_with_icon`, `Adw.MessageDialog`, `Adw.EntryRow`, `Adw.SwitchRow`) must be guarded with `hasattr`/`getattr` or avoided.
- App ID `io.github.shiron.XamppPanel`; polkit action `io.github.shiron.xampppanel.helper`; tray app ID `io.github.shiron.XamppPanel.Tray`.
- Install paths: code `/opt/xampp-panel/lib/xampp_panel/`, launchers `/opt/xampp-panel/bin/{xampp-panel,xampp-helper}`, state `/opt/xampp-panel/state/sites.json`, XAMPP in `/opt/lampp`.
- The helper never uses `shell=True`, always passes `env=SAFE_ENV`, and only accepts the commands in `USAGE`.
- Marker comments in edited config files: `# BEGIN xampp-panel <id>` / `# END xampp-panel <id>`, and `# xampp-panel: …` for single-line edits.
- No network access, no telemetry, nothing runs at login or boot.
- Run all tests from the repo root with: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- Commit after every task, ending the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Map

| File | Responsibility |
|---|---|
| `src/xampp_panel/__init__.py` | Package marker + version |
| `src/xampp_panel/paths.py` | `Paths` dataclass: every filesystem location, overridable in tests |
| `src/xampp_panel/fsutil.py` | `atomic_write`, `backup_once`, `tail` |
| `src/xampp_panel/services.py` | Service metadata, `/proc`-based status, log paths |
| `src/xampp_panel/configedit.py` | Pure text transforms for httpd.conf / my.cnf / proftpd.conf / hosts / vhosts |
| `src/xampp_panel/sites.py` | `Site` model, name validation, state JSON load/save |
| `src/xampp_panel/helper.py` | Root helper: validation + whitelisted commands |
| `src/xampp_panel/privileged.py` | Builds `pkexec` argv, interprets exit codes |
| `src/xampp_panel/settings.py` | Per-user JSON settings |
| `src/xampp_panel/watch.py` | Gio inotify watcher + pausable fallback timer |
| `src/xampp_panel/window.py` | GTK4 main window, dialogs |
| `src/xampp_panel/app.py` | `Adw.Application`, app actions |
| `src/xampp_panel/tray.py` | GTK3 AppIndicator tray process |
| `src/xampp_panel/main.py` | Entry point: `--tray` → tray, else panel |
| `bin/xampp-panel`, `bin/xampp-helper` | Installed launchers (`python3 -I`) |
| `data/…` | `.desktop`, polkit policy, SVG icons |
| `setup.sh`, `uninstall.sh` | Install / reverse |
| `tests/test_*.py` | Unit tests |

---

### Task 1: Scaffold, paths and fsutil

**Files:**
- Create: `.gitignore`, `src/xampp_panel/__init__.py`, `src/xampp_panel/paths.py`, `src/xampp_panel/fsutil.py`
- Test: `tests/test_fsutil.py`, `tests/test_paths.py`

**Interfaces:**
- Produces: `Paths(lampp: Path, app: Path, hosts: Path, proc: Path)` with properties `lampp_script, httpd_conf, ssl_conf, my_cnf, proftpd_conf, vhosts_conf, lean_httpd, lean_mysql, htdocs, apachectl, mysql_client, helper, launcher, state_file, watch_dirs`; `DEFAULT = Paths()`.
- Produces: `fsutil.atomic_write(path, text, mode=None) -> None`, `fsutil.backup_once(path) -> Path`, `fsutil.tail(path, max_bytes=65536) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_paths.py`:
```python
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
```

`tests/test_fsutil.py`:
```python
import os
import tempfile
import unittest
from pathlib import Path

from xampp_panel import fsutil


class FsutilCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class AtomicWriteTest(FsutilCase):
    def test_creates_file_with_default_mode(self):
        p = self.dir / "a.txt"
        fsutil.atomic_write(p, "hi\n")
        self.assertEqual(p.read_text(), "hi\n")
        self.assertEqual(p.stat().st_mode & 0o777, 0o644)

    def test_preserves_existing_mode(self):
        p = self.dir / "a.txt"
        p.write_text("old")
        p.chmod(0o600)
        fsutil.atomic_write(p, "new")
        self.assertEqual(p.read_text(), "new")
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_explicit_mode_wins(self):
        p = self.dir / "a.txt"
        fsutil.atomic_write(p, "x", mode=0o600)
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_leaves_no_temp_files(self):
        fsutil.atomic_write(self.dir / "a.txt", "x")
        self.assertEqual(os.listdir(self.dir), ["a.txt"])


class BackupOnceTest(FsutilCase):
    def test_backs_up_only_the_first_time(self):
        p = self.dir / "httpd.conf"
        p.write_text("original")
        bak = fsutil.backup_once(p)
        p.write_text("changed")
        fsutil.backup_once(p)
        self.assertEqual(bak, self.dir / "httpd.conf.xampp-panel.bak")
        self.assertEqual(bak.read_text(), "original")

    def test_missing_file_is_ignored(self):
        bak = fsutil.backup_once(self.dir / "nope")
        self.assertFalse(bak.exists())


class TailTest(FsutilCase):
    def test_short_file_is_returned_whole(self):
        p = self.dir / "log"
        p.write_text("a\nb\n")
        self.assertEqual(fsutil.tail(p), "a\nb\n")

    def test_long_file_keeps_last_whole_lines(self):
        p = self.dir / "log"
        p.write_text("".join(f"line {i}\n" for i in range(1000)))
        out = fsutil.tail(p, max_bytes=100)
        self.assertTrue(out.endswith("line 999\n"))
        self.assertTrue(out.startswith("line "))
        self.assertLessEqual(len(out), 100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'xampp_panel'`

- [ ] **Step 3: Write the implementation**

`.gitignore`:
```
__pycache__/
*.pyc
```

`src/xampp_panel/__init__.py`:
```python
"""XAMPP Panel: a GNOME control panel for XAMPP on Linux."""

__version__ = "0.1.0"
```

`src/xampp_panel/paths.py`:
```python
"""Every filesystem location the app touches, in one overridable place."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    lampp: Path = Path("/opt/lampp")
    app: Path = Path("/opt/xampp-panel")
    hosts: Path = Path("/etc/hosts")
    proc: Path = Path("/proc")

    @property
    def lampp_script(self) -> Path:
        return self.lampp / "lampp"

    @property
    def httpd_conf(self) -> Path:
        return self.lampp / "etc/httpd.conf"

    @property
    def ssl_conf(self) -> Path:
        return self.lampp / "etc/extra/httpd-ssl.conf"

    @property
    def my_cnf(self) -> Path:
        return self.lampp / "etc/my.cnf"

    @property
    def proftpd_conf(self) -> Path:
        return self.lampp / "etc/proftpd.conf"

    @property
    def vhosts_conf(self) -> Path:
        return self.lampp / "etc/extra/xampp-panel-vhosts.conf"

    @property
    def lean_httpd(self) -> Path:
        return self.lampp / "etc/extra/xampp-panel-lean.conf"

    @property
    def lean_mysql(self) -> Path:
        return self.lampp / "etc/xampp-panel-lean.cnf"

    @property
    def htdocs(self) -> Path:
        return self.lampp / "htdocs"

    @property
    def apachectl(self) -> Path:
        return self.lampp / "bin/apachectl"

    @property
    def mysql_client(self) -> Path:
        return self.lampp / "bin/mysql"

    @property
    def helper(self) -> Path:
        return self.app / "bin/xampp-helper"

    @property
    def launcher(self) -> Path:
        return self.app / "bin/xampp-panel"

    @property
    def state_file(self) -> Path:
        return self.app / "state/sites.json"

    @property
    def watch_dirs(self) -> tuple[Path, ...]:
        """Directories whose PID/socket files change when services start/stop."""
        return (self.lampp / "logs", self.lampp / "var", self.lampp / "var/mysql")


DEFAULT = Paths()
```

`src/xampp_panel/fsutil.py`:
```python
"""Small, safe file helpers."""

import os
import shutil
import tempfile
from pathlib import Path


def atomic_write(path, text: str, mode: int | None = None) -> None:
    """Replace `path` with `text` atomically (temp file + rename in the same dir).

    Keeps the existing file's permission bits unless `mode` is given.
    """
    path = Path(path)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o7777
        except FileNotFoundError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def backup_once(path) -> Path:
    """Copy `path` to `<path>.xampp-panel.bak` unless that backup already exists."""
    path = Path(path)
    bak = path.with_name(path.name + ".xampp-panel.bak")
    if path.exists() and not bak.exists():
        shutil.copy2(path, bak)
    return bak


def tail(path, max_bytes: int = 65536) -> str:
    """Return at most the last `max_bytes` of a text file, starting at a line boundary."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes))
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = text.partition("\n")[2]
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add .gitignore src tests
git commit -m "feat: add paths and safe file helpers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Service status detection

**Files:**
- Create: `src/xampp_panel/services.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `Paths`, `DEFAULT` (Task 1).
- Produces: `State` enum (`STOPPED, STARTING, RUNNING, CONFLICT`); `Service(key, title, description, port, process_names)`; `SERVICES` tuple (apache, mysql, ftp); `BY_KEY: dict[str, Service]`; `listening_ports(paths) -> set[int]`; `running_services(paths) -> set[str]`; `snapshot(paths) -> dict[str, State]`; `log_path(key, paths, hostname=None) -> Path | None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_services.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_services -v`
Expected: ERROR `cannot import name 'services'`

- [ ] **Step 3: Write the implementation**

`src/xampp_panel/services.py`:
```python
"""Which XAMPP services are running, read cheaply from /proc (no subprocesses, no root)."""

import os
import socket
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .paths import DEFAULT, Paths


class State(Enum):
    STOPPED = "stopped"
    STARTING = "starting"   # XAMPP process exists, port not listening yet
    RUNNING = "running"
    CONFLICT = "conflict"   # port is taken by a program that is not XAMPP


@dataclass(frozen=True)
class Service:
    key: str
    title: str
    description: str
    port: int
    process_names: tuple[str, ...]


SERVICES = (
    Service("apache", "Apache", "Web server", 80, ("httpd",)),
    Service("mysql", "MySQL", "Database (MariaDB)", 3306, ("mysqld", "mariadbd")),
    Service("ftp", "ProFTPD", "FTP server", 21, ("proftpd",)),
)
BY_KEY = {s.key: s for s in SERVICES}
_BY_PROCESS = {name: s for s in SERVICES for name in s.process_names}
_LISTEN = "0A"


def listening_ports(paths: Paths = DEFAULT) -> set[int]:
    ports = set()
    for name in ("tcp", "tcp6"):
        try:
            lines = (paths.proc / "net" / name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[3] == _LISTEN:
                ports.add(int(parts[1].rsplit(":", 1)[1], 16))
    return ports


def running_services(paths: Paths = DEFAULT) -> set[str]:
    """Keys of services with a live XAMPP process.

    ProFTPD rewrites its command line ("proftpd: (accepting connections)"), so
    it is matched on process name alone; the others must mention /opt/lampp.
    """
    found: set[str] = set()
    marker = str(paths.lampp).encode()
    try:
        entries = os.scandir(paths.proc)
    except OSError:
        return found
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            base = Path(entry.path)
            try:
                svc = _BY_PROCESS.get((base / "comm").read_text().strip())
                if svc is None or svc.key in found:
                    continue
                if svc.key != "ftp" and marker not in (base / "cmdline").read_bytes():
                    continue
            except OSError:
                continue  # process exited while we looked
            found.add(svc.key)
    return found


def snapshot(paths: Paths = DEFAULT) -> dict[str, State]:
    running = running_services(paths)
    ports = listening_ports(paths)
    result = {}
    for svc in SERVICES:
        if svc.key in running:
            result[svc.key] = State.RUNNING if svc.port in ports else State.STARTING
        else:
            result[svc.key] = State.CONFLICT if svc.port in ports else State.STOPPED
    return result


def log_path(key: str, paths: Paths = DEFAULT, hostname: str | None = None) -> Path | None:
    if key == "apache":
        return paths.lampp / "logs/error_log"
    if key == "mysql":
        return paths.lampp / "var/mysql" / f"{hostname or socket.gethostname()}.err"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/services.py tests/test_services.py
git commit -m "feat: detect XAMPP service state from /proc

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Config transforms and site model

**Files:**
- Create: `src/xampp_panel/configedit.py`, `src/xampp_panel/sites.py`
- Test: `tests/test_configedit.py`, `tests/test_sites.py`

**Interfaces:**
- Consumes: `fsutil.atomic_write` (Task 1).
- Produces (`configedit`): `set_block(text, block_id, body: str | None) -> str`, `has_block(text, block_id) -> bool`, `apache_localhost(text, on: bool) -> str`, `mysql_localhost(text, on: bool) -> str`, constants `PROFTPD_LOCAL`, `LEAN_HTTPD`, `LEAN_MYSQL`, `render_vhosts(sites, htdocs) -> str`, `render_hosts(sites) -> str | None`.
- Produces (`sites`): `Site(name: str, path: str, uid: int)` with `.url`; `UNSAFE_PATH_CHARS: frozenset[str]`; `validate_name(name) -> bool`; `load(state_file) -> list[Site]`; `save(state_file, sites) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sites.py`:
```python
import tempfile
import unittest
from pathlib import Path

from xampp_panel import sites
from xampp_panel.sites import Site


class ValidateNameTest(unittest.TestCase):
    def test_accepts_simple_names(self):
        for name in ("blog", "my-shop", "a", "site2"):
            self.assertTrue(sites.validate_name(name), name)

    def test_rejects_bad_names(self):
        for name in ("", "Blog", "my_shop", "-x", "x-", "a.b", "a b", "x" * 64, "../etc", "a\n"):
            self.assertFalse(sites.validate_name(name), repr(name))


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "sites.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_means_no_sites(self):
        self.assertEqual(sites.load(self.file), [])

    def test_round_trip_and_world_readable(self):
        data = [Site("blog", "/home/u/Sites/blog", 1000)]
        sites.save(self.file, data)
        self.assertEqual(sites.load(self.file), data)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)

    def test_url(self):
        self.assertEqual(Site("blog", "/x", 1).url, "http://blog.local/")
```

`tests/test_configedit.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_sites tests.test_configedit -v`
Expected: ERROR `cannot import name 'sites'`

- [ ] **Step 3: Write the implementation**

`src/xampp_panel/sites.py`:
```python
"""Per-project sites (name.local → folder) and their root-owned state file."""

import json
import re
from dataclasses import asdict, dataclass

from . import fsutil

_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
# Characters that could break out of an Apache config string or trigger ${VAR} expansion.
UNSAFE_PATH_CHARS = frozenset('"$\\\n\r\t')


@dataclass(frozen=True)
class Site:
    name: str
    path: str
    uid: int

    @property
    def url(self) -> str:
        return f"http://{self.name}.local/"


def validate_name(name: str) -> bool:
    return bool(_NAME.fullmatch(name))


def load(state_file) -> list[Site]:
    try:
        with open(state_file, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return []
    return [Site(str(d["name"]), str(d["path"]), int(d["uid"])) for d in raw]


def save(state_file, sites: list[Site]) -> None:
    fsutil.atomic_write(state_file, json.dumps([asdict(s) for s in sites], indent=2) + "\n", mode=0o644)
```

`src/xampp_panel/configedit.py`:
```python
"""Pure, reversible text transforms for XAMPP and system config files."""

import re
from pathlib import Path

_BEGIN = "# BEGIN xampp-panel {}"
_END = "# END xampp-panel {}"


def set_block(text: str, block_id: str, body: str | None) -> str:
    """Remove the marked block `block_id`, then (if `body`) append it again at the end."""
    begin, end = _BEGIN.format(block_id), _END.format(block_id)
    pattern = re.compile(rf"(?ms)^{re.escape(begin)}\n.*?^{re.escape(end)}\n?")
    text = pattern.sub("", text)
    if body is None:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}{begin}\n{body.rstrip(chr(10))}\n{end}\n"


def has_block(text: str, block_id: str) -> bool:
    return _BEGIN.format(block_id) in text


# Apache does not allow trailing comments, so the original value goes on a comment line above.
_LISTEN = re.compile(r"(?m)^Listen[ \t]+(\d+)[ \t]*$")
_LOCAL_LISTEN = re.compile(r'(?m)^# xampp-panel: was "Listen (\d+)"\nListen 127\.0\.0\.1:\d+[ \t]*$')


def apache_localhost(text: str, on: bool) -> str:
    if on:
        return _LISTEN.sub(lambda m: f'# xampp-panel: was "Listen {m[1]}"\nListen 127.0.0.1:{m[1]}', text)
    return _LOCAL_LISTEN.sub(lambda m: f"Listen {m[1]}", text)


_MYSQLD = re.compile(r"(?m)^\[mysqld\][ \t]*\n")
_BIND = "# xampp-panel: localhost only\nbind-address=127.0.0.1\n"


def mysql_localhost(text: str, on: bool) -> str:
    text = text.replace(_BIND, "")
    if not on:
        return text
    new, count = _MYSQLD.subn(lambda m: m[0] + _BIND, text, count=1)
    if count:
        return new
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}[mysqld]\n{_BIND}"


PROFTPD_LOCAL = "DefaultAddress 127.0.0.1\nSocketBindTight on"

LEAN_HTTPD = """\
# XAMPP Panel lean mode: few idle processes, plenty for local development.
<IfModule mpm_prefork_module>
    StartServers 2
    MinSpareServers 1
    MaxSpareServers 3
    MaxRequestWorkers 20
    MaxConnectionsPerChild 1000
</IfModule>
"""

LEAN_MYSQL = """\
# XAMPP Panel lean mode: smaller buffers for a single developer.
[mysqld]
innodb_buffer_pool_size=64M
performance_schema=OFF
max_connections=30
"""

_VHOST = """
<VirtualHost *:80>
    ServerName {name}.local
    DocumentRoot "{path}"
    <Directory "{path}">
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require local
    </Directory>
</VirtualHost>
"""


def render_vhosts(sites, htdocs: Path) -> str:
    header = (
        "# Managed by XAMPP Panel. Changes here are overwritten.\n"
        "# The first vhost keeps http://localhost (and phpMyAdmin) working.\n"
        "<VirtualHost *:80>\n"
        "    ServerName localhost\n"
        f'    DocumentRoot "{htdocs}"\n'
        "</VirtualHost>\n"
    )
    return header + "".join(_VHOST.format(name=s.name, path=s.path) for s in sites)


def render_hosts(sites) -> str | None:
    return "\n".join(f"127.0.0.1\t{s.name}.local" for s in sites) or None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/configedit.py src/xampp_panel/sites.py tests/test_configedit.py tests/test_sites.py
git commit -m "feat: reversible config transforms and site model

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Root helper

**Files:**
- Create: `src/xampp_panel/helper.py`, `bin/xampp-helper`
- Test: `tests/test_helper.py`

**Interfaces:**
- Consumes: `Paths`, `fsutil`, `services.running_services`, `services.log_path`, `configedit.*`, `sites.*`.
- Produces: `helper.main(argv=None, helper=None) -> int` (0 ok, 1 failure, 2 usage/validation); `Helper(paths, run, env, getpw, out)` with `dispatch(argv)`; `SAFE_ENV`; `USAGE`; `validate_site_dir(raw, home, uid) -> Path`; `traversal_dirs(home, site) -> list[Path]`.
- Command-line contract (used by the panel, tray and setup): `start|stop apache|mysql|ftp|all`, `site-add NAME DIR`, `site-remove NAME`, `log apache|mysql`, `lean on|off`, `harden on|off`, `integrate on|off`.

- [ ] **Step 1: Write the failing tests**

`tests/test_helper.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_helper -v`
Expected: ERROR `cannot import name 'helper'`

- [ ] **Step 3: Write the implementation**

`src/xampp_panel/helper.py`:
```python
"""Privileged helper. Runs as root via pkexec (or from setup.sh / uninstall.sh).

Only the commands in USAGE are accepted. Arguments are validated, subprocesses
get a fixed environment and never go through a shell, and user folders are
only touched with the invoking user's own privileges.
"""

import os
import pwd
import subprocess
import sys
from pathlib import Path

from . import configedit, fsutil, services, sites
from .paths import DEFAULT, Paths

SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}
APACHE_USER = "daemon"  # XAMPP's httpd.conf runs Apache as User/Group daemon
USAGE = """usage: xampp-helper COMMAND
  start|stop apache|mysql|ftp|all
  site-add NAME DIR
  site-remove NAME
  log apache|mysql
  lean on|off
  harden on|off
  integrate on|off"""

_START = {"apache": ["startapache"], "mysql": ["startmysql"], "ftp": ["startftp"],
          "all": ["startapache", "startmysql"]}
_STOP = {"apache": ["stopapache"], "mysql": ["stopmysql"], "ftp": ["stopftp"], "all": ["stop"]}


class UsageError(Exception):
    """Bad input: exit code 2."""


class HelperFailure(Exception):
    """A step failed: exit code 1."""


def validate_site_dir(raw: str, home: str, uid: int) -> Path:
    if not raw.startswith("/") or any(c in sites.UNSAFE_PATH_CHARS for c in raw):
        raise UsageError("the folder path contains characters that are not supported")
    real = os.path.realpath(raw)
    if real != os.path.normpath(raw):
        raise UsageError("the folder must not be, or be inside, a symbolic link")
    home = os.path.realpath(home)
    if real == home or os.path.commonpath([home, real]) != home:
        raise UsageError("the folder must be inside your home folder")
    if not os.path.isdir(real):
        raise UsageError("the folder does not exist")
    if os.stat(real).st_uid != uid:
        raise UsageError("the folder must be owned by you")
    return Path(real)


def traversal_dirs(home: Path, site: Path) -> list[Path]:
    """Directories Apache must be able to enter (x) to reach `site`."""
    dirs, current = [home], home
    for part in site.relative_to(home).parts[:-1]:
        current = current / part
        dirs.append(current)
    return dirs


def _overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


class Helper:
    def __init__(self, paths: Paths = DEFAULT, run=subprocess.run, env=None, getpw=pwd.getpwuid, out=sys.stdout):
        self.paths = paths
        self.run = run
        self.env = os.environ if env is None else env
        self.getpw = getpw
        self.out = out

    # -- plumbing ---------------------------------------------------------
    def _run(self, argv, **kwargs) -> str:
        argv = [str(a) for a in argv]
        proc = self.run(argv, env=SAFE_ENV, capture_output=True, text=True, **kwargs)
        if proc.returncode != 0:
            raise HelperFailure((proc.stderr or proc.stdout).strip() or f"{argv[0]} failed")
        return proc.stdout

    def _run_as(self, uid: int, argv) -> str:
        pw = self.getpw(uid)
        return self._run(argv, user=pw.pw_uid, group=pw.pw_gid, extra_groups=[])

    def _edit(self, path: Path, transform) -> None:
        text = path.read_text()
        new = transform(text)
        if new != text:
            fsutil.backup_once(path)
            fsutil.atomic_write(path, new)

    def _caller(self):
        raw = self.env.get("PKEXEC_UID", "")
        if not raw.isdigit():
            raise UsageError("site commands must be run from the XAMPP Panel (via pkexec)")
        return self.getpw(int(raw))

    # -- commands ---------------------------------------------------------
    def dispatch(self, argv: list[str]) -> None:
        match argv:
            case ["start", svc] if svc in _START:
                self.lampp(_START[svc])
            case ["stop", svc] if svc in _STOP:
                self.lampp(_STOP[svc])
            case ["site-add", name, folder]:
                self.site_add(name, folder)
            case ["site-remove", name]:
                self.site_remove(name)
            case ["log", ("apache" | "mysql") as svc]:
                self.log(svc)
            case ["lean", ("on" | "off") as mode]:
                self.lean(mode == "on")
            case ["harden", ("on" | "off") as mode]:
                self.harden(mode == "on")
            case ["integrate", ("on" | "off") as mode]:
                self.integrate(mode == "on")
            case _:
                raise UsageError(USAGE)

    def lampp(self, actions) -> None:
        for action in actions:
            self.out.write(self._run([self.paths.lampp_script, action]))

    def log(self, key: str) -> None:
        path = services.log_path(key, self.paths)
        try:
            self.out.write(fsutil.tail(path))
        except FileNotFoundError:
            raise HelperFailure("there is no log file yet") from None

    def lean(self, on: bool) -> None:
        p = self.paths
        if on:
            fsutil.atomic_write(p.lean_httpd, configedit.LEAN_HTTPD)
            fsutil.atomic_write(p.lean_mysql, configedit.LEAN_MYSQL)
        self._edit(p.httpd_conf, lambda t: configedit.set_block(t, "lean", f"Include {p.lean_httpd}" if on else None))
        self._edit(p.my_cnf, lambda t: configedit.set_block(t, "lean", f"!include {p.lean_mysql}" if on else None))
        if not on:
            p.lean_httpd.unlink(missing_ok=True)
            p.lean_mysql.unlink(missing_ok=True)
        self.out.write(f"Lean mode {'on' if on else 'off'}. Restart Apache and MySQL to apply.\n")

    def harden(self, on: bool) -> None:
        p = self.paths
        self._edit(p.httpd_conf, lambda t: configedit.apache_localhost(t, on))
        if p.ssl_conf.exists():
            self._edit(p.ssl_conf, lambda t: configedit.apache_localhost(t, on))
        self._edit(p.my_cnf, lambda t: configedit.mysql_localhost(t, on))
        if p.proftpd_conf.exists():
            body = configedit.PROFTPD_LOCAL if on else None
            self._edit(p.proftpd_conf, lambda t: configedit.set_block(t, "localhost", body))

    def integrate(self, on: bool) -> None:
        p = self.paths
        if on:
            p.state_file.parent.mkdir(parents=True, exist_ok=True)
            if not p.vhosts_conf.exists():
                fsutil.atomic_write(p.vhosts_conf, configedit.render_vhosts(sites.load(p.state_file), p.htdocs))
            self._edit(p.httpd_conf, lambda t: configedit.set_block(t, "vhosts", f"Include {p.vhosts_conf}"))
            return
        for site in sites.load(p.state_file):
            self._revoke(site, [])
        self._edit(p.hosts, lambda t: configedit.set_block(t, "sites", None))
        self._edit(p.httpd_conf, lambda t: configedit.set_block(t, "vhosts", None))
        p.vhosts_conf.unlink(missing_ok=True)
        p.state_file.unlink(missing_ok=True)

    def site_add(self, name: str, folder: str) -> None:
        if not sites.validate_name(name):
            raise UsageError("site names use lowercase letters, numbers and dashes")
        pw = self._caller()
        path = validate_site_dir(folder, pw.pw_dir, pw.pw_uid)
        if not configedit.has_block(self.paths.httpd_conf.read_text(), "vhosts"):
            raise UsageError("XAMPP Panel is not set up yet; run setup.sh first")
        current = sites.load(self.paths.state_file)
        for s in current:
            if s.name == name:
                raise UsageError(f"a site called {name}.local already exists")
            if _overlaps(path, Path(s.path)):
                raise UsageError(f"that folder overlaps with {s.name}.local")
        site = sites.Site(name, str(path), pw.pw_uid)
        self._grant(pw, path)
        try:
            self._apply(current + [site])
        except Exception:
            self._revoke(site, current)
            raise
        self.out.write(site.url + "\n")

    def site_remove(self, name: str) -> None:
        pw = self._caller()
        current = sites.load(self.paths.state_file)
        site = next((s for s in current if s.name == name), None)
        if site is None:
            raise UsageError(f"there is no site called {name}.local")
        if site.uid != pw.pw_uid:
            raise UsageError("that site belongs to another user")
        remaining = [s for s in current if s.name != name]
        self._apply(remaining)
        self._revoke(site, remaining)

    # -- site internals ---------------------------------------------------
    def _apply(self, new_sites) -> None:
        """Write vhosts (config-tested, rolled back on failure), hosts and state; reload Apache."""
        p = self.paths
        old = p.vhosts_conf.read_text() if p.vhosts_conf.exists() else None
        fsutil.atomic_write(p.vhosts_conf, configedit.render_vhosts(new_sites, p.htdocs))
        try:
            self._run([p.apachectl, "-t"])
        except HelperFailure:
            if old is None:
                p.vhosts_conf.unlink(missing_ok=True)
            else:
                fsutil.atomic_write(p.vhosts_conf, old)
            raise
        self._edit(p.hosts, lambda t: configedit.set_block(t, "sites", configedit.render_hosts(new_sites)))
        sites.save(p.state_file, new_sites)
        if "apache" in services.running_services(p):
            self._run([p.lampp_script, "reloadapache"])

    def _grant(self, pw, site_path: Path) -> None:
        home = Path(os.path.realpath(pw.pw_dir))
        for d in traversal_dirs(home, site_path):
            self._run_as(pw.pw_uid, ["setfacl", "-m", f"u:{APACHE_USER}:x", d])
        self._run_as(pw.pw_uid, ["setfacl", "-R", "-P", "-m",
                                 f"u:{APACHE_USER}:rX,d:u:{APACHE_USER}:rX", site_path])

    def _revoke(self, site, remaining) -> None:
        """Best effort: removing a site must not fail because an ACL is already gone."""
        try:
            home = Path(os.path.realpath(self.getpw(site.uid).pw_dir))
            path = Path(site.path)
            if path.is_dir():
                self._run_as(site.uid, ["setfacl", "-R", "-P", "-x",
                                        f"u:{APACHE_USER},d:u:{APACHE_USER}", path])
            still_needed = {d for s in remaining if s.uid == site.uid
                            for d in traversal_dirs(home, Path(s.path))}
            for d in traversal_dirs(home, path):
                if d not in still_needed and d.is_dir():
                    self._run_as(site.uid, ["setfacl", "-x", f"u:{APACHE_USER}", d])
        except (HelperFailure, OSError, KeyError, ValueError) as e:
            print(f"warning: could not remove folder permissions for {site.name}: {e}", file=sys.stderr)


def main(argv=None, helper: Helper | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if helper is None:
        if os.geteuid() != 0:
            print("xampp-helper must run as root (it is started by pkexec)", file=sys.stderr)
            return 1
        os.umask(0o022)
        helper = Helper()
    try:
        helper.dispatch(argv)
    except UsageError as e:
        print(e, file=sys.stderr)
        return 2
    except (HelperFailure, OSError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0
```

`bin/xampp-helper`:
```python
#!/usr/bin/python3 -I
# Root helper for XAMPP Panel. Started by pkexec; see io.github.shiron.xampppanel.policy.
import sys

sys.path.insert(0, "/opt/xampp-panel/lib")
from xampp_panel.helper import main  # noqa: E402

sys.exit(main())
```

Then: `chmod +x bin/xampp-helper`

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/helper.py bin/xampp-helper tests/test_helper.py
git commit -m "feat: whitelisted root helper for services, sites, lean and hardening

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: pkexec wrapper and user settings

**Files:**
- Create: `src/xampp_panel/privileged.py`, `src/xampp_panel/settings.py`
- Test: `tests/test_privileged.py`, `tests/test_settings.py`

**Interfaces:**
- Consumes: `Paths.helper`, `fsutil.atomic_write`.
- Produces: `privileged.argv_for(*args, paths=DEFAULT) -> list[str]`, `privileged.interpret(returncode, stdout, stderr) -> str`, exceptions `HelperError`, `Cancelled(HelperError)`.
- Produces: `settings.DEFAULTS = {"tray": False}`, `settings.config_path(env=None) -> Path`, `settings.load(path=None) -> dict`, `settings.save(data, path=None) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_privileged.py`:
```python
import unittest

from xampp_panel import privileged


class PrivilegedTest(unittest.TestCase):
    def test_argv(self):
        self.assertEqual(privileged.argv_for("start", "apache"),
                         ["pkexec", "/opt/xampp-panel/bin/xampp-helper", "start", "apache"])

    def test_success_returns_stdout(self):
        self.assertEqual(privileged.interpret(0, "ok\n", ""), "ok\n")

    def test_cancelled_auth(self):
        for code in (126, 127):
            with self.assertRaises(privileged.Cancelled):
                privileged.interpret(code, "", "Not authorized")

    def test_error_uses_last_stderr_line(self):
        with self.assertRaises(privileged.HelperError) as ctx:
            privileged.interpret(1, "", "details\nport 80 in use\n")
        self.assertEqual(str(ctx.exception), "port 80 in use")

    def test_error_without_output(self):
        with self.assertRaises(privileged.HelperError) as ctx:
            privileged.interpret(3, "", "")
        self.assertEqual(str(ctx.exception), "the helper failed (exit code 3)")
```

`tests/test_settings.py`:
```python
import tempfile
import unittest
from pathlib import Path

from xampp_panel import settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "cfg/xampp-panel/settings.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_when_missing_or_corrupt(self):
        self.assertEqual(settings.load(self.file), {"tray": False})
        self.file.parent.mkdir(parents=True)
        self.file.write_text("{not json")
        self.assertEqual(settings.load(self.file), {"tray": False})
        self.file.write_text("[1, 2]")
        self.assertEqual(settings.load(self.file), {"tray": False})

    def test_round_trip_is_private(self):
        settings.save({"tray": True}, self.file)
        self.assertEqual(settings.load(self.file), {"tray": True})
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)

    def test_unknown_keys_are_dropped(self):
        settings.save({"tray": True, "evil": 1}, self.file)
        self.assertEqual(settings.load(self.file), {"tray": True})

    def test_config_path_honours_xdg(self):
        self.assertEqual(settings.config_path({"XDG_CONFIG_HOME": "/x"}), Path("/x/xampp-panel/settings.json"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_privileged tests.test_settings -v`
Expected: ERROR `cannot import name 'privileged'`

- [ ] **Step 3: Write the implementation**

`src/xampp_panel/privileged.py`:
```python
"""Talking to the root helper through pkexec (GUI side, no GTK imports)."""

from .paths import DEFAULT, Paths

# pkexec: 126 = the user dismissed the dialog, 127 = not authorized / auth failed.
_CANCELLED = (126, 127)


class HelperError(Exception):
    pass


class Cancelled(HelperError):
    pass


def argv_for(*args: str, paths: Paths = DEFAULT) -> list[str]:
    return ["pkexec", str(paths.helper), *args]


def interpret(returncode: int, stdout: str, stderr: str) -> str:
    if returncode in _CANCELLED:
        raise Cancelled("authentication cancelled")
    if returncode != 0:
        lines = [line for line in (stderr or stdout).splitlines() if line.strip()]
        raise HelperError(lines[-1].strip() if lines else f"the helper failed (exit code {returncode})")
    return stdout
```

`src/xampp_panel/settings.py`:
```python
"""Per-user preferences in ~/.config/xampp-panel/settings.json."""

import json
import os
from pathlib import Path

from . import fsutil

DEFAULTS = {"tray": False}


def config_path(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "xampp-panel" / "settings.json"


def load(path=None) -> dict:
    try:
        data = json.loads(Path(path or config_path()).read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {key: type(default)(data.get(key, default)) for key, default in DEFAULTS.items()}


def save(data: dict, path=None) -> None:
    path = Path(path or config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    fsutil.atomic_write(path, json.dumps(clean, indent=2) + "\n", mode=0o600)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/privileged.py src/xampp_panel/settings.py tests/test_privileged.py tests/test_settings.py
git commit -m "feat: pkexec result handling and user settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: GTK4 control panel

The GUI can't be unit-tested in the dev sandbox (no PyGObject there). All logic it uses is already tested. This task is checked by compiling it, by an import-guard test that runs wherever `gi` exists, and by a manual run on the host (Task 9).

**Files:**
- Create: `src/xampp_panel/watch.py`, `src/xampp_panel/window.py`, `src/xampp_panel/app.py`, `src/xampp_panel/main.py`, `bin/xampp-panel`
- Test: `tests/test_gui_import.py`

**Interfaces:**
- Consumes: `services.SERVICES/State/snapshot/log_path`, `privileged.argv_for/interpret/Cancelled/HelperError`, `sites.load/validate_name`, `settings.load/save`, `configedit.has_block`, `fsutil.tail`, `Paths.watch_dirs/launcher/state_file/htdocs/mysql_client/httpd_conf`.
- Produces: `watch.StatusWatcher(dirs, callback, fallback_seconds)` with `resume()`, `pause()`, `poke()` (used by the tray in Task 7); `main.main(argv=None) -> int`; `app.APP_ID`; `MainWindow.call_helper(args, busy=(), done=None, failed=None)`; `MainWindow.toast(text)`.

- [ ] **Step 1: Write the import-guard test**

`tests/test_gui_import.py`:
```python
import importlib.util
import os
import py_compile
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src/xampp_panel"
HAS_GTK4 = False
if importlib.util.find_spec("gi"):
    import gi
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        HAS_GTK4 = True
    except ValueError:
        pass


class GuiCompileTest(unittest.TestCase):
    def test_gui_modules_compile(self):
        for name in ("watch", "window", "app", "main", "tray"):
            path = SRC / f"{name}.py"
            if path.exists():
                py_compile.compile(str(path), doraise=True)

    def test_launchers_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("xampp-panel", "xampp-helper"):
                path = SRC.parent.parent / "bin" / name
                self.assertTrue(path.read_text().startswith("#!/usr/bin/python3 -I\n"), name)
                py_compile.compile(str(path), doraise=True, cfile=os.path.join(tmp, name + ".pyc"))

    @unittest.skipUnless(HAS_GTK4, "GTK 4 / libadwaita not available")
    def test_window_imports(self):
        import xampp_panel.window  # noqa: F401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_gui_import -v`
Expected: FAIL in `test_launchers_compile` (`bin/xampp-panel` missing)

- [ ] **Step 3: Write the implementation**

`src/xampp_panel/watch.py`:
```python
"""Event-driven status updates shared by the panel and the tray.

inotify (Gio.FileMonitor) on XAMPP's PID/socket directories triggers a
refresh; a slow fallback timer (only while resumed) catches crashes that
leave stale files behind. Uses only Gio/GLib, so it works with GTK 3 and 4.
"""

from gi.repository import Gio, GLib

_TRIGGER_SUFFIXES = (".pid", ".sock")
_DEBOUNCE_MS = 300


class StatusWatcher:
    def __init__(self, dirs, callback, fallback_seconds: int):
        self._callback = callback
        self._fallback_seconds = fallback_seconds
        self._debounce = 0
        self._timer = 0
        self._monitors = []
        for d in dirs:
            try:
                monitor = Gio.File.new_for_path(str(d)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            except GLib.Error:
                continue  # unreadable dir (e.g. var/mysql): the fallback timer covers it
            monitor.connect("changed", self._on_changed)
            self._monitors.append(monitor)

    def _on_changed(self, _monitor, file, _other, _event):
        name = file.get_basename() or ""
        if name.endswith(_TRIGGER_SUFFIXES):
            self.poke()

    def poke(self) -> None:
        """Schedule one refresh soon (coalesces bursts of events)."""
        if not self._debounce:
            self._debounce = GLib.timeout_add(_DEBOUNCE_MS, self._fire)

    def _fire(self):
        self._debounce = 0
        self._callback()
        return GLib.SOURCE_REMOVE

    def resume(self) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(self._fallback_seconds, self._tick)

    def pause(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self):
        self._callback()
        return GLib.SOURCE_CONTINUE
```

`src/xampp_panel/window.py`:
```python
"""Main window: Services and Sites pages (GTK 4.6+ / libadwaita 1.1+)."""

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import fsutil, privileged, services, sites  # noqa: E402
from .paths import DEFAULT as PATHS  # noqa: E402
from .services import State  # noqa: E402
from .watch import StatusWatcher  # noqa: E402

FALLBACK_SECONDS = 10
SITES_DIR = Path.home() / "Sites"
STARTER_PHP = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{name}.local</title></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 4rem auto; line-height: 1.5">
<h1>{name}.local works</h1>
<p>Edit <code><?= htmlspecialchars(__FILE__) ?></code> to get started.</p>
<p>PHP <?= PHP_VERSION ?></p>
</body></html>
"""
_DOT_CLASS = {State.RUNNING: "success", State.STARTING: "warning",
              State.CONFLICT: "error", State.STOPPED: "dim-label"}
_STATE_NOTE = {State.STARTING: " · starting…", State.CONFLICT: " · port used by another program"}


def open_uri(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        pass


def _make_banner(text):
    """Adw.Banner on libadwaita ≥ 1.3, a revealer with a label otherwise."""
    if hasattr(Adw, "Banner"):
        banner = Adw.Banner(title=text)
        return banner, banner.set_revealed
    label = Gtk.Label(label=text, wrap=True, margin_top=8, margin_bottom=8,
                      margin_start=12, margin_end=12, css_classes=["warning"])
    revealer = Gtk.Revealer(child=label)
    return revealer, revealer.set_reveal_child


class ServiceRow(Adw.ActionRow):
    def __init__(self, svc, has_log, on_toggle, on_log):
        super().__init__(title=svc.title)
        self.svc = svc
        self.dot = Gtk.Label(label="●")
        self.add_prefix(self.dot)
        if has_log:
            log = Gtk.Button(icon_name="text-x-generic-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="View log", css_classes=["flat"])
            log.connect("clicked", lambda *_: on_log(svc))
            self.add_suffix(log)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._handler = self.switch.connect("notify::active", lambda sw, _p: on_toggle(svc, sw.get_active()))
        self.add_suffix(self.switch)
        self.set_activatable_widget(self.switch)

    def show_state(self, state: State, busy: bool) -> None:
        self.dot.set_css_classes([_DOT_CLASS[state]])
        self.switch.handler_block(self._handler)
        self.switch.set_active(state in (State.RUNNING, State.STARTING))
        self.switch.handler_unblock(self._handler)
        self.switch.set_sensitive(not busy and state != State.CONFLICT)
        self.set_subtitle(f"{self.svc.description} · port {self.svc.port}{_STATE_NOTE.get(state, '')}")


class LogWindow(Adw.Window):
    def __init__(self, parent, title, text):
        super().__init__(transient_for=parent, title=f"{title} log", default_width=760, default_height=480)
        view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                            top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        buffer = view.get_buffer()
        buffer.set_text(text or "The log is empty.")
        scroll = Gtk.ScrolledWindow(child=view, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        box.append(scroll)
        self.set_content(box)
        end = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.connect("map", lambda *_: GLib.idle_add(lambda: view.scroll_to_mark(end, 0, False, 0, 1) or False))


class AddSiteWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True, title="Add site", default_width=460)
        self.panel = parent
        self.folder = None
        self._chooser = None

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        self.add_button = Gtk.Button(label="Add", sensitive=False, css_classes=["suggested-action"])
        self.add_button.connect("clicked", self._add)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(self.add_button)

        self.name = Gtk.Entry(placeholder_text="blog", valign=Gtk.Align.CENTER, hexpand=True)
        self.name.connect("changed", self._validate)
        self.name.connect("activate", lambda *_: self.add_button.get_sensitive() and self._add())
        name_row = Adw.ActionRow(title="Name", subtitle="Lowercase letters, numbers and dashes")
        name_row.add_suffix(self.name)

        self.folder_row = Adw.ActionRow(title="Folder")
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._choose)
        self.folder_row.add_suffix(choose)

        group = Adw.PreferencesGroup(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        group.add(name_row)
        group.add(self.folder_row)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(group)
        self.set_content(box)
        self._validate()

    def _validate(self, *_):
        name = self.name.get_text().strip()
        self.add_button.set_sensitive(sites.validate_name(name))
        if self.folder is None:
            self.folder_row.set_subtitle(f"~/Sites/{name or '<name>'} (created for you)")

    def _choose(self, *_):
        if hasattr(Gtk, "FileDialog"):  # GTK ≥ 4.10
            dialog = Gtk.FileDialog(title="Choose the site folder")
            dialog.select_folder(self, None, self._chosen_dialog)
        else:
            self._chooser = Gtk.FileChooserNative(title="Choose the site folder", transient_for=self,
                                                  action=Gtk.FileChooserAction.SELECT_FOLDER)
            self._chooser.connect("response", self._chosen_native)
            self._chooser.show()

    def _chosen_dialog(self, dialog, result):
        try:
            self._set_folder(dialog.select_folder_finish(result))
        except GLib.Error:
            pass

    def _chosen_native(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            self._set_folder(chooser.get_file())
        self._chooser = None

    def _set_folder(self, file):
        if file and file.get_path():
            self.folder = Path(file.get_path())
            self.folder_row.set_subtitle(str(self.folder))

    def _add(self, *_):
        name = self.name.get_text().strip()
        folder = self.folder or SITES_DIR / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
            index = folder / "index.php"
            if self.folder is None and not index.exists():
                index.write_text(STARTER_PHP.format(name=name))
        except OSError as e:
            self.panel.toast(f"Could not create {folder}: {e.strerror}")
            return
        self.add_button.set_sensitive(False)

        def done(_out):
            self.panel.reload_sites()
            self.panel.toast(f"{name}.local is ready")
            open_uri(f"http://{name}.local/")
            self.close()

        self.panel.call_helper(["site-add", name, str(folder)], done=done,
                               failed=lambda: self.add_button.set_sensitive(True))


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="XAMPP", default_width=580, default_height=660)
        self.busy: set[str] = set()
        self.states: dict[str, State] = {}
        self.rows: dict[str, ServiceRow] = {}
        self.site_rows = []

        stack = Adw.ViewStack()
        stack.add_titled(self._services_page(), "services", "Services").set_icon_name("network-server-symbolic")
        stack.add_titled(self._sites_page(), "sites", "Sites").set_icon_name("folder-symbolic")

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcherTitle(stack=stack, title="XAMPP"))
        menu = Gio.Menu()
        menu.append("Keep in tray when closed", "app.tray")
        menu.append("Lean mode (uses less memory)", "app.lean")
        menu.append("Quit", "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))

        self.banner, self.show_banner = _make_banner(
            "MySQL root has no password. Run “sudo /opt/lampp/lampp security” to set one.")
        self.toasts = Adw.ToastOverlay(child=stack, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(self.banner)
        box.append(self.toasts)
        self.set_content(box)

        self.watcher = StatusWatcher(PATHS.watch_dirs, self.refresh, FALLBACK_SECONDS)
        # The fallback timer only runs while the window is focused; inotify covers the rest.
        self.connect("notify::is-active", self._on_active_changed)
        self.refresh()
        self.reload_sites()

    # -- pages ------------------------------------------------------------
    def _services_page(self):
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Services")
        buttons = Gtk.Box(spacing=6)
        start = Gtk.Button(label="Start", valign=Gtk.Align.CENTER, css_classes=["suggested-action"],
                           tooltip_text="Start Apache and MySQL")
        start.connect("clicked", lambda *_: self.call_helper(["start", "all"], busy={"apache", "mysql"}))
        stop = Gtk.Button(label="Stop all", valign=Gtk.Align.CENTER)
        stop.connect("clicked", lambda *_: self.call_helper(["stop", "all"], busy={s.key for s in services.SERVICES}))
        buttons.append(start)
        buttons.append(stop)
        group.set_header_suffix(buttons)
        for svc in services.SERVICES:
            row = ServiceRow(svc, services.log_path(svc.key, PATHS) is not None, self.toggle_service, self.show_log)
            self.rows[svc.key] = row
            group.add(row)
        page.add(group)

        links = Adw.PreferencesGroup(title="Shortcuts")
        for title, target, icon in (
            ("Open localhost", "http://localhost/", "web-browser-symbolic"),
            ("Open phpMyAdmin", "http://localhost/phpmyadmin/", "network-server-symbolic"),
            ("Open htdocs folder", PATHS.htdocs.as_uri(), "folder-symbolic"),
            ("Open Sites folder", SITES_DIR.as_uri(), "folder-symbolic"),
        ):
            row = Adw.ActionRow(title=title, activatable=True)
            row.add_prefix(Gtk.Image(icon_name=icon))
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.connect("activated", lambda _r, t=target: self.open_target(t))
            links.add(row)
        page.add(links)
        return page

    def _sites_page(self):
        page = Adw.PreferencesPage()
        self.sites_group = Adw.PreferencesGroup(
            title="Sites", description="Each site gets its own address, like http://blog.local, "
                                       "served from a folder in your home. Only this computer can open them.")
        add = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
                         tooltip_text="Add site", css_classes=["flat"])
        add.connect("clicked", lambda *_: AddSiteWindow(self).present())
        self.sites_group.set_header_suffix(add)
        page.add(self.sites_group)
        return page

    # -- status -----------------------------------------------------------
    def _on_active_changed(self, *_):
        if self.is_active():
            self.refresh()
            self.watcher.resume()
        else:
            self.watcher.pause()

    def refresh(self):
        previous_mysql = self.states.get("mysql")
        self.states = services.snapshot(PATHS)
        for key, row in self.rows.items():
            row.show_state(self.states[key], key in self.busy)
        mysql = self.states["mysql"]
        if mysql == State.RUNNING and previous_mysql != State.RUNNING:
            self._check_mysql_password()
        elif mysql != State.RUNNING:
            self.show_banner(False)

    def _check_mysql_password(self):
        """Show the banner if MySQL root accepts a login without a password (runs once per start)."""
        argv = [str(PATHS.mysql_client), "-uroot", "-h127.0.0.1", "--protocol=TCP",
                "--connect-timeout=2", "-e", "SELECT 1"]
        try:
            proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error:
            return

        def finished(p, result):
            try:
                self.show_banner(p.wait_check_finish(result))
            except GLib.Error:
                self.show_banner(False)

        proc.wait_check_async(None, finished)

    # -- actions ----------------------------------------------------------
    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=5))

    def call_helper(self, args, busy=(), done=None, failed=None):
        """Run the root helper asynchronously; the UI never blocks."""
        busy = set(busy)
        self.busy |= busy
        self.refresh()
        try:
            proc = Gio.Subprocess.new(privileged.argv_for(*args),
                                      Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
        except GLib.Error as e:
            self.busy -= busy
            self.toast(e.message)
            self.refresh()
            return

        def finished(p, result):
            try:
                _ok, out, err = p.communicate_utf8_finish(result)
            except GLib.Error as e:
                out, err = "", e.message
            code = p.get_exit_status() if p.get_if_exited() else 1
            self.busy -= busy
            try:
                out = privileged.interpret(code, out or "", err or "")
            except privileged.Cancelled:
                if failed:
                    failed()
            except privileged.HelperError as e:
                self.toast(str(e))
                if failed:
                    failed()
            else:
                if done:
                    done(out)
            self.refresh()

        proc.communicate_utf8_async(None, None, finished)

    def toggle_service(self, svc, active: bool):
        self.call_helper(["start" if active else "stop", svc.key], busy={svc.key})

    def show_log(self, svc):
        path = services.log_path(svc.key, PATHS)
        try:
            text = fsutil.tail(path)
        except PermissionError:
            self.call_helper(["log", svc.key], done=lambda out: LogWindow(self, svc.title, out).present())
            return
        except FileNotFoundError:
            text = "No log entries yet."
        LogWindow(self, svc.title, text).present()

    def open_target(self, target: str):
        if target == SITES_DIR.as_uri():
            SITES_DIR.mkdir(exist_ok=True)
        open_uri(target)

    # -- sites ------------------------------------------------------------
    def reload_sites(self):
        for row in self.site_rows:
            self.sites_group.remove(row)
        self.site_rows = []
        try:
            mine = [s for s in sites.load(PATHS.state_file) if s.uid == os.getuid()]
        except (OSError, ValueError, KeyError):
            mine = []
        if not mine:
            self._add_site_row(Adw.ActionRow(title="No sites yet", subtitle="Click + to create one."))
        for site in mine:
            row = Adw.ActionRow(title=f"{site.name}.local", subtitle=site.path)
            for icon, tip, action in (
                ("web-browser-symbolic", "Open in browser", lambda _b, s=site: open_uri(s.url)),
                ("folder-open-symbolic", "Open folder", lambda _b, s=site: open_uri(Path(s.path).as_uri())),
                ("user-trash-symbolic", "Remove site (keeps the folder)", lambda _b, s=site: self.remove_site(s)),
            ):
                button = Gtk.Button(icon_name=icon, tooltip_text=tip, valign=Gtk.Align.CENTER, css_classes=["flat"])
                button.connect("clicked", action)
                row.add_suffix(button)
            self._add_site_row(row)

    def _add_site_row(self, row):
        self.sites_group.add(row)
        self.site_rows.append(row)

    def remove_site(self, site):
        def done(_out):
            self.reload_sites()
            self.toast(f"Removed {site.name}.local. Its folder was kept.")

        self.call_helper(["site-remove", site.name], done=done)
```

`src/xampp_panel/app.py`:
```python
"""The Adw.Application: single instance, app-level actions (tray, lean mode, quit)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from . import configedit, settings  # noqa: E402
from .paths import DEFAULT as PATHS  # noqa: E402
from .window import MainWindow  # noqa: E402

APP_ID = "io.github.shiron.XamppPanel"
_SNI_WATCHER = "org.kde.StatusNotifierWatcher"  # provided by GNOME's AppIndicator extension


def tray_available() -> bool:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "NameHasOwner", GLib.Variant("(s)", (_SNI_WATCHER,)), GLib.VariantType("(b)"),
                              Gio.DBusCallFlags.NONE, 500, None)
        return reply.unpack()[0]
    except GLib.Error:
        return False


def launch_tray() -> None:
    try:
        Gio.Subprocess.new([str(PATHS.launcher), "--tray"], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        pass


def lean_enabled() -> bool:
    try:
        return configedit.has_block(PATHS.httpd_conf.read_text(), "lean")
    except OSError:
        return False


class PanelApp(Adw.Application):
    def __init__(self):
        flags = getattr(Gio.ApplicationFlags, "DEFAULT_FLAGS", Gio.ApplicationFlags.FLAGS_NONE)
        super().__init__(application_id=APP_ID, flags=flags)
        self.settings = settings.load()

    def do_startup(self):
        Adw.Application.do_startup(self)
        tray = Gio.SimpleAction.new_stateful("tray", None, GLib.Variant.new_boolean(self.settings["tray"]))
        tray.set_enabled(tray_available())
        tray.connect("change-state", self._on_tray)
        self.add_action(tray)

        lean = Gio.SimpleAction.new_stateful("lean", None, GLib.Variant.new_boolean(lean_enabled()))
        lean.connect("change-state", self._on_lean)
        self.add_action(lean)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        if self.settings["tray"] and tray.get_enabled():
            launch_tray()

    def do_activate(self):
        window = self.props.active_window or MainWindow(self)
        window.present()

    def _on_tray(self, action, value):
        action.set_state(value)
        self.settings["tray"] = value.get_boolean()
        settings.save(self.settings)
        if value.get_boolean():
            launch_tray()  # the tray quits by itself when the setting turns off

    def _on_lean(self, action, value):
        on = value.get_boolean()
        window = self.props.active_window
        if window is None:
            return

        def done(_out):
            action.set_state(value)
            window.toast(f"Lean mode {'on' if on else 'off'}. Restart Apache and MySQL to apply.")

        window.call_helper(["lean", "on" if on else "off"], done=done)


def run_app(argv) -> int:
    return PanelApp().run(argv)
```

`src/xampp_panel/main.py`:
```python
"""Entry point. `xampp-panel` opens the panel; `xampp-panel --tray` runs the tray icon."""

import sys


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    if "--tray" in argv[1:]:
        from .tray import run_tray  # GTK 3: must not share a process with GTK 4
        return run_tray()
    from .app import run_app
    return run_app(argv)


if __name__ == "__main__":
    sys.exit(main())
```

`bin/xampp-panel`:
```python
#!/usr/bin/python3 -I
# XAMPP Panel launcher (installed to /opt/xampp-panel/bin/xampp-panel).
import sys

sys.path.insert(0, "/opt/xampp-panel/lib")
from xampp_panel.main import main  # noqa: E402

sys.exit(main())
```

Then: `chmod +x bin/xampp-panel`

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS (`test_window_imports` is SKIPPED in the sandbox; it runs on the host)

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/watch.py src/xampp_panel/window.py src/xampp_panel/app.py src/xampp_panel/main.py bin/xampp-panel tests/test_gui_import.py
git commit -m "feat: GTK4/libadwaita control panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Tray indicator

**Files:**
- Create: `src/xampp_panel/tray.py`
- Test: covered by `tests/test_gui_import.py::test_gui_modules_compile` (already lists `tray`)

**Interfaces:**
- Consumes: `watch.StatusWatcher`, `services.snapshot/BY_KEY/State`, `privileged.argv_for`, `settings.load/save/config_path`, `Paths.watch_dirs/launcher`.
- Produces: `tray.run_tray() -> int` (called by `main.main` for `--tray`).

- [ ] **Step 1: Write the implementation**

`src/xampp_panel/tray.py`:
```python
"""Tray icon: GTK 3 + AyatanaAppIndicator, in its own lightweight process.

Quits by itself when the "tray" setting is turned off. Refreshes on inotify
events, with a 30 s fallback; there is no busy polling.
"""

import sys

TRAY_ID = "io.github.shiron.XamppPanel.Tray"
FALLBACK_SECONDS = 30


def run_tray() -> int:
    import gi

    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except (ValueError, ImportError):
        print("xampp-panel: the tray needs the gir1.2-ayatanaappindicator3-0.1 package", file=sys.stderr)
        return 1
    from gi.repository import Gio, GLib, Gtk

    from . import privileged, services, settings
    from .paths import DEFAULT as PATHS
    from .services import State
    from .watch import StatusWatcher

    class Tray(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=TRAY_ID)

        def do_startup(self):
            Gtk.Application.do_startup(self)
            self.hold()  # no windows; stay alive until quit
            self.indicator = AppIndicator.Indicator.new(
                "xampp-panel", "xampp-panel-stopped", AppIndicator.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.indicator.set_title("XAMPP")

            menu = Gtk.Menu()
            self.status_item = Gtk.MenuItem(label="XAMPP", sensitive=False)
            menu.append(self.status_item)
            menu.append(Gtk.SeparatorMenuItem())
            for label, callback in (
                ("Start Apache + MySQL", lambda *_: self.helper("start", "all")),
                ("Stop all", lambda *_: self.helper("stop", "all")),
                ("Open control panel", lambda *_: self.open_panel()),
            ):
                item = Gtk.MenuItem(label=label)
                item.connect("activate", callback)
                menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())
            hide = Gtk.MenuItem(label="Hide tray icon")
            hide.connect("activate", lambda *_: self.disable())
            menu.append(hide)
            menu.show_all()
            self.indicator.set_menu(menu)

            self.watcher = StatusWatcher(PATHS.watch_dirs, self.refresh, FALLBACK_SECONDS)
            self.watcher.resume()
            self.settings_monitor = Gio.File.new_for_path(str(settings.config_path())).monitor_file(
                Gio.FileMonitorFlags.NONE, None)
            self.settings_monitor.connect("changed", self._settings_changed)
            self.refresh()

        def do_activate(self):
            pass  # a second launch just finds this instance

        def refresh(self):
            states = services.snapshot(PATHS)
            running = [services.BY_KEY[k].title for k, s in states.items() if s == State.RUNNING]
            if running:
                self.indicator.set_icon_full("xampp-panel-running", "XAMPP running")
                self.status_item.set_label("Running: " + ", ".join(running))
            else:
                self.indicator.set_icon_full("xampp-panel-stopped", "XAMPP stopped")
                self.status_item.set_label("XAMPP is stopped")

        def helper(self, *args):
            try:
                proc = Gio.Subprocess.new(privileged.argv_for(*args),
                                          Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
            except GLib.Error:
                return
            proc.wait_async(None, lambda *_: self.watcher.poke())

        def open_panel(self):
            try:
                Gio.Subprocess.new([str(PATHS.launcher)], Gio.SubprocessFlags.NONE)
            except GLib.Error:
                pass

        def disable(self):
            data = settings.load()
            data["tray"] = False
            settings.save(data)
            self.quit()

        def _settings_changed(self, *_):
            if not settings.load()["tray"]:
                self.quit()

    return Tray().run([sys.argv[0]])
```

- [ ] **Step 2: Run tests**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS (tray.py now compiles in `test_gui_modules_compile`)

- [ ] **Step 3: Commit**

```bash
git add src/xampp_panel/tray.py
git commit -m "feat: optional AppIndicator tray icon

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Desktop entry, polkit policy and icons

**Files:**
- Create: `data/io.github.shiron.XamppPanel.desktop`, `data/io.github.shiron.xampppanel.policy`, `data/icons/io.github.shiron.XamppPanel.svg`, `data/icons/xampp-panel-running.svg`, `data/icons/xampp-panel-stopped.svg`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: `Paths().helper`, `Paths().launcher` (the policy and desktop file must match them).
- Produces: file names that `setup.sh` (Task 9) installs.

- [ ] **Step 1: Write the failing test**

`tests/test_data.py`:
```python
import configparser
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from xampp_panel.paths import DEFAULT

DATA = Path(__file__).resolve().parent.parent / "data"


class DataFilesTest(unittest.TestCase):
    def test_desktop_entry(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(DATA / "io.github.shiron.XamppPanel.desktop")
        entry = parser["Desktop Entry"]
        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(entry["Exec"], str(DEFAULT.launcher))
        self.assertEqual(entry["Icon"], "io.github.shiron.XamppPanel")
        self.assertEqual(entry["Terminal"], "false")

    def test_polkit_policy_pins_helper_and_requires_admin(self):
        root = ET.parse(DATA / "io.github.shiron.xampppanel.policy").getroot()
        action = root.find("action")
        self.assertEqual(action.get("id"), "io.github.shiron.xampppanel.helper")
        defaults = action.find("defaults")
        self.assertEqual(defaults.findtext("allow_any"), "no")
        self.assertEqual(defaults.findtext("allow_inactive"), "no")
        self.assertEqual(defaults.findtext("allow_active"), "auth_admin_keep")
        annotations = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotations["org.freedesktop.policykit.exec.path"], str(DEFAULT.helper))

    def test_icons_are_valid_svg(self):
        for name in ("io.github.shiron.XamppPanel", "xampp-panel-running", "xampp-panel-stopped"):
            root = ET.parse(DATA / "icons" / f"{name}.svg").getroot()
            self.assertTrue(root.tag.endswith("svg"), name)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_data -v`
Expected: FAIL / ERROR (`KeyError: 'Desktop Entry'` / `FileNotFoundError`)

- [ ] **Step 3: Create the files**

`data/io.github.shiron.XamppPanel.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=XAMPP Control Panel
GenericName=Local Web Server
Comment=Start and stop Apache, MySQL and FTP, and manage local sites
Exec=/opt/xampp-panel/bin/xampp-panel
Icon=io.github.shiron.XamppPanel
Terminal=false
Categories=Development;WebDevelopment;
Keywords=apache;mysql;mariadb;php;lampp;xampp;server;localhost;
StartupNotify=true
```

`data/io.github.shiron.xampppanel.policy`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>XAMPP Panel</vendor>
  <action id="io.github.shiron.xampppanel.helper">
    <description>Control XAMPP services and local sites</description>
    <message>Authentication is required to control XAMPP</message>
    <icon_name>io.github.shiron.XamppPanel</icon_name>
    <defaults>
      <allow_any>no</allow_any>
      <allow_inactive>no</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/opt/xampp-panel/bin/xampp-helper</annotate>
  </action>
</policyconfig>
```

`data/icons/io.github.shiron.XamppPanel.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect x="8" y="8" width="112" height="112" rx="26" fill="#fb7a24"/>
  <rect x="8" y="8" width="112" height="56" rx="26" fill="#ff9a4d" opacity="0.35"/>
  <path d="M40 38 L88 90 M88 38 L40 90" stroke="#ffffff" stroke-width="14" stroke-linecap="round"/>
</svg>
```

`data/icons/xampp-panel-running.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M4 4 L12 12 M12 4 L4 12" stroke="#fb7a24" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="12.5" cy="12.5" r="3" fill="#33d17a"/>
</svg>
```

`data/icons/xampp-panel-stopped.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M4 4 L12 12 M12 4 L4 12" stroke="#9a9996" stroke-width="2.5" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add data tests/test_data.py
git commit -m "feat: desktop entry, polkit policy and icons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: setup.sh, uninstall.sh and README

**Files:**
- Create: `setup.sh`, `uninstall.sh`, `README.md`
- Test: `tests/test_scripts.py`

**Interfaces:**
- Consumes: helper commands `integrate|harden|lean on|off` (Task 4); data file names (Task 8); `bin/*` (Tasks 4, 6).
- Produces: `/opt/xampp-panel/install-manifest.txt` (one absolute path per line, each under `/usr/share/` or `/usr/local/bin/`).

- [ ] **Step 1: Write the failing test**

`tests/test_scripts.py`:
```python
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ScriptsTest(unittest.TestCase):
    def test_syntax(self):
        for name in ("setup.sh", "uninstall.sh"):
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
        import os
        if os.geteuid() == 0:
            self.skipTest("running as root")
        proc = subprocess.run(["bash", str(ROOT / "setup.sh")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("sudo", proc.stderr)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src python3 -m unittest tests.test_scripts -v`
Expected: FAIL (`bash: …/setup.sh: No such file or directory`)

- [ ] **Step 3: Write the scripts**

`setup.sh`:
```bash
#!/usr/bin/env bash
# Install XAMPP (if missing) and XAMPP Panel on Zorin OS / Ubuntu.
set -euo pipefail
shopt -s nullglob

APP_DIR=/opt/xampp-panel
LAMPP=/opt/lampp
APP_ID=io.github.shiron.XamppPanel
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ALLOW_LAN=0
LEAN=ask
INSTALLER=""

usage() {
  cat <<'EOF'
Usage: sudo ./setup.sh [options]

Installs XAMPP (if /opt/lampp does not exist yet) and the XAMPP Panel app.

Options:
  --installer PATH  XAMPP installer to use (default: look next to this
                    folder and in ~/Downloads)
  --allow-lan       let other devices on your network reach XAMPP
                    (default: only this computer can)
  --lean            turn on lean mode without asking
  --no-lean         leave lean mode off without asking
  -h, --help        show this help
EOF
}

while (($#)); do
  case "$1" in
    --installer) INSTALLER="${2:?--installer needs a path}"; shift ;;
    --allow-lan) ALLOW_LAN=1 ;;
    --lean) LEAN=yes ;;
    --no-lean) LEAN=no ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
ask() { local reply=""; read -r -p "$1 [y/N] " reply </dev/tty || true; [[ $reply =~ ^[Yy] ]]; }

[[ $EUID -eq 0 ]] || die "run this with: sudo ./setup.sh"
[[ $(uname -m) == x86_64 ]] || die "XAMPP for Linux only supports 64-bit x86 (x86_64)."
command -v apt-get >/dev/null || die "this script needs an apt-based system (Zorin OS, Ubuntu, Debian)."
REAL_USER="${SUDO_USER:-}"
[[ -n $REAL_USER && $REAL_USER != root ]] || die "run this with sudo from your normal account, not as root."
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
apt-cache show gir1.2-adw-1 >/dev/null 2>&1 || die "libadwaita is not available: XAMPP Panel needs Zorin OS 17 / Ubuntu 22.04 or newer."

say "Installing required packages"
packages=(libcrypt1 net-tools acl python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
if apt-cache show pkexec >/dev/null 2>&1; then packages+=(pkexec); else packages+=(policykit-1); fi
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${packages[@]}"

say "Checking XAMPP"
if [[ -x $LAMPP/lampp ]]; then
  echo "XAMPP is already installed in $LAMPP."
else
  if [[ -z $INSTALLER ]]; then
    for candidate in "$SRC_DIR"/xampp-linux-x64-*-installer.run \
                     "$SRC_DIR"/../xampp-linux-x64-*-installer.run \
                     "$REAL_HOME"/Downloads/xampp-linux-x64-*-installer.run; do
      INSTALLER="$candidate"
    done
  fi
  [[ -n $INSTALLER && -f $INSTALLER ]] || die "XAMPP installer not found. Use: sudo ./setup.sh --installer /path/to/xampp-linux-x64-…-installer.run"
  echo "Installing $(basename "$INSTALLER"). This takes a minute…"
  chmod +x "$INSTALLER"
  "$INSTALLER" --mode unattended --unattendedmodeui none
  [[ -x $LAMPP/lampp ]] || die "the XAMPP installer finished but $LAMPP/lampp is missing."
fi

if pgrep -f "^$LAMPP/" >/dev/null; then
  say "Stopping XAMPP so the configuration changes apply cleanly"
  "$LAMPP/lampp" stop || true
fi

say "Checking ports 80, 443, 3306 and 21"
declare -A offered=()
for port in 80 443 3306 21; do
  line="$(ss -Hltnp "sport = :$port" 2>/dev/null | head -n1 || true)"
  [[ -n $line ]] || continue
  process="$(grep -oP 'users:\(\("\K[^"]+' <<<"$line" || true)"
  echo "Port $port is already used by: ${process:-an unknown program}"
  case "$process" in
    apache2) units=(apache2) ;;
    nginx) units=(nginx) ;;
    mysqld|mariadbd) units=(mysql mariadb) ;;
    *) units=() ;;
  esac
  for unit in "${units[@]}"; do
    [[ -z ${offered[$unit]:-} ]] || continue
    offered[$unit]=1
    systemctl is-active --quiet "$unit" || continue
    if ask "Stop and disable the system '$unit' service so XAMPP can use port $port?"; then
      systemctl disable --now "$unit"
    else
      echo "Keeping $unit. XAMPP's service on port $port will not start while it runs."
    fi
  done
done

say "Installing XAMPP Panel to $APP_DIR"
install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/bin" "$APP_DIR/lib" "$APP_DIR/state"
rm -rf "$APP_DIR/lib/xampp_panel"
cp -r "$SRC_DIR/src/xampp_panel" "$APP_DIR/lib/"
find "$APP_DIR/lib" -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR/lib"
chmod -R u=rwX,go=rX "$APP_DIR/lib"
python3 -I -m compileall -q "$APP_DIR/lib"
install -o root -g root -m 0755 "$SRC_DIR/bin/xampp-panel" "$SRC_DIR/bin/xampp-helper" "$APP_DIR/bin/"

installed=()
put() { install -D -o root -g root -m 0644 "$SRC_DIR/$1" "$2"; installed+=("$2"); }
put "data/io.github.shiron.xampppanel.policy" /usr/share/polkit-1/actions/io.github.shiron.xampppanel.policy
put "data/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
put "data/icons/$APP_ID.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
put "data/icons/xampp-panel-running.svg" /usr/share/icons/hicolor/scalable/status/xampp-panel-running.svg
put "data/icons/xampp-panel-stopped.svg" /usr/share/icons/hicolor/scalable/status/xampp-panel-stopped.svg
ln -sfn "$APP_DIR/bin/xampp-panel" /usr/local/bin/xampp-panel
installed+=(/usr/local/bin/xampp-panel)
printf '%s\n' "${installed[@]}" > "$APP_DIR/install-manifest.txt"
gtk-update-icon-cache -qtf /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true

say "Configuring XAMPP"
HELPER="$APP_DIR/bin/xampp-helper"
"$HELPER" integrate on
if ((ALLOW_LAN)); then
  "$HELPER" harden off
  echo "LAN access allowed: other devices on your network can reach XAMPP."
else
  "$HELPER" harden on
  echo "XAMPP now only accepts connections from this computer."
fi
case "$LEAN" in
  yes) "$HELPER" lean on ;;
  no) ;;
  ask) if ask "Turn on lean mode (fewer Apache processes, roughly 150–300 MB less RAM for MySQL)?"; then "$HELPER" lean on; fi ;;
esac

if ask "Set passwords for MySQL root and phpMyAdmin now (recommended)?"; then
  "$LAMPP/lampp" startmysql
  "$LAMPP/lampp" security </dev/tty || echo "Password setup did not finish. You can run it again with: sudo $LAMPP/lampp security"
  "$LAMPP/lampp" stopmysql
fi

say "Done"
echo "Open “XAMPP Control Panel” from your app menu, or run: xampp-panel"
echo "To remove the panel later: sudo $SRC_DIR/uninstall.sh"
```

`uninstall.sh`:
```bash
#!/usr/bin/env bash
# Remove XAMPP Panel and undo its changes to the XAMPP configuration.
set -euo pipefail
shopt -s nullglob

APP_DIR=/opt/xampp-panel
LAMPP=/opt/lampp
REMOVE_XAMPP=0

usage() {
  cat <<'EOF'
Usage: sudo ./uninstall.sh [--remove-xampp]

Removes XAMPP Panel and reverts every change it made to XAMPP's configuration
and /etc/hosts. Your ~/Sites folders are kept.

Options:
  --remove-xampp   also uninstall XAMPP itself (/opt/lampp, including databases!)
  -h, --help       show this help
EOF
}

while (($#)); do
  case "$1" in
    --remove-xampp) REMOVE_XAMPP=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run this with: sudo ./uninstall.sh"

if [[ -x $APP_DIR/bin/xampp-helper && -x $LAMPP/lampp ]]; then
  echo "Stopping XAMPP…"
  "$LAMPP/lampp" stop || true
  "$APP_DIR/bin/xampp-helper" integrate off
  "$APP_DIR/bin/xampp-helper" lean off
  "$APP_DIR/bin/xampp-helper" harden off
fi

if [[ -f $APP_DIR/install-manifest.txt ]]; then
  while IFS= read -r path; do
    case "$path" in
      /usr/share/*|/usr/local/bin/*) rm -f -- "$path" ;;
      "") ;;
      *) echo "Skipping unexpected manifest entry: $path" >&2 ;;
    esac
  done < "$APP_DIR/install-manifest.txt"
fi
rm -rf -- "$APP_DIR"
for backup in "$LAMPP"/etc/*.xampp-panel.bak "$LAMPP"/etc/extra/*.xampp-panel.bak /etc/hosts.xampp-panel.bak; do
  rm -f -- "$backup"
done
gtk-update-icon-cache -qtf /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true
if [[ -n ${SUDO_USER:-} ]]; then
  rm -f -- "$(getent passwd "$SUDO_USER" | cut -d: -f6)/.config/xampp-panel/settings.json"
fi

if ((REMOVE_XAMPP)) && [[ -x $LAMPP/uninstall ]]; then
  echo "Uninstalling XAMPP…"
  "$LAMPP/uninstall" --mode unattended
fi
echo "XAMPP Panel removed. Your ~/Sites folders were kept."
```

Then: `chmod +x setup.sh uninstall.sh`

`README.md`:
````markdown
# XAMPP Panel

A native control panel for XAMPP on Zorin OS (and other GNOME / Ubuntu 22.04+ systems).

- Start and stop Apache, MySQL and FTP with switches. You get a graphical password prompt, not `sudo` in a terminal.
- Add local sites like `http://blog.local` served from `~/Sites/blog`.
- XAMPP only listens on this computer by default. Lean mode is optional and saves RAM.
- Optional tray icon. Nothing runs at boot.

## Install

```bash
cd ~/Downloads/xampp-panel
sudo ./setup.sh
```

The script installs XAMPP from `~/Downloads/xampp-linux-x64-*-installer.run` if it isn't already in
`/opt/lampp`. Run `./setup.sh --help` for options (`--allow-lan`, `--lean`, `--installer PATH`).

## Remove

```bash
sudo ./uninstall.sh                 # removes the panel, keeps XAMPP and your data
sudo ./uninstall.sh --remove-xampp  # also removes XAMPP (including databases)
```

## Develop

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m xampp_panel.main      # run the panel from the source tree
```
````

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add setup.sh uninstall.sh README.md tests/test_scripts.py
git commit -m "feat: setup and uninstall scripts, README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Verify on the real machine (done by the user, guided)

The development sandbox can't reach `/opt` or run root commands, so these checks happen on the host. Record the results. Fix anything that fails in a follow-up task that includes a regression test where one is possible.

- [ ] **Step 1:** `cd ~/Downloads/xampp-panel && PYTHONPATH=src python3 -m unittest discover -s tests -v`. Expect all to pass, with `test_window_imports` running (not skipped).
- [ ] **Step 2:** `sudo ./setup.sh`. Answer the prompts, then confirm it finishes with "Done".
- [ ] **Step 3:** Open "XAMPP Control Panel" from the app menu. Check it follows the system light/dark style.
- [ ] **Step 4:** Toggle Apache on. You should get one password prompt, and the dot turns green. Toggle MySQL within 5 minutes: there should be **no** second prompt.
- [ ] **Step 5:** `ss -ltn | grep -E ':(80|3306) '` should show only `127.0.0.1` listeners.
- [ ] **Step 6:** Sites tab → + → name `demo` → Add. The browser should open `http://demo.local/` and show "demo.local works".
- [ ] **Step 7:** `getfacl ~/Sites/demo | grep daemon` should show `user:daemon:r-x`. `getfacl ~ | grep daemon` should show `user:daemon:--x`.
- [ ] **Step 8:** Open `http://localhost/phpmyadmin/`. It should load.
- [ ] **Step 9:** Idle check: `top -p $(pgrep -f xampp_panel -d,)` should show about 0 % CPU, and panel RES under 60 MB.
- [ ] **Step 10:** Menu → Lean mode on, then restart MySQL. `ps -o rss= -C mysqld` should drop compared with before.
- [ ] **Step 11:** Menu → Keep in tray. The tray icon appears (needs the AppIndicator extension), and its Start/Stop items work.
- [ ] **Step 12:** Remove the `demo` site, then `sudo ./uninstall.sh`. Afterwards `grep xampp-panel /opt/lampp/etc/httpd.conf /etc/hosts` should find nothing, and the app-menu entry should be gone.
