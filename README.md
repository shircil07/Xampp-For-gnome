# XAMPP Panel

A native control panel for XAMPP on Zorin OS (and other GNOME / Ubuntu 22.04+ systems).

- Start and stop Apache, MySQL and FTP with switches. You get a graphical password prompt, not `sudo` in a terminal.
- Add local sites like `http://blog.local` served from `~/Sites/blog`.
- XAMPP only listens on this computer by default. Optional lean mode runs fewer idle processes.
- Optional tray icon. Nothing runs at boot.
- Repair & configure menu (☰) for passwords and known XAMPP problems; also available as `sudo xampp-repair`.

## Documentation

- [User guide](docs/USER-GUIDE.md): using the panel, sites, common problems
- [Technical reference](docs/MAINTAINER.md): architecture, every file it touches, security model, troubleshooting, upgrading

## Install

```bash
git clone https://github.com/shircil07/Xampp-For-gnome.git
cd Xampp-For-gnome              # or ~/Downloads/xampp-panel on the original machine
sudo ./setup.sh
```

The script installs XAMPP from `xampp-linux-x64-*-installer.run` (looked for next to the project folder and in `~/Downloads`) if it isn't already in
`/opt/lampp`. Run `./setup.sh --help` for options (`--allow-lan`, `--lean`, `--installer PATH`).

## Remove

```bash
sudo ./uninstall.sh                 # removes the panel, keeps XAMPP and your data
sudo ./uninstall.sh --remove-xampp  # also removes XAMPP (including databases)
```

## Develop

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m xampp_panel.main      # run the panel from the source tree
```
