# XAMPP Panel — Technical Reference

Use this when something breaks, when you upgrade XAMPP or the OS, or when you
want to change the panel. For everyday use, see [USER-GUIDE.md](USER-GUIDE.md).

- **Version:** 0.1.0 (built 2026-09-23)
- **Target:** Zorin OS (GNOME, Wayland), x86_64; works on Ubuntu 22.04+ bases
- **XAMPP:** 8.2.12 (`xampp-linux-x64-8.2.12-0-installer.run`, MariaDB 10.4.32)
- **Repo:** https://github.com/shircil07/Xampp-For-gnome (private), branch `master`; local copy `~/Downloads/xampp-panel`
- **Design history:** `docs/superpowers/specs/2026-09-23-xampp-panel-design.md` (the spec) and
  `docs/superpowers/plans/2026-09-23-xampp-panel.md` (the task-by-task plan)

---

## Handover — 2026-09-23 (evening)

State on the original machine (`zbook`) after this session: Apache, MySQL and ProFTPD all start from the
panel; MySQL listens on `127.0.0.1:3306` again; `mysql_upgrade` has been run.

What broke and why (both caused by XAMPP's own `lampp security` script, not by the panel):

1. **MySQL had TCP switched off** (log: `port: 0`). `lampp security` offers to "turn off network access"
   and adds `skip-networking` to `my.cnf`. `setup.sh` ran that step *after* `harden on`, so the panel's
   `bind-address` was defeated. Clients using `127.0.0.1` failed and the panel showed MySQL as
   "starting…" forever (it waits for port 3306).
   **Fixed in code:** `harden on` now comments out an active `skip-networking` (reversible, see §4), and
   `setup.sh` applies harden **after** the password step.
2. **ProFTPD wouldn't start** (`unknown configuration directive 'function' on line 44`). `lampp security`
   sets the FTP password by running a PHP snippet; with short tags off, PHP printed the snippet's source
   and it was pasted into `proftpd.conf` as the `UserPassword daemon` value. **Fixed by hand** (see §11);
   the broken file is kept as `/opt/lampp/etc/proftpd.conf.broken`.
3. **phpMyAdmin: `Access denied for user 'pma'@'localhost'` / "Connection for controluser as defined in
   your configuration failed"** (seen 2026-10-06). `lampp security` wrote a `controlpass` into
   `/opt/lampp/phpmyadmin/config.inc.php` (line 48; the original blank line 47 commented out) but did not
   make the MySQL account `pma` match. **Fixed with `tools/fix-pma.sh`** (see §11), which reported `OK`.
4. **phpMyAdmin: `#1044 - Access denied for user ''@'localhost' to database 'students'`** (2026-10-06).
   Root still had **no password** and XAMPP's
   anonymous account `''@'localhost'` (no password, no rights) still existed. With phpMyAdmin's cookie
   login and `AllowNoPassword = true`, signing in with any user name other than `root` and no password
   silently logs in as the anonymous account. **Fix: `tools/secure-mysql.sh`** (see §11) drops the
   anonymous accounts and sets the root password; the panel's banner now points to it instead of
   `lampp security`.

Still open:

- `setup.sh` still runs `lampp security` for the password step. Switching it to `tools/secure-mysql.sh`
  would avoid all four problems above on new installs.
- A "Repair & configure" menu entry that opens a terminal with these fixes (whiptail menu) is being
  designed; `tools/` would move into it.
- No automatic repair of a `proftpd.conf` already broken by `lampp security`.

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
| Root helper (`xampp-helper`) | The **only** code that runs as root, started through `pkexec` (graphical password prompt) |

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
      └─ Tray (GTK3, separate process, only when enabled) ──► same pkexec helper
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
| `src/xampp_panel/configedit.py` | Pure, reversible text edits for XAMPP/system config files; lean-mode values; vhost and hosts rendering |
| `src/xampp_panel/sites.py` | `Site(name, path, uid)`, name validation, `sites.json` load/save, `UNSAFE_PATH_CHARS` |
| `src/xampp_panel/helper.py` | **Root helper**: validation + whitelisted commands |
| `src/xampp_panel/privileged.py` | Builds the `pkexec` command, turns exit codes into errors |
| `src/xampp_panel/settings.py` | Per-user settings (`~/.config/xampp-panel/settings.json`, mode 0600) |
| `src/xampp_panel/watch.py` | inotify watcher + pausable fallback timer (shared by panel and tray) |
| `src/xampp_panel/window.py` | Main window: Services and Sites pages, log viewer, Add-site dialog |
| `src/xampp_panel/app.py` | `Adw.Application`: single instance, menu actions (tray, lean, quit) |
| `src/xampp_panel/tray.py` | Tray process |
| `src/xampp_panel/main.py` | Entry point: `--tray` → tray, otherwise panel |
| `bin/xampp-panel`, `bin/xampp-helper` | Installed launchers (`#!/usr/bin/python3 -I`) |
| `data/` | `.desktop` file, polkit policy, SVG icons |
| `tests/` | stdlib `unittest` suite |
| `tools/fix-pma.sh`, `tools/fix-pma.php` | One-off repair for the phpMyAdmin `pma` control user (§11). Not installed by `setup.sh` |
| `tools/secure-mysql.sh` | Sets the MariaDB root password on all root accounts, drops all anonymous accounts and, if phpMyAdmin logs in automatically (`auth_type = 'config'`), switches it to its login page; without `lampp security` (§11). Not installed by `setup.sh` |

---

## 4. What gets installed where

### Files created by `setup.sh`

| Path | Owner / mode | Purpose |
|---|---|---|
| `/opt/xampp-panel/lib/xampp_panel/` | root, 0755/0644 | Python code (plus compiled `.pyc`) |
| `/opt/xampp-panel/bin/xampp-panel` | root, 0755 | Panel launcher |
| `/opt/xampp-panel/bin/xampp-helper` | root, 0755 | Root helper launcher |
| `/opt/xampp-panel/state/sites.json` | root, 0644 | List of sites (world-readable so the panel can list them) |
| `/opt/xampp-panel/install-manifest.txt` | root | Files outside `/opt/xampp-panel` that uninstall must delete |
| `/usr/share/polkit-1/actions/io.github.shiron.xampppanel.policy` | root, 0644 | Password-prompt policy |
| `/usr/share/applications/io.github.shiron.XamppPanel.desktop` | root, 0644 | App-menu entry |
| `/usr/share/icons/hicolor/scalable/apps/io.github.shiron.XamppPanel.svg` | root, 0644 | App icon |
| `/usr/share/icons/hicolor/scalable/status/xampp-panel-{running,stopped}.svg` | root, 0644 | Tray icons |
| `/usr/local/bin/xampp-panel` | symlink | So `xampp-panel` works in a terminal |
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
| same | Active `skip-networking` commented out (restored by `harden off`) | `# xampp-panel: was "skip-networking"` |
| same | `!include` for lean mode (only if on) | `# BEGIN xampp-panel lean` |
| `/opt/lampp/etc/proftpd.conf` | `DefaultAddress 127.0.0.1` + `SocketBindTight on` | `# BEGIN xampp-panel localhost` |
| `/etc/hosts` | `127.0.0.1  <name>.local` for each site | `# BEGIN xampp-panel sites` |

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
| A broken config taking Apache down | `apachectl -t` runs before every site change; on failure the previous vhost file is restored |

**Accepted limitation:** every site's PHP runs as `daemon` and can read anything `daemon` can read,
including your other sites. That's normal for XAMPP and fine on a single-user computer.

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
| (after `64dcc65`) | `tools/fix-pma.sh` (pma control user) and `tools/secure-mysql.sh` (root password, anonymous accounts); banner points to `secure-mysql.sh` |

Decisions made during the build (and what they cost if wrong):

- **Failed Apache reload after a site change:**
  - What happens: it's a *warning*, not an error.
  - Why: the config already passed `apachectl -t`, so the saved state is consistent.
  - Cost if wrong: you may need to restart Apache by hand.
- **XAMPP start/stop output:** it goes to a temp file, not a pipe, so the Apache and MySQL daemons can't keep the panel waiting forever.
- **Wrong-typed settings values:** they're ignored and the default is used.
- **Uninstall:** it continues past a failed revert step, but then **keeps** the `.bak` files and lists them.
- **"Start" button:** it starts Apache + MySQL only. FTP must be switched on explicitly.
- **`skip-networking` vs `bind-address`:** "localhost only" uses `bind-address=127.0.0.1` and removes
  `skip-networking`. Both keep MySQL off the network, but `skip-networking` also breaks `127.0.0.1`
  clients and the panel's port-based status check.
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
| MariaDB warns `Incorrect definition of table mysql.event` / `mysql.column_stats` / `Please run mysql_upgrade` | Old system tables from an earlier install: `sudo /opt/lampp/bin/mysql_upgrade -u root` (add `-p` if a password is set) |
| XAMPP's `lampp security` breaks things: its "turn off MySQL network access" adds `skip-networking`, and its FTP password step writes PHP source into `proftpd.conf` | Answer **no** to both questions. Fixes for both are in §11 |
| `Access denied for user 'pma'@'localhost'` in the MySQL log or phpMyAdmin | Caused by `lampp security`. Run `bash tools/fix-pma.sh` (§11) |
| XAMPP ships an anonymous MariaDB account and no root password | Run `bash tools/secure-mysql.sh` (§11) |
| Starting `xampp-panel` from SSH/remote terminal fails with "Gtk couldn't be initialized" | Normal: there's no display. Open it from the app menu. Errors are then in `journalctl --user` |
| `shellcheck` was never run on the scripts | `shellcheck setup.sh uninstall.sh` |

---

## 11. Troubleshooting

Always start by reading the actual error. The panel's own errors appear at the bottom of its window.
Anything else goes to the user journal:

```bash
journalctl --user --since "10 min ago" | grep -iA25 xampp
```

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Switch flips back, no message | Password dialog closed (exit 126) | Try again and enter your password |
| "Not authorized, or the XAMPP Panel helper is missing" | Wrong password, or `/opt/xampp-panel/bin/xampp-helper` missing / not executable | `ls -l /opt/xampp-panel/bin/`; re-run `sudo ./setup.sh` |
| "port used by another program" | Another server (Ubuntu's `apache2`, `nginx`, `mysql`), **or** a detection problem | `sudo ss -ltnp 'sport = :80'`. If it names `/opt/lampp/...`, it's XAMPP (see §7) |
| phpMyAdmin: `mysqli::real_connect(): (HY000/2002): No such file or directory` | MySQL isn't running (its socket file is missing) | Start MySQL; if it won't start, see the MySQL log |
| phpMyAdmin: `Access denied for user 'pma'@'localhost'` / "Connection for controluser … failed" | `lampp security` set `controlpass` in `config.inc.php` but not on the MySQL `pma` account | `bash tools/fix-pma.sh` from the repo (asks for sudo and the MySQL root password; prints `OK` or `FAILED`). It creates the `phpmyadmin` storage tables if missing, creates/updates `pma` with the config's password (read by PHP, never on a command line) and grants it `SELECT, INSERT, UPDATE, DELETE` on that database only. Safe to re-run |
| phpMyAdmin: `#1044 - Access denied for user ''@'localhost' to database …` | Logged in as MariaDB's anonymous account: a user name other than `root` with no password matches `''@'localhost'` (needs root without a password, the anonymous account, and `AllowNoPassword`) | Right now: log out of phpMyAdmin and log in as `root`. For good: `bash tools/secure-mysql.sh`. Prompts in order: sudo password, new root password twice (8–128 characters), current root password (Enter if none), new root password once more to list the remaining accounts. MariaDB itself lists the accounts (`EXECUTE IMMEDIATE` over `mysql.user`), so every `''@<host>` is dropped and every `root@<host>` gets the password, all in one session. If phpMyAdmin's `auth_type` is `config` (auto-login as root), it is switched to `cookie` **after** the password change succeeded, with a one-time backup `config.inc.php.xampp-panel.bak`. If a statement fails, `mysql` stops there: at worst the anonymous accounts are gone and root is unchanged. Then log in to phpMyAdmin as `root` with the new password |
| MySQL won't start | See its log | `sudo tail -n 40 /opt/lampp/var/mysql/$(hostname).err` |
| MySQL stuck on "starting…"; log says `port: 0` | `skip-networking` active in `my.cnf` (added by `lampp security`) | `sudo grep -n networking /opt/lampp/etc/my.cnf`; then `sudo /opt/xampp-panel/bin/xampp-helper harden on` and `sudo /opt/lampp/lampp stopmysql && sudo /opt/lampp/lampp startmysql` |
| FTP won't start: `unknown configuration directive 'function'` | `lampp security` wrote PHP source into `proftpd.conf` | `HASH=$(openssl passwd -6) && sudo sed -i '/^UserPassword daemon <?/,/^?>/c\UserPassword daemon '"$HASH" /opt/lampp/etc/proftpd.conf`, then `sudo /opt/lampp/sbin/proftpd -t -c /opt/lampp/etc/proftpd.conf` |
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
PYTHONPATH=src python3 -m unittest discover -s tests -v   # 88 tests; GUI import test needs PyGObject; fix-pma tests need a PHP CLI (php on PATH or XAMPP_TEST_PHP=/opt/lampp/bin/php)
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
