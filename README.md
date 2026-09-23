# XAMPP Panel

A native control panel for XAMPP on Zorin OS (and other GNOME / Ubuntu 22.04+ systems).

- Start and stop Apache, MySQL and FTP with switches. You get a graphical password prompt, not `sudo` in a terminal.
- Add local sites like `http://blog.local` served from `~/Sites/blog`.
- XAMPP only listens on this computer by default. Lean mode is optional and saves RAM.
- Optional tray icon. Nothing runs at boot.

## Install

```bash
cd ~/Downloads/xampp-panel
sudo ./setup.sh
```

The script installs XAMPP from `~/Downloads/xampp-linux-x64-*-installer.run` if it isn't already in
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
