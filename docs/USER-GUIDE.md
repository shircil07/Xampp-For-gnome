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
- **Set passwords?** Recommended. Sets passwords for the MySQL admin user and phpMyAdmin.

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

A yellow bar at the top means **MySQL has no password**. Fix it from the XAMPP Panel source folder
(the folder you ran `setup.sh` from):

```bash
bash tools/secure-mysql.sh
```

It asks, in this order, for: your computer (sudo) password, a new root password twice, the current root
password (just press Enter if there is none), and the new password once more to show the remaining
accounts. It also removes MySQL's anonymous accounts. If phpMyAdmin used to open without asking for a
password, it now shows a login page. Log in there as `root` with the new password.

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
| Keep in tray when closed | Shows a small XAMPP icon in the top bar with Start/Stop/Open. Needs the AppIndicator extension; the item says so if it's missing. |
| Lean mode (uses less memory) | Fewer background Apache processes and a smaller MySQL. Restart Apache and MySQL afterwards. |
| Quit | Closes the panel. Apache and MySQL keep running until you stop them. |

Closing the panel does **not** stop your servers. Nothing starts automatically when the computer boots.
Open the panel and press **Start** when you want to work.

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
| phpMyAdmin says `Access denied for user 'pma'@'localhost'` or "Connection for controluser … failed" | `lampp security` left phpMyAdmin's helper account with the wrong password. From the project folder run `bash tools/fix-pma.sh`. It asks for your computer (sudo) password, then your MySQL root password, and should print `OK`. |
| phpMyAdmin says `#1044 - Access denied for user ''@'localhost'` when creating a database | You're logged in under the wrong user name. Log out of phpMyAdmin and log in as `root`. To stop it happening, run `bash tools/secure-mysql.sh` (see the yellow bar above). |
| MySQL log mentions `Please run mysql_upgrade` or `mysql.column_stats` | Run `sudo /opt/lampp/bin/mysql_upgrade -u root` (add `-p` if you set a password), then restart MySQL. |
| MySQL stays yellow ("starting…") and its log says `port: 0` | Run `sudo /opt/xampp-panel/bin/xampp-helper harden on`, then switch MySQL off and on. |
| FTP won't start; its error mentions `'function'` | `lampp security` damaged the FTP config. See "Troubleshooting" in [MAINTAINER.md](MAINTAINER.md) §11. |
| `http://name.local` "can't be reached" | Check the site is listed in the Sites tab. If it is and Chrome still fails, turn off Chrome's "Use secure DNS" or try Firefox. |
| `name.local` says **Forbidden** | Remove the site and add it again. |
| Running `xampp-panel` in a remote/SSH terminal says "Gtk couldn't be initialized" | Normal: there's no screen there. Open it from the app menu. |

When asking for help, include the message the panel showed plus the output of:

```bash
journalctl --user --since "10 min ago" | grep -iA25 xampp
```

Put commands on **one line** when pasting them. If a command starting with `pkexec` wraps so that
`pkexec` ends up alone on a line, it opens an **admin shell** (the prompt shows `root@`). Type `exit` to leave it.
