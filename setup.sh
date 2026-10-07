#!/usr/bin/env bash
# Install XAMPP (if missing) and XAMPP Panel on Zorin OS / Ubuntu.
set -euo pipefail
shopt -s nullglob

APP_DIR=/opt/xampp-panel
LAMPP=/opt/lampp
APP_ID=io.github.shiron.XamppPanel
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/xampp-download.sh
source "$SRC_DIR/lib/xampp-download.sh"

ALLOW_LAN=0
LEAN=ask
INSTALLER=""

usage() {
  cat <<EOF
Usage: sudo ./setup.sh [options]

Installs XAMPP (if /opt/lampp does not exist yet) and the XAMPP Panel app.

Options:
  --installer PATH  XAMPP installer to use (default: look in this folder
                    and in ~/Downloads; if none is there, download XAMPP
                    $XAMPP_VERSION into ~/Downloads and check its checksum)
  --allow-lan       let other devices on your network reach XAMPP
                    (default: only this computer can)
  --lean            turn on lean mode without asking
  --no-lean         leave lean mode off without asking
  -h, --help        show this help
EOF
}

while (($#)); do
  case "$1" in
    --installer) INSTALLER="${2:?--installer needs a path}"; shift ;;
    --allow-lan) ALLOW_LAN=1 ;;
    --lean) LEAN=yes ;;
    --no-lean) LEAN=no ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
ask() { local reply=""; read -r -p "$1 [y/N] " reply </dev/tty || true; [[ $reply =~ ^[Yy] ]]; }

[[ $EUID -eq 0 ]] || die "run this with: sudo ./setup.sh"
[[ $(uname -m) == x86_64 ]] || die "XAMPP for Linux only supports 64-bit x86 (x86_64)."
command -v apt-get >/dev/null || die "this script needs an apt-based system (Zorin OS, Ubuntu, Debian)."
REAL_USER="${SUDO_USER:-}"
[[ -n $REAL_USER && $REAL_USER != root ]] || die "run this with sudo from your normal account, not as root."
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
apt-cache show gir1.2-adw-1 >/dev/null 2>&1 || die "libadwaita is not available: XAMPP Panel needs Zorin OS 17 / Ubuntu 22.04 or newer."

say "Installing required packages"
packages=(curl ca-certificates libcrypt1 net-tools acl whiptail python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
if apt-cache show pkexec >/dev/null 2>&1; then packages+=(pkexec); else packages+=(policykit-1); fi
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${packages[@]}"

say "Checking XAMPP"
if [[ -x $LAMPP/lampp ]]; then
  echo "XAMPP is already installed in $LAMPP."
else
  # The installer runs as root, so it runs from a private copy in a root-only folder (not /tmp,
  # which may be noexec), never from the user's folder.
  workdir="$(mktemp -d -p /root xampp-setup.XXXXXX)"
  trap 'rm -rf -- "$workdir"' EXIT
  run="$(xampp_prepare "$workdir" "$REAL_HOME/Downloads" "$INSTALLER" "$SRC_DIR")" || exit 1
  echo "Installing $(basename -- "$run"). This takes a minute…"
  "$run" --mode unattended --unattendedmodeui none
  rm -rf -- "$workdir"   # don't keep a 150 MB copy around for the rest of setup
  trap - EXIT
  [[ -x $LAMPP/lampp ]] || die "the XAMPP installer finished but $LAMPP/lampp is missing."
fi

if pgrep -f "^$LAMPP/" >/dev/null; then
  say "Stopping XAMPP so the configuration changes apply cleanly"
  "$LAMPP/lampp" stop || true
fi

say "Checking ports 80, 443, 3306 and 21"
declare -A offered=()
for port in 80 443 3306 21; do
  line="$(ss -Hltnp "sport = :$port" 2>/dev/null | head -n1 || true)"
  [[ -n $line ]] || continue
  process="$(grep -oP 'users:\(\("\K[^"]+' <<<"$line" || true)"
  echo "Port $port is already used by: ${process:-an unknown program}"
  case "$process" in
    apache2) units=(apache2) ;;
    nginx) units=(nginx) ;;
    mysqld|mariadbd) units=(mysql mariadb) ;;
    *) units=() ;;
  esac
  for unit in "${units[@]}"; do
    [[ -z ${offered[$unit]:-} ]] || continue
    offered[$unit]=1
    systemctl is-active --quiet "$unit" || continue
    if ask "Stop and disable the system '$unit' service so XAMPP can use port $port?"; then
      systemctl disable --now "$unit"
    else
      echo "Keeping $unit. XAMPP's service on port $port will not start while it runs."
    fi
  done
done

say "Installing XAMPP Panel to $APP_DIR"
install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/bin" "$APP_DIR/lib" "$APP_DIR/state"
rm -rf "$APP_DIR/lib/xampp_panel"
cp -r "$SRC_DIR/src/xampp_panel" "$APP_DIR/lib/"
find "$APP_DIR/lib" -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root "$APP_DIR/lib"
chmod -R u=rwX,go=rX "$APP_DIR/lib"
python3 -I -m compileall -q "$APP_DIR/lib"
install -o root -g root -m 0755 "$SRC_DIR/bin/xampp-panel" "$SRC_DIR/bin/xampp-helper" "$SRC_DIR/bin/xampp-repair" "$APP_DIR/bin/"

installed=()
put() { install -D -o root -g root -m 0644 "$SRC_DIR/$1" "$2"; installed+=("$2"); }
put "data/io.github.shiron.xampppanel.policy" /usr/share/polkit-1/actions/io.github.shiron.xampppanel.policy
put "data/$APP_ID.desktop" "/usr/share/applications/$APP_ID.desktop"
put "data/icons/$APP_ID.svg" "/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
put "data/icons/xampp-panel-running.svg" /usr/share/icons/hicolor/scalable/status/xampp-panel-running.svg
put "data/icons/xampp-panel-stopped.svg" /usr/share/icons/hicolor/scalable/status/xampp-panel-stopped.svg
ln -sfn "$APP_DIR/bin/xampp-panel" /usr/local/bin/xampp-panel
installed+=(/usr/local/bin/xampp-panel)
ln -sfn "$APP_DIR/bin/xampp-repair" /usr/local/bin/xampp-repair
installed+=(/usr/local/bin/xampp-repair)
printf '%s\n' "${installed[@]}" > "$APP_DIR/install-manifest.txt"
gtk-update-icon-cache -qtf /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true

say "Configuring XAMPP"
HELPER="$APP_DIR/bin/xampp-helper"
"$HELPER" integrate on
case "$LEAN" in
  yes) "$HELPER" lean on ;;
  no) ;;
  ask) if ask "Turn on lean mode (fewer idle Apache processes and a smaller MySQL)?"; then "$HELPER" lean on; fi ;;
esac

say "Setting up MySQL and phpMyAdmin accounts"
# Replaces XAMPP's "lampp security", which breaks MySQL networking, the FTP config and phpMyAdmin.
"$APP_DIR/bin/xampp-repair" first-install </dev/tty >/dev/tty \
  || echo "Account setup did not finish. Run it later with: sudo xampp-repair"

# Last, so nothing above can undo the localhost-only setting.
if ((ALLOW_LAN)); then
  "$HELPER" harden off
  echo "LAN access allowed: other devices on your network can reach XAMPP."
else
  "$HELPER" harden on
  echo "XAMPP now only accepts connections from this computer."
fi

say "Done"
echo "Open “XAMPP Control Panel” from your app menu, or run: xampp-panel"
echo "To remove the panel later: sudo $SRC_DIR/uninstall.sh"
