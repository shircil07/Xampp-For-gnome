"""xampp-repair: a whiptail menu to configure XAMPP and fix known problems.

Runs as root (sudo in a terminal the panel opens, or from setup.sh).
`xampp-repair first-install` replaces XAMPP's "lampp security" during setup.
"""

import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time

from . import configedit, fsutil, health, pmaconfig, services, sites
from .dialogs import Dialogs
from .helper import SAFE_ENV, Helper, HelperFailure
from .mysqladmin import (PMA_USER, PMADB, MysqlAdmin, MysqlError, drop_anonymous_sql, password_problem,
                         pma_account_sql, set_root_password_sql)
from .paths import DEFAULT, Paths

PMA_PASSWORD_BYTES = 24  # secrets.token_urlsafe(24): 32 characters from [A-Za-z0-9_-]
MYSQL_START_SECONDS = 20
USAGE = "usage: sudo xampp-repair [first-install]"
_FAILURES = (MysqlError, HelperFailure, OSError, ValueError, subprocess.SubprocessError)
# The control user's password gets reset, so it must not be able to name root or anything odd.
_PMA_USER_NAME = re.compile(r"[A-Za-z0-9_]{1,32}")


class RepairError(Exception):
    pass


class Cancelled(Exception):
    pass


class RepairApp:
    def __init__(self, dialogs, admin, helper, paths: Paths = DEFAULT, run=subprocess.run,
                 token=secrets.token_urlsafe, mysql_running=None, sleep=time.sleep):
        self.dialogs = dialogs
        self.admin = admin
        self.helper = helper
        self.paths = paths
        self.run = run
        self.token = token
        # A running mysqld counts even when its port is not listening (skip-networking):
        # the client still reaches it through the socket.
        self.mysql_running = mysql_running or (lambda: "mysql" in services.running_services(paths))
        self.sleep = sleep
        self.check = health.HealthCheck(admin, paths, run)
        self.root_password: str | None = None  # None = not known yet, "" = root has no password

    # -- menu -------------------------------------------------------------
    def menu_items(self):
        return [
            ("1", "Health check", self.health_check),
            ("2", health.FIX_ROOT, self.change_root_password),
            ("3", "Show phpMyAdmin pma password", self.show_pma_password),
            ("4", health.FIX_PMA, self.fix_pma),
            ("5", health.FIX_FTP, self.fix_ftp),
            ("6", health.FIX_NETWORK, self.fix_networking),
            ("7", "Run mysql_upgrade", self.mysql_upgrade),
            ("8", health.FIX_REAPPLY, self.reapply),
            ("q", "Quit", None),
        ]

    def main_menu(self) -> int:
        items = self.menu_items()
        actions = {tag: action for tag, _, action in items}
        while True:
            action = actions.get(self.dialogs.menu("Choose what to do:", [(t, label) for t, label, _ in items]))
            if action is None:
                return 0
            self._attempt(action)

    def _attempt(self, action) -> bool:
        try:
            action()
            return True
        except Cancelled:
            return False
        except (RepairError, *_FAILURES) as e:
            self.dialogs.msgbox(f"That did not work:\n\n{e}")
            return False

    # -- shared steps -----------------------------------------------------
    def _ensure_mysql(self) -> bool:
        """Start MySQL if needed. Returns True if this call started it."""
        if self.mysql_running():
            return False
        print("Starting MySQL (it is needed for this)…", file=sys.stderr)
        self.helper.lampp(["startmysql"])
        for _ in range(MYSQL_START_SECONDS):
            if self.mysql_running():
                return True
            self.sleep(1)
        raise RepairError("MySQL did not start. Check its log in the panel.")

    def _root(self) -> str:
        """The current root password, asked once per session ("" if root has none)."""
        if self.root_password is None:
            if self.admin.can_login("root", ""):
                self.root_password = ""
            else:
                while True:
                    answer = self.dialogs.passwordbox("Current MySQL root password:")
                    if answer is None:
                        raise Cancelled()
                    if self.admin.can_login("root", answer):
                        self.root_password = answer
                        break
                    self.dialogs.msgbox("That password is not right. Try again.")
        return self.root_password

    def _new_password(self, prompt: str, allow_skip: bool = False) -> str | None:
        """Asks twice. Cancel/Esc on either prompt (or an empty first answer when allow_skip)
        returns None if allow_skip, else raises Cancelled."""
        while True:
            first = self.dialogs.passwordbox(prompt)
            if first is None or (allow_skip and first == ""):
                return self._cancel(allow_skip)
            problem = password_problem(first)
            if problem:
                self.dialogs.msgbox(problem)
                continue
            second = self.dialogs.passwordbox("Repeat it:")
            if second is None:
                return self._cancel(allow_skip)
            if second == first:
                return first
            self.dialogs.msgbox("The passwords don't match. Try again.")

    @staticmethod
    def _cancel(allow_skip: bool) -> None:
        if not allow_skip:
            raise Cancelled()

    def _write(self, path, text: str) -> None:
        if text != path.read_text():
            fsutil.backup_once(path)
            fsutil.atomic_write(path, text)

    # -- actions ----------------------------------------------------------
    def health_check(self) -> None:
        self.dialogs.msgbox(health.render(self.check.run_checks(self.root_password)))

    def change_root_password(self) -> None:
        self._ensure_mysql()
        current = self._root()
        self._set_root_password(current, self._new_password("New MySQL root password:"))
        self.dialogs.msgbox("Done. Log in to phpMyAdmin as 'root' with the new password.")

    def _set_root_password(self, current: str, new: str | None) -> None:
        """Drop anonymous accounts and set the root password; only then give phpMyAdmin a login page."""
        self.admin.execute(drop_anonymous_sql() + (set_root_password_sql(new) if new else ""), current)
        if new:
            self.root_password = new
            conf = self.paths.phpmyadmin_conf
            if conf.exists():
                text = conf.read_text()
                if pmaconfig.get_value(text, "auth_type") == "config":
                    self._write(conf, pmaconfig.set_value(text, "auth_type", "cookie"))

    def show_pma_password(self) -> None:
        text = self.paths.phpmyadmin_conf.read_text()
        user = pmaconfig.get_value(text, "controluser")
        password = pmaconfig.get_value(text, "controlpass")
        if not user or not password:
            self.dialogs.msgbox(f"phpMyAdmin's control user is not set up yet. Use “{health.FIX_PMA}”.")
            return
        if self.dialogs.yesno("This shows a password on screen. Continue?"):
            self.dialogs.secret("phpMyAdmin control user",
                                f"User:     {user}\nPassword: {password}\n\n"
                                "phpMyAdmin uses this account itself; you never need to type it.")

    def fix_pma(self) -> None:
        self._ensure_mysql()
        user = self._setup_pma(fresh=False)
        self.dialogs.msgbox(f"Done. phpMyAdmin's control user '{user}' can log in. Reload phpMyAdmin.")

    def _setup_pma(self, fresh: bool) -> str:
        """Create/update the control user. The config is only written after MySQL accepted the account."""
        conf = self.paths.phpmyadmin_conf
        text = conf.read_text()
        db = pmaconfig.get_value(text, "pmadb")
        if db not in (None, "", PMADB):
            raise RepairError(f"phpMyAdmin's pmadb is '{db}'; only '{PMADB}' is supported.")
        user = self._pma_user(text)
        password = pmaconfig.get_value(text, "controlpass") or ""
        if fresh or not password:
            password = self.token(PMA_PASSWORD_BYTES)
        tables = self.paths.pma_tables_sql.read_text()
        self.admin.execute(tables + "\n" + pma_account_sql(user, password), self._root())
        for key, value in (("controluser", user), ("controlpass", password), ("pmadb", PMADB)):
            text = pmaconfig.set_value(text, key, value)
        self._write(conf, text)
        if not self.admin.can_login(user, password, PMADB):
            raise RepairError(f"The account was set up, but '{user}' still cannot log in.")
        return user

    def _pma_user(self, text: str) -> str:
        user = pmaconfig.get_value(text, "controluser") or PMA_USER
        if not _PMA_USER_NAME.fullmatch(user) or user.lower() == "root":
            raise RepairError(f"phpMyAdmin's controluser is '{user}'; it should be '{PMA_USER}'. "
                              f"Change it in {self.paths.phpmyadmin_conf} and try again.")
        return user

    def fix_ftp(self) -> None:
        conf = self.paths.proftpd_conf
        old = conf.read_text()
        if not configedit.proftpd_password_broken(old) and not self.dialogs.yesno(
                "The FTP config looks fine. Set a new password for the FTP user 'daemon' anyway?"):
            return
        password = self._new_password("New FTP password for the user 'daemon':")
        proc = self.run(["openssl", "passwd", "-6", "-stdin"], input=password + "\n", env=SAFE_ENV,
                        capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RepairError(f"openssl could not hash the password: {proc.stderr.strip()}")
        self._write(conf, configedit.proftpd_set_password(old, proc.stdout.strip()))
        ok, detail = self.check.command([self.paths.proftpd_bin, "-t", "-c", conf])
        if not ok:
            fsutil.atomic_write(conf, old)
            raise RepairError(f"ProFTPD rejected the new config, so the old one was put back:\n{detail}")
        self.dialogs.msgbox("Done. Start FTP from the panel and log in as 'daemon' with the new password.")

    def fix_networking(self) -> None:
        conf = self.paths.my_cnf
        text = conf.read_text()
        if not configedit.mysql_networking_off(text):
            self.dialogs.msgbox("MySQL networking is already on.")
            return
        self._write(conf, configedit.mysql_networking_on(text))
        if self.mysql_running() and self.dialogs.yesno("Done. Restart MySQL now to apply it?"):
            self.helper.lampp(["stopmysql", "startmysql"])
        elif not self.mysql_running():
            self.dialogs.msgbox("Done. Start MySQL from the panel.")

    def mysql_upgrade(self) -> None:
        self._ensure_mysql()
        tail = "\n".join(self.admin.upgrade(self._root()).strip().splitlines()[-15:])
        self.dialogs.msgbox(f"mysql_upgrade finished:\n\n{tail}\n\nRestart MySQL from the panel.")

    def reapply(self) -> None:
        local_only = self.dialogs.yesno("Only allow this computer to reach XAMPP? (recommended; "
                                        "choose No if you set it up with --allow-lan)")
        lean = self.dialogs.yesno("Use lean mode (fewer idle Apache processes, smaller MySQL)?")
        self.helper.integrate(True)
        self.helper.harden(local_only)
        self.helper.lean(lean)
        self.helper.apply_sites(sites.load(self.paths.state_file))
        self.dialogs.msgbox("Done. Restart Apache and MySQL from the panel to apply.")

    # -- first install ----------------------------------------------------
    def first_install(self) -> int:
        """setup.sh's replacement for "lampp security". Never raises; returns 1 if a step failed."""
        try:
            started = self._ensure_mysql()
        except (RepairError, *_FAILURES) as e:
            print(f"MySQL did not start, so its accounts were not set up: {e}\n"
                  "Do it later with: sudo xampp-repair", file=sys.stderr)
            return 1
        notes: list[str] = []  # printed at the end, after the last whiptail screen
        ok = self._step("phpMyAdmin control user", lambda: self._first_pma(notes), health.FIX_PMA)
        ok = self._step("MySQL root password", lambda: self._first_root_password(notes), health.FIX_ROOT) and ok
        if started:
            try:
                self.helper.lampp(["stopmysql"])
            except HelperFailure as e:
                print(f"warning: MySQL did not stop: {e}", file=sys.stderr)
        for note in notes:
            print(note)
        return 0 if ok else 1

    def _step(self, name: str, step, fix: str) -> bool:
        try:
            step()
            return True
        except Cancelled:
            self.dialogs.msgbox(f"{name}: skipped. Later: sudo xampp-repair → {fix}")
        except (RepairError, *_FAILURES) as e:
            self.dialogs.msgbox(f"{name} did not work:\n\n{e}\n\nLater: sudo xampp-repair → {fix}")
        return False

    def _first_pma(self, notes: list[str]) -> None:
        """Re-running setup.sh keeps a control user that already logs in; otherwise sets it up fresh."""
        text = self.paths.phpmyadmin_conf.read_text()
        user = self._pma_user(text)
        password = pmaconfig.get_value(text, "controlpass")
        configured = (pmaconfig.get_value(text, "controluser") and password
                      and pmaconfig.get_value(text, "pmadb") == PMADB)  # what the health check calls set up
        if configured and self.admin.can_login(user, password, PMADB):
            notes.append(f"phpMyAdmin control user '{user}': already working, left as it is.")
            return
        self._setup_pma(fresh=True)

    def _first_root_password(self, notes: list[str]) -> None:
        """Only a root without a password is asked for one; an existing password is never asked for here."""
        if not self.admin.can_login("root", ""):
            notes.append(f"MySQL root already has a password: kept. "
                         f"To change it: sudo xampp-repair → {health.FIX_ROOT}")
            return
        new = self._new_password("Choose a MySQL root password.\n\nLeave it empty to skip "
                                 "(the panel will remind you).", allow_skip=True)
        self._set_root_password("", new)


def _exit(signum, frame):
    raise SystemExit(128 + signum)


def exit_on_signals() -> None:
    """Closing the terminal (SIGHUP) or a kill (SIGTERM) exits through Python, so `finally`
    blocks still delete the 0600 temp files that hold passwords."""
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, _exit)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv not in ([], ["first-install"]):
        print(USAGE, file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("xampp-repair must run as root: sudo xampp-repair", file=sys.stderr)
        return 1
    if shutil.which("whiptail") is None:
        print("whiptail is missing: sudo apt install whiptail", file=sys.stderr)
        return 1
    os.umask(0o022)
    exit_on_signals()
    app = RepairApp(Dialogs(), MysqlAdmin(), Helper())
    try:
        return app.first_install() if argv else app.main_menu()
    except KeyboardInterrupt:
        return 130
