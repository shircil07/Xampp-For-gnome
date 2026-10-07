# Repair Menu and Safe First-Install Passwords Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `lampp security` with an installed `xampp-repair` whiptail menu (also used by `setup.sh` on first install) that sets MySQL/phpMyAdmin accounts safely and repairs known XAMPP breakages.

**Architecture:** New pure modules (`pmaconfig`, `mysqladmin` SQL builders, `configedit` additions) hold all logic and are unit-tested; `MysqlAdmin` runs XAMPP's `mysql` client with SQL on stdin and credentials in a 0600 option file; `repair.RepairApp` wires whiptail `Dialogs` to the logic and runs as root via `sudo` in a terminal the panel opens.

**Tech Stack:** Python ≥ 3.10 stdlib only, whiptail, GTK4/libadwaita (panel only), bash (`setup.sh`), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-06-repair-menu-design.md`

## Global Constraints

- Stdlib only, Python ≥ 3.10 (code uses `match`, `X | None`). No new pip dependencies.
- Run tests with: `PYTHONPATH=src python3 -m unittest discover -s tests` (must say OK). Tests never touch real `/opt`, `/etc`, MySQL or sudo: use `Paths(...)` overrides and fakes.
- Passwords never on argv or in the environment. SQL goes on stdin; MySQL credentials go in a `tempfile.mkstemp` option file (mode 0600) deleted in `finally`.
- Every SQL batch that contains escaped values starts with `SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');`. Escaping: `\` → `\\`, `'` → `''`.
- Config edits: `fsutil.backup_once(path)` then `fsutil.atomic_write(path, text)` (keeps mode **and owner**, see Task 1).
- MySQL root password rules: 8–128 characters, no control characters (ord < 32 or 127), kept verbatim (leading/trailing spaces allowed).
- Generated phpMyAdmin control password: `secrets.token_urlsafe(24)`; control user default `pma`; storage database exactly `phpmyadmin`.
- Commits: `git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit ...`. **No** `Co-Authored-By` or any AI attribution. Never push.
- Match surrounding code style: short module docstring, comments only where the "why" is not obvious, type hints on public functions.

## File Structure

| File | Responsibility |
|---|---|
| `src/xampp_panel/fsutil.py` (modify) | `atomic_write` also keeps the file's owner/group |
| `src/xampp_panel/paths.py` (modify) | New paths: `phpmyadmin_conf`, `pma_tables_sql`, `mysql_upgrade`, `proftpd_bin`, `repair` |
| `src/xampp_panel/pmaconfig.py` (new) | Read/write single-quoted `$cfg['Servers'][$i][...]` settings in phpMyAdmin's config as text |
| `src/xampp_panel/mysqladmin.py` (new) | SQL builders, password rules, `MysqlAdmin` client runner |
| `src/xampp_panel/configedit.py` (modify) | ProFTPD broken-password detection/repair, MySQL networking/hardening detection |
| `src/xampp_panel/dialogs.py` (new) | `Dialogs`: whiptail wrapper |
| `src/xampp_panel/health.py` (new) | `HealthCheck` read-only report + menu labels of fixes |
| `src/xampp_panel/repair.py` (new) | `RepairApp` menu + flows + `first-install`; `main()` |
| `bin/xampp-repair` (new) | Installed launcher |
| `src/xampp_panel/terminal.py` (new) | Pick a terminal emulator and build its argv (pure) |
| `src/xampp_panel/window.py` (modify) | ☰ "Repair & configure…", banner text |
| `setup.sh` (modify) | whiptail package, install `xampp-repair`, replace `lampp security` |
| `tests/fakes.py` (new) | `FakeDialogs`, `FakeAdmin`, `FakeHelper`, `FakeRun` shared by tests |
| `tools/` (delete) | Superseded by `xampp-repair` |
| docs (modify) | README, `docs/MAINTAINER.md`, `docs/USER-GUIDE.md` |

---

### Task 1: Keep file owner on atomic writes; new paths

phpMyAdmin's `config.inc.php` is owned by `daemon` with mode 0600. `atomic_write` (running as root) creates a temp file owned by root and renames it over the original, so Apache could no longer read the config. Fix that first.

**Files:**
- Modify: `src/xampp_panel/fsutil.py` (`atomic_write`)
- Modify: `src/xampp_panel/paths.py`
- Test: `tests/test_fsutil.py`, `tests/test_paths.py`

**Interfaces:**
- Produces: `atomic_write(path, text, mode=None)` keeps uid/gid of an existing file. `Paths.phpmyadmin_conf`, `Paths.pma_tables_sql`, `Paths.mysql_upgrade`, `Paths.proftpd_bin`, `Paths.repair` (all `Path`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fsutil.py` (keep existing imports; add `from unittest import mock` and `import os` if missing):

```python
class AtomicWriteOwnerTest(unittest.TestCase):
    def test_keeps_owner_and_group_of_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.inc.php"
            path.write_text("old")
            st = path.stat()
            calls = []
            real_fchown = os.fchown
            with mock.patch("os.fchown", side_effect=lambda fd, uid, gid: calls.append((uid, gid)) or real_fchown(fd, uid, gid)):
                fsutil.atomic_write(path, "new")
            self.assertEqual(calls, [(st.st_uid, st.st_gid)])
            self.assertEqual(path.read_text(), "new")

    def test_new_file_is_not_chowned(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("os.fchown") as fchown:
                fsutil.atomic_write(Path(d) / "new.conf", "x")
            fchown.assert_not_called()
```

Append to `tests/test_paths.py`:

```python
class RepairPathsTest(unittest.TestCase):
    def test_repair_paths(self):
        p = Paths(lampp=Path("/l"), app=Path("/a"))
        self.assertEqual(p.phpmyadmin_conf, Path("/l/phpmyadmin/config.inc.php"))
        self.assertEqual(p.pma_tables_sql, Path("/l/phpmyadmin/sql/create_tables.sql"))
        self.assertEqual(p.mysql_upgrade, Path("/l/bin/mysql_upgrade"))
        self.assertEqual(p.proftpd_bin, Path("/l/sbin/proftpd"))
        self.assertEqual(p.repair, Path("/a/bin/xampp-repair"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_fsutil tests.test_paths -v`
Expected: FAIL (`calls == []`, `AttributeError: 'Paths' object has no attribute 'phpmyadmin_conf'`).

- [ ] **Step 3: Implement**

In `fsutil.atomic_write`, replace the mode lookup and the write block with:

```python
    path = Path(path)
    owner = None
    try:
        st = path.stat()
        owner = (st.st_uid, st.st_gid)
        if mode is None:
            mode = st.st_mode & 0o7777
    except FileNotFoundError:
        if mode is None:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if owner is not None:
                os.fchown(fh.fileno(), *owner)  # root rewriting a daemon-owned file must not take it over
            os.fchmod(fh.fileno(), mode)
            fh.write(text)
```

(keep the rest — `flush`, `fsync`, `os.replace`, cleanup — unchanged; update the docstring to "Keeps the existing file's owner and permission bits unless `mode` is given.")

In `paths.py`, add after `mysql_client`:

```python
    @property
    def mysql_upgrade(self) -> Path:
        return self.lampp / "bin/mysql_upgrade"

    @property
    def proftpd_bin(self) -> Path:
        return self.lampp / "sbin/proftpd"

    @property
    def phpmyadmin_conf(self) -> Path:
        return self.lampp / "phpmyadmin/config.inc.php"

    @property
    def pma_tables_sql(self) -> Path:
        return self.lampp / "phpmyadmin/sql/create_tables.sql"
```

and after `launcher`:

```python
    @property
    def repair(self) -> Path:
        return self.app / "bin/xampp-repair"
```

- [ ] **Step 4: Run all tests**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/fsutil.py src/xampp_panel/paths.py tests/test_fsutil.py tests/test_paths.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "fix: keep file owner on atomic writes; add repair paths"
```

---

### Task 2: `pmaconfig` — phpMyAdmin settings as text

**Files:**
- Create: `src/xampp_panel/pmaconfig.py`
- Test: `tests/test_pmaconfig.py`

**Interfaces:**
- Produces: `KEYS: tuple[str, ...]`, `get_value(text: str, key: str) -> str | None`, `set_value(text: str, key: str, value: str) -> str` (raises `ValueError` for unknown key or a value with `\n`, `\r`, `\0`).

- [ ] **Step 1: Write the failing tests** — `tests/test_pmaconfig.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_pmaconfig -v`
Expected: FAIL with `ImportError: cannot import name 'pmaconfig'`.

- [ ] **Step 3: Implement** — `src/xampp_panel/pmaconfig.py`:

```python
"""Text edits for phpMyAdmin's config.inc.php.

The file is parsed as text and never executed. Only one-line assignments of
single-quoted strings are read or written, e.g.
    $cfg['Servers'][$i]['controlpass'] = 'secret';
"""

import re

KEYS = ("auth_type", "controluser", "controlpass", "pmadb")
_ASSIGN = r"""(?m)^([ \t]*\$cfg\['Servers'\]\[\$i\]\['KEY'\][ \t]*=[ \t]*)'((?:[^'\\\n]|\\.)*)'([ \t]*;.*)$"""
_SERVER_LINE = re.compile(r"(?m)^[ \t]*\$cfg\['Servers'\]\[\$i\]\[.*$")
_PHP_ESCAPE = re.compile(r"\\([\\'])")


def _pattern(key: str) -> re.Pattern:
    if key not in KEYS:
        raise ValueError(f"unsupported phpMyAdmin setting: {key}")
    return re.compile(_ASSIGN.replace("KEY", key))


def get_value(text: str, key: str) -> str | None:
    """Value of the last active assignment of `key` (commented-out lines are ignored), or None."""
    matches = list(_pattern(key).finditer(text))
    return _PHP_ESCAPE.sub(r"\1", matches[-1][2]) if matches else None


def set_value(text: str, key: str, value: str) -> str:
    """Rewrite the last active assignment of `key`, or add one after the last server setting."""
    if any(c in value for c in "\n\r\0"):
        raise ValueError("phpMyAdmin settings cannot contain line breaks or NUL")
    literal = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    matches = list(_pattern(key).finditer(text))
    if matches:
        m = matches[-1]
        return text[:m.start()] + m[1] + literal + m[3] + text[m.end():]
    line = f"$cfg['Servers'][$i]['{key}'] = {literal};"
    servers = list(_SERVER_LINE.finditer(text))
    if servers:
        end = servers[-1].end()
        return text[:end] + "\n" + line + text[end:]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"
```

- [ ] **Step 4: Run tests** — `PYTHONPATH=src python3 -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/pmaconfig.py tests/test_pmaconfig.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: read and write phpMyAdmin settings as text"
```

---

### Task 3: `mysqladmin` — SQL builders and client runner

**Files:**
- Create: `src/xampp_panel/mysqladmin.py`
- Test: `tests/test_mysqladmin.py`

**Interfaces:**
- Consumes: `Paths.mysql_client`, `Paths.mysql_upgrade` (Task 1); `helper.SAFE_ENV`.
- Produces: `MIN_PASSWORD = 8`, `MAX_PASSWORD = 128`, `PMADB = "phpmyadmin"`, `class MysqlError(Exception)`, `sql_quote(value: str) -> str`, `password_problem(password: str) -> str | None`, `drop_anonymous_sql() -> str`, `set_root_password_sql(password: str) -> str`, `pma_account_sql(user: str, password: str) -> str`, `class MysqlAdmin(paths=DEFAULT, run=subprocess.run)` with `execute(sql: str, root_password: str) -> str`, `can_login(user: str, password: str, database: str | None = None) -> bool`, `anonymous_accounts(root_password: str) -> list[str]`, `upgrade(root_password: str) -> str`.

- [ ] **Step 1: Write the failing tests** — `tests/test_mysqladmin.py`:

```python
import os
import stat
import subprocess
import unittest
from pathlib import Path

from xampp_panel import mysqladmin
from xampp_panel.paths import Paths

GUARD = "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');"


class SqlTest(unittest.TestCase):
    def test_sql_quote(self):
        self.assertEqual(mysqladmin.sql_quote("a'b\\c"), "'a''b\\\\c'")
        with self.assertRaises(ValueError):
            mysqladmin.sql_quote("a\0b")

    def test_password_problem(self):
        self.assertIsNone(mysqladmin.password_problem("  pass word  "))
        self.assertIsNotNone(mysqladmin.password_problem("short"))
        self.assertIsNotNone(mysqladmin.password_problem("x" * 129))
        self.assertIsNotNone(mysqladmin.password_problem("tab\there1"))
        self.assertIsNotNone(mysqladmin.password_problem("del\x7fhere1"))

    def test_drop_anonymous_lets_mariadb_list_accounts(self):
        sql = mysqladmin.drop_anonymous_sql()
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("FROM mysql.user WHERE user = '';", sql)
        self.assertIn("EXECUTE IMMEDIATE IF(@accounts IS NULL, 'DO 0', CONCAT('DROP USER ', @accounts));", sql)

    def test_set_root_password_escapes_once(self):
        sql = mysqladmin.set_root_password_sql("a'b\\c$x`y")
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("SET @pw = 'a''b\\\\c$x`y';", sql)
        self.assertEqual(sql.count("a''b"), 1)
        self.assertIn("FROM mysql.user WHERE user = 'root';", sql)
        self.assertTrue(sql.rstrip().endswith("SET @pw = NULL, @accounts = NULL;"))

    def test_pma_account_sql(self):
        sql = mysqladmin.pma_account_sql("p'ma", "s3cret")
        self.assertTrue(sql.startswith(GUARD))
        self.assertIn("CREATE USER IF NOT EXISTS 'p''ma'@'localhost';", sql)
        self.assertIn("ALTER USER 'p''ma'@'localhost' IDENTIFIED BY 's3cret';", sql)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON `phpmyadmin`.* TO 'p''ma'@'localhost';", sql)


class RecordingRun:
    """Fake subprocess.run that captures the option file while it still exists."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.calls = []

    def __call__(self, argv, **kwargs):
        option_file = argv[1].split("=", 1)[1]
        mode = stat.S_IMODE(os.stat(option_file).st_mode)
        self.calls.append({"argv": argv, "kwargs": kwargs, "option_file": option_file,
                           "options": Path(option_file).read_text(), "mode": mode})
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


class MysqlAdminTest(unittest.TestCase):
    def setUp(self):
        self.paths = Paths(lampp=Path("/l"))

    def test_execute_keeps_secrets_off_argv_and_env(self):
        run = RecordingRun(stdout="ok\n")
        out = mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", 'pa"ss\\word')
        self.assertEqual(out, "ok\n")
        call = run.calls[0]
        self.assertEqual(call["argv"][0], "/l/bin/mysql")
        self.assertTrue(call["argv"][1].startswith("--defaults-extra-file="))
        self.assertNotIn("pa", " ".join(call["argv"][2:]))
        self.assertEqual(call["kwargs"]["input"], "SELECT 1;")
        self.assertNotIn("MYSQL_PWD", call["kwargs"]["env"])
        self.assertEqual(call["mode"], 0o600)
        self.assertEqual(call["options"], '[client]\nuser="root"\npassword="pa\\"ss\\\\word"\n')
        self.assertFalse(os.path.exists(call["option_file"]))

    def test_empty_password_writes_no_password_line(self):
        run = RecordingRun()
        mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "")
        self.assertEqual(run.calls[0]["options"], '[client]\nuser="root"\n')

    def test_failure_raises_last_error_line_and_still_removes_file(self):
        run = RecordingRun(returncode=1, stderr="warning\nERROR 1045: Access denied\n")
        with self.assertRaisesRegex(mysqladmin.MysqlError, "ERROR 1045: Access denied"):
            mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "x")
        self.assertFalse(os.path.exists(run.calls[0]["option_file"]))

    def test_timeout_becomes_mysql_error(self):
        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaises(mysqladmin.MysqlError):
            mysqladmin.MysqlAdmin(self.paths, run).execute("SELECT 1;", "")

    def test_can_login(self):
        ok = RecordingRun()
        self.assertTrue(mysqladmin.MysqlAdmin(self.paths, ok).can_login("pma", "pw", "phpmyadmin"))
        self.assertEqual(ok.calls[0]["argv"][-1], "phpmyadmin")
        self.assertIn('user="pma"', ok.calls[0]["options"])
        self.assertFalse(mysqladmin.MysqlAdmin(self.paths, RecordingRun(returncode=1)).can_login("pma", "pw"))

    def test_anonymous_accounts(self):
        run = RecordingRun(stdout="''@'localhost'\n''@'zbook'\n")
        self.assertEqual(mysqladmin.MysqlAdmin(self.paths, run).anonymous_accounts(""),
                         ["''@'localhost'", "''@'zbook'"])

    def test_upgrade_uses_mysql_upgrade(self):
        run = RecordingRun(stdout="Phase 1/7\nOK\n")
        self.assertIn("OK", mysqladmin.MysqlAdmin(self.paths, run).upgrade("pw"))
        self.assertEqual(run.calls[0]["argv"][0], "/l/bin/mysql_upgrade")
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src python3 -m unittest tests.test_mysqladmin -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — `src/xampp_panel/mysqladmin.py`:

```python
"""MariaDB account administration through XAMPP's mysql client (used by xampp-repair, as root).

Passwords never appear on a command line or in the environment: SQL goes in on
stdin and credentials in a private option file that is deleted right after use.
"""

import os
import subprocess
import tempfile

from .helper import SAFE_ENV
from .paths import DEFAULT, Paths

MIN_PASSWORD = 8
MAX_PASSWORD = 128
PMADB = "phpmyadmin"  # the database phpMyAdmin's sql/create_tables.sql creates
TIMEOUT = 120  # seconds

# Escaped backslashes only mean the same in every sql_mode once NO_BACKSLASH_ESCAPES is off.
_SQL_MODE = "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');\n"
_LONG_LISTS = "SET SESSION group_concat_max_len = 65536;\n"


class MysqlError(Exception):
    pass


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

    def _client(self, program, user: str, password: str, args=(), sql: str = "") -> str:
        name = os.path.basename(str(program))
        fd, option_file = tempfile.mkstemp(prefix="xampp-repair-", suffix=".cnf")  # mode 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"[client]\nuser={_option_value(user)}\n")
                if password:
                    fh.write(f"password={_option_value(password)}\n")
            argv = [str(program), f"--defaults-extra-file={option_file}", *args]
            try:
                proc = self.run(argv, input=sql, env=SAFE_ENV, capture_output=True, text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                raise MysqlError(f"{name} did not finish within {TIMEOUT} seconds") from None
        finally:
            os.unlink(option_file)
        if proc.returncode != 0:
            lines = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()]
            raise MysqlError(lines[-1].strip() if lines else f"{name} failed")
        return proc.stdout

    def execute(self, sql: str, root_password: str) -> str:
        return self._client(self.paths.mysql_client, "root", root_password, ["--batch", "--skip-column-names"], sql)

    def can_login(self, user: str, password: str, database: str | None = None) -> bool:
        args = ["--batch", "--skip-column-names"] + ([database] if database else [])
        try:
            self._client(self.paths.mysql_client, user, password, args, "SELECT 1;\n")
        except MysqlError:
            return False
        return True

    def anonymous_accounts(self, root_password: str) -> list[str]:
        out = self.execute("SELECT CONCAT(QUOTE(user), '@', QUOTE(host)) FROM mysql.user WHERE user = '';\n",
                           root_password)
        return [line for line in out.splitlines() if line.strip()]

    def upgrade(self, root_password: str) -> str:
        return self._client(self.paths.mysql_upgrade, "root", root_password)
```

- [ ] **Step 4: Run tests** — `PYTHONPATH=src python3 -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/mysqladmin.py tests/test_mysqladmin.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: MariaDB account SQL and a client runner that keeps passwords off argv"
```

---

### Task 4: `configedit` — ProFTPD password and MySQL networking helpers

**Files:**
- Modify: `src/xampp_panel/configedit.py` (append after `mysql_localhost`)
- Test: `tests/test_configedit.py`

**Interfaces:**
- Produces: `proftpd_password_broken(text: str) -> bool`, `proftpd_set_password(text: str, hashed: str) -> str` (raises `ValueError` unless `hashed` is a SHA-512 crypt hash `$6$salt$86chars`), `mysql_networking_off(text: str) -> bool`, `mysql_hardened(text: str) -> bool`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_configedit.py`:

```python
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

    def test_hardened(self):
        self.assertFalse(configedit.mysql_hardened("[mysqld]\nport=3306\n"))
        self.assertTrue(configedit.mysql_hardened(configedit.mysql_localhost("[mysqld]\nport=3306\n", True)))
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src python3 -m unittest tests.test_configedit -v` → FAIL (`AttributeError`).

- [ ] **Step 3: Implement** — append to `configedit.py` after `mysql_localhost`:

```python
def mysql_networking_off(text: str) -> bool:
    return bool(_SKIP_NET.search(text))


def mysql_hardened(text: str) -> bool:
    return _BIND in text


# "lampp security" pastes the PHP meant to compute the FTP password hash into proftpd.conf.
_PROFTPD_BROKEN = re.compile(r"(?ms)^UserPassword[ \t]+daemon[ \t]+<\?.*?^\?>[ \t]*$\n?")
_PROFTPD_PASSWORD = re.compile(r"(?m)^UserPassword[ \t]+daemon[ \t]+.*$\n?")
_SHA512_CRYPT = re.compile(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}")


def proftpd_password_broken(text: str) -> bool:
    return bool(_PROFTPD_BROKEN.search(text))


def proftpd_set_password(text: str, hashed: str) -> str:
    """Set the FTP user daemon's password hash, replacing a broken block or an old line."""
    if not _SHA512_CRYPT.fullmatch(hashed):
        raise ValueError("not a SHA-512 crypt hash")
    line = f"UserPassword daemon {hashed}\n"
    for pattern in (_PROFTPD_BROKEN, _PROFTPD_PASSWORD):
        new, count = pattern.subn(lambda m: line, text, count=1)
        if count:
            return new
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line
```

- [ ] **Step 4: Run tests** — full suite → OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/configedit.py tests/test_configedit.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: detect and repair the FTP password and MySQL networking breakage"
```

---

### Task 5: `dialogs` and shared test fakes

**Files:**
- Create: `src/xampp_panel/dialogs.py`
- Create: `tests/fakes.py`
- Test: `tests/test_dialogs.py`

**Interfaces:**
- Produces: `class Dialogs(run=subprocess.run, height=20, width=74)` with `menu(text: str, items: list[tuple[str, str]]) -> str | None`, `yesno(text: str) -> bool`, `msgbox(text: str) -> None`, `passwordbox(text: str) -> str | None`.
- Produces (tests): `fakes.FakeDialogs(answers)` (same four methods; `menu`/`yesno`/`passwordbox` pop the next scripted answer, `msgbox` only records; `.shown` list of `(kind, text)`; `.messages()`), `fakes.FakeAdmin`, `fakes.FakeHelper`, `fakes.FakeRun` (defined below, used by Tasks 6–7).

- [ ] **Step 1: Write the failing tests** — `tests/test_dialogs.py`:

```python
import subprocess
import unittest

from xampp_panel.dialogs import Dialogs


class Run:
    def __init__(self, returncode=0, stderr=""):
        self.returncode, self.stderr, self.calls = returncode, stderr, []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, None, self.stderr)


class DialogsTest(unittest.TestCase):
    def test_menu_returns_tag_from_stderr(self):
        run = Run(stderr="2")
        self.assertEqual(Dialogs(run).menu("Pick:", [("1", "One"), ("2", "Two")]), "2")
        argv, kwargs = run.calls[0]
        self.assertEqual(argv[:3], ["whiptail", "--title", "XAMPP repair & configure"])
        self.assertEqual(argv[3:], ["--menu", "Pick:", "20", "74", "2", "1", "One", "2", "Two"])
        self.assertEqual(kwargs["stderr"], subprocess.PIPE)
        self.assertNotIn("stdout", kwargs)  # whiptail draws on the terminal

    def test_cancel_returns_none(self):
        self.assertIsNone(Dialogs(Run(returncode=1)).menu("Pick:", [("1", "One")]))
        self.assertIsNone(Dialogs(Run(returncode=255)).passwordbox("Password:"))

    def test_passwordbox_keeps_spaces(self):
        self.assertEqual(Dialogs(Run(stderr="  pass word  ")).passwordbox("Password:"), "  pass word  ")

    def test_yesno(self):
        self.assertTrue(Dialogs(Run(0)).yesno("Sure?"))
        self.assertFalse(Dialogs(Run(1)).yesno("Sure?"))

    def test_msgbox_scrolls(self):
        run = Run()
        Dialogs(run).msgbox("Hello")
        self.assertEqual(run.calls[0][0][3:], ["--scrolltext", "--msgbox", "Hello", "20", "74"])
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src python3 -m unittest tests.test_dialogs -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — `src/xampp_panel/dialogs.py`:

```python
"""whiptail dialog boxes for xampp-repair. whiptail draws on the terminal and writes the answer to stderr."""

import subprocess

TITLE = "XAMPP repair & configure"


class Dialogs:
    def __init__(self, run=subprocess.run, height: int = 20, width: int = 74):
        self.run = run
        self.size = [str(height), str(width)]

    def _show(self, *args: str) -> subprocess.CompletedProcess:
        return self.run(["whiptail", "--title", TITLE, *args], stderr=subprocess.PIPE, text=True)

    def _answer(self, *args: str) -> str | None:
        proc = self._show(*args)
        return proc.stderr if proc.returncode == 0 else None  # 1 = Cancel, 255 = Esc

    def menu(self, text: str, items: list[tuple[str, str]]) -> str | None:
        flat = [part for item in items for part in item]
        return self._answer("--menu", text, *self.size, str(len(items)), *flat)

    def yesno(self, text: str) -> bool:
        return self._show("--yesno", text, *self.size).returncode == 0

    def msgbox(self, text: str) -> None:
        self._show("--scrolltext", "--msgbox", text, *self.size)

    def passwordbox(self, text: str) -> str | None:
        return self._answer("--passwordbox", text, *self.size)
```

Then create `tests/fakes.py` (used from Task 6 on; `unittest discover -s tests` puts `tests/` on `sys.path`, so tests import it as `import fakes`):

```python
"""Fakes shared by the repair and health tests."""

import re
import subprocess
from pathlib import Path

from xampp_panel.mysqladmin import MysqlError


class FakeDialogs:
    def __init__(self, answers=()):
        self.answers = list(answers)
        self.shown = []

    def _next(self, kind, text):
        self.shown.append((kind, text))
        if not self.answers:
            raise AssertionError(f"no scripted answer for {kind}: {text}")
        return self.answers.pop(0)

    def menu(self, text, items):
        return self._next("menu", text)

    def yesno(self, text):
        return self._next("yesno", text)

    def passwordbox(self, text):
        return self._next("passwordbox", text)

    def msgbox(self, text):
        self.shown.append(("msgbox", text))

    def messages(self):
        return [text for kind, text in self.shown if kind == "msgbox"]


class FakeAdmin:
    """Pretends to be MariaDB: a root password, a control-user login result, recorded SQL."""

    def __init__(self, root_password="", pma_login=True):
        self.root_password = root_password
        self.pma_login = pma_login
        self.executed = []
        self.fail = None
        self.anonymous = ["''@'localhost'"]

    def can_login(self, user, password, database=None):
        if user == "root":
            return password == self.root_password
        return self.pma_login

    def execute(self, sql, root_password):
        if root_password != self.root_password:
            raise MysqlError("ERROR 1045 (28000): Access denied for user 'root'@'localhost'")
        if self.fail:
            raise MysqlError(self.fail)
        self.executed.append(sql)
        if "DROP USER" in sql:
            self.anonymous = []
        m = re.search(r"^SET @pw = '((?:[^']|'')*)';$", sql, re.M)
        if m:
            self.root_password = m[1].replace("''", "'").replace("\\\\", "\\")
        return ""

    def anonymous_accounts(self, root_password):
        return list(self.anonymous)

    def upgrade(self, root_password):
        return "Phase 7/7: Running 'FLUSH PRIVILEGES'\nOK\n"


class FakeHelper:
    def __init__(self):
        self.calls = []

    def lampp(self, actions):
        self.calls.append(("lampp", list(actions)))

    def integrate(self, on):
        self.calls.append(("integrate", on))

    def harden(self, on):
        self.calls.append(("harden", on))

    def lean(self, on):
        self.calls.append(("lean", on))

    def _apply(self, sites):
        self.calls.append(("apply", list(sites)))


class FakeRun:
    """subprocess.run stand-in answering by program name: {"openssl": (0, "$6$...\\n", "")}."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(map(str, argv)), kwargs))
        code, out, err = self.answers.get(Path(str(argv[0])).name, (0, "", ""))
        return subprocess.CompletedProcess(argv, code, out, err)
```

- [ ] **Step 4: Run tests** — full suite → OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/dialogs.py tests/test_dialogs.py tests/fakes.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: whiptail dialogs and shared test fakes"
```

---

### Task 6: `health` — read-only report

**Files:**
- Create: `src/xampp_panel/health.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `pmaconfig.get_value`, `mysqladmin.PMADB`, `configedit.mysql_networking_off`, `configedit.proftpd_password_broken`, `configedit.has_block`, `services.snapshot`, `services.SERVICES`, `services.State`, `sites.load`, `helper.SAFE_ENV`, `fakes.FakeAdmin`, `fakes.FakeRun`.
- Produces: labels `FIX_ROOT = "Change MySQL root password"`, `FIX_PMA = "Fix phpMyAdmin pma login"`, `FIX_FTP = "Fix FTP config"`, `FIX_NETWORK = "Turn MySQL networking back on"`, `FIX_REAPPLY = "Re-apply panel config"`; `@dataclass(frozen=True) Finding(ok: bool, text: str, fix: str = "")`; `render(findings: list[Finding]) -> str`; `class HealthCheck(admin, paths=DEFAULT, run=subprocess.run, snapshot=services.snapshot)` with `run_checks(root_password: str | None) -> list[Finding]` and `command(argv) -> tuple[bool, str]`.

- [ ] **Step 1: Write the failing tests** — `tests/test_health.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path

import fakes
from xampp_panel import health
from xampp_panel.paths import Paths
from xampp_panel.services import State

GOOD_PMA = ("<?php\n$cfg['Servers'][$i]['controluser'] = 'pma';\n"
            "$cfg['Servers'][$i]['controlpass'] = 'pw';\n$cfg['Servers'][$i]['pmadb'] = 'phpmyadmin';\n")


class HealthCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc")
        for d in ("lampp/etc", "lampp/phpmyadmin", "lampp/sbin", "app/state"):
            (root / d).mkdir(parents=True)
        self.paths.my_cnf.write_text("[mysqld]\nport=3306\n")
        self.paths.httpd_conf.write_text("# BEGIN xampp-panel vhosts\nInclude x\n# END xampp-panel vhosts\n")
        self.paths.proftpd_conf.write_text("UserPassword daemon $6$x$y\n")
        self.paths.proftpd_bin.write_text("")
        self.paths.phpmyadmin_conf.write_text(GOOD_PMA)
        self.paths.hosts.write_text("127.0.0.1\tlocalhost\n")
        self.admin = fakes.FakeAdmin(root_password="secret1!")
        self.admin.anonymous = []
        self.run = fakes.FakeRun()
        self.states = {"apache": State.RUNNING, "mysql": State.RUNNING, "ftp": State.STOPPED}

    def check(self, root_password="secret1!"):
        hc = health.HealthCheck(self.admin, self.paths, self.run, snapshot=lambda paths: self.states)
        return hc.run_checks(root_password)

    def problems(self, findings):
        return [(f.text, f.fix) for f in findings if not f.ok]


class HealthCheckTest(HealthCase):
    def test_healthy_install_has_no_problems(self):
        findings = self.check()
        self.assertEqual(self.problems(findings), [])
        self.assertIn("No problems found.", health.render(findings))

    def test_mysql_networking_off(self):
        self.paths.my_cnf.write_text("[mysqld]\nskip-networking\n")
        self.assertIn(health.FIX_NETWORK, [fix for _, fix in self.problems(self.check())])

    def test_mysql_starting_points_to_networking_fix(self):
        self.states["mysql"] = State.STARTING
        self.assertIn(health.FIX_NETWORK, [fix for _, fix in self.problems(self.check())])

    def test_broken_ftp_config(self):
        self.paths.proftpd_conf.write_text("UserPassword daemon <?\nphp\n?>\n")
        self.assertIn(health.FIX_FTP, [fix for _, fix in self.problems(self.check())])

    def test_config_test_failure_is_reported(self):
        self.run.answers["apachectl"] = (1, "", "Syntax error on line 3\n")
        texts = [text for text, _ in self.problems(self.check())]
        self.assertTrue(any("Syntax error on line 3" in t for t in texts), texts)

    def test_root_without_password_and_anonymous_accounts(self):
        self.admin.root_password = ""
        self.admin.anonymous = ["''@'localhost'"]
        fixes = [fix for _, fix in self.problems(self.check(root_password=None))]
        self.assertEqual(fixes.count(health.FIX_ROOT), 2)

    def test_anonymous_check_skipped_without_root_password(self):
        self.admin.anonymous = ["''@'localhost'"]
        self.assertEqual(self.problems(self.check(root_password=None)), [])

    def test_pma_not_set_up_or_cannot_log_in(self):
        self.paths.phpmyadmin_conf.write_text("<?php\n")
        self.assertIn(health.FIX_PMA, [fix for _, fix in self.problems(self.check())])
        self.paths.phpmyadmin_conf.write_text(GOOD_PMA)
        self.admin.pma_login = False
        self.assertIn(health.FIX_PMA, [fix for _, fix in self.problems(self.check())])

    def test_mysql_stopped_skips_account_checks(self):
        self.states["mysql"] = State.STOPPED
        self.admin.root_password = ""
        self.assertEqual(self.problems(self.check()), [])

    def test_site_missing_from_hosts(self):
        self.paths.state_file.write_text('[{"name": "demo", "path": "/home/u/Sites/demo", "uid": 1000}]')
        self.assertIn(health.FIX_REAPPLY, [fix for _, fix in self.problems(self.check())])
        self.paths.hosts.write_text("127.0.0.1\tdemo.local\n")
        self.assertEqual(self.problems(self.check()), [])

    def test_render_counts_problems(self):
        text = health.render([health.Finding(True, "fine"), health.Finding(False, "broken", health.FIX_FTP)])
        self.assertIn("OK   fine", text)
        self.assertIn("FIX  broken", text)
        self.assertIn(f"→ {health.FIX_FTP}", text)
        self.assertIn("1 problem(s) found.", text)
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src python3 -m unittest tests.test_health -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — `src/xampp_panel/health.py`:

```python
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
        if states["mysql"] is State.RUNNING:
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
        if self.admin.can_login("root", ""):
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
        if not self.admin.can_login(user, password, PMADB):
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
```

`FIX_REAPPLY` is the right advice for missing hosts entries because Task 7's `reapply` re-writes the vhosts, `/etc/hosts` and state through `Helper._apply(sites.load(state_file))`.

- [ ] **Step 4: Run tests** — full suite → OK.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/health.py tests/test_health.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: read-only health report for xampp-repair"
```

---

### Task 7: `repair` — menu, flows, first-install, launcher

**Files:**
- Create: `src/xampp_panel/repair.py`, `bin/xampp-repair`
- Test: `tests/test_repair.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6; `helper.Helper` (`lampp(actions)`, `integrate(on)`, `harden(on)`, `lean(on)`, `_apply(sites)`), `helper.HelperFailure`, `fsutil.backup_once`, `fsutil.atomic_write`.
- Produces: `class RepairError(Exception)`, `class Cancelled(Exception)`, `class RepairApp(dialogs, admin, helper, paths=DEFAULT, run=subprocess.run, token=secrets.token_urlsafe, mysql_running=None, sleep=time.sleep)` with `main_menu() -> int`, `first_install() -> int`, and the menu actions; `main(argv=None) -> int`. `bin/xampp-repair` calls `main()`.

Spec deviation (recorded in the spec in Task 9): **Re-apply panel config** asks "only this computer?" and "lean mode?" instead of detecting markers, because a XAMPP upgrade that overwrote the configs also removed the markers.

- [ ] **Step 1: Write the failing tests** — `tests/test_repair.py`:

```python
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fakes
from xampp_panel import health, pmaconfig, repair
from xampp_panel.paths import Paths

PMA_XAMPP = ("<?php\n$i = 0;\n$i++;\n$cfg['Servers'][$i]['auth_type'] = 'config';\n"
             "$cfg['Servers'][$i]['user'] = 'root';\n$cfg['Servers'][$i]['controluser'] = 'pma';\n"
             "#$cfg['Servers'][$i]['controlpass'] = '';\n")
HASH = "$6$abcdefgh12345678$" + "B" * 86
NEW = "new-pass 1"


class RepairCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", hosts=root / "hosts", proc=root / "proc")
        for d in ("lampp/etc", "lampp/phpmyadmin/sql", "lampp/sbin", "app/state"):
            (root / d).mkdir(parents=True)
        self.paths.phpmyadmin_conf.write_text(PMA_XAMPP)
        self.paths.pma_tables_sql.write_text("CREATE DATABASE IF NOT EXISTS phpmyadmin;\n")
        self.paths.my_cnf.write_text("[mysqld]\nport=3306\n")
        self.paths.httpd_conf.write_text("Listen 80\n")
        self.paths.proftpd_conf.write_text("A\nUserPassword daemon <?\nphp\n?>\nB\n")
        self.admin = fakes.FakeAdmin(root_password="")
        self.helper = fakes.FakeHelper()
        self.run = fakes.FakeRun({"openssl": (0, HASH + "\n", "")})
        self.running = True

    def app(self, *answers, token="generated-token"):
        self.dialogs = fakes.FakeDialogs(answers)
        return repair.RepairApp(self.dialogs, self.admin, self.helper, self.paths, self.run,
                                token=lambda n: token, mysql_running=lambda: self.running, sleep=lambda s: None)

    def pma(self, key):
        return pmaconfig.get_value(self.paths.phpmyadmin_conf.read_text(), key)


class ChangeRootPasswordTest(RepairCase):
    def test_sets_password_drops_anonymous_then_switches_login_page(self):
        self.app(NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertTrue(Path(str(self.paths.phpmyadmin_conf) + ".xampp-panel.bak").exists())

    def test_failure_leaves_phpmyadmin_alone(self):
        self.admin.fail = "ERROR 1064 syntax"
        app = self.app(NEW, NEW)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertEqual(self.pma("auth_type"), "config")
        self.assertIn("ERROR 1064 syntax", self.dialogs.messages()[-1])

    def test_asks_current_password_until_right(self):
        self.admin.root_password = "old-pass 1"
        self.app("wrong", "old-pass 1", NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertIn("not right", self.dialogs.messages()[0])

    def test_rejects_short_and_mismatched_passwords(self):
        self.app("short", NEW, "other-pass", NEW, NEW).change_root_password()
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(len(self.dialogs.messages()), 3)  # too short, mismatch, done

    def test_cancel_changes_nothing(self):
        app = self.app(None)
        self.assertFalse(app._attempt(app.change_root_password))
        self.assertEqual(self.admin.executed, [])

    def test_starts_mysql_when_stopped(self):
        self.running = False
        app = self.app()
        with self.assertRaises(repair.RepairError):
            app._ensure_mysql()
        self.assertEqual(self.helper.calls[0], ("lampp", ["startmysql"]))


class PmaTest(RepairCase):
    def test_fix_generates_password_writes_config_and_account(self):
        self.app().fix_pma()
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.pma("pmadb"), "phpmyadmin")
        self.assertIn("CREATE DATABASE IF NOT EXISTS phpmyadmin;", self.admin.executed[0])
        self.assertIn("IDENTIFIED BY 'generated-token'", self.admin.executed[0])

    def test_fix_keeps_existing_password(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "kept"))
        self.app(token="unused").fix_pma()
        self.assertEqual(self.pma("controlpass"), "kept")

    def test_sql_failure_leaves_config_untouched(self):
        self.admin.fail = "ERROR"
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertEqual(self.paths.phpmyadmin_conf.read_text(), PMA_XAMPP)

    def test_other_pmadb_refused(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "pmadb", "custom"))
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertEqual(self.admin.executed, [])

    def test_login_still_failing_is_reported(self):
        self.admin.pma_login = False
        app = self.app()
        self.assertFalse(app._attempt(app.fix_pma))
        self.assertIn("cannot log in", self.dialogs.messages()[-1])

    def test_show_password_only_after_yes(self):
        self.paths.phpmyadmin_conf.write_text(pmaconfig.set_value(PMA_XAMPP, "controlpass", "s3cret"))
        self.app(False).show_pma_password()
        self.assertEqual(self.dialogs.messages(), [])
        self.app(True).show_pma_password()
        self.assertIn("s3cret", self.dialogs.messages()[0])


class FtpTest(RepairCase):
    def test_replaces_broken_block_with_hash(self):
        self.app("ftp-pass 1", "ftp-pass 1").fix_ftp()
        self.assertEqual(self.paths.proftpd_conf.read_text(), f"A\nUserPassword daemon {HASH}\nB\n")
        openssl = [c for c in self.run.calls if c[0][0] == "openssl"][0]
        self.assertEqual(openssl[0], ["openssl", "passwd", "-6", "-stdin"])
        self.assertEqual(openssl[1]["input"], "ftp-pass 1\n")

    def test_rolls_back_when_proftpd_rejects_it(self):
        self.run.answers["proftpd"] = (1, "", "Fatal: bad config\n")
        before = self.paths.proftpd_conf.read_text()
        app = self.app("ftp-pass 1", "ftp-pass 1")
        self.assertFalse(app._attempt(app.fix_ftp))
        self.assertEqual(self.paths.proftpd_conf.read_text(), before)
        self.assertIn("Fatal: bad config", self.dialogs.messages()[-1])


class OtherActionsTest(RepairCase):
    def test_networking_fix_comments_out_skip_networking(self):
        self.paths.my_cnf.write_text("[mysqld]\nskip-networking\n")
        self.app(True).fix_networking()
        self.assertIn("#skip-networking", self.paths.my_cnf.read_text())
        self.assertEqual(self.helper.calls, [("lampp", ["stopmysql", "startmysql"])])

    def test_mysql_upgrade_shows_output(self):
        self.app().mysql_upgrade()
        self.assertIn("OK", self.dialogs.messages()[0])

    def test_reapply_asks_and_applies(self):
        self.app(True, False).reapply()
        self.assertEqual(self.helper.calls, [("integrate", True), ("harden", True), ("lean", False), ("apply", [])])

    def test_health_check_shows_report(self):
        app = self.app()
        app.check.snapshot = lambda paths: {"apache": repair.State.STOPPED, "mysql": repair.State.STOPPED,
                                            "ftp": repair.State.STOPPED}
        app.health_check()
        self.assertRegex(self.dialogs.messages()[0], r"problem\(s\) found\.|No problems found\.")


class FirstInstallTest(RepairCase):
    def test_sets_everything_up_and_stops_mysql_it_started(self):
        self.running = False
        states = iter([False, True])
        app = self.app(NEW, NEW)
        app.mysql_running = lambda: next(states, True)
        self.assertEqual(app.first_install(), 0)
        self.assertEqual(self.pma("controlpass"), "generated-token")
        self.assertEqual(self.admin.root_password, NEW)
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "cookie")
        self.assertEqual(self.helper.calls, [("lampp", ["startmysql"]), ("lampp", ["stopmysql"])])

    def test_skipping_password_still_drops_anonymous(self):
        self.assertEqual(self.app("").first_install(), 0)
        self.assertEqual(self.admin.root_password, "")
        self.assertEqual(self.admin.anonymous, [])
        self.assertEqual(self.pma("auth_type"), "config")
        self.assertEqual(self.helper.calls, [])  # MySQL was already running: left running

    def test_existing_root_password_is_kept(self):
        self.admin.root_password = "old-pass 1"
        self.assertEqual(self.app("old-pass 1").first_install(), 0)
        self.assertEqual(self.admin.root_password, "old-pass 1")

    def test_failed_step_returns_1_and_names_the_fix(self):
        self.admin.fail = "ERROR 2002"
        self.assertEqual(self.app("").first_install(), 1)
        self.assertIn(health.FIX_PMA, self.dialogs.messages()[0])


class MenuAndMainTest(RepairCase):
    def test_menu_runs_action_reports_errors_and_quits(self):
        self.admin.fail = "boom"
        app = self.app("4", "q")
        self.assertEqual(app.main_menu(), 0)
        self.assertIn("boom", self.dialogs.messages()[0])

    def test_escape_quits(self):
        self.assertEqual(self.app(None).main_menu(), 0)

    def test_main_rejects_bad_usage_and_non_root(self):
        self.assertEqual(repair.main(["bogus"]), 2)
        with mock.patch("os.geteuid", return_value=1000):
            self.assertEqual(repair.main([]), 1)
```

- [ ] **Step 2: Run to verify failure** — `PYTHONPATH=src python3 -m unittest tests.test_repair -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — `src/xampp_panel/repair.py`:

```python
"""xampp-repair: a whiptail menu to configure XAMPP and fix known problems.

Runs as root (sudo in a terminal the panel opens, or from setup.sh).
`xampp-repair first-install` replaces XAMPP's "lampp security" during setup.
"""

import os
import secrets
import shutil
import subprocess
import sys
import time

from . import configedit, fsutil, health, pmaconfig, services, sites
from .dialogs import Dialogs
from .helper import SAFE_ENV, Helper, HelperFailure
from .mysqladmin import (PMADB, MysqlAdmin, MysqlError, drop_anonymous_sql, password_problem,
                         pma_account_sql, set_root_password_sql)
from .paths import DEFAULT, Paths
from .services import State

PMA_PASSWORD_BYTES = 24  # secrets.token_urlsafe(24): 32 characters from [A-Za-z0-9_-]
MYSQL_START_SECONDS = 20
USAGE = "usage: sudo xampp-repair [first-install]"
_FAILURES = (MysqlError, HelperFailure, OSError, ValueError)


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
        self.mysql_running = mysql_running or (lambda: services.snapshot(paths)["mysql"] is State.RUNNING)
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
        while True:
            first = self.dialogs.passwordbox(prompt)
            if first is None or (allow_skip and first == ""):
                if allow_skip:
                    return None
                raise Cancelled()
            problem = password_problem(first)
            if problem:
                self.dialogs.msgbox(problem)
            elif self.dialogs.passwordbox("Repeat it:") != first:
                self.dialogs.msgbox("The passwords don't match. Try again.")
            else:
                return first

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
            self.dialogs.msgbox(f"phpMyAdmin control user\n\nUser:     {user}\nPassword: {password}\n\n"
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
        user = pmaconfig.get_value(text, "controluser") or "pma"
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
        self._write(conf, configedit.mysql_localhost(text, True))
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
        self.helper._apply(sites.load(self.paths.state_file))
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
        ok = self._step("phpMyAdmin control user", lambda: self._setup_pma(fresh=True), health.FIX_PMA)
        ok = self._step("MySQL root password", self._first_root_password, health.FIX_ROOT) and ok
        if started:
            try:
                self.helper.lampp(["stopmysql"])
            except HelperFailure as e:
                print(f"warning: MySQL did not stop: {e}", file=sys.stderr)
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

    def _first_root_password(self) -> None:
        current = self._root()
        new = None
        if current == "":
            new = self._new_password("Choose a MySQL root password.\n\nLeave it empty to skip "
                                     "(the panel will remind you).", allow_skip=True)
        self._set_root_password(current, new)


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
    app = RepairApp(Dialogs(), MysqlAdmin(), Helper())
    try:
        return app.first_install() if argv else app.main_menu()
    except KeyboardInterrupt:
        return 130
```

Create `bin/xampp-repair` (mode 0755):

```python
#!/usr/bin/python3 -I
# Repair & configure menu for XAMPP Panel. Run with: sudo xampp-repair
import sys

sys.path.insert(0, "/opt/xampp-panel/lib")
from xampp_panel.repair import main  # noqa: E402

sys.exit(main())
```

Run `chmod 0755 bin/xampp-repair`.

- [ ] **Step 4: Run tests** — full suite → OK. Also `python3 -m py_compile bin/xampp-repair`.

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/repair.py bin/xampp-repair tests/test_repair.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: xampp-repair menu and first-install account setup"
```

---

### Task 8: `setup.sh` uses `xampp-repair first-install`

**Files:**
- Modify: `setup.sh` (packages line ~57, install block ~118-128, passwords block ~143-147)
- Test: `tests/test_scripts.py`

- [ ] **Step 1: Write the failing test** — add to `ScriptsTest` in `tests/test_scripts.py`:

```python
    def test_setup_uses_xampp_repair_not_lampp_security(self):
        text = (ROOT / "setup.sh").read_text()
        self.assertNotIn('lampp" security', text)
        self.assertIn('"$APP_DIR/bin/xampp-repair" first-install', text)
        self.assertIn("whiptail", text)
        self.assertIn('"$SRC_DIR/bin/xampp-repair"', text)
        self.assertIn("/usr/local/bin/xampp-repair", text)
```

- [ ] **Step 2: Run** — `PYTHONPATH=src python3 -m unittest tests.test_scripts -v` → FAIL.

- [ ] **Step 3: Implement** in `setup.sh`:

1. Packages: `packages=(libcrypt1 net-tools acl whiptail python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)`
2. Install line becomes:
   `install -o root -g root -m 0755 "$SRC_DIR/bin/xampp-panel" "$SRC_DIR/bin/xampp-helper" "$SRC_DIR/bin/xampp-repair" "$APP_DIR/bin/"`
3. After the existing `ln -sfn "$APP_DIR/bin/xampp-panel" /usr/local/bin/xampp-panel` / `installed+=(...)` lines add:
   ```bash
   ln -sfn "$APP_DIR/bin/xampp-repair" /usr/local/bin/xampp-repair
   installed+=(/usr/local/bin/xampp-repair)
   ```
4. Replace the whole `if ask "Set passwords for MySQL root and phpMyAdmin now (recommended)?"; then … fi` block with:
   ```bash
   say "Setting up MySQL and phpMyAdmin accounts"
   # Replaces XAMPP's "lampp security", which breaks MySQL networking, the FTP config and phpMyAdmin.
   "$APP_DIR/bin/xampp-repair" first-install </dev/tty >/dev/tty \
     || echo "Account setup did not finish. Run it later with: sudo xampp-repair"
   ```
5. Change the comment above the harden block to `# Last, so nothing above can undo the localhost-only setting.`

- [ ] **Step 4: Run** — full suite → OK; `bash -n setup.sh`.

- [ ] **Step 5: Commit**

```bash
git add setup.sh tests/test_scripts.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: setup.sh sets up MySQL accounts with xampp-repair instead of lampp security"
```

---

### Task 9: Panel menu item, banner, terminal selection

**Files:**
- Create: `src/xampp_panel/terminal.py`
- Modify: `src/xampp_panel/window.py` (menu ~line 220-228, banner ~230-232, new method near `toast`)
- Test: `tests/test_terminal.py`

**Interfaces:**
- Consumes: `Paths.repair` (Task 1).
- Produces: `TERMINALS: tuple[tuple[str, tuple[str, ...]], ...]`, `repair_command(paths) -> list[str]`, `terminal_argv(command: list[str], which=shutil.which, terminals=TERMINALS) -> list[str] | None`.

- [ ] **Step 1: Write the failing tests** — `tests/test_terminal.py`:

```python
import unittest
from pathlib import Path

from xampp_panel import terminal
from xampp_panel.paths import Paths


class TerminalTest(unittest.TestCase):
    def test_first_installed_terminal_wins(self):
        which = {"kgx": "/usr/bin/kgx", "x-terminal-emulator": "/usr/bin/x-terminal-emulator"}.get
        self.assertEqual(terminal.terminal_argv(["sh", "-c", "x"], which), ["/usr/bin/kgx", "--", "sh", "-c", "x"])

    def test_x_terminal_emulator_uses_e(self):
        which = {"x-terminal-emulator": "/usr/bin/x-terminal-emulator"}.get
        self.assertEqual(terminal.terminal_argv(["sh"], which), ["/usr/bin/x-terminal-emulator", "-e", "sh"])

    def test_none_found(self):
        self.assertIsNone(terminal.terminal_argv(["sh"], lambda name: None))

    def test_repair_command_waits_before_closing(self):
        argv = terminal.repair_command(Paths(app=Path("/a")))
        self.assertEqual(argv[:2], ["sh", "-c"])
        self.assertIn("sudo /a/bin/xampp-repair", argv[2])
        self.assertIn("read", argv[2])
```

- [ ] **Step 2: Run** → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — `src/xampp_panel/terminal.py`:

```python
"""Open xampp-repair in a terminal emulator (no GTK imports, so it is testable)."""

import shlex
import shutil

from .paths import DEFAULT, Paths

# Tried in order; each with the option that runs a command.
TERMINALS = (
    ("gnome-terminal", ("--",)),
    ("ptyxis", ("--",)),
    ("kgx", ("--",)),
    ("x-terminal-emulator", ("-e",)),
)


def repair_command(paths: Paths = DEFAULT) -> list[str]:
    """sudo + xampp-repair, then wait so a sudo error stays readable before the window closes."""
    script = f"sudo {shlex.quote(str(paths.repair))}; printf '\\nPress Enter to close. '; read _"
    return ["sh", "-c", script]


def terminal_argv(command: list[str], which=shutil.which, terminals=TERMINALS) -> list[str] | None:
    for name, run_option in terminals:
        path = which(name)
        if path:
            return [path, *run_option, *command]
    return None
```

In `window.py`:
- add `terminal` to `from . import fsutil, privileged, services, sites`.
- In `MainWindow.__init__`, before `menu.append("Quit", "app.quit")`, add:
  ```python
        repair_action = Gio.SimpleAction.new("repair", None)
        repair_action.connect("activate", lambda *_: self.open_repair())
        self.add_action(repair_action)
        menu.append("Repair & configure…", "win.repair")
  ```
- Banner text: `"MySQL root has no password. Use ☰ → Repair & configure to set one."`
- Add after `toast`:
  ```python
    def open_repair(self) -> None:
        argv = terminal.terminal_argv(terminal.repair_command(PATHS))
        if argv is None:
            self.toast(f"No terminal found. Run in a terminal: sudo {PATHS.repair}")
            return
        try:
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
        except GLib.Error as e:
            self.toast(f"Could not open a terminal: {e.message}")
  ```

- [ ] **Step 4: Run** — full suite → OK (the GUI test only compiles `window.py` when GTK is missing).

- [ ] **Step 5: Commit**

```bash
git add src/xampp_panel/terminal.py src/xampp_panel/window.py tests/test_terminal.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: open the repair menu from the panel"
```

---

### Task 10: Remove `tools/`, update docs and spec

**Files:**
- Delete: `tools/fix-pma.sh`, `tools/fix-pma.php`, `tools/secure-mysql.sh`
- Modify: `tests/test_scripts.py` (remove `FixPmaSqlTest`, `SecureMysqlTest`, the `tools/*` names in `test_syntax`, and now-unused imports `os`, `shutil`, `tempfile` if nothing else uses them)
- Modify: `README.md`, `docs/MAINTAINER.md`, `docs/USER-GUIDE.md`, `docs/superpowers/specs/2026-10-06-repair-menu-design.md`

- [ ] **Step 1: Delete and clean tests** — `git rm -r tools`; edit `tests/test_scripts.py` as listed; run the suite → OK.

- [ ] **Step 2: Docs** (each must match the code; grep afterwards for `tools/`, `fix-pma`, `secure-mysql`, `lampp security` and fix every stale hit):
  - `README.md`: one line under features: "Repair & configure menu (☰) for passwords and known XAMPP problems"; mention `sudo xampp-repair`.
  - `docs/MAINTAINER.md`:
    - §3 file table: add `pmaconfig.py`, `mysqladmin.py`, `dialogs.py`, `health.py`, `repair.py`, `terminal.py`, `bin/xampp-repair`; remove the two `tools/` rows.
    - §4 installed files: `/opt/xampp-panel/bin/xampp-repair` (root, 0755), `/usr/local/bin/xampp-repair` (symlink); "files it edits": `phpmyadmin/config.inc.php` (`auth_type`, `controluser`, `controlpass`, `pmadb`; backup once; owner kept), `proftpd.conf` (`UserPassword daemon` via the menu).
    - Architecture diagram: add `xampp-repair` (sudo in a terminal) → `repair.RepairApp` → `Dialogs` / `MysqlAdmin` / `pmaconfig` / `Helper`.
    - §6 security: xampp-repair runs as root only via sudo; passwords on stdin / 0600 option file; config parsed as text, never executed; pma grants.
    - §10/§11: replace every `tools/...` and `lampp security` remedy with the matching menu item (`sudo xampp-repair` → item). Keep the manual commands as a fallback only where no menu item exists.
    - Handover: setup no longer runs `lampp security`; list what was verified only by unit tests (real whiptail, MariaDB, sudo, terminals: see Task 11 manual checks); remove the "Still open" items that are now done.
    - Change history row for this feature; test count from the real run.
  - `docs/USER-GUIDE.md`: new section "Repair & configure" (how to open it, each item in one line, what "Show phpMyAdmin pma password" is for); yellow-bar section → "☰ → Repair & configure → Change MySQL root password"; troubleshooting rows point to menu items.
  - Spec: add under "Main menu" the recorded deviation: "Re-apply panel config asks two yes/no questions (localhost only, lean mode) instead of detecting markers, because a XAMPP upgrade removes them too", and set Status to "implemented".

- [ ] **Step 3: Verify** — `PYTHONPATH=src python3 -m unittest discover -s tests` → OK; `grep -rn "tools/\|fix-pma\|secure-mysql" README.md docs src setup.sh tests` → only history/plan/spec mentions.

- [ ] **Step 4: Commit**

```bash
git add -A tools tests/test_scripts.py README.md docs
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "docs: repair menu replaces tools/; handover updated"
```

---

### Task 11: Final review and manual checks

- [ ] **Step 1:** Full suite + `bash -n setup.sh uninstall.sh` + `python3 -m py_compile bin/*`.
- [ ] **Step 2:** Parallel review agents (security; dead code + correctness; efficiency + best practices) over `git diff 326e82f..HEAD`; verify findings, report by severity, fix approved ones, fresh agent reviews the fixes.
- [ ] **Step 3:** Hand the user this manual checklist (cannot run in the sandbox):
  1. `cd ~/Xampp-For-gnome && sudo ./setup.sh` → account step shows whiptail; set a root password.
  2. phpMyAdmin: login page appears; log in as root; create database `students` works; no `pma` error.
  3. ☰ → Repair & configure… opens a terminal; `sudo` prompt; menu appears.
  4. Health check: no problems (or only expected ones).
  5. Show phpMyAdmin pma password: shows a 32-character password.
  6. Change MySQL root password, with a password containing a space and a `"`; log in to phpMyAdmin with it.
  7. `sudo xampp-repair` from a plain terminal works too.
  8. (Added 2026-10-07.) Reset forgotten MySQL root password: choose a new password, then check:
     phpMyAdmin accepts it; `grep -i init_file /opt/lampp/var/mysql/*.err | tail` shows the init
     file ran without errors; `grep init-file /opt/lampp/etc/my.cnf` prints nothing;
     `sudo ls /run/xampp-panel` is empty.
- [ ] **Step 4:** Give the user the push command (`git push origin master`).
