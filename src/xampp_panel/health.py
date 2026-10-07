"""Read-only health report for xampp-repair. Each problem names the menu item that fixes it."""

import subprocess
from dataclasses import dataclass

from . import configedit, pmaconfig, services, sites
from .helper import SAFE_ENV
from .mysqladmin import PMADB, MysqlError
from .paths import DEFAULT, Paths
from .services import State

# Labels of the xampp-repair menu items that fix a problem.
FIX_ROOT = "Change MySQL root password"
FIX_RESET = "Reset forgotten MySQL root password"
FIX_PMA = "Fix phpMyAdmin pma login"
FIX_FTP = "Fix FTP config"
FIX_NETWORK = "Turn MySQL networking back on"
FIX_REAPPLY = "Re-apply panel config"
COMMAND_TIMEOUT = 30  # seconds


@dataclass(frozen=True)
class Finding:
    ok: bool
    text: str
    fix: str = ""


def render(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        lines.append(f"{'OK ' if f.ok else 'FIX'}  {f.text}")
        if f.fix:
            lines.append(f"      → {f.fix}")
    problems = sum(not f.ok for f in findings)
    lines += ["", f"{problems} problem(s) found." if problems else "No problems found."]
    return "\n".join(lines)


class HealthCheck:
    def __init__(self, admin, paths: Paths = DEFAULT, run=subprocess.run, snapshot=services.snapshot):
        self.admin = admin
        self.paths = paths
        self.run = run
        self.snapshot = snapshot

    def command(self, argv) -> tuple[bool, str]:
        """Run a config test; returns (ok, last line of its output)."""
        try:
            proc = self.run([str(a) for a in argv], env=SAFE_ENV, capture_output=True, text=True,
                            timeout=COMMAND_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)
        lines = [line for line in (proc.stderr + proc.stdout).splitlines() if line.strip()]
        return proc.returncode == 0, (lines[-1].strip() if lines else "")

    def run_checks(self, root_password: str | None) -> list[Finding]:
        """root_password: None when not known yet; checks that need it are skipped."""
        states = self.snapshot(self.paths)
        findings = self._services(states) + self._configs()
        if states["mysql"] in (State.RUNNING, State.STARTING):  # STARTING: no port, but the socket works
            findings += self._mysql(root_password)
        else:
            findings.append(Finding(True, "MySQL is not running: account checks skipped"))
        return findings + self._sites()

    def _services(self, states) -> list[Finding]:
        findings = []
        for svc in services.SERVICES:
            state = states[svc.key]
            if state is State.RUNNING:
                findings.append(Finding(True, f"{svc.title} is running (port {svc.port})"))
            elif state is State.STOPPED:
                findings.append(Finding(True, f"{svc.title} is stopped"))
            elif state is State.STARTING:
                findings.append(Finding(False, f"{svc.title} is running but port {svc.port} is not listening",
                                        FIX_NETWORK if svc.key == "mysql" else ""))
            else:
                findings.append(Finding(False, f"Port {svc.port} is used by another program "
                                               f"(see: sudo ss -ltnp 'sport = :{svc.port}')"))
        return findings

    def _configs(self) -> list[Finding]:
        p = self.paths
        findings = []
        try:
            if configedit.mysql_networking_off(p.my_cnf.read_text()):
                findings.append(Finding(False, "MySQL networking is switched off (skip-networking)", FIX_NETWORK))
            else:
                findings.append(Finding(True, "MySQL networking is on"))
        except OSError as e:
            findings.append(Finding(False, f"Cannot read {p.my_cnf}: {e}"))
        ok, detail = self.command([p.apachectl, "-t"])
        findings.append(Finding(ok, "Apache config is valid" if ok else f"Apache config error: {detail}"))
        if p.proftpd_conf.exists():
            if configedit.proftpd_password_broken(p.proftpd_conf.read_text()):
                findings.append(Finding(False, "FTP config was damaged by 'lampp security'", FIX_FTP))
            elif p.proftpd_bin.exists():
                ok, detail = self.command([p.proftpd_bin, "-t", "-c", p.proftpd_conf])
                findings.append(Finding(ok, "FTP config is valid" if ok else f"FTP config error: {detail}",
                                        "" if ok else FIX_FTP))
        return findings

    def _mysql(self, root_password: str | None) -> list[Finding]:
        findings = []
        try:
            root_open = self.admin.can_login("root", "")
        except MysqlError as e:  # still starting, or the socket is gone: no account check can run
            return [Finding(False, f"MySQL: cannot connect: {e}")]
        if root_open:
            findings.append(Finding(False, "MySQL root has no password", FIX_ROOT))
            root_password = ""
        else:
            findings.append(Finding(True, "MySQL root has a password"))
        if root_password is None:
            findings.append(Finding(True, "Anonymous accounts not checked (root password not entered yet)"))
        else:
            try:
                anonymous = self.admin.anonymous_accounts(root_password)
                findings.append(Finding(not anonymous, "No anonymous MySQL accounts" if not anonymous
                                        else f"Anonymous MySQL accounts exist: {', '.join(anonymous)}",
                                        "" if not anonymous else FIX_ROOT))
            except MysqlError as e:
                findings.append(Finding(False, f"Could not list MySQL accounts: {e}"))
        findings.append(self._pma())
        return findings

    def _pma(self) -> Finding:
        try:
            text = self.paths.phpmyadmin_conf.read_text()
        except OSError as e:
            return Finding(False, f"Cannot read phpMyAdmin's config: {e}", FIX_PMA)
        user = pmaconfig.get_value(text, "controluser")
        password = pmaconfig.get_value(text, "controlpass")
        if not user or not password:
            return Finding(False, "phpMyAdmin's control user is not set up", FIX_PMA)
        if pmaconfig.get_value(text, "pmadb") != PMADB:
            return Finding(False, f"phpMyAdmin's pmadb is not '{PMADB}'", FIX_PMA)
        try:
            login = self.admin.can_login(user, password, PMADB)
        except MysqlError as e:
            return Finding(False, f"MySQL: cannot connect: {e}")
        if not login:
            return Finding(False, f"phpMyAdmin's control user '{user}' cannot log in", FIX_PMA)
        return Finding(True, f"phpMyAdmin's control user '{user}' can log in")

    def _sites(self) -> list[Finding]:
        p = self.paths
        try:
            if not configedit.has_block(p.httpd_conf.read_text(), "vhosts"):
                return [Finding(False, "The panel's sites setup is missing from httpd.conf", FIX_REAPPLY)]
            hosts = p.hosts.read_text()
            missing = [s.name for s in sites.load(p.state_file) if f"{s.name}.local" not in hosts]
        except (OSError, ValueError, KeyError) as e:
            return [Finding(False, f"Cannot check sites: {e}")]
        if missing:
            return [Finding(False, f"Sites missing from /etc/hosts: {', '.join(missing)}", FIX_REAPPLY)]
        return [Finding(True, "Sites are set up")]
