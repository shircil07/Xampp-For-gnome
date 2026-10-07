# XAMPP Control Panel — User Guide

XAMPP gives you a local web server (Apache), a database (MySQL/MariaDB) and PHP on your own
computer, so you can build websites without putting them online. The **XAMPP Control Panel** is
the app that turns those on and off and manages your projects.

Technical details and troubleshooting are in [MAINTAINER.md](MAINTAINER.md).

---

## Installing

In a terminal:

```bash
cd ~/Downloads/xampp-panel     # the project folder (a GitHub clone is called Xampp-For-gnome)
sudo ./setup.sh
```

The script:

- installs what's missing
- installs XAMPP from `~/Downloads` if it isn't installed yet
- makes XAMPP reachable **only from this computer**
- adds **XAMPP Control Panel** to your app menu

It asks before doing anything you might not want:

- **Stop another web server?** Only asked if something else, like Ubuntu's own Apache, is using XAMPP's ports.
- **Lean mode?** Uses less memory. Fine for one person developing.
- **MySQL root password** (a password box near the end): the password for the MySQL admin user `root`.
  Recommended. Leave it empty to skip; the panel then reminds you with a yellow bar. Not asked again
  when you re-run `setup.sh` and root already has a password (change it from the repair menu instead).
  If setup needs the current root password to repair phpMyAdmin's account, it asks for it once and
  also uses it to remove XAMPP's anonymous MySQL accounts.

phpMyAdmin's internal account (`pma`) is always set up for you, without a question. Re-running
`setup.sh` leaves it alone if it already works.

Options (`./setup.sh --help`):

| Option | Effect |
|---|---|
| `--allow-lan` | Let phones and other computers on your Wi-Fi open your sites (off by default for safety) |
| `--lean` / `--no-lean` | Answer the lean-mode question in advance |
| `--installer PATH` | Use a specific XAMPP installer file |

---

## The control panel

Open **XAMPP Control Panel** from the app menu. It follows your light or dark theme.
When you start or stop something, it asks for **your password** in a normal system window.
It then remembers it for a few minutes.

### Services tab

| Row | What it is | Port |
|---|---|---|
| Apache | Web server that shows your sites | 80 |
| MySQL | Database | 3306 |
| ProFTPD | File transfer server (rarely needed; off unless you switch it on) | 21 |

- **Switch:** turns that service on or off.
- **Start** (top): starts Apache and MySQL together. **Stop all** stops everything.
- **Coloured dot:**
  - 🟢 **running**
  - 🟡 **starting / working**
  - ⚪ **stopped**
  - 🔴 **another program is using the port**
- **Log button** (page icon): shows the service's latest log messages, with a refresh button.
  Use it when something won't start.

**Shortcuts** at the bottom:

- **Open localhost:** your main XAMPP web folder in the browser.
- **Open phpMyAdmin:** manage databases in the browser (Apache and MySQL must be running).
- **Open htdocs folder:** `/opt/lampp/htdocs`, the classic XAMPP web folder (needs admin rights to edit).
- **Open Sites folder:** `~/Sites`, where your own projects live (you can edit freely).

A yellow bar at the top means **MySQL has no password**. Fix it from
**☰ → Repair & configure → Change MySQL root password** (see below).

Don't use XAMPP's own `sudo /opt/lampp/lampp security` for this: its MySQL network and FTP options are
broken in XAMPP 8.2 and stop MySQL or FTP working.

### Sites tab: your own projects

Instead of putting projects in `/opt/lampp/htdocs`, where you need admin rights, each project gets its own
address and a normal folder in your home:

1. Click **+**.
2. Type a name, such as `blog`. Use lowercase letters, numbers and dashes.
3. Optionally, **Choose…** an existing folder. Otherwise `~/Sites/blog` is created for you, with a starter page.
4. Click **Add**, and enter your password if asked.
5. Your browser opens **http://blog.local**.

Edit the files in the folder and refresh the browser. PHP works as normal.

Each site row has three buttons:

- **open in browser**
- **open folder**
- **remove**: removes the address only. **Your folder and files are kept.**

Rules for folders:

- the folder must be inside your home folder
- the folder must belong to you
- no site folder may sit inside another site's folder

### Menu (☰ top right)

| Item | What it does |
|---|---|
| Repair & configure… | Opens a terminal with the repair menu (below). Asks for your password (sudo). |
| Keep in tray when closed | Shows a small XAMPP icon in the top bar with Start/Stop/Open. Needs the AppIndicator extension; the item says so if it's missing. |
| Lean mode (uses less memory) | Fewer background Apache processes and a smaller MySQL. Restart Apache and MySQL afterwards. |
| Quit | Closes the panel. Apache and MySQL keep running until you stop them. |

Closing the panel does **not** stop your servers. Nothing starts automatically when the computer boots.
Open the panel and press **Start** when you want to work.

---

## Repair & configure

Open it from **☰ → Repair & configure…**, or type `sudo xampp-repair` in a terminal. It opens in a
terminal window with a text menu (use the arrow keys, Enter to choose, Esc to cancel). Use it for
MySQL/phpMyAdmin passwords and to fix the known ways XAMPP's own `lampp security` tool breaks things.

| Menu item | What it's for |
|---|---|
| Health check | A read-only report: are Apache/MySQL/FTP running and their configs valid, does MySQL have anonymous accounts or a password, can phpMyAdmin log in, are your sites set up. Each problem it finds names the menu item below that fixes it. |
| Change MySQL root password | Sets (or changes) the MySQL admin password, and removes XAMPP's unprotected "anonymous" account. Do this if the yellow bar is showing, or after `#1044 Access denied for user ''@'localhost'` in phpMyAdmin. |
| Show phpMyAdmin pma password | Shows the generated password of phpMyAdmin's own internal account (`pma`). You almost never need to type this yourself — it's for checking the account still has one, or copying it somewhere you manage MariaDB. |
| Fix phpMyAdmin pma login | Repairs `Access denied for user 'pma'@'localhost'`: recreates phpMyAdmin's internal account to match its own config. |
| Fix FTP config | Repairs `unknown configuration directive 'function'`, caused by XAMPP's `lampp security` writing broken text into the FTP config. Asks for a new FTP password for the user `daemon`. |
| Turn MySQL networking back on | Repairs MySQL staying on "starting…" with its log saying `port: 0`. |
| Run mysql_upgrade | Fixes MariaDB warnings like `Please run mysql_upgrade` after an update. |
| Re-apply panel config | Puts back the panel's site list, localhost-only settings and lean mode, in case an XAMPP reinstall removed them. |
| Quit | Closes the menu. If you opened it from the panel, the terminal then shows "Press Enter to close"; press Enter. |

It's safe to open the menu and look around: Health check and Show phpMyAdmin pma password only read.
Esc or Cancel at any question stops without changing anything, with three exceptions that do their
work as soon as you choose them: "Fix phpMyAdmin pma login" and "Run mysql_upgrade" ask nothing
(except the MySQL root password, if root has one and the menu doesn't know it yet), and "Turn MySQL
networking back on" fixes the config first and then asks whether to restart MySQL (No or Esc there
only skips the restart). Items that need MySQL start it if it isn't running (the terminal says so),
wait until it answers, and leave it running. If it doesn't answer within about 20 seconds you get a
message saying so; check the MySQL log in the panel.

---

## Everyday tasks

| I want to… | Do this |
|---|---|
| Start working | Panel → **Start** |
| Finish for the day | Panel → **Stop all** (saves memory and battery) |
| Make a new project | Sites tab → **+** |
| Create a database | Open phpMyAdmin → **New** |
| See why something failed | Click the service's log button, or read the message at the bottom of the panel |
| Use it without the window | Menu → Keep in tray when closed |

---

## Removing it

```bash
cd ~/Downloads/xampp-panel
sudo ./uninstall.sh                 # removes the panel, keeps XAMPP, databases and ~/Sites
sudo ./uninstall.sh --remove-xampp  # ALSO deletes XAMPP and all its databases
```

Before `--remove-xampp`, export any databases you want to keep: phpMyAdmin → Export.

---

## Common problems

| Problem | Fix |
|---|---|
| A switch flips back by itself | You closed the password window. Try again. |
| "Not authorized, or the XAMPP Panel helper is missing" | Wrong password, or the install is broken. Re-run `sudo ./setup.sh`. |
| 🔴 "port used by another program" | Something else uses that port. Run `sudo ss -ltnp 'sport = :80'` (or `:3306`) to see what. |
| phpMyAdmin says `(HY000/2002): No such file or directory` | MySQL isn't running. Switch it on. |
| phpMyAdmin says `Access denied for user 'pma'@'localhost'` or "Connection for controluser … failed" | **☰ → Repair & configure → Fix phpMyAdmin pma login.** |
| phpMyAdmin says `#1044 - Access denied for user ''@'localhost'` when creating a database | You're logged in under the wrong user name. Log out of phpMyAdmin and log in as `root`. To stop it happening, **☰ → Repair & configure → Change MySQL root password** (see the yellow bar above). |
| MySQL log mentions `Please run mysql_upgrade` or `mysql.column_stats` | **☰ → Repair & configure → Run mysql_upgrade.** |
| MySQL stays yellow ("starting…") and its log says `port: 0` | **☰ → Repair & configure → Turn MySQL networking back on.** |
| FTP won't start; its error mentions `'function'` | **☰ → Repair & configure → Fix FTP config.** |
| `http://name.local` "can't be reached" | Check the site is listed in the Sites tab. If it is and Chrome still fails, turn off Chrome's "Use secure DNS" or try Firefox. |
| `name.local` says **Forbidden** | Remove the site and add it again. |
| Running `xampp-panel` in a remote/SSH terminal says "Gtk couldn't be initialized" | Normal: there's no screen there. Open it from the app menu. |

When asking for help, include the message the panel showed plus the output of:

```bash
journalctl --user --since "10 min ago" | grep -iA25 xampp
```

Put commands on **one line** when pasting them. If a command starting with `pkexec` wraps so that
`pkexec` ends up alone on a line, it opens an **admin shell** (the prompt shows `root@`). Type `exit` to leave it.
