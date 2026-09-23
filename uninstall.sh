#!/usr/bin/env bash
# Remove XAMPP Panel and undo its changes to the XAMPP configuration.
set -euo pipefail
shopt -s nullglob

APP_DIR=/opt/xampp-panel
LAMPP=/opt/lampp
REMOVE_XAMPP=0

usage() {
  cat <<'EOF'
Usage: sudo ./uninstall.sh [--remove-xampp]

Removes XAMPP Panel and reverts every change it made to XAMPP's configuration
and /etc/hosts. Your ~/Sites folders are kept.

Options:
  --remove-xampp   also uninstall XAMPP itself (/opt/lampp, including databases!)
  -h, --help       show this help
EOF
}

while (($#)); do
  case "$1" in
    --remove-xampp) REMOVE_XAMPP=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run this with: sudo ./uninstall.sh"

if [[ -x $APP_DIR/bin/xampp-helper && -x $LAMPP/lampp ]]; then
  echo "Stopping XAMPP…"
  "$LAMPP/lampp" stop || true
  "$APP_DIR/bin/xampp-helper" integrate off
  "$APP_DIR/bin/xampp-helper" lean off
  "$APP_DIR/bin/xampp-helper" harden off
fi

if [[ -f $APP_DIR/install-manifest.txt ]]; then
  while IFS= read -r path; do
    case "$path" in
      /usr/share/*|/usr/local/bin/*) rm -f -- "$path" ;;
      "") ;;
      *) echo "Skipping unexpected manifest entry: $path" >&2 ;;
    esac
  done < "$APP_DIR/install-manifest.txt"
fi
rm -rf -- "$APP_DIR"
for backup in "$LAMPP"/etc/*.xampp-panel.bak "$LAMPP"/etc/extra/*.xampp-panel.bak /etc/hosts.xampp-panel.bak; do
  rm -f -- "$backup"
done
gtk-update-icon-cache -qtf /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true
if [[ -n ${SUDO_USER:-} ]]; then
  rm -f -- "$(getent passwd "$SUDO_USER" | cut -d: -f6)/.config/xampp-panel/settings.json"
fi

if ((REMOVE_XAMPP)) && [[ -x $LAMPP/uninstall ]]; then
  echo "Uninstalling XAMPP…"
  "$LAMPP/uninstall" --mode unattended
fi
echo "XAMPP Panel removed. Your ~/Sites folders were kept."
