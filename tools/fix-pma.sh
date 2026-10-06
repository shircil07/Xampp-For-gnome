#!/bin/bash
# Fix phpMyAdmin's "Access denied for user 'pma'@'localhost'" /
# "Connection for controluser as defined in your configuration failed".
#
# "lampp security" writes a controlpass into config.inc.php without making the
# MySQL account 'pma' match. This creates/updates 'pma' with that password and
# makes sure the phpMyAdmin storage database exists. Safe to run more than once.
# Not installed by setup.sh. Run from a normal terminal: bash tools/fix-pma.sh
set -euo pipefail

LAMPP=/opt/lampp
CFG=$LAMPP/phpmyadmin/config.inc.php
TABLES=$LAMPP/phpmyadmin/sql/create_tables.sql
PHP_SRC=$(dirname "$(readlink -f "$0")")/fix-pma.php

for f in "$CFG" "$TABLES" "$LAMPP/bin/php" "$LAMPP/bin/mysql"; do
  sudo test -e "$f" || { echo "Missing: $f" >&2; exit 1; }
done

# The config is owned by the web server user and could be edited by a compromised
# site, so it is only ever run as that user, never as root. The PHP file goes in on
# stdin because that user usually can't read files in your home folder.
OWNER=$(sudo stat -c %U "$CFG")
if [[ $OWNER == root ]]; then
  echo "$CFG is owned by root; refusing to run its PHP as root." >&2
  echo "XAMPP normally gives it to the web server user (daemon): sudo chown daemon $CFG" >&2
  exit 1
fi
config_php() { sudo -u "$OWNER" "$LAMPP/bin/php" -d display_errors=stderr -- "$1" "$CFG" < "$PHP_SRC"; }

# SQL goes into a private temp file so the password never shows on a command line.
SQL=$(mktemp)
trap 'rm -f "$SQL"' EXIT

# create_tables.sql only uses IF NOT EXISTS, so existing data is kept.
sudo cat "$TABLES" > "$SQL"
config_php sql >> "$SQL"

echo "Enter the MySQL root password (press Enter if root has none yet):"
"$LAMPP/bin/mysql" -u root -p < "$SQL"

echo
echo "Testing the control user login..."
config_php check
