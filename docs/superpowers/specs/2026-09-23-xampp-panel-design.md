# XAMPP Panel for Zorin OS — Design

Date: 2026-09-23
Status: Approved in brainstorming, pending spec review

## Goal

Make XAMPP 8.2.12 (`xampp-linux-x64-8.2.12-0-installer.run`) pleasant to use on
Zorin OS (GNOME, Wayland, x86_64): one-command install, a native-looking control
panel, an optional tray icon, graphical password prompts instead of `sudo` in a
terminal, and easy per-project sites in the user's home directory.

XAMPP itself is a prebuilt binary distribution and is **not modified**, except
for adding one `Include` line to its Apache config for managed vhosts.

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
2. **Dependencies (apt):** `libcrypt1`, `net-tools`, `python3-gi`,
   `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-ayatanaappindicator3-0.1`,
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
7. **Manifest:** write every created file/modified line to
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

Status queries **do not** need root: the panel reads PID files in
`/opt/lampp/logs` / `/opt/lampp/var/mysql` and checks ports directly.

Polkit policy: `allow_active = auth_admin_keep` (password once, cached a few
minutes), `allow_inactive/any = no`.

### 4. Control panel app (`/opt/xampp-panel/xampp_panel/`)

Python package, GTK4 + libadwaita, `Adw.Application` id `org.zorin.XamppPanel`.

- **Main window** (`Adw.ApplicationWindow` + `Adw.ViewSwitcher`), two pages:
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
  default), stored in `~/.config/xampp-panel/settings.json`.
- Follows system light/dark automatically (libadwaita default).
- Status is polled every 2 s off the main loop; switches are insensitive while
  a helper call is in flight.
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
  checks, rejection of `..`, symlinks out of home); vhost/hosts block
  rendering and idempotent add/remove on temp files.
- **Script checks:** `shellcheck` on `setup.sh` / `uninstall.sh`; `bash -n`.
- **Manual on the real machine:** run `setup.sh`, launch from app menu,
  toggle each service, add/remove a site and load it in the browser, enable
  tray, run `uninstall.sh` and confirm the manifest is fully reversed.

Note: development happens inside a snap sandbox that cannot see `/opt` or run
root commands, so installation and service control can only be verified by
the user running the scripts on the host.

## Out of scope

Boot autostart, non-apt distros, non-GNOME desktops, editing php.ini/my.cnf
from the UI, HTTPS certificates for `.local` sites, modifying XAMPP binaries.
