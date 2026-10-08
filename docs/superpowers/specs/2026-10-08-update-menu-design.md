# Update menu (`xampp-update`) and startup update check — design

Date: 2026-10-08. Status: design approved in the brainstorm; spec awaiting review.

## Problem

Upgrading the parts of XAMPP is manual, undocumented beyond MAINTAINER §12, and risky:

- phpMyAdmin is a folder swap that must keep `config.inc.php` (owner `daemon`, holds the generated
  `controlpass`). The installed 5.2.1 is behind upstream 5.2.3.
- XAMPP bundles MariaDB 10.4.32, which is out of support. Replacing it by hand means editing
  `my.cnf`, `plugin_dir`, library paths and running the upgrade tool, with no way back for the data.
- PHP and Apache cannot be updated alone. The only route is a newer XAMPP installer, which replaces
  `/opt/lampp` (databases, `htdocs`, panel edits).
- Nothing tells the user a newer version exists.

## Goals

1. A **Update components…** terminal menu (`sudo xampp-update`, also opened from the panel's ☰ menu)
   that updates **phpMyAdmin**, **MySQL (MariaDB)** and **PHP + Apache (XAMPP)**.
2. For each component the menu lists the **installed version and the 5 newest**, newest first. The
   user can pick any of them, **older ones too** (going back is allowed everywhere).
3. When the panel opens it checks in the background whether newer versions exist and shows a bar
   with **Update…** / **Later**. It never blocks Start.
4. Every change is snapshotted, verified, and rolled back automatically on failure.
5. A **Restore previous version** button in the panel, so that if the user's own code does not work
   under an updated component they can go back quickly (see "Restore button").

Non-goals: switching PHP independently of XAMPP; updating the panel itself; installing anything
without the user choosing it; tray notifications or scheduled installs; ProFTPD, Perl or other
bundled parts; non-x86_64; a GTK update window; replication (Galera) setups.

## Decisions from the brainstorm

| Question | Decision |
|---|---|
| Components | All three: phpMyAdmin, MariaDB, XAMPP (PHP + Apache). |
| Where | New `xampp-update` tool run with `sudo` in a terminal, like `xampp-repair`. The pkexec helper's whitelist does **not** grow. |
| Startup check | Background check when the panel opens; bar with Update… / Later; cached about a day; never blocks Start. |
| "Later" | Hides the bar until a version newer than the dismissed one appears. Updates are never forced. |
| MariaDB list | Installed + the 5 newest **stable** releases from **long-term-support series that are not past end-of-life** (by release date; previews, RCs and rolling releases excluded). |
| XAMPP trust | Auto-download, check every hash obtainable (MD5; SHA-1 where published), show them, and run only after the user types `yes`. Runs from a private root-only copy. |
| Going back | Allowed for all. MariaDB across series goes through export and reload (§MariaDB). |

## Facts this design rests on

Read on the target machine (probe, 2026-10-08) and from the live upstream APIs the same day.

| Fact | Value / source |
|---|---|
| XAMPP version | `/opt/lampp/properties.ini`, `base_stack_version=8.2.12-0` |
| phpMyAdmin version | first lines of `/opt/lampp/phpmyadmin/README`: `Version 5.2.1` (also `RELEASE-DATE-5.2.1`) |
| PHP / MariaDB version | `bin/php -v` → 8.2.12; `bin/mysql --version` → `Distrib 10.4.32-MariaDB` |
| How MySQL starts | `lampp startmysql` → `bin/mysql.server start` (symlink to `share/mysql/mysql.server`) → `mysqld_safe` → `sbin/mysqld` (`sbin/mariadbd` is a symlink to it) |
| Data | `/opt/lampp/var/mysql`, `mysql:mysql` 0775, 97 MB. Disk has 805 GB free. |
| `my.cnf` | `plugin_dir=/opt/lampp/lib/mysql/plugin/`, `bind-address=127.0.0.1`, socket `/opt/lampp/var/mysql/mysql.sock`, `character-set-server=utf8mb4` |
| Libraries | `mysqld` uses XAMPP's own `libssl.so.1.1`, `libstdc++`, `libpcre`, `libz`, `libbz2` from `/opt/lampp/lib`, and system libc/libcrypt |
| phpMyAdmin config | `config.inc.php` is `daemon:daemon` 0644; a `config.inc.php.xampp-panel.bak` sits next to it |
| Newest XAMPP for Linux | 8.2.12 (Apache Friends lists 8.0.30, 8.1.25, 8.2.12). Older builds exist on SourceForge. |
| MariaDB series today | Stable LTS: 12.3, 11.8, 11.4, 10.11, 10.6 (10.6 reached EOL 2026-07-06, so excluded) |
| Tools present for root | `tar`, `xz`, `gpg`, `sha256sum`, `flock`. The tool uses Python's `tarfile`/`lzma`/`hashlib`, not these, except `gpg` for signatures. |

Upstream sources (all fetched over HTTPS):

| Component | List | Download and integrity |
|---|---|---|
| phpMyAdmin | `https://www.phpmyadmin.net/files/` (release folders `/files/<ver>/`); `https://www.phpmyadmin.net/home_page/version.json` gives the PHP range per branch | `https://files.phpmyadmin.net/phpMyAdmin/<ver>/phpMyAdmin-<ver>-all-languages.tar.xz` plus `.sha256` and `.asc` |
| MariaDB | `https://downloads.mariadb.org/rest-api/mariadb/` (series, `release_status`, `release_support_type`, `release_eol_date`); `/rest-api/mariadb/<series>/` (release dates); `/rest-api/mariadb/all-releases/?olderReleases=true` (per-release `status`: `preview`, `rc`, `stable`) | `/rest-api/mariadb/<ver>/`: file `mariadb-<ver>-linux-systemd-x86_64.tar.gz` with its `sha256sum` and download URL |
| XAMPP | `https://sourceforge.net/projects/xampp/rss?path=/XAMPP%20Linux&limit=50` (needs a browser-like `User-Agent`; carries MD5). Apache Friends' download page shows MD5 and SHA-1 for the releases it lists (MAINTAINER §12). | `…/XAMPP Linux/<ver>/xampp-linux-x64-<ver>-0-installer.run` |

Items **confirmed on the target machine before the code that depends on them** (a read-only probe,
the first implementation task), each with a defined outcome whatever the answer:

| Item | If it turns out unfavourable |
|---|---|
| Which library path `lampp` gives `mysqld` (`LD_LIBRARY_PATH`) | The rehearsal and the live start use the same value (config). A new `mariadbd` that cannot start under it fails the rehearsal, nothing live is touched. |
| How `lampp`'s `testrun` recognises a running MySQL, and whether a `mysqld` name is required | The slot gets a `mysqld` symlink and `my.cnf` gets `[mysqld_safe] mysqld=mysqld`. If `lampp` still misjudges, the live verify (start, stop, restart) fails and the update rolls back. |
| Whether `mysql.server` honours `basedir` from `[mysqld]` | The live verify checks `SELECT VERSION()` equals the target; the old binaries starting means rollback. The MariaDB component then reports "cannot be updated on this install" with the reason. |
| Apache Friends' page format for SHA-1 | If SHA-1 cannot be read for a release, the confirmation screen says **MD5 only** (weaker). |
| Full phpMyAdmin folder listing (is there a `tmp/`?) | The keep-list in config (`config.inc.php`, its `.bak`, `tmp`) covers it; anything else stays in the snapshot folder and the summary names that folder. |

## Architecture

```
 panel opens ──► xampp-update --check (your user, background) ──► ~/.cache/xampp-panel/updates.json
     │                                                                   │
     └── bar: "Updates available: …   [Update…] [Later]" ◄───────────────┘
              │ Update…                              (Later → settings.json "dismissed_updates")
              ▼
 terminal: sudo /opt/xampp-panel/bin/xampp-update ──► updates/app.py (UpdateApp, root)
                                                           │
        ┌──────────────┬────────────┬──────────────┬───────┴──────┬────────────┐
   updates/config   versions     releases       fetcher        archive     snapshots
   (UpdateConfig)   (parse,pick) (3 sources)   (download+hash) (safe unpack) (manifest,retention)
                                                           │
                              updates/pma.py   updates/mariadb.py   updates/xampp.py   (Component implementations)
                                                           │
   reused: Dialogs, MysqlAdmin, Helper (integrate/harden/lean), configedit, fsutil, services, HealthCheck, Paths
```

A subpackage `xampp_panel/updates/` keeps the ten or so new modules apart from the flat existing ones.
Everything except the panel bar stays free of GTK and is unit-tested.

### Modules

| Module | Responsibility |
|---|---|
| `updates/config.py` | `UpdateConfig` (frozen dataclass): every URL, `count=5`, timeouts, response and download size caps, check throttle (24 h), cache max age (7 d), `user_agent`, free-space factors, pma keep-list, pma signing fingerprints, lampp library path. Injectable, like `Paths`. |
| `updates/versions.py` | `parse()` (strict `^\d{1,3}(\.\d{1,3}){1,3}$`, else rejected; so `-rc`/`-beta` phpMyAdmin tags never reach a list), compare, `pick(releases, installed, count)` → installed (marked) + the `count` newest, tagging each entry. |
| `updates/releases.py` | `Transport` (injected: capped, timed, HTTPS-only GET) and the three sources parsing list pages into `Release` objects. Strict validation; unknown shapes are errors, never guesses. |
| `updates/fetcher.py` | Resumable HTTPS download into a root-only folder (`.part`, stall timeout, size cap, `O_EXCL|O_NOFOLLOW`) and hash verification (SHA-256, or every available MD5/SHA-1). |
| `updates/fsops.py` | `copy_owned`: copy a tree with owner, group, mode and times, safe over folders others can write (descriptor-relative, no links followed, private until the real mode is applied last). |
| `updates/panelstate.py` | What the panel's two bars say and the "Later"/"Hide" settings updates; pure, so it is tested without GTK. |
| `updates/archive.py` | Safe unpack of `.tar.xz`/`.tar.gz`: rejects absolute paths, `..`, devices, links leaving the tree, and over-limit entry count or unpacked size. Normalises owner and mode. |
| `updates/http.py` | HTTPS-only URL check, an opener whose redirects must stay HTTPS, request headers; shared by `releases` and `fetcher`. |
| `updates/gpg.py` | Verifies a detached signature with a throwaway `gpg` home folder; accepts it only when `VALIDSIG` names a pinned primary-key fingerprint. |
| `updates/snapshots.py` | One snapshot per component, in `/var/backups/xampp-panel`: path allocation, `manifest.json`, retention (the previous one is deleted after a successful update), lookup for restore; keeps the public index in step. |
| `updates/restore_points.py` | The public `restore-points.json`: tolerant read (used by the panel, no root) and atomic write (root). |
| `updates/base.py` | `Release`, `Plan`, `UpdateContext`, `UpdateError`, the `Component` protocol. |
| `updates/pma.py`, `mariadb.py`, `xampp.py` | The three components. |
| `updates/check.py` | `UpdateCheck`: installed vs newest per component, throttle, cache read/write, dismissed filter. |
| `updates/app.py`, `bin/xampp-update` | `UpdateApp` menu and `main()` (refuses non-root unless `--check`); launcher `python3 -I`. |

Existing code touched, each for a stated reason:

- `repair.py`: the root-password lookup/prompt (`_root`) moves into a small shared class so both tools
  use one implementation; behaviour unchanged.
- `configedit.py`: new pure, reversible functions for the MariaDB `basedir`/`plugin_dir` block.
- `paths.py`: new locations (update launcher, `backups`, `mariadb` slots) and the **active MariaDB
  folder**, read from the `my.cnf` block, so `mysql_client` and `mysql_upgrade` follow the active slot.
- `terminal.py`: `repair_command` generalised to a launcher-path function; `repair_command` stays as a wrapper.
- `window.py`: ☰ **Update components…** and the update bar (separate from the yellow MySQL one).
- `settings.py`: validated `dismissed_updates` and `dismissed_restore` maps (string to string).
- `dialogs.py`: an optional `title` argument (default unchanged), so the update menu has its own title.
- `setup.sh`, `uninstall.sh`: install/remove the subpackage, the launcher, the `/usr/local/bin/xampp-update`
  symlink and `gnupg` if missing. Snapshots live in `/var/backups/xampp-panel`, outside `/opt/xampp-panel`,
  so `uninstall.sh` (which removes the app folder) leaves them; it says so and also removes the user's
  update cache file.

### Interface

```python
@dataclass(frozen=True)
class Release:
    version: str                 # validated
    series: str | None           # MariaDB: "12.3"
    date: str | None
    url: str
    hashes: Mapping[str, str]    # {"sha256": …} or {"md5": …, "sha1": …}
    signature_url: str | None
    notes: tuple[str, ...]       # "major upgrade", "downgrade via export/reload", "older PHP branch"

class Component(Protocol):
    key: str; title: str
    def installed(self) -> str | None: ...
    def releases(self) -> list[Release]: ...          # filtered, newest first
    def plan(self, target: Release) -> Plan: ...      # kind, warnings, downtime, what is backed up
    def apply(self, target: Release) -> str: ...      # message for the user; raises UpdateError after rolling back
    def restore_note(self, snapshot) -> str: ...      # what the restore confirmation says
    def restore(self) -> str: ...                     # go back to the saved version; message for the user
```

Ordering: phpMyAdmin and XAMPP by version number (descending), MariaDB by release date (descending,
ties by version), because MariaDB series interleave. The installed version is always shown and marked,
even when it is not in the filtered set (an EOL 10.4.32 is shown as `installed`).

## Menu and flow

```
 1  phpMyAdmin           5.2.1   → 5.2.3 available
 2  MySQL (MariaDB)      10.4.32 → 12.3.3 available
 3  PHP + Apache (XAMPP) 8.2.12    up to date
 4  Restore previous version…
 5  Check for updates now
 q  Quit
```

Choosing a component shows installed + 5 newest with tags `installed`, `newer`, `older`, `major upgrade`,
`downgrade via export/reload`, `older PHP branch`. A summary screen then says what is backed up, what
stops and for roughly how long, and where the snapshot goes; yes/no. Progress prints to the terminal;
the end is a message box. Esc or Cancel at any question changes nothing.

### Shared pipeline

1. **Preflight:** root; the `xampp-repair` lock (`flock`), so only one of the two tools runs; free
   space; tools; network.
2. **Download** over HTTPS to a root-only folder under `/opt/xampp-panel/cache/` (0700), resumable,
   size-capped; **verify the hash before anything is unpacked or run**.
3. **Snapshot** (component-specific; manifest records what was running).
4. **Apply**, with SIGINT/SIGHUP/SIGTERM blocked during the swap steps (as in the password reset).
5. **Verify** (component-specific). **Any** failure after the snapshot triggers an automatic rollback;
   if the rollback itself fails the tool prints the exact manual recovery steps and snapshot paths.
6. **Leave things as they were:** services that were running are running again, stopped ones stay stopped.
7. Delete the previous snapshot of that component and the download cache.

### phpMyAdmin

- **Versions:** the 5 newest releases; both directions. A release whose declared PHP range (from
  `version.json`, when known for that branch) excludes the installed PHP is refused with the reason.
- **Integrity:** SHA-256 from the `.sha256` file must match; the `.asc` is verified with `gpg` against
  the pinned fingerprints in `UpdateConfig`. The keyring (`files.phpmyadmin.net/phpmyadmin.keyring`) is
  only key material: trust comes from the pinned fingerprints, checked against the `VALIDSIG` line.
  Observed 2026-10-08: the keyring holds the release signers Michal Čihař
  `63CB1DF1EF12CF2AC0EE5A329C27B31342B7511D`, Marc Delisle `436FF1884B1A0C3FDCBF0D79FEFC65D181AF644A` and
  Isaac Bennetch `3D06A59ECE730EB71B511C17CE752F178259BD92` (signed 5.2.3), plus the Security Team key
  (not pinned: it does not sign releases). The user confirms these three against phpMyAdmin's own
  published instructions before they are pinned (a checkpoint in the plan). A missing `gpg` or a signature
  that does not verify stops the update; there is no "continue anyway".
- **Apply:** unpack to `/opt/lampp/phpmyadmin.new-<ts>` (top folder stripped; root-owned, dirs 0755,
  files 0644); carry over the keep-list with owner and mode (`config.inc.php` stays `daemon`);
  rename the old folder to `phpmyadmin.before-<oldver>-<ts>` (the snapshot) and the new one to
  `phpmyadmin` (two renames; if the second fails the first is undone).
- **Verify:** `README` version equals the target; `bin/php -l index.php` passes; if Apache is running,
  `http://127.0.0.1/phpmyadmin/` answers 200/302 within 10 s.
- **Roll back:** swap the folders back.

### MySQL (MariaDB)

Installed side-by-side, never over XAMPP's files. Slot folder: `/opt/lampp/mariadb/<ver>/`. `my.cnf`
points at it with a marked, reversible block; the 10.4 files are untouched, so switching back is a
`my.cnf` change.

**Upgrade or older patch in the same series (in place on the data):**

1. Preflight: free space ≥ 3 × data folder + `mariadb_headroom` (config); the tarball's `ldd` check (below).
2. Download, verify SHA-256 (from the API), unpack to `/opt/lampp/mariadb/.staging-<ver>/` on the same
   filesystem. Under the library environment `lampp` uses, `ldd` on `bin/mariadbd` and `bin/mariadb`
   must show no `not found`, and `mariadbd --version` must print the target.
3. Start MySQL if needed; take a **logical dump** (all databases, routines, events) with the current
   client into the snapshot folder (0600, root). Ask for the root password the same way `xampp-repair` does.
4. Stop MySQL (`lampp stopmysql`). **Snapshot the data folder** (full copy, owner kept) and `my.cnf`
   into `/var/backups/xampp-panel/mariadb/`.
5. **Rehearsal on a copy:** copy the snapshot to a scratch folder owned by `mysql`; generate a config from
   the live `my.cnf` with only these overrides: scratch `datadir`, socket and pid in the scratch folder,
   `skip-networking`, the new `basedir` and `plugin_dir`. Start the new `mariadbd` directly under the
   same library environment, run the new `mariadb-upgrade`, check `SELECT VERSION()` and that the
   per-database table counts equal the original. Shut it down and delete the scratch folder. Any problem
   (library mismatch, an option the new version rejects, a failed data upgrade) **stops here with nothing live changed**.
6. **Switch:** rename staging to `/opt/lampp/mariadb/<ver>`; create `mysql*`/`mariadb*` compatibility
   symlinks in the slot where missing (`mysqld`, `mysql`, `mysqldump`, `mysqladmin`, `mysql_upgrade`,
   `mysqld_safe`); write the `my.cnf` block (`basedir`, `plugin_dir`, `[mysqld_safe] mysqld=mysqld`),
   keeping the old values as marked comments.
7. Start with `lampp startmysql`; run the new `mariadb-upgrade` on the live data.
8. **Verify:** `SELECT VERSION()` starts with the target; root and `pma` log in; every database present
   before is present; `lampp stopmysql` and `startmysql` both work. If MySQL was stopped before, stop it again.
9. **Failure at any point after step 4:** stop MySQL, put `my.cnf` back, move the live data folder aside
   as `…/datadir.failed-<ts>`, copy the snapshot back, remove the slot, start the old MySQL if it was
   running. Before step 6 nothing live changed beyond MySQL being stopped, so it is just restarted.

**Older series (e.g. 12.3 → 11.8): export and reload,** because MariaDB cannot open data written by a newer series:

1. Same preflight and download as above.
2. Dump every non-system database (including `phpmyadmin`) with routines, triggers and events, and
   record the non-system accounts with `SHOW CREATE USER` and `SHOW GRANTS`.
3. Stop MySQL; **rename** the live data folder into the snapshot (instant, same filesystem); create an
   empty `/opt/lampp/var/mysql` (`mysql:mysql` 0775).
4. Switch `my.cnf` to the older slot; run its `mariadb-install-db`; start MySQL.
5. Import the dump; replay the accounts (any that fail are listed, not fatal); then run the existing
   repair flows for the root password, anonymous-account removal and the `pma` account.
6. Verify as above, plus the database list equals the dumped list.
7. On failure: stop, restore `my.cnf`, delete the new data folder, rename the snapshot back, start the old server.

The confirmation screen for this path says: slower on large databases; root and `pma` are re-created
from the existing flows and other accounts are replayed; your old data folder is kept untouched.

### PHP + Apache (XAMPP)

Offered: installed + the 5 newest by version number, both directions (an older entry is a different
PHP branch, tagged `older PHP branch`; the confirmation warns that your own sites may use newer PHP
features). Today nothing newer than 8.2.12 exists, so the menu says "up to date".

1. Download the installer; check every hash obtainable; show the version, the PHP-branch change, the
   hashes (and **MD5 only** if SHA-1 could not be read). The user must type `yes`.
2. Copy to a private root-only folder under `/root` (as `setup.sh` does) and check again **on that copy**.
3. `lampp stop`; record what was running.
4. **Snapshot by rename:** `/opt/lampp` → `/opt/lampp.before-<ver>-<ts>` (instant, same filesystem). The
   installer then creates a fresh `/opt/lampp`, so no old file can linger.
5. Run the installer unattended (`--mode unattended --unattendedmodeui none`, XAMPP's default prefix).
   `/opt/lampp/lampp` must exist afterwards.
6. **Carry over by copy, never by move,** so the snapshot stays complete: `var/mysql` (data, owner
   kept), `htdocs`, the `mariadb/` slots, and `phpmyadmin/config.inc.php` (owner and mode kept). If the old
   phpMyAdmin is newer than the one the installer shipped, the old phpMyAdmin folder is kept instead.
   Not carried: `etc/php.ini` (extension paths change with PHP; saved beside the new one as
   `php.ini.previous`) and other hand edits under `etc/` (they stay in the snapshot; the summary lists the
   path). The FTP password returns to XAMPP's default.
7. **Re-apply the panel's config:** the existing `integrate on`, `harden on`, `lean on` (if lean was on),
   and the MariaDB block if a slot was active. Run `mysql_upgrade` if the bundled MariaDB version changed.
8. **Verify:** `properties.ini` shows the target; `apachectl -t` passes; Apache and MySQL start if they
   were running; `MysqlAdmin.ping`/`can_login` pass; the health check report is shown.
9. **Failure:** stop, rename the new tree to `/opt/lampp.failed-<ts>`, rename the snapshot back to
   `/opt/lampp`, start what was running.

The summary recommends a phpMyAdmin Export of important databases first and states the disk the
snapshot keeps (about the size of `/opt/lampp`).

### Restore previous version (the restore button)

Added at the user's request: if their own code does not work under an updated component, going back
must be quick and not require knowing the menu.

- **Restore points.** Each successful update leaves one restore point per component (the snapshot).
  Restoring uses the same steps as the automatic failure rollback, after a confirmation that says plainly:
  **database changes made since the update are lost** (MariaDB, XAMPP; phpMyAdmin has no such loss).
  Restoring consumes the restore point.
- **Public index.** The root tool keeps `/opt/xampp-panel/state/restore-points.json` (0644, atomic, no
  secrets: component, title, from version, to version, time) in step with the snapshots, so the panel can
  see them without root, as it does `sites.json`. The snapshots themselves live in `/var/backups/xampp-panel`
  (root, 0700), outside the folder `uninstall.sh` removes, so uninstalling the panel does not delete them.
- **In the panel.** (1) After an update, a bar for 7 days (config): "phpMyAdmin was updated to 5.2.3.
  Something not working? **Restore previous version** / **Hide**". (2) A permanent ☰ item
  **Restore previous version…**, enabled while any restore point exists. Both open the terminal at
  `sudo xampp-update --restore`, which goes straight to the choice of restore point (skipped when there is
  only one) and the confirmation. No new `pkexec` command is added: the security model is unchanged.
- **In the menu.** The same action is menu item 4.
- **Panel changes after the terminal closes.** The panel re-reads the index when its window regains focus,
  so the bar disappears once the restore is done.
- **Hide** stores the restore point's timestamp in `dismissed_restore` in `settings.json`.

## Startup check

`xampp-update --check [--force]` runs as the normal user and needs no root.

- Reads installed versions without root (`properties.ini`, `README`, `bin/php -v`, `bin/mysql --version`).
- Fetches the lists with the config's timeouts and caps (about 10 requests: phpMyAdmin 2, XAMPP 1,
  MariaDB up to 7 — series list, release-status list, up to 5 series date lists). Total budget 30 s;
  failure of one source does not lose the others.
- Writes `~/.cache/xampp-panel/updates.json` (0600, atomic):
  `{"checked_at": <Unix time of the last successful list fetch>, "components": {"phpmyadmin": {"title": …, "installed": "5.2.1", "latest": "5.2.3", "latest_at": <Unix time>}, …}}`.
  `installed` is always read fresh (it is local), and the panel re-reads it from disk when drawing the bars, so an update
  or a restore is reflected at once. A time in the future, a non-finite time, or a `latest` older than 7 days is ignored.
  "Later" hides a version and anything not newer than it.
  `latest` is the top of the offered list, so the bar and the menu always agree.
- Runs at most once per 24 h unless `--force`; offline it stays silent and keeps the old file; a file older
  than 7 days is ignored.

The panel starts the check with `Gio.Subprocess` when the window opens and reads the file when it
finishes. A component appears in the bar when `latest` is newer than `installed` and differs from
`dismissed_updates[component]` in `~/.config/xampp-panel/settings.json`. **Later** stores the shown
`latest` values there. **Update…** opens the terminal menu (`terminal.py`).

## Security

| Threat | Protection |
|---|---|
| A tampered or substituted download | Hash checked before unpacking or running (SHA-256; or every MD5/SHA-1 obtained for XAMPP); phpMyAdmin also by PGP signature with pinned fingerprints; downloads go to a root-only `O_EXCL|O_NOFOLLOW` folder |
| Network attacker | HTTPS only including redirects, TLS 1.2+; integrity rests on hashes, not on the host |
| A hostile list page or API response | Size and time caps; strict parsers (regex on fixed shapes, `json`); every version string validated by a strict pattern before it reaches a path, URL or command; unknown shapes are errors |
| A malicious archive | `archive.py` rejects absolute paths, `..`, devices, escaping links, too many entries, too much unpacked size |
| Running arbitrary code as root | XAMPP installer only after `yes` and from a private root-only copy checked again; everything else runs from `/opt/xampp-panel/lib` with `python3 -I`; subprocesses use argument lists, never a shell |
| Passwords | Never on argv or in the environment; the existing `MysqlAdmin` client handles them (0600 defaults file, SQL on stdin) |
| A rehearsal server reachable by others | `skip-networking`, socket inside a root-owned scratch folder, deleted afterwards |
| Concurrent runs | The `xampp-repair` lock is shared |
| A user-controlled cache file driving root | The root tool never reads the user's cache or settings; it fetches the lists itself |

Accepted limitation: the root tool parses network responses in its own process. The mitigation is the
caps and strict validation above, with no external parsers and no `eval`.

## Error handling

- Every user-visible failure is a message box with what was attempted, what state things are in now, and
  the next step. `UpdateError` carries that text; `_attempt` shows it, as in `repair.py`.
- Download problems (offline, hash mismatch, signature failure, disk full) happen before any live change
  and say so. A hash mismatch deletes the download.
- After a successful rollback the message says the old version is running again.
- If the rollback fails, the message lists the snapshot paths and the exact commands to restore by hand.
- The check never shows errors in the panel; at most one line in the journal.

## Testing

Standard library `unittest`, like the rest of the suite. Nothing touches the real `/opt`, `/etc` or network.

- **Fixtures** recorded from the live APIs of 2026-10-08 (phpMyAdmin `/files/` and `version.json`,
  MariaDB series/release/status JSON, SourceForge RSS), plus hostile variants (huge, truncated,
  wrong types, bad version strings).
- `versions`, `releases`, `config`: pure tests; `pick` covers installed-in/out-of-list, EOL filter, status
  filter, both directions, ties.
- `fetcher`/`archive`: resume, stall, size cap, hash mismatch; traversal, link, device, bomb tests.
- `snapshots`: retention, manifest round trip.
- Components with a fake runner, clock, `Dialogs`, `MysqlAdmin` and a temp-dir `Paths`: the ordering of
  steps (snapshot before switch, verify before success), the failure path at **every** step, rollback
  restoring byte-for-byte, "leave things as they were", cancel at every question.
- `check`: throttle, stale cache, offline, dismissed filter, partial source failure.
- `configedit` MariaDB block: apply/remove round trip, idempotent, preserves unrelated lines.
- Scripts: `bash -n`; `test_data`/`test_scripts` extended for the launcher, symlink, manifest entries.
- GUI import test covers the new bar.

**Not verifiable in the build environment** (no `/opt/lampp`, no root, no MariaDB): the real MariaDB
swap, real library resolution, `lampp` behaviour with a new server, real XAMPP installer run, whiptail
rendering. A manual checklist goes into the plan, run in this order on the target: (1) the probe items
above, (2) phpMyAdmin up and back, (3) MariaDB rehearsal only, (4) full MariaDB upgrade and roll back,
(5) XAMPP last. Take a phpMyAdmin Export of important databases before step 4.

## Documentation

Following the project's existing split (not new files):

- `README.md`: one line and the command.
- `docs/USER-GUIDE.md`: an **Updates** section (the bar, the menu, version tags, going back, roll back,
  what each component backs up and costs in disk and downtime), plus rows in Common problems.
- `docs/MAINTAINER.md`: module table and diagram updated; new sections for sources and how to change
  them, files created (`/opt/lampp/mariadb/`, `/var/backups/xampp-panel/`, `/opt/lampp.before-*`,
  `~/.cache/xampp-panel/updates.json`, the `my.cnf` block), the security rows, decisions and what each
  costs if wrong, known limitations, and "adding a component". §12 "Upgrading" points to the menu.

## Delivery order and review

Three implementation plans, one per phase, so value arrives early and the risky parts are reviewed and
tried on the real machine one at a time. Phases 2 and 3 are planned only after phase 1 has been reviewed
and the probe items in "Facts" have been answered on the target, because their code depends on those answers.

1. **Core + phpMyAdmin + startup check + restore button:** `config`, `versions`, `http`, `releases`,
   `fetcher`, `archive`, `gpg`, `snapshots`, `restore_points`, `base`, the phpMyAdmin component, `check`,
   the menu (`app.py`, launcher, `setup.sh` and `uninstall.sh` changes, `terminal.py`), the panel's update
   bar, restore bar and ☰ items, docs. Shippable on its own.
2. **MySQL (MariaDB):** the probe items, `configedit` block, `paths.py` active slot, shared root-password
   class, the in-place path, the export/reload path, rehearsal, roll back, docs.
3. **PHP + Apache (XAMPP):** release source, typed confirmation, snapshot-by-rename, carry-over,
   re-apply, roll back, docs.

Each phase ends with the full suite green, then the review your standing rules require: parallel
review agents (security; dead or useless code and correctness bugs; efficiency and best practices), each
finding verified against the code and reported by severity, approved fixes applied, and a fresh agent
reviewing the fixes. Docs are updated in the same phase as the code, not afterwards.

## Out of scope / later

- Choosing a PHP version independently of XAMPP.
- Deleting old snapshots on request (one per component is kept; documented how to remove by hand).
- Tray notifications for updates.
- Dropping privileges for the network phase of the root tool.
