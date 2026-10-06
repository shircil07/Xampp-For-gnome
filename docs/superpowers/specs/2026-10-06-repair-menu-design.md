# Repair menu and safe first-install passwords — design

Date: 2026-10-06. Status: approved in chat, spec awaiting review.

## Problem

`setup.sh` runs XAMPP's `lampp security` for passwords. On XAMPP 8.2 it:

- adds `skip-networking` to `my.cnf` (MySQL TCP off, panel stuck on "starting…"),
- writes PHP source into `proftpd.conf` (FTP won't start),
- writes a phpMyAdmin `controlpass` without updating the MySQL `pma` account
  (`Access denied for user 'pma'@'localhost'`),
- and when skipped leaves root without a password next to XAMPP's anonymous account
  (`#1044 Access denied for user ''@'localhost'` in phpMyAdmin).

The fixes exist as one-off scripts in `tools/` (commit `326e82f`), but they are not installed,
so they disappear with the source folder and a new install still breaks.

## Goals

1. A first install never runs `lampp security` and ends with: no anonymous accounts, a working
   `pma` account with a generated password, and a root password if the user gave one.
2. A **Repair & configure** terminal menu (whiptail), installed with the app and opened from the
   panel's ☰ menu, to configure and fix things later, including:
   - change the MySQL root password,
   - show the generated phpMyAdmin `pma` password.
3. `tools/` is removed; its logic lives in the app with unit tests.

Non-goals: FTP user management beyond repairing the broken config; a GTK repair UI; LAN setup.

## User decisions (from the brainstorm)

- Install does: MySQL root password (skippable) + anonymous accounts dropped always + `pma` with
  a generated password. Skipping the root password keeps the panel's yellow banner.
- Repair menu keeps all fixes "just in case", plus "show pma password" and "change root password".
- UI: whiptail dialog boxes. Architecture: Python module (approach A), not a bash script.

## Architecture

```
 panel ☰ "Repair & configure…"            setup.sh (root)
        │ opens a terminal                      │
        ▼                                       ▼
 sudo /opt/xampp-panel/bin/xampp-repair   /opt/xampp-panel/bin/xampp-repair first-install
        │                                       │
        └──────────────► repair.py (RepairApp: menu + flows, runs as root)
                             │            │               │
                       dialogs.py    mysqladmin.py    pmaconfig.py
                       (Dialogs:     (MysqlAdmin:      (pure text transforms for
                        whiptail)     SQL + mysql       phpMyAdmin's config.inc.php)
                                      client runner)
                             │
                       existing: helper.Helper (harden/integrate/lean), configedit, fsutil,
                                 services, Paths
```

All new code runs as root in a terminal the user opened, so no new `pkexec` helper commands
are needed. The panel only launches the terminal.

### Components

**`pmaconfig.py`** — pure functions over the text of `config.inc.php` (like `configedit.py`):
- `get(text, key) -> str | None`: value of the active `$cfg['Servers'][$i]['<key>'] = '...';`
  line (last active one wins, commented lines ignored, PHP single-quote unescaping of `\\` and `\'`).
- `set(text, key, value) -> str`: replace the active line's value, or append a line after the
  last `$cfg['Servers'][$i]` line if none is active. Values are PHP-single-quote escaped.
- Used for `auth_type`, `controluser`, `controlpass`, `pmadb`. Nothing in the config is executed.

**`mysqladmin.py`** — `MysqlAdmin(paths, run=subprocess.run)`:
- `sql_quote(s)`: `'`→`''`, `\`→`\\`; every SQL batch starts with
  `SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '')`.
- SQL builders (pure, unit-tested): `drop_anonymous_sql()`, `set_root_password_sql(pw)`
  (MariaDB lists the accounts: `GROUP_CONCAT` over `mysql.user` + `EXECUTE IMMEDIATE`, as in
  `tools/secure-mysql.sh`), `pma_account_sql(user, pw)` (`CREATE USER IF NOT EXISTS`,
  `ALTER USER`, `GRANT SELECT, INSERT, UPDATE, DELETE ON phpmyadmin.*`).
- `execute(sql, root_password)`: runs `mysql -u root` with the SQL on **stdin** and the password
  in a temporary `--defaults-extra-file` (mode 0600, deleted in `finally`). Never on argv.
- `check_login(user, password) -> bool`, `root_has_password() -> bool`, `anonymous_accounts()`.
- Root password validation: 8–128 chars, no control characters, kept verbatim (spaces allowed).

**`dialogs.py`** — `Dialogs` wraps whiptail (`menu`, `yesno`, `msgbox`, `textbox`,
`passwordbox`, `inputbox`): UI on the terminal, the answer read from whiptail's stderr; Esc/Cancel
returns `None`. `FakeDialogs` in tests replays scripted answers.

**`repair.py`** — `RepairApp(dialogs, admin, helper, paths)`; entry points:
- no arguments → main menu (loops until Quit),
- `first-install` → the install flow below (called by `setup.sh`).
Refuses to run unless root. The root password, once entered, is kept in memory for the session.

**`bin/xampp-repair`** — launcher like `bin/xampp-helper` (`#!/usr/bin/python3 -I`).

### Main menu

| Item | What it does |
|---|---|
| Health check | Read-only report in a textbox: services and ports, `apachectl -t`, `proftpd -t`, `skip-networking` active, `proftpd.conf` corrupted by `lampp security`, root has a password, anonymous accounts, `pma` login, `sites.json` vs `/etc/hosts`. Each problem names the menu item that fixes it. |
| Change MySQL root password | Current password (Enter if none) → new twice → set on every root account, drop anonymous accounts; if phpMyAdmin `auth_type` is `config`, back up and switch to `cookie` after success. |
| Show phpMyAdmin pma password | Shows `controluser` / `controlpass` from the config after a yes/no warning. |
| Fix phpMyAdmin pma login | Sets `controluser = 'pma'` and `pmadb = 'phpmyadmin'` if missing, generates a `controlpass` if empty, writes them (backup once), creates/updates `pma` and runs `create_tables.sql`; confirms the login works. |
| Fix FTP config | If `proftpd.conf` contains the broken `UserPassword daemon <?…?>` block: asks for a new FTP password, hashes it with `openssl passwd -6 -stdin`, replaces the block (backup once), validates with `proftpd -t`, rolls back on failure. |
| Turn MySQL networking back on | `helper.harden(True)` (comments out `skip-networking`), offers to restart MySQL. |
| Run mysql_upgrade | With the root password via the defaults file. |
| Re-apply panel config | `integrate on`; `harden on` only if `my.cnf` still has the panel's `bind-address` marker (otherwise LAN mode was chosen and is left alone); `lean on` only if `httpd.conf` has the `lean` block. |
| Quit | |

MySQL-dependent items start MySQL first if it isn't running (and say so).

### First-install flow (`xampp-repair first-install`, replaces `lampp security` in `setup.sh`)

1. Start MySQL (`lampp startmysql`).
2. `pma`: same as the menu's "Fix phpMyAdmin pma login", but always generates a fresh
   `controlpass` (`secrets.token_urlsafe(24)`).
3. Ask for a root password (passwordbox; empty/Cancel = skip, with a note about the banner).
4. Drop anonymous accounts always; set the root password if given; switch phpMyAdmin
   `auth_type` `config` → `cookie` only if a password was set.
5. Stop MySQL. Any failure prints the error and the menu item that retries it; setup continues.

`setup.sh` changes: add `whiptail` to the packages, replace the `lampp security` block with
`xampp-repair first-install`, keep `harden` after it, install `bin/xampp-repair`.

### Panel changes

- ☰ menu: **Repair & configure…** opens the first available terminal from a configurable list
  (`gnome-terminal --`, `ptyxis --`, `kgx --`, `x-terminal-emulator -e`) running
  `sudo /opt/xampp-panel/bin/xampp-repair`. If none is found, a toast shows the command.
- Yellow banner text: "MySQL root has no password. Use ☰ → Repair & configure to set one."

### Security

- Runs as root only after `sudo` in a terminal the user opened; refuses otherwise.
- Passwords never on argv or in the environment: SQL on stdin, credentials in a 0600 defaults
  file removed in `finally`, FTP hash via `openssl passwd -stdin`.
- No PHP from `config.inc.php` is executed (pure text parsing).
- SQL escaping as above, with the sql_mode guard; account lists built by MariaDB itself.
- Config edits: backup once (`*.xampp-panel.bak`) + atomic write (`fsutil`), same as the panel.
- `pma` gets only `SELECT, INSERT, UPDATE, DELETE` on `phpmyadmin.*`.

### Error handling

- Each menu action catches failures and shows them in a msgbox; the menu keeps running.
- Ordering guarantees: phpMyAdmin is switched to `cookie` only after the root password change
  succeeded; FTP config is rolled back if `proftpd -t` fails.
- `first-install` never aborts `setup.sh`; it reports what to retry.

### Testing

- `pmaconfig`: get/set with commented lines, escaping, append when missing.
- `mysqladmin`: SQL builders (escaping, sql_mode guard, account discovery), `execute` with a fake
  runner (password not in argv, defaults file 0600 and removed, SQL on stdin), validation.
- `repair`: each flow with `FakeDialogs` + fake admin/helper (ordering, cancel paths, errors).
- Panel: terminal selection logic (pure function).
- Not testable here: real whiptail rendering, real MariaDB, real sudo — checked by a manual run
  on the user's machine (listed in the plan).

### Docs

README, `docs/MAINTAINER.md` (architecture, files, troubleshooting now points to the menu,
handover), `docs/USER-GUIDE.md` (Repair & configure section). `tools/` references removed.

## Migration

`tools/` is deleted. On the user's machine nothing else changes; re-running `setup.sh` installs
`xampp-repair`. The user's pending "secure root" step is done with the new menu item.
