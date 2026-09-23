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
