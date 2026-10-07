"""MariaDB account administration through XAMPP's mysql client (used by xampp-repair, as root).

Passwords never appear on a command line or in the environment: SQL goes in on
stdin and credentials in a private option file that is deleted right after use.
"""

import os
import re
import subprocess
import tempfile

from .helper import SAFE_ENV
from .paths import DEFAULT, Paths

MIN_PASSWORD = 8
MAX_PASSWORD = 128
PMADB = "phpmyadmin"  # the database phpMyAdmin's sql/create_tables.sql creates
PMA_USER = "pma"  # phpMyAdmin's default control user
TIMEOUT = 120  # seconds, for real work (execute, upgrade)
PROBE_TIMEOUT = 5  # seconds to connect when only checking a login (can_login, ping)
_PROBE_LIMIT = PROBE_TIMEOUT + 5  # the whole probe: connect plus "SELECT 1"

# Escaped backslashes only mean the same in every sql_mode once NO_BACKSLASH_ESCAPES is off.
_SQL_MODE = "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');\n"
_LONG_LISTS = "SET SESSION group_concat_max_len = 65536;\n"
# The server answered and refused: 1044 no access to the database, 1045 wrong password,
# 1049 no such database, 1698 a password is needed. Anything else (e.g. 2002) means it did not answer.
_REFUSED = re.compile(r"^ERROR (1044|1045|1049|1698)\b", re.M)
# The server answered but will not take this login for another reason (not a wrong password):
# 1040 too many connections, 1129 host blocked, 1130 host not allowed, 1862 password expired.
_ANSWERED = re.compile(r"^ERROR (1040|1129|1130|1862)\b")


class MysqlError(Exception):
    pass


class AccessDenied(MysqlError):
    """MySQL answered but refused the login, as opposed to not answering at all."""


def sql_quote(value: str) -> str:
    if "\0" in value:
        raise ValueError("NUL bytes are not allowed")
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def password_problem(password: str) -> str | None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        return f"Use {MIN_PASSWORD} to {MAX_PASSWORD} characters."
    if any(ord(c) < 32 or ord(c) == 127 for c in password):
        return "Control characters are not allowed."
    return None


def drop_anonymous_sql() -> str:
    """Drops every anonymous account (''@any host). MariaDB lists them itself."""
    return (_SQL_MODE + _LONG_LISTS
            + "SELECT GROUP_CONCAT(CONCAT(QUOTE(user), '@', QUOTE(host))) INTO @accounts"
              " FROM mysql.user WHERE user = '';\n"
            + "EXECUTE IMMEDIATE IF(@accounts IS NULL, 'DO 0', CONCAT('DROP USER ', @accounts));\n"
            + "SET @accounts = NULL;\n")


def set_root_password_sql(password: str) -> str:
    """Sets one password on every root account (localhost, 127.0.0.1, ::1, ...)."""
    return (_SQL_MODE + _LONG_LISTS
            + f"SET @pw = {sql_quote(password)};\n"
            + "SELECT GROUP_CONCAT(CONCAT(QUOTE(user), '@', QUOTE(host), ' IDENTIFIED BY ', QUOTE(@pw)))"
              " INTO @accounts FROM mysql.user WHERE user = 'root';\n"
            + "EXECUTE IMMEDIATE CONCAT('ALTER USER ', @accounts);\n"
            + "SET @pw = NULL, @accounts = NULL;\n")


def reset_root_sql(password: str) -> str:
    """For MariaDB's init-file, run once at startup with the grant tables on (unlike
    --skip-grant-tables, MySQL is never open without a password). One statement per line.
    Only root@localhost: the caller then sets the other root accounts with set_root_password_sql."""
    if "\n" in password or "\r" in password:
        raise ValueError("line breaks are not allowed in the password")
    return _SQL_MODE + f"ALTER USER 'root'@'localhost' IDENTIFIED BY {sql_quote(password)};\n"


def pma_account_sql(user: str, password: str) -> str:
    """Creates or updates phpMyAdmin's control user, with access to its own database only."""
    account = f"{sql_quote(user)}@'localhost'"
    return (_SQL_MODE
            + f"CREATE USER IF NOT EXISTS {account};\n"
            + f"ALTER USER {account} IDENTIFIED BY {sql_quote(password)};\n"
            + f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{PMADB}`.* TO {account};\n")


def _option_value(value: str) -> str:
    """A double-quoted option-file value; \\ and \" are the option file's escapes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MysqlAdmin:
    def __init__(self, paths: Paths = DEFAULT, run=subprocess.run):
        self.paths = paths
        self.run = run

    def _client(self, program, user: str, password: str, args=(), sql: str = "", timeout: int = TIMEOUT) -> str:
        name = os.path.basename(str(program))
        fd, option_file = tempfile.mkstemp(prefix="xampp-repair-", suffix=".cnf")  # mode 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"[client]\nuser={_option_value(user)}\n")
                if password:
                    fh.write(f"password={_option_value(password)}\n")
            argv = [str(program), f"--defaults-extra-file={option_file}", *args]
            try:
                proc = self.run(argv, input=sql, env=SAFE_ENV, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise MysqlError(f"{name} did not finish within {timeout} seconds") from None
        finally:
            os.unlink(option_file)
        if proc.returncode != 0:
            lines = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()]
            error = AccessDenied if _REFUSED.search(proc.stderr or "") else MysqlError
            raise error(lines[-1].strip() if lines else f"{name} failed")
        return proc.stdout

    def execute(self, sql: str, root_password: str) -> str:
        return self._client(self.paths.mysql_client, "root", root_password, ["--batch", "--skip-column-names"], sql)

    def can_login(self, user: str, password: str, database: str | None = None) -> bool:
        args = ["--batch", "--skip-column-names", f"--connect-timeout={PROBE_TIMEOUT}"]
        args += [database] if database else []
        try:
            self._client(self.paths.mysql_client, user, password, args, "SELECT 1;\n", _PROBE_LIMIT)
        except AccessDenied:
            return False
        return True

    def ping(self) -> bool:
        """True once the server answers, even if it refuses the login (empty root password or otherwise)."""
        try:
            self.can_login("root", "")
        except MysqlError as e:
            return bool(_ANSWERED.match(str(e)))
        return True

    def anonymous_accounts(self, root_password: str) -> list[str]:
        out = self.execute("SELECT CONCAT(QUOTE(user), '@', QUOTE(host)) FROM mysql.user WHERE user = '';\n",
                           root_password)
        return [line for line in out.splitlines() if line.strip()]

    def upgrade(self, root_password: str) -> str:
        return self._client(self.paths.mysql_upgrade, "root", root_password)
