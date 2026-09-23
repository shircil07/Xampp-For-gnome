# XAMPP Panel for Zorin OS — Design

Date: 2026-09-23
Status: Approved (spec reviewed 2026-09-23)

## Goal

Make XAMPP 8.2.12 (`xampp-linux-x64-8.2.12-0-installer.run`) pleasant to use on
Zorin OS (GNOME, Wayland, x86_64): one-command install, a native-looking control
panel, an optional tray icon, graphical password prompts instead of `sudo` in a
terminal, and easy per-project sites in the user's home directory.

XAMPP's binaries are **not modified**. Only its config files are touched: the
managed-vhost `Include`, the localhost binding and optional lean-mode includes.
Every change is backed up first and reverted by `uninstall.sh`.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Current pain | XAMPP works but is clunky (terminal, sudo, no menu entry, dated UI) |
| UI | Native control panel window **and** optional tray icon |
| Privileges | Graphical password prompt via polkit (`pkexec`), cached per polkit's auth timeout |
| Boot autostart | Not included |
| Install scope | Full setup script, including silent XAMPP install and port-conflict checks, plus per-project `.local` sites |
| Stack | Python 3 + GTK4 + libadwaita (PyGObject); AppIndicator for tray |

## Components

### 1. `setup.sh` (run once with `sudo ./setup.sh`)

Steps, each idempotent and logged to stdout:

1. **Preflight:** must be root; must be x86_64; detects apt. Aborts with a clear
   message otherwise.
   Options: `--allow-lan` (skip localhost binding), `--lean` / `--no-lean`
   (skip the lean-mode prompt).
2. **Dependencies (apt):** `libcrypt1`, `net-tools`, `python3-gi`,
   `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-ayatanaappindicator3-0.1`, `acl`,
   `policykit-1` (or `pkexec` on newer releases — install whichever exists).
3. **XAMPP:** if `/opt/lampp/lampp` exists, skip. Otherwise locate
   `xampp-linux-x64-*-installer.run` (argument, or same dir, or `~/Downloads`)
   and run it with `--mode unattended`. Verify `/opt/lampp/lampp` afterwards.
4. **Port check:** for 80, 443, 3306, 21 report the owning process (`ss -ltnp`).
   If it is a system `apache2`/`mysql`/`mariadb` service, offer (y/N) to
   `systemctl disable --now` it. Never kills anything without confirmation.
5. **Install panel:** copy app to `/opt/xampp-panel/`, helper to
   `/opt/xampp-panel/libexec/xampp-helper` (root-owned, 0755), polkit policy to
   `/usr/share/polkit-1/actions/org.zorin.xampppanel.policy`, `.desktop` file to
   `/usr/share/applications/`, icons to `/usr/share/icons/hicolor/`, launcher
   `/usr/local/bin/xampp-panel`.
6. **Vhost include:** create `/opt/lampp/etc/extra/xampp-panel-vhosts.conf`
   (empty) and append `Include etc/extra/xampp-panel-vhosts.conf` to
   `/opt/lampp/etc/httpd.conf` if not present (backup first as
   `httpd.conf.xampp-panel.bak`).
7. **Hardening & lean mode:** apply the localhost binding, then offer the
   `lampp security` password step and lean mode (see Security and Resource
   efficiency).
8. **Manifest:** write every created file/modified line to
   `/opt/xampp-panel/install-manifest.txt` for the uninstaller.

### 2. `uninstall.sh`

Reverses the manifest: removes panel files, policy, desktop entry, icons,
launcher, the `Include` line, managed vhost file and managed `/etc/hosts`
entries. Leaves `/opt/lampp` untouched unless `--remove-xampp` is passed
(then runs `/opt/lampp/uninstall --mode unattended`). Leaves `~/Sites` alone.

### 3. `xampp-helper` (root, invoked via `pkexec`)

A small Python script accepting a **fixed whitelist** of subcommands; any other
input exits non-zero. No shell interpolation of user input.

| Command | Action |
|---|---|
| `start <svc>` / `stop <svc>` | `svc` ∈ {apache, mysql, ftp, all} → `/opt/lampp/lampp start<svc>` etc. |
| `site-add <name> <dir>` | `name` must match `^[a-z0-9][a-z0-9-]{0,62}$`; `dir` must be an existing absolute path under the invoking user's home (`PKEXEC_UID`). Writes a `<VirtualHost>` block for `<name>.local` into the managed vhost file, adds `127.0.0.1 <name>.local` to `/etc/hosts` inside a `# BEGIN xampp-panel` / `# END xampp-panel` block, then graceful-reloads Apache. |
| `site-remove <name>` | Reverses the above. |
| `lean on\|off` | Adds/removes the lean-mode include lines (see Resource efficiency). |

Status queries **do not** need root: the panel reads PID files in
`/opt/lampp/logs` / `/opt/lampp/var/mysql` and checks ports directly.

Polkit policy: `allow_active = auth_admin_keep` (password once, cached a few
minutes), `allow_inactive/any = no`.

### 4. Control panel app (`/opt/xampp-panel/xampp_panel/`)

Python package, GTK4 + libadwaita, `Adw.Application` id `org.zorin.XamppPanel`.

- **Main window** (`Adw.ApplicationWindow` + `Adw.ViewSwitcher`), two pages:
  - A warning banner (`Adw.Banner`) is shown while MySQL root has no password.
  - **Services:** one `Adw.PreferencesGroup` with a row per service (Apache,
    MySQL, ProFTPD): status dot (green running / grey stopped / amber busy),
    port subtitle, `Gtk.Switch`, "Log" button opening a log viewer dialog
    (tail of `error_log` / `mysql` error log, refresh button). Header buttons:
    Start all / Stop all. Quick-link buttons: Open localhost, Open phpMyAdmin,
    Open htdocs, Open `~/Sites`.
  - **Sites:** list of managed sites (name.local → folder) with open-in-browser,
    open-folder and remove actions; "Add site" dialog with name entry and
    folder chooser (defaults to creating `~/Sites/<name>` with a starter
    `index.php`).
- **Preferences:** "Keep running in tray when window is closed" (off by
  default) and a "Lean mode" toggle, stored in `~/.config/xampp-panel/settings.json`.
- Follows system light/dark automatically (libadwaita default).
- Status updates are event-driven (see Resource efficiency); switches are
  insensitive while a helper call is in flight.
- Errors from the helper (non-zero exit, cancelled auth) show an `Adw.Toast`
  with the stderr summary; cancelled auth reverts the switch silently.

### 5. Tray helper

A separate small process (`xampp_panel.tray`) using AyatanaAppIndicator3
(GTK3 — cannot share a process with GTK4). Started by the panel when the tray
preference is on. Menu: status line, Start all, Stop all, Open panel, Quit.
Communicates with the panel only by launching it / calling the helper; its own
status comes from the same non-root status module. If the indicator library or
the GNOME AppIndicator extension is unavailable, the preference is disabled
with an explanatory subtitle.

## Security

XAMPP's defaults are made for convenience, not safety: it listens on all
network interfaces, MySQL `root` has no password, and phpMyAdmin is open. The
setup and helper harden this:

1. **Localhost only (default, applied by setup):** Apache `Listen 127.0.0.1:80`
   / `127.0.0.1:443`, MySQL `bind-address=127.0.0.1`, ProFTPD bound to
   127.0.0.1. Nothing is reachable from the LAN/Wi-Fi. Original config files
   are backed up (`*.xampp-panel.bak`) and restored by `uninstall.sh`.
   `setup.sh --allow-lan` skips this for users who knowingly want LAN access.
2. **FTP off by default:** "Start all" starts Apache + MySQL only; ProFTPD must
   be switched on explicitly.
3. **MySQL/phpMyAdmin passwords:** setup offers (y/N) to run XAMPP's own
   `/opt/lampp/lampp security` to set the MySQL root and phpMyAdmin passwords.
   The panel shows a warning banner while MySQL root still has no password
   (checked via `mysql -uroot --connect-timeout=1 -e ''` returning success).
4. **Helper hardening:**
   - Installed root-owned 0755 in a root-owned directory; polkit policy pins
     it with `org.freedesktop.policykit.exec.path`.
   - Whitelisted subcommands only; `argv` only, never `shell=True`; fixed
     `PATH`; ignores the caller's environment.
   - Site names validated by regex; site dirs resolved with `realpath` and
     required to be inside the invoking user's home (uid from `PKEXEC_UID`),
     owned by that user, and not a symlink escape.
   - Writes to `/etc/hosts` and the vhost file are atomic (temp file in the
     same dir + `os.replace`), touch only the managed `# BEGIN/END
     xampp-panel` block, and keep a one-time backup.
   - Runs `apachectl -t` config test before reload; on failure restores the
     previous vhost file and reports the error.
5. **Site vhosts:** `Require local`, `Options -Indexes +FollowSymLinks`,
   `AllowOverride All`. Apache runs as XAMPP's `daemon` user, so the helper
   grants the minimum read access with ACLs (package `acl`): `u:daemon:--x`
   on `$HOME` and `~/Sites`, `u:daemon:r-X` (plus default ACL) on the site
   folder only. The rest of the home directory stays unreadable. `site-remove`
   revokes these ACLs.
6. **Polkit:** `auth_admin_keep` for active local sessions only; remote/inactive
   sessions denied.
7. The unprivileged GUI never runs as root, and nothing is added to sudoers.

## Resource efficiency

**Panel and tray (target: ~0 % CPU when idle, < 60 MB RSS panel, < 30 MB tray):**

- **Event-driven status:** `Gio.FileMonitor` (inotify) on the XAMPP PID files
  (`/opt/lampp/logs/httpd.pid`, the MySQL `.pid`, `proftpd.pid`) instead of
  tight polling. A 10 s fallback check (PID alive via `os.kill(pid, 0)`, no
  subprocesses) catches crashed services that left a stale PID file.
- The fallback timer runs **only while the window is visible**; it pauses when
  the window is hidden or minimized. The tray uses file monitors plus a 30 s
  fallback.
- Status checks read files and `/proc` directly: no `ps`, `netstat` or `ss`
  subprocesses. Port-owner lookups happen only on demand (when a start fails).
- Closing the window **exits the process** unless tray mode is on. The tray is
  a separate small process only when enabled. There are no background daemons,
  and nothing runs at login.
- The log viewer reads only the last 64 KB of a log file, and only while it is
  open.
- Slow imports (e.g. the folder chooser) are loaded lazily.

**XAMPP itself (optional "Lean mode", offered by setup, reversible):**

- Apache prefork: `StartServers 2`, `MinSpareServers 1`, `MaxSpareServers 3`,
  `MaxRequestWorkers 20`. That's plenty for local development and far fewer
  idle processes than the defaults.
- MySQL: `innodb_buffer_pool_size=64M`, `performance_schema=OFF`,
  `max_connections=30`. This cuts idle RAM by roughly 150–300 MB.
- These settings go into separate drop-in files (`xampp-panel-lean.conf`) that
  are included, so turning lean mode off just removes the include. The
  Preferences page has a toggle that calls the helper (`lean on|off`, added to
  the whitelist).
- Nothing starts at boot, so XAMPP only uses resources while you use it.

## Module layout

```
xampp-panel/
  setup.sh
  uninstall.sh
  data/
    org.zorin.XamppPanel.desktop
    org.zorin.xampppanel.policy
    icons/ (scalable svg: app, tray-running, tray-stopped)
  src/xampp_panel/
    __init__.py
    main.py          # Adw.Application entry
    window.py        # main window, pages
    services.py      # status detection (pure, no GTK) + service metadata
    privileged.py    # wrapper that runs pkexec helper, returns result
    sites.py         # read managed sites list (pure)
    settings.py      # JSON settings
    tray.py          # AppIndicator process
  libexec/xampp-helper   # root helper (Python, stdlib only)
  tests/               # pytest for services.py, sites.py, helper validation
```

## Testing

- **Unit (pytest, no root, no GTK):** status detection against fake PID/port
  fixtures; helper argument validation (whitelist, name regex, path-under-home
  checks, rejection of `..`, symlinks out of home, ownership); atomic write
  helpers; localhost-binding and lean-mode config rewriting on fixture copies of
  XAMPP's `httpd.conf`/`my.cnf`; vhost/hosts block
  rendering and idempotent add/remove on temp files.
- **Script checks:** `shellcheck` on `setup.sh` / `uninstall.sh`; `bash -n`.
- **Manual on the real machine:** run `setup.sh`, confirm
  `ss -ltn` shows only 127.0.0.1 listeners, check idle panel CPU/RAM with
  `top`, check the MySQL RSS difference with lean mode on and off, launch from app menu,
  toggle each service, add/remove a site and load it in the browser, enable
  tray, run `uninstall.sh` and confirm the manifest is fully reversed.

Note: development happens inside a snap sandbox that cannot see `/opt` or run
root commands, so installation and service control can only be verified by
the user running the scripts on the host.

## Out of scope

Boot autostart, non-apt distros, non-GNOME desktops, editing php.ini/my.cnf
from the UI, HTTPS certificates for `.local` sites, modifying XAMPP binaries.

## Plan-time refinements (2026-09-23)

Found while planning. Where these conflict with earlier sections, this section wins.

1. **App ID** is `io.github.shiron.XamppPanel` (polkit action
   `io.github.shiron.xampppanel.helper`), not `org.zorin.*`, so we don't use
   Zorin's namespace.
2. **Status detection** reads `/proc/<pid>/comm` + `cmdline` (XAMPP processes
   have `/opt/lampp` in their command line) and `/proc/net/tcp{,6}` for
   listening ports. This avoids unreadable PID files owned by `mysql`/`root`.
   PID files are only used as inotify *triggers*. The states are Running,
   Starting (process up, port not yet listening), Stopped, and Conflict (port
   taken by a non-XAMPP program).
3. **Minimum platform:** Zorin OS 17 / Ubuntu 22.04 (GTK 4.6, libadwaita 1.1,
   Python 3.10). Newer widgets (`Adw.Banner`, `Gtk.FileDialog`) are used only
   when present, with fallbacks. `setup.sh` refuses older releases.
4. **Config changes are reversed by inverse edits**, not by restoring
   `.bak` files, so lean mode, hardening and vhosts can be toggled
   independently. `.bak` copies are kept as a safety net and deleted by
   `uninstall.sh`.
5. **ACLs are applied as the site owner** (the helper drops to the user's uid
   to run `setfacl`), so a folder swapped for a symlink can never make root
   grant access to system files. Nested/overlapping site folders are rejected.
6. **Default vhost:** the managed vhost file starts with a `localhost`
   vhost for `/opt/lampp/htdocs`, so `http://localhost` and phpMyAdmin keep
   working once name-based vhosts exist.
7. The FTP row has **no log button**, because the ProFTPD log location in
   XAMPP 8.2 is unconfirmed. The MySQL log falls back to `pkexec … log mysql`
   when the file isn't readable.
8. Tests use stdlib `unittest` (pytest isn't installed), so no pip dependencies
   are needed.
