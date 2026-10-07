# XAMPP Panel — Technical Reference

Use this when something breaks, when you upgrade XAMPP or the OS, or when you
want to change the panel. For everyday use, see [USER-GUIDE.md](USER-GUIDE.md).

- **Version:** 0.1.0 (built 2026-09-23)
- **Target:** Zorin OS (GNOME, Wayland), x86_64; works on Ubuntu 22.04+ bases
- **XAMPP:** 8.2.12 (`xampp-linux-x64-8.2.12-0-installer.run`, MariaDB 10.4.32)
- **Repo:** https://github.com/shircil07/Xampp-For-gnome (private), branch `master`; local copy `~/Downloads/xampp-panel`
- **Design history:** `docs/superpowers/specs/2026-09-23-xampp-panel-design.md` (the spec) and
  `docs/superpowers/plans/2026-09-23-xampp-panel.md` (the task-by-task plan); the repair menu added
  later has its own spec, `docs/superpowers/specs/2026-10-06-repair-menu-design.md`, and plan,
  `docs/superpowers/plans/2026-10-06-repair-menu.md`

---

## Handover — 2026-10-06

Repair & configure menu (`xampp-repair`) shipped. It replaces the `tools/` one-off scripts and
XAMPP's own `lampp security`, both for first install and for fixing things later.

What the earlier session found broken, and how it's fixed now:

1. **MySQL had TCP switched off** (log: `port: 0`). XAMPP's `lampp security` offers to "turn off
   network access" and adds `skip-networking` to `my.cnf`.
   **Fixed in code:** `harden on` comments out an active `skip-networking` for good (`harden off`
   only removes `bind-address` and never brings `skip-networking` back, so `--allow-lan` keeps TCP
   on; an old `# xampp-panel: was "skip-networking"` marker from earlier versions is dropped);
   `xampp-repair` → "Turn MySQL networking back on" only comments it out
   (`configedit.mysql_networking_on`, `bind-address` untouched), and the health check flags it. `setup.sh` no longer calls `lampp security` at all (see below).
2. **ProFTPD wouldn't start** (`unknown configuration directive 'function' on line 44`). `lampp
   security` sets the FTP password by running a PHP snippet; with short tags off, PHP printed the
   snippet's source and it was pasted into `proftpd.conf` as the `UserPassword daemon` value.
   **Fixed:** `xampp-repair` → "Fix FTP config" detects the broken block
   (`configedit.proftpd_password_broken`), asks for a new password, hashes it with
   `openssl passwd -6 -stdin` (never on argv) and validates with `proftpd -t` before keeping the
   change, rolling back otherwise.
3. **phpMyAdmin: `Access denied for user 'pma'@'localhost'`**. `lampp security` wrote a
   `controlpass` into `config.inc.php` without making the MySQL account `pma` match.
   **Fixed:** `xampp-repair` → "Fix phpMyAdmin pma login" (and the first-install flow) always
   creates/updates the MySQL account to match the config, in that order, and confirms the login
   works before reporting success.
4. **phpMyAdmin: `#1044 - Access denied for user ''@'localhost'`**. Root had no password and
   XAMPP's anonymous account still existed; phpMyAdmin's cookie login with `AllowNoPassword =
   true` silently logs in as the anonymous account for any other user name.
   **Fixed:** first install always drops anonymous accounts (`drop_anonymous_sql`); "Change MySQL
   root password" does the same whenever it runs. The panel's banner now points at the menu
   instead of `lampp security`.

`setup.sh` no longer runs `lampp security`: it runs `xampp-repair first-install` instead. On a
fresh XAMPP it sets up the `pma` control user, asks for a root password (empty = skip) and drops
anonymous accounts. Re-running `setup.sh` keeps what works: a `pma` that is configured and can log
in is left alone (otherwise it is set up fresh), and if root already has a password the root step is
skipped with a note pointing at "Change MySQL root password". The root step never asks for the
current root password itself; if the `pma` step already had to ask for it, it is used to drop the
anonymous accounts too, otherwise they are left alone. Notes are printed after the last dialog.
Before any of this, `xampp-repair` waits (about 20 s, measured on a clock) until MySQL actually
answers, not just until `mysqld` exists, and only "access denied" counts as "wrong password": a
connection error is shown as an error, never read as "root has a password".

Verified only by the unit suite below (`PYTHONPATH=src python3 -m unittest discover -s tests`,
259 tests, OK) — not by a real run: whiptail rendering, a real MariaDB server, real `sudo`, and
terminal-emulator detection on an actual desktop. See the plan's Task 11 for the manual checklist
to run once on the target machine.

---

## 1. What it is

XAMPP ships as a prebuilt binary bundle in `/opt/lampp`. Its own control panel is old, and it
needs `sudo` in a terminal. XAMPP Panel **does not modify XAMPP's binaries**. It adds:

| Part | What it does |
|---|---|
| `setup.sh` | One-command install: packages, XAMPP (if missing), port check, panel files, config hardening |
| `uninstall.sh` | Reverses everything setup did (keeps XAMPP unless `--remove-xampp`) |
| Control panel (GTK4 + libadwaita) | Start/stop Apache, MySQL, FTP; logs; shortcuts; per-project `.local` sites |
| Tray icon (GTK3 + AyatanaAppIndicator) | Optional; status icon plus start/stop menu |
| Root helper (`xampp-helper`) | The **only** code that runs as root through `pkexec` (graphical password prompt) |
| Repair tool (`xampp-repair`) | A whiptail menu, run as root via `sudo` in a terminal, for passwords and known XAMPP config problems; also runs once at first install |

---

## 2. Architecture

```
 You ─┬─ App menu / `xampp-panel` ──► Panel (GTK4, your user)
      │                                 │  reads status from /proc (no root)
      │                                 │  reads /opt/xampp-panel/state/sites.json
      │                                 ▼
      │                            pkexec /opt/xampp-panel/bin/xampp-helper <command>
      │                                 │   (polkit asks for your password once,
      │                                 │    remembered for a few minutes)
      │                                 ▼
      │                            Root helper ──► /opt/lampp/lampp start…/stop…
      │                                        ──► edits httpd.conf, my.cnf, proftpd.conf, /etc/hosts
      │                                        ──► setfacl (run as YOU, not root)
      │
      ├─ Tray (GTK3, separate process, only when enabled) ──► same pkexec helper
      │
      └─ ☰ "Repair & configure…" ──► opens a terminal running
                                      `sudo /opt/xampp-panel/bin/xampp-repair`
                                            │  (also run directly by setup.sh as
                                            │   `xampp-repair first-install`)
                                            ▼
                                      repair.RepairApp (whiptail menu, runs as root)
                                            │        │            │          │
                                        Dialogs  MysqlAdmin   pmaconfig   Helper
                                       (whiptail) (mysql CLI) (config.inc.php  (harden/integrate/
                                                                text edits)    lean, lampp start/stop)
```

Design rules:

- **Two processes for the UI.** The panel uses GTK 4 and the tray uses GTK 3, and they can't share a process.
- **Status never needs root.** It comes from `/proc/<pid>/comm`, `/proc/<pid>/cmdline` and `/proc/net/tcp{,6}`.
- **Every root action goes through one whitelisted CLI.** That makes the attack surface one small file.
- **Pure logic is kept free of GTK.** Everything except `window.py`, `app.py`, `tray.py` and `watch.py`
  is plain Python and unit-tested.

---

## 3. Source layout

| Path | Responsibility |
|---|---|
| `src/xampp_panel/paths.py` | `Paths` dataclass: **every** filesystem location in one place (tests override it) |
| `src/xampp_panel/fsutil.py` | `atomic_write` (temp file + rename), `backup_once`, `tail` (last 64 KB) |
| `src/xampp_panel/services.py` | Service list (Apache :80, MySQL :3306, ProFTPD :21), state detection, log paths |
| `src/xampp_panel/configedit.py` | Pure, reversible text edits for XAMPP/system config files; lean-mode values; vhost and hosts rendering; ProFTPD broken-password detection/repair, MySQL networking detection, the one-time `init-file` line for a root password reset |
| `src/xampp_panel/sites.py` | `Site(name, path, uid)`, name validation, `sites.json` load/save, `UNSAFE_PATH_CHARS` |
| `src/xampp_panel/helper.py` | **Root helper**: validation + whitelisted commands |
| `src/xampp_panel/privileged.py` | Builds the `pkexec` command, turns exit codes into errors |
| `src/xampp_panel/settings.py` | Per-user settings (`~/.config/xampp-panel/settings.json`, mode 0600) |
| `src/xampp_panel/watch.py` | inotify watcher + pausable fallback timer (shared by panel and tray) |
| `src/xampp_panel/window.py` | Main window: Services and Sites pages, log viewer, Add-site dialog, ☰ "Repair & configure…" |
| `src/xampp_panel/app.py` | `Adw.Application`: single instance, menu actions (tray, lean, quit) |
| `src/xampp_panel/tray.py` | Tray process |
| `src/xampp_panel/main.py` | Entry point: `--tray` → tray, otherwise panel |
| `src/xampp_panel/pmaconfig.py` | Pure text `get`/`set` of single-quoted `$cfg['Servers'][$i][...]` settings in phpMyAdmin's `config.inc.php`; never executes the file |
| `src/xampp_panel/mysqladmin.py` | `MysqlAdmin`: runs XAMPP's `mysql`/`mysql_upgrade` as root, SQL builders (`drop_anonymous_sql`, `set_root_password_sql`, `reset_root_sql`, `pma_account_sql`), password rules, SQL escaping |
| `src/xampp_panel/dialogs.py` | `Dialogs`: thin whiptail wrapper (menu, yesno, msgbox, passwordbox, `secret`) |
| `src/xampp_panel/health.py` | `HealthCheck`: read-only report (services, configs, MySQL accounts, phpMyAdmin login, sites) with the menu item that fixes each problem |
| `src/xampp_panel/repair.py` | `RepairApp`: the `xampp-repair` menu, its flows, and `first-install`; `main()` |
| `src/xampp_panel/terminal.py` | Picks a terminal emulator and builds its argv for "Repair & configure…" (pure, no GTK) |
| `lib/xampp-download.sh` | Sourced by `setup.sh`: the pinned XAMPP version (`XAMPP_VERSION`, `XAMPP_SHA256`; file name and URL derive from the version) and `xampp_prepare`, which `setup.sh` calls once: `xampp_find_installer` (the pinned file only), `xampp_other_installers` (other versions, for a hint), `xampp_download` (as the user, HTTPS only, resumable `.part`, retries, stall timeout), `xampp_verified_copy` (private copy, checksum checked on the copy; exit 1 = wrong checksum, 2 = copy failed) |
| `bin/xampp-panel`, `bin/xampp-helper`, `bin/xampp-repair` | Installed launchers (`#!/usr/bin/python3 -I`) |
| `data/` | `.desktop` file, polkit policy, SVG icons |
| `tests/` | stdlib `unittest` suite |

---

## 4. What gets installed where

### Files created by `setup.sh`

| Path | Owner / mode | Purpose |
|---|---|---|
| `/opt/xampp-panel/lib/xampp_panel/` | root, 0755/0644 | Python code (plus compiled `.pyc`) |
| `/opt/xampp-panel/bin/xampp-panel` | root, 0755 | Panel launcher |
| `/opt/xampp-panel/bin/xampp-helper` | root, 0755 | Root helper launcher |
| `/opt/xampp-panel/bin/xampp-repair` | root, 0755 | Repair tool launcher |
| `/usr/local/bin/xampp-repair` | symlink | So `sudo xampp-repair` works in a terminal |
| `/opt/xampp-panel/state/sites.json` | root, 0644 | List of sites (world-readable so the panel can list them) |
| `/opt/xampp-panel/install-manifest.txt` | root | Files outside `/opt/xampp-panel` that uninstall must delete |
| `/usr/share/polkit-1/actions/io.github.shiron.xampppanel.policy` | root, 0644 | Password-prompt policy |
| `/usr/share/applications/io.github.shiron.XamppPanel.desktop` | root, 0644 | App-menu entry |
| `/usr/share/icons/hicolor/scalable/apps/io.github.shiron.XamppPanel.svg` | root, 0644 | App icon |
| `/usr/share/icons/hicolor/scalable/status/xampp-panel-{running,stopped}.svg` | root, 0644 | Tray icons |
| `/usr/local/bin/xampp-panel` | symlink | So `xampp-panel` works in a terminal |
| `/run/xampp-panel/` | root, 0755 (tmpfs) | Created by `xampp-repair`: `repair.lock` (0600, one `xampp-repair` at a time) and, for the seconds a password reset runs, `reset-*/reset.sql` (`root:mysql`, 0710/0640, hash only); gone at reboot |
| `~/.config/xampp-panel/settings.json` | you, 0600 | Created when you change the tray option |

### Files it edits (all reversible, all backed up once)

Before the first change, each file gets a copy named `<file>.xampp-panel.bak`.

| File | Change | Marker you can grep for |
|---|---|---|
| `/opt/lampp/etc/httpd.conf` | `Listen 80` → `Listen 127.0.0.1:80` | `# xampp-panel: was "Listen 80"` |
| same | Include for managed vhosts | `# BEGIN xampp-panel vhosts` … `# END xampp-panel vhosts` |
| same | Include for lean mode (only if on) | `# BEGIN xampp-panel lean` |
| `/opt/lampp/etc/extra/httpd-ssl.conf` | `Listen 443` → `Listen 127.0.0.1:443` | `# xampp-panel: was "Listen 443"` |
| `/opt/lampp/etc/my.cnf` | `bind-address=127.0.0.1` added under `[mysqld]` | `# xampp-panel: localhost only` |
| same | Active `skip-networking` commented out (for good: `harden off` does not restore it) | none; it becomes `#skip-networking` |
| same | `!include` for lean mode (only if on) | `# BEGIN xampp-panel lean` |
| same | `init-file=…` under `[mysqld]`, only **during** "Reset forgotten MySQL root password" (removed in a `finally`; a leftover from a run killed with `kill -9` is removed when `xampp-repair` next starts) | `# xampp-panel: one-time root password reset (removed right after)` |
| `/opt/lampp/etc/proftpd.conf` | `DefaultAddress 127.0.0.1` + `SocketBindTight on` | `# BEGIN xampp-panel localhost` |
| same | `UserPassword daemon` replaced with a new hash (`xampp-repair` → "Fix FTP config" only, not `setup.sh`) | none; detected by `configedit.proftpd_password_broken` |
| `/etc/hosts` | `127.0.0.1  <name>.local` for each site | `# BEGIN xampp-panel sites` |
| `/opt/lampp/phpmyadmin/config.inc.php` | `auth_type`, `controluser`, `controlpass`, `pmadb` set/updated by `xampp-repair` (text edit via `pmaconfig.py`; owner kept, see `fsutil.atomic_write`) | none; read back with `pmaconfig.get_value` |

Files it creates inside XAMPP:

- `/opt/lampp/etc/extra/xampp-panel-vhosts.conf`: generated. **Don't edit it**, because it's rewritten on every site change.
  Its first vhost is `localhost` → `/opt/lampp/htdocs`, which keeps `http://localhost` and phpMyAdmin working.
- `/opt/lampp/etc/extra/xampp-panel-lean.conf` and `/opt/lampp/etc/xampp-panel-lean.cnf`: only while lean mode is on.

Quick check of everything the panel changed:

```bash
grep -rn "xampp-panel" /opt/lampp/etc/httpd.conf /opt/lampp/etc/extra/httpd-ssl.conf \
  /opt/lampp/etc/my.cnf /opt/lampp/etc/proftpd.conf /etc/hosts
```

### Permissions on your folders (ACLs)

Apache runs as the user `daemon`, which can't read your home folder by default. For each site, the
helper grants the minimum it needs, and it runs `setfacl` **as you**, not as root:

- `u:daemon:--x` (pass-through only) on `~` and on each folder between `~` and the site
- `u:daemon:r-X` (plus the default ACL) on the site folder, recursively

Check with `getfacl ~/Sites/<name> | grep daemon`. Removing a site revokes these permissions.

---

## 5. Root helper reference

`/opt/xampp-panel/bin/xampp-helper` must run as root. The panel calls it through `pkexec`.
`setup.sh` and `uninstall.sh` call it directly under `sudo`.

| Command | What it does |
|---|---|
| `start apache\|mysql\|ftp\|all` | `lampp startapache` etc. `all` = Apache + MySQL (**FTP is never started by "all"**) |
| `stop apache\|mysql\|ftp\|all` | `lampp stopapache` etc. `all` = `lampp stop` (everything) |
| `site-add NAME DIR` | Validates, grants ACLs, writes the vhost, runs `apachectl -t`, updates `/etc/hosts` and `sites.json`, reloads Apache if it's running |
| `site-remove NAME` | Reverse of the above. **The folder is kept.** |
| `log apache\|mysql` | Prints the last 64 KB of the log (refuses symlinks and non-regular files) |
| `lean on\|off` | Writes/removes the lean include files and include lines |
| `harden on\|off` | Localhost-only binding for Apache, MySQL and FTP |
| `integrate on\|off` | Adds/removes the managed vhost include. `off` also removes all sites. |

**Exit codes:** `0` ok · `1` a step failed (message on stderr) · `2` bad input (message on stderr).
Through `pkexec`, `126` means you closed the password dialog and `127` means not authorized or the helper is missing.
A line starting with `warning:` on stderr with exit `0` (e.g. "Apache did not reload") is shown as a notification in the panel.

Validation rules for `site-add`:

- **NAME:** `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$`
- **DIR:** absolute, and it must not contain `" $ \ * ? [ ]`, tab or newline. It must also meet all of these:
  - it isn't a symlink and isn't inside one
  - it's inside your home folder but isn't the home folder itself
  - it exists and is owned by you
  - it doesn't overlap an existing site (no site inside another)

Test it by hand. Put everything on **one line**: if `pkexec` ends up alone on a line, it opens a root shell.

```bash
pkexec /opt/xampp-panel/bin/xampp-helper site-add demo "$HOME/Sites/demo"; echo "exit=$?"
```

---

## 6. Security model

| Threat | Protection |
|---|---|
| Other devices on your Wi-Fi reaching MySQL (no root password by default) or phpMyAdmin | `harden on`: Apache, MySQL and FTP listen on `127.0.0.1` only |
| Running arbitrary commands as root through the panel | The helper accepts a fixed command list, uses no shell, and runs with a fixed `PATH`/env (`SAFE_ENV`) |
| Loading Python code from somewhere the user controls | Launchers use `python3 -I` (ignores `PYTHON*` env vars and user site-packages). Code lives in root-owned `/opt/xampp-panel/lib`. |
| Pointing a site at a system folder, or at a symlink to one | Path checks (above). ACLs are applied **as the user**, so even a swapped symlink can't give Apache access to files the user can't already grant. |
| Injecting Apache config through a site name or path | Strict name regex; quotes, `$`, backslash, wildcards and newlines are banned in paths |
| Anyone using the password prompt remotely | polkit policy: `allow_active = auth_admin_keep`; inactive and remote sessions are denied |
| A damaged, swapped or planted XAMPP installer run as root by `setup.sh` | Only the pinned, checksummed file (`$XAMPP_FILE`) is picked up automatically, and only from the project folder and `~/Downloads` (not the folder above the project, which may be shared, e.g. `/tmp`). Other versions found there are only named in a hint (only file names matching the strict `xampp-linux-x64-<version>-<n>-installer.run` pattern, so no odd characters in a file name reach the terminal; the path is shell-quoted with `%q` so the suggested command can be pasted); a stray or planted `xampp-linux-x64-99.0-…` is never run. Whatever runs is first copied into a root-only folder under `/root` (`mktemp -d -p /root`, so not `$TMPDIR` and not a noexec `/tmp`); for the pinned version the SHA-256 is checked **on that copy**, which is what runs. Downloads and deletions in `~/Downloads` run as the user (`runuser`); curl is HTTPS-only, also on redirects, TLS 1.2+. A pinned file with a wrong checksum stops the install; it is deleted only if `setup.sh` downloaded it in this run. Another version runs only when given with `--installer` (the user's explicit choice), and then unchecked. curl runs with `-q` (no `~/.curlrc`) and its stdout goes to stderr, so nothing it prints can change the path `setup.sh` runs. |
| A broken config taking Apache down | `apachectl -t` runs before every site change; on failure the previous vhost file is restored |

**Accepted limitation:** every site's PHP runs as `daemon` and can read anything `daemon` can read,
including your other sites. That's normal for XAMPP and fine on a single-user computer.

### `xampp-repair`'s security model

- **Runs as root only via `sudo`** in a terminal the user opened (or directly by `setup.sh` as
  root); `main()` in `repair.py` refuses to proceed if `os.geteuid() != 0`. There is no `pkexec`
  action for it — the whole tool is one program, not a set of whitelisted commands, because it is
  always run interactively by a human who already has root.
- **Passwords never touch argv or the environment:**
  - MySQL root/`pma` passwords and all SQL go to `mysql`/`mysql_upgrade` on **stdin**; the
    username/password pair goes in a `tempfile.mkstemp` `--defaults-extra-file` (mode 0600),
    deleted in a `finally` (`mysqladmin.MysqlAdmin._client`).
  - The SQL on stdin is always UTF-8 (`encoding="utf-8"`, not the locale), like the option file:
    MariaDB stores a hash of the bytes it receives, and a login (phpMyAdmin, a UTF-8 terminal) sends
    UTF-8, so a non-ASCII password set under another locale would otherwise never log in.
  - The FTP password is piped to `openssl passwd -6 -stdin`, never passed as an argument.
  - Every SQL batch containing an escaped value starts with
    `SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '')`, so `\`/`'` escaping
    means the same thing regardless of the server's configured `sql_mode`.
  - MySQL account lists (which accounts to drop/alter) are built by MariaDB itself
    (`GROUP_CONCAT` over `mysql.user` + `EXECUTE IMMEDIATE`), not assembled in Python, so there is
    one query to audit instead of string-built `DROP USER`/`ALTER USER` statements per account.
- **`config.inc.php` is parsed as text, never executed** (`pmaconfig.py`): only single-quoted
  `$cfg['Servers'][$i]['key'] = '...';` assignments are read or written, with PHP's own `\\`/`\'`
  escaping. No `php` or `eval` is invoked.
- **`pma` gets least privilege:** `SELECT, INSERT, UPDATE, DELETE` on `phpmyadmin.*` only, never
  `GRANT OPTION` or access to any other database.
- **Deviation from the design spec:** "Show phpMyAdmin pma password" uses `Dialogs.secret`
  (writes the text to a 0600 temp file and shows it with `whiptail --textbox`, deleting the file
  afterwards) instead of `whiptail --msgbox`. A `--msgbox` argument lands on the process's argv,
  which anyone on the machine can read from `/proc/<pid>/cmdline` while the dialog is open; a
  private temp file does not have that problem. The design doc's component list already named
  `textbox` as one of the wrapped dialogs; this is the only screen that uses it instead of
  `msgbox` for that reason.

---

## 7. How status detection works

- **Where the logic lives:** `services.snapshot()` returns one of four states for each service:

| State | Meaning | Panel shows |
|---|---|---|
| RUNNING | XAMPP process found **and** its port is listening | green dot |
| STARTING | XAMPP process found, port not listening yet | amber, "starting…" |
| STOPPED | no process, port free | grey |
| CONFLICT | port busy, but not by an XAMPP process | red, "port used by another program" |

- **How a process counts as XAMPP's:**
  1. Its name must be `httpd`, `mysqld`/`mariadbd` or `proftpd`. The name is taken from `/proc/<pid>/comm` **or** from the program name in `cmdline`.
  2. Except for ProFTPD, its command line must also contain `/opt/lampp`.
- **Found on the real machine:** XAMPP's Apache reports `comm` as `/opt/lampp/bin/` (its path cut to 15 characters), not `httpd`.
  - Before fix `23307a9`, the panel therefore showed a false **CONFLICT** on port 80.
  - If a future XAMPP version shows a false CONFLICT, check how the process names itself:
    ```bash
    for p in $(pgrep -f /opt/lampp/); do echo "$p [$(cat /proc/$p/comm)] $(tr '\0' ' ' </proc/$p/cmdline)"; done
    ```
- **When status refreshes (resource use):**
  - **inotify** on `/opt/lampp/logs`, `/opt/lampp/var` and `/opt/lampp/var/mysql` reacts only to `.pid`/`.sock` changes, with a 300 ms debounce.
  - **Fallback check** every 10 s, only while the panel window is focused. The tray checks every 30 s.
  - **No subprocesses** are used for status. Closing the window exits the panel unless the tray is on.

---

## 8. Lean mode

Menu → "Lean mode", or `sudo ./setup.sh --lean`. Takes effect after restarting Apache and MySQL.

- **Apache** (prefork MPM): `StartServers 2`, `MinSpareServers 1`, `MaxSpareServers 3`, `MaxRequestWorkers 20`,
  `MaxConnectionsPerChild 1000`.
- **MySQL:** `innodb_buffer_pool_size=16M`, `max_connections=30`.
- **Measured on this machine:** XAMPP's own buffer pool is already 16M (MySQL log: "total size = 16M"), so
  the MySQL half mostly caps connections. The savings have **not been measured**. To measure:
  `ps -o rss= -C mysqld` and `ps -o rss= -C httpd` before and after.
- Check that Apache really uses prefork: `/opt/lampp/bin/httpd -V | grep -i mpm`. If it doesn't, the Apache block has no effect.

---

## 9. Build history and decisions

The build went through brainstorm → spec → plan → implementation. Each task had its own review, then a
final whole-project review and fixes. Security-sensitive parts were reviewed by the strongest model.

| Commit | What |
|---|---|
| `3923ab2` | Paths and safe file helpers |
| `4ecd218` | Service status from `/proc` |
| `81e4534` | Reversible config edits, site model |
| `e16f5a2`, `36e5b68` | Root helper; then fixes: rollback, safe log reads, daemons can't hold the helper's output pipe |
| `08ed6de`, `f3b85fa` | pkexec handling, settings; strict settings types |
| `1dd96f1`, `558bc75`, `b467e85` | Panel and tray; then fixes: startup safety, busy state, markup escaping, log refresh |
| `8ca9ac6` | Desktop entry, polkit policy, icons |
| `533398f`, `fdfe944` | setup/uninstall/README; uninstall keeps going past failed steps |
| `87b68c1` | Final review fixes: lean values, keep backups when a revert fails, surface helper warnings, pkexec 127 message, wildcard path chars |
| `23307a9` | Host fix: detect XAMPP processes whose comm is a truncated path |
| `64dcc65` | Host fix: `harden on` replaces `skip-networking`; `setup.sh` hardens after `lampp security`; banner warning |
| `326e82f` | `tools/fix-pma.sh`/`fix-pma.php` and `tools/secure-mysql.sh`: one-off scripts for the pma control user and root password/anonymous accounts (superseded below) |
| `cee3d20`, `3450fda`, `9afd8e8` | `fsutil.atomic_write` keeps the file's owner; new paths for the repair tool |
| `2fa2c5a` | `pmaconfig.py`: read/write phpMyAdmin's `config.inc.php` as text |
| `e9556f3` | `mysqladmin.py`: SQL builders and a `mysql`/`mysql_upgrade` client runner that keeps passwords off argv and in a 0600 defaults file |
| `1dc0533` | `configedit.py`: detect/repair the FTP password breakage and MySQL networking |
| `0c49c2b` | `dialogs.py` (whiptail wrapper) and shared test fakes |
| `3873a06` | `health.py`: read-only health report, each finding naming its fix |
| `2e87555` | `repair.py` (`RepairApp`, `bin/xampp-repair`): the menu, its flows, `first-install`; account setup moved out of `tools/` |
| `499ca04` | Security fix: "Show phpMyAdmin pma password" uses a 0600 tempfile + `--textbox`, not a `--msgbox` argument (passwords must never be on a process's argv) |
| `6721c49` | `setup.sh` runs `xampp-repair first-install` instead of `lampp security` |
| `8770da2` | Panel ☰ "Repair & configure…" opens a terminal running `sudo xampp-repair` (`terminal.py`) |
| `1a7ba0b` | `tools/` deleted; its tests removed; README/MAINTAINER/USER-GUIDE/spec updated to match |
| `5f2b3e4` | Review fix: a running `mysqld` without its port (skip-networking) counts as running in `xampp-repair` and the health check; "Turn MySQL networking back on" uses `mysql_networking_on`, not `harden` |
| `bbc0c53` | Review fix: refuse a `root`/odd phpMyAdmin `controluser`; SIGHUP/SIGTERM exit through `finally` (temp files removed); subprocess timeouts reported |
| `311d44d` | Review fix: re-running `first-install` keeps a working `pma` and an existing root password; Cancel on "Repeat it" cancels; "Starting MySQL" notice |
| `d1cd3b5` | Review fix: public `Helper.apply_sites`; tighter tests |
| `c8a867e` | Docs updated to the review fixes |
| `153aaed` | Fix wave 2: `MysqlAdmin.can_login` is False only on "access denied" (`AccessDenied`: errors 1044/1045/1049/1698), other errors propagate; `ping()`; `_ensure_mysql` waits until MySQL answers; the health check reports "MySQL: cannot connect" |
| `0a6917b` | Fix wave 2: Esc on a yes/no question raises `Cancelled` (was: No); `Cancelled` moved to `dialogs.py` |
| `30c84d7` | Fix wave 2: `harden off` no longer restores `skip-networking`; old restore markers are dropped |
| `c953c2b` | Fix wave 2: first install drops anonymous accounts when the root password is known from the `pma` step |
| `b3cee33` | Fix wave 2: test tidying |
| `e9b6bbf` | Docs for fix wave 2 |
| `b927dd7` | Fix wave 3: login probes (`can_login`, `ping`) use `--connect-timeout=5` and a 10 s limit instead of 120 s; `_ensure_mysql` waits on a monotonic deadline (injected `clock`), not a count of rounds |
| `9fc18fa` | Fix wave 3: `ping()` also counts errors 1040/1129/1130/1862 as "the server answers"; `can_login` still raises them |
| `0b6ed50` | Docs for fix wave 3 (USER-GUIDE: "Run mysql_upgrade" acts without a question) |
| `2d904ca` | `setup.sh` downloads XAMPP 8.2.12 when no installer is found (`lib/xampp-download.sh`), checks its SHA-256 and runs a private copy |
| `9ea8b88` | Review fixes for the download: pinned file wins over a name that sorts later, folder above the project no longer searched, failed copy ≠ wrong checksum, resumable download with stall timeout, private copy under `/root`, deletes as the user, whole decision in the tested `xampp_prepare` |
| `63c0489` | Second review: only the pinned file is used automatically (other versions need `--installer`, a hint names them); curl `-q` and stdout to stderr; tests check what runs as the user and that the download really resumes |
| `4cdecda` | Third review: the hint's `--installer` path is shell-quoted; `--help` says only the pinned version is checksummed; doc and test-comment precision |
| `6c40e9e` | "Reset forgotten MySQL root password" (`repair.reset_root_password`, `configedit.mysql_init_file`, `mysqladmin.reset_root_sql`, health finding for a leftover line); a wrong current root password points to it |
| `8a29444` | Review fixes for the reset: hash only in the file, `/run/xampp-panel` with `root:mysql` 0710/0640 and the group set via the open descriptor, folder removed first and signals blocked during cleanup, stale line removed on start, combined restart message, MySQL left as it was, `mysql` user checked first |
| this task | Second review: stale-line clean-up only deletes `<runtime>/reset-*/` folders; MySQL left as it was on every path; success stays success if the final stop fails; clearer clean-up messages; one `xampp-repair` at a time (`flock`); SQL on stdin always UTF-8 |

Decisions made during the build (and what they cost if wrong):

- **Failed Apache reload after a site change:**
  - What happens: it's a *warning*, not an error.
  - Why: the config already passed `apachectl -t`, so the saved state is consistent.
  - Cost if wrong: you may need to restart Apache by hand.
- **XAMPP start/stop output:** it goes to a temp file, not a pipe, so the Apache and MySQL daemons can't keep the panel waiting forever.
- **Wrong-typed settings values:** they're ignored and the default is used.
- **Uninstall:** it continues past a failed revert step, but then **keeps** the `.bak` files and lists them.
- **"Start" button:** it starts Apache + MySQL only. FTP must be switched on explicitly.
- **"MySQL is running" in `xampp-repair`:** a live XAMPP `mysqld` process, port or not
  (`services.running_services`). With `skip-networking` port 3306 never listens, but the `mysql`
  client still connects through the socket, so starting MySQL again would only fail.
- **`skip-networking` vs `bind-address`:** "localhost only" uses `bind-address=127.0.0.1` and removes
  `skip-networking`. Both keep MySQL off the network, but `skip-networking` also breaks `127.0.0.1`
  clients and the panel's port-based status check. That is also why `harden off` does not put it
  back: `--allow-lan` means TCP on, whatever `lampp security` once wrote.
- **"Wrong password" vs "cannot connect":** `MysqlAdmin.can_login` answers False only when MySQL
  refused the login (errors 1044, 1045, 1049, 1698 in the client's stderr → `AccessDenied`). Any
  other client error (e.g. 2002, socket missing while MySQL starts) is raised, so a starting server
  is never mistaken for "root has a password". `ping()` treats success, `AccessDenied` and the
  refusals that are not about the password (1040 too many connections, 1129 host blocked, 1130 host
  not allowed, 1862 password expired) as "the server answers"; `can_login` still raises those, so
  the caller shows MySQL's own message. `_ensure_mysql` polls `ping()` once a second until a
  monotonic deadline of `MYSQL_WAIT_SECONDS` (20 s) and does not sleep after the last poll.
- **Timeouts:** probes (`can_login`, `ping`) pass `--connect-timeout=PROBE_TIMEOUT` (5 s) and are
  killed after `PROBE_TIMEOUT + 5` s; `execute` and `mysql_upgrade` get `TIMEOUT` (120 s), since
  real work can take long. A hanging probe therefore stretches the 20 s readiness wait by at most
  one probe (about 10 s), not by 120 s per round.
- **Forgotten root password: `init-file`, not `--skip-grant-tables`.** `reset_root_password`:
  1. Checks the `mysql` user exists (`MYSQL_USER`, whom XAMPP's `mysqld_safe` runs `mysqld` as)
     before asking anything else, then asks for the new password.
  2. Writes **only the password's hash** (`ALTER USER 'root'@'localhost' IDENTIFIED BY PASSWORD
     '*…'`, `mysqladmin.reset_root_sql` / `native_password_hash`) into `reset.sql` in a fresh
     `mkdtemp` folder under `/run/xampp-panel` (tmpfs, `Paths.runtime`, refused unless it is a real
     root-owned folder nobody else can write). Folder `root:mysql 0710`, file `root:mysql 0640`
     (`O_EXCL|O_NOFOLLOW`, group set through the open descriptor): mysqld can read it, nobody but
     root can swap or change it. The plaintext never touches disk because anything mysqld can read,
     a MySQL account with the FILE privilege can read too (`LOAD_FILE(@@init_file)`).
  3. Adds `init-file=<that file>` under `[mysqld]` (`configedit.mysql_init_file`, absolute path
     restricted to `/[A-Za-z0-9_./-]+`) and starts MySQL with the normal `lampp startmysql`.
     MariaDB runs the file once at startup **with password checks on**, so unlike
     `--skip-grant-tables` nobody can connect without a password at any moment, and XAMPP's own
     start command is reused instead of copied.
  4. Cleans up in a `finally`, with SIGINT/SIGHUP/SIGTERM blocked meanwhile: the folder first, then
     the `my.cnf` line. If that fails (e.g. disk full) it says exactly what to remove and does not
     restart MySQL.
  5. Restarts MySQL normally (one combined message if that fails, saying whether the reset itself
     worked), verifies the new password with a login, remembers it, and runs
     `_set_root_password(new, new)`: the real password over stdin on every root account (127.0.0.1,
     ::1; same hash), anonymous accounts dropped, phpMyAdmin switched to its login page. MySQL is
     stopped again if it was stopped before.

  MySQL is left the way it was: if it was stopped before, it is stopped again at the end, also
  after a failed reset (a failure to stop it is added to the message, and a successful reset still
  says "Done"). A run killed with `kill -9` can leave the `my.cnf` line (every start would run it
  again); `xampp-repair` removes such a leftover (`remove_stale_reset`) every time it starts, but
  deletes a folder only if the line names exactly `<runtime>/reset-*/reset.sql` (no `..`, no
  symlink); any other path just loses its line. Only one `xampp-repair` runs at a time
  (`single_instance`: `flock` on `/run/xampp-panel/repair.lock`), so that start-up clean-up can never
  remove a reset another copy is in the middle of. The folder is in tmpfs anyway. Cost if wrong: if MariaDB fails on the file, MySQL is started normally again
  and the user sees the error. Not verified against a real MariaDB here (no server in the sandbox);
  see the manual check in the plan's Task 11.
- **Esc on a yes/no question:** whiptail exits 255 on Esc; `Dialogs.yesno` raises `Cancelled` then,
  so Esc never counts as "No" (it used to turn localhost-only off in "Re-apply panel config").
- **XAMPP download:** pinned to one version with a SHA-256 instead of "the newest", because the
  installer runs as root and Apache Friends publishes only MD5/SHA-1. The SHA-256 was taken from a
  download that matched the published MD5 and SHA-1. Cost if wrong: a newer XAMPP needs the two
  values in `lib/xampp-download.sh` bumped by hand (see §12).
- **XAMPP download resumes:** curl runs with `--continue-at -` in a loop of `XAMPP_ATTEMPTS` (not
  `--retry`, which would restart from byte 0), and `--speed-limit 1 --speed-time 60` so a stalled
  connection fails into the next attempt instead of hanging. A `.part` left by Ctrl-C is resumed by
  the next run; after the last failed attempt it is deleted, so a corrupt `.part` can't stick. The
  checksum guards the result either way.
- **Minimum platform:** GTK 4.6 / libadwaita 1.1 / GLib 2.72. Newer widgets (`Adw.Banner`, `Gtk.FileDialog`) are used only when available.

---

## 10. Known issues and limitations

| Issue | Workaround |
|---|---|
| If your home folder path contains a symlink, every "Add site" is refused with a misleading "symbolic link" message | Check with `[ "$(readlink -f ~)" = "$HOME" ] && echo ok` |
| `uninstall.sh` doesn't close an open panel window | Close the panel first |
| The FTP row has no log button (ProFTPD log location in XAMPP 8.2 unconfirmed) | Look in `/opt/lampp/logs/` and `/opt/lampp/var/` |
| A log line longer than 64 KB shows as empty in the log viewer | Read the file directly |
| If `/etc/hosts` is a symlink (rare), editing it replaces the link with a regular file | Not an issue on Zorin |
| MariaDB warns `Incorrect definition of table mysql.event` / `mysql.column_stats` / `Please run mysql_upgrade` | `sudo xampp-repair` → "Run mysql_upgrade" |
| XAMPP's own `lampp security` would break things (`skip-networking`, FTP config). **Not run any more**: `setup.sh` runs `xampp-repair first-install` instead | Nothing to do on a fresh install. If you ran `lampp security` by hand, see the next three rows |
| `Access denied for user 'pma'@'localhost'` in the MySQL log or phpMyAdmin | `sudo xampp-repair` → "Fix phpMyAdmin pma login" (§11) |
| XAMPP ships an anonymous MariaDB account and no root password | `sudo xampp-repair` → "Change MySQL root password" (§11) |
| Forgotten MySQL root password | `sudo xampp-repair` → "Reset forgotten MySQL root password" |
| MySQL stuck "starting…", log says `port: 0` (`skip-networking` active) | `sudo xampp-repair` → "Turn MySQL networking back on" |
| FTP won't start: `unknown configuration directive 'function'` | `sudo xampp-repair` → "Fix FTP config" |
| Starting `xampp-panel` from SSH/remote terminal fails with "Gtk couldn't be initialized" | Normal: there's no display. Open it from the app menu. Errors are then in `journalctl --user` |
| `shellcheck` was never run on the scripts | `shellcheck -x setup.sh uninstall.sh lib/xampp-download.sh` |

---

## 11. Troubleshooting

Always start by reading the actual error. The panel's own errors appear at the bottom of its window.
Anything else goes to the user journal:

```bash
journalctl --user --since "10 min ago" | grep -iA25 xampp
```

For anything below involving MySQL accounts, phpMyAdmin or ProFTPD, `sudo xampp-repair` →
**"Health check"** is a good first step: a read-only report of services, config problems, MySQL
accounts and phpMyAdmin's login, each naming the menu item that fixes it.

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Switch flips back, no message | Password dialog closed (exit 126) | Try again and enter your password |
| "Not authorized, or the XAMPP Panel helper is missing" | Wrong password, or `/opt/xampp-panel/bin/xampp-helper` missing / not executable | `ls -l /opt/xampp-panel/bin/`; re-run `sudo ./setup.sh` |
| "port used by another program" | Another server (Ubuntu's `apache2`, `nginx`, `mysql`), **or** a detection problem | `sudo ss -ltnp 'sport = :80'`. If it names `/opt/lampp/...`, it's XAMPP (see §7) |
| phpMyAdmin: `mysqli::real_connect(): (HY000/2002): No such file or directory` | MySQL isn't running (its socket file is missing) | Start MySQL; if it won't start, see the MySQL log |
| phpMyAdmin: `Access denied for user 'pma'@'localhost'` / "Connection for controluser … failed" | `lampp security` (or a broken config) set `controlpass` in `config.inc.php` but not on the MySQL `pma` account | `sudo xampp-repair` → **"Fix phpMyAdmin pma login"**. Creates the `phpmyadmin` storage tables if missing, creates/updates `pma` with the config's password (never on a command line) and grants it `SELECT, INSERT, UPDATE, DELETE` on that database only; confirms the login works before reporting success. Safe to re-run |
| phpMyAdmin: `#1044 - Access denied for user ''@'localhost' to database …` | Logged in as MariaDB's anonymous account: a user name other than `root` with no password matches `''@'localhost'` (needs root without a password, the anonymous account, and `AllowNoPassword`) | Right now: log out of phpMyAdmin and log in as `root`. For good: `sudo xampp-repair` → **"Change MySQL root password"**. Asks for the current root password only if root has one, then the new one twice (8–128 characters). MariaDB itself lists the accounts (`EXECUTE IMMEDIATE` over `mysql.user`), so every `''@<host>` is dropped and every `root@<host>` gets the password, in one `mysql` session. If phpMyAdmin's `auth_type` is `config` (auto-login as root), it is switched to `cookie` **after** the password change succeeded, with a one-time backup `config.inc.php.xampp-panel.bak`. If a statement fails, `mysql` stops there: at worst the anonymous accounts are gone and root is unchanged. Then log in to phpMyAdmin as `root` with the new password |
| MySQL won't start | See its log | `sudo tail -n 40 /opt/lampp/var/mysql/$(hostname).err` |
| MySQL stuck on "starting…"; log says `port: 0` | `skip-networking` active in `my.cnf` | `sudo xampp-repair` → **"Turn MySQL networking back on"** (comments out `skip-networking`, leaves `bind-address` to `harden`, offers a MySQL restart). Manual fallback: `sudo grep -n networking /opt/lampp/etc/my.cnf`; then `sudo /opt/xampp-panel/bin/xampp-helper harden on` and `sudo /opt/lampp/lampp stopmysql && sudo /opt/lampp/lampp startmysql` |
| `xampp-repair`: "MySQL did not start" / "MySQL is running but does not answer", or the health check says "MySQL: cannot connect" | `mysqld` is not accepting connections within 20 s (still starting, crashed, socket missing) | Check the MySQL log in the panel (or `/opt/lampp/var/mysql/$(hostname).err`), restart MySQL from the panel, then run the item again |
| FTP won't start: `unknown configuration directive 'function'` | `lampp security` wrote PHP source into `proftpd.conf` | `sudo xampp-repair` → **"Fix FTP config"**. Detects the broken block, asks for a new FTP password for the `daemon` user, hashes it with `openssl passwd -6 -stdin` (never on argv), writes it back (one-time backup) and validates with `proftpd -t`, restoring the old config if that fails |
| Apache won't start | Config error | `sudo /opt/lampp/bin/apachectl -t`; `sudo tail -n 40 /opt/lampp/logs/error_log` |
| `http://name.local` "site can't be reached" | Site not created, or name not resolving | `grep -A5 "BEGIN xampp-panel sites" /etc/hosts`; `cat /opt/xampp-panel/state/sites.json`; `getent hosts name.local` |
| `name.local` gives **403 Forbidden** | Apache can't read the folder | `getfacl ~/Sites/name \| grep daemon`; remove and re-add the site |
| `name.local` shows the XAMPP welcome page | Apache not reloaded after the site was added | Restart Apache from the panel |
| Chrome still can't open `.local` while `curl -I http://name.local` works | Chrome "Secure DNS" bypassing `/etc/hosts` | Chrome settings → Privacy → Security → turn off "Use secure DNS", or use Firefox |
| Tray option greyed out ("needs the AppIndicator extension") | No AppIndicator/StatusNotifier support running in GNOME | Enable the AppIndicator extension in the Extensions app (on Zorin, check Zorin Appearance → Extensions); then reopen the panel |
| Everything looks wrong after an XAMPP reinstall | XAMPP's config files were replaced | See §12, "Upgrading XAMPP" |

Full manual reset of the config, if the tools themselves are broken:

```bash
sudo /opt/lampp/lampp stop
# each edited file has a one-time backup of the original:
ls /opt/lampp/etc/*.xampp-panel.bak /opt/lampp/etc/extra/*.xampp-panel.bak /etc/hosts.xampp-panel.bak
# restore one, e.g.:
sudo cp /opt/lampp/etc/httpd.conf.xampp-panel.bak /opt/lampp/etc/httpd.conf
```

Only restore `/etc/hosts` from its backup if you haven't edited it for other reasons since.

---

## 12. Upgrading

### Updating the panel after changing its code

```bash
cd ~/Downloads/xampp-panel          # or wherever you cloned the repo
PYTHONPATH=src python3 -m unittest discover -s tests   # must say OK
sudo ./setup.sh --no-lean     # re-running is safe; it stops XAMPP, reinstalls the code, re-applies config
```

`setup.sh` is idempotent: steps already done are skipped or give the same result. Use `--lean` instead of
`--no-lean` if you use lean mode. For a single changed file, copying it is enough:

```bash
sudo install -o root -g root -m 0644 src/xampp_panel/<file>.py /opt/xampp-panel/lib/xampp_panel/
```

### Checking the installed copy matches the repo

```bash
cd ~/Downloads/xampp-panel
diff -r -x __pycache__ src/xampp_panel /opt/xampp-panel/lib/xampp_panel && echo "installed = repo"
```

If it prints differences, re-run `sudo ./setup.sh --no-lean` (or `--lean`).

### Upgrading XAMPP (new version or reinstall)

A new XAMPP installer replaces `/opt/lampp`, including its config files, so the panel's edits disappear.
**Back up your databases first**, from phpMyAdmin → Export or with `mysqldump`. Then:

```bash
sudo /opt/lampp/lampp stop
# run the new XAMPP installer, then:
sudo /opt/xampp-panel/bin/xampp-helper integrate on   # re-creates the vhost file from sites.json
sudo /opt/xampp-panel/bin/xampp-helper harden on
sudo /opt/xampp-panel/bin/xampp-helper lean on        # only if you use lean mode
sudo /opt/lampp/bin/mysql_upgrade -u root             # if MariaDB's version changed
```

Your sites stay listed in `sites.json` and `/etc/hosts`, and your folder ACLs are untouched.

Then check the things that depend on XAMPP internals. The panel relies on each of these:

```bash
grep -nE '^\s*"?(startapache|stopapache|reloadapache|startmysql|stopmysql|startftp|stopftp)\b' /opt/lampp/lampp
ls -l /opt/lampp/bin/apachectl /opt/lampp/bin/mysql
grep -nE '^(User|Group|Listen)' /opt/lampp/etc/httpd.conf    # expect User daemon, Listen 127.0.0.1:80
```

If `User` isn't `daemon`, change `APACHE_USER` in `src/xampp_panel/helper.py`. If a path changed,
change it in `src/xampp_panel/paths.py`. That's the only place paths live.

### Changing the XAMPP version `setup.sh` downloads

`setup.sh` downloads only when `/opt/lampp` is missing, no `--installer` is given and the pinned file
is in neither the project folder nor `~/Downloads` (other versions there don't count). The version is
pinned in `lib/xampp-download.sh` (`XAMPP_VERSION`, `XAMPP_SHA256`; `XAMPP_FILE` and `XAMPP_URL`
are built from the version). To move to a new one:

1. Download the new installer from https://www.apachefriends.org/download.html.
2. Compare `md5sum` / `sha1sum` of the file with the values the download page shows
   (hover "md5" / "sha1" next to the Linux download). Apache Friends publishes no SHA-256.
3. Put the new version and the file's `sha256sum` into `lib/xampp-download.sh`. Check the file
   name pattern (`-0-installer.run`) and the SourceForge folder still match the new release.
   `--help` follows automatically; update the version in README, USER-GUIDE and
   `tests/test_xampp_download.py` (`PINNED`, and the `--help` test in `tests/test_scripts.py`).
4. Run the suite.

Use the same version on machines whose databases you copy around: a raw MySQL data folder only
works on the same MariaDB version.

### Upgrading Zorin OS / Ubuntu

The panel uses the system's Python 3, PyGObject, GTK 4 and libadwaita. After a major upgrade:

```bash
python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Adw; print(Adw.get_major_version(), Adw.get_minor_version())"
```

If the packages were removed, re-running `sudo ./setup.sh` reinstalls them.

---

## 13. Development

```bash
cd ~/Downloads/xampp-panel
PYTHONPATH=src python3 -m unittest discover -s tests -v   # 259 tests; GUI import test needs PyGObject
PYTHONPATH=src python3 -m xampp_panel.main                # run the panel from source (uses installed helper)
```

- **Rule for all pure modules:** stdlib only, Python ≥ 3.10.
- **How tests stay safe:** `Paths` is overridden in tests, so nothing touches the real `/opt` or `/etc`. The helper tests inject
  a fake command runner and a fake user database.
- **Before committing:** run the full suite. Run `bash -n setup.sh uninstall.sh` too if you touched the scripts.

### Adding a helper command

1. Add a `case [...]` line to `Helper.dispatch` in `helper.py` and a line to `USAGE`.
2. Validate every argument; call subprocesses only through `self._run` / `self._run_lampp` (no shell, `SAFE_ENV`).
3. Add tests in `tests/test_helper.py`, including a rejected-input test.
4. Call it from the GUI with `self.call_helper([...], done=..., failed=...)` in `window.py`.

### Adding a service

Add a `Service(...)` to `SERVICES` in `services.py` (key, title, description, port, process names). Then:

- add start/stop actions to `_START`/`_STOP` in `helper.py`
- add a log path to `services.log_path` if it has one
- add a test in `tests/test_services.py`

### Changing a path

Only in `paths.py`. `test_paths.py` pins the defaults. The polkit policy (`data/…policy`) and the
`.desktop` file contain the helper and launcher paths too; `test_data.py` checks that they match.

### Adding an `xampp-repair` fix

1. Write the pure logic first: a detector (`configedit.py` or a new read in `health.py`/`pmaconfig.py`)
   and, if it touches MySQL, a SQL builder in `mysqladmin.py` (escape with `sql_quote`, start the
   batch with the `sql_mode` guard if it contains an escaped value).
2. Add a method to `RepairApp` in `repair.py`: read state, ask with `self.dialogs.*`, apply the change
   with `self._write(path, new_text)` (backs up once, writes atomically) or `self.admin.execute(sql,
   self._root())`, then confirm it worked before showing success. Let `RepairError`/`MysqlError`/
   `HelperFailure` propagate — `_attempt` catches them and shows a msgbox; don't swallow errors yourself.
3. Add it to `menu_items()`. If the health check should flag the problem, add a `FIX_*` label constant
   in `health.py` and a `Finding` in `HealthCheck`, reusing that label so the two stay in sync.
4. Test `repair.py`'s method with `FakeDialogs` (script the answers) and a fake admin/helper (assert
   ordering and the failure path); test any new `configedit`/`mysqladmin`/`pmaconfig` function on its
   own first. `tests/fakes.py` has the shared fakes.
5. If it's relevant during a fresh install, call it from `first_install()` via `self._step(name, step,
   fix_label)` so a failure is reported but doesn't abort `setup.sh`.
6. Document it: one line in the "Main menu" table (§ design spec or here), and a troubleshooting row
   in §11 / `docs/USER-GUIDE.md` pointing at the new menu item.
