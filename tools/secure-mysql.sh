#!/bin/bash
# Secure XAMPP's MariaDB without "lampp security" (which also breaks MySQL
# networking and the FTP config):
#   - removes every anonymous account (''@...). With them, a wrong or empty user name
#     logs in with no rights instead of failing, e.g. phpMyAdmin
#     "#1044 - Access denied for user ''@'localhost' to database ...".
#   - sets one password on every root account (localhost, 127.0.0.1, ::1, ...).
#   - if phpMyAdmin logs in automatically as root without a password
#     (auth_type 'config'), switches it to its login page (auth_type 'cookie'),
#     keeping a backup. Otherwise phpMyAdmin would be locked out.
# Safe to run more than once. Not installed by setup.sh.
# Run from a normal terminal: bash tools/secure-mysql.sh
set -euo pipefail

LAMPP=/opt/lampp
PMA_CFG=$LAMPP/phpmyadmin/config.inc.php
BACKUP_SUFFIX=.xampp-panel.bak  # same convention as the panel's own config edits
MIN_LENGTH=8
MAX_LENGTH=128

# Matches the active (not commented out) auth_type line of phpMyAdmin's config.
AUTH_TYPE_RE="^([[:space:]]*\\\$cfg\\['Servers'\\]\\[\\\$i\\]\\['auth_type'\\][[:space:]]*=[[:space:]]*')([a-z]+)(';.*)$"

as_root() { sudo "$@"; }

# SQL string literal. Used after switching NO_BACKSLASH_ESCAPES off, so both escapes hold.
sql_quote() {
  local s=${1//\\/\\\\}
  printf "'%s'" "${s//\'/\'\'}"
}

# Prints the SQL to stdout. Argument: new root password.
# MariaDB lists the accounts itself, so accounts with unusual hosts are covered too.
build_sql() {
  cat <<EOF
SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');
SET SESSION group_concat_max_len = 65536;
SET @pw = $(sql_quote "$1");
SELECT GROUP_CONCAT(CONCAT(QUOTE(user), '@', QUOTE(host))) INTO @accounts FROM mysql.user WHERE user = '';
EXECUTE IMMEDIATE IF(@accounts IS NULL, 'DO 0', CONCAT('DROP USER ', @accounts));
SELECT GROUP_CONCAT(CONCAT(QUOTE(user), '@', QUOTE(host), ' IDENTIFIED BY ', QUOTE(@pw))) INTO @accounts FROM mysql.user WHERE user = 'root';
EXECUTE IMMEDIATE CONCAT('ALTER USER ', @accounts);
SET @pw = NULL, @accounts = NULL;
EOF
}

# Prints phpMyAdmin's active auth_type (empty if none is set).
pma_auth_type() {
  as_root sed -nE "s/$AUTH_TYPE_RE/\\2/p" "$1" | tail -n 1
}

# Backs the config up once, like the panel does.
pma_backup() {
  as_root test -e "$1$BACKUP_SUFFIX" || as_root cp -p "$1" "$1$BACKUP_SUFFIX"
}

# Switches auth_type 'config' to 'cookie'.
pma_use_login_page() {
  as_root sed -i -E "s/$AUTH_TYPE_RE/\\1cookie\\3/" "$1"
}

read_new_password() {
  local first second
  while true; do
    # IFS= keeps spaces at the start and end of the password.
    IFS= read -rsp "New MySQL root password: " first; echo
    IFS= read -rsp "Repeat it: " second; echo
    if [[ $first != "$second" ]]; then
      echo "The passwords don't match. Try again."
    elif (( ${#first} < MIN_LENGTH || ${#first} > MAX_LENGTH )); then
      echo "Use $MIN_LENGTH to $MAX_LENGTH characters. Try again."
    elif [[ $first == *[[:cntrl:]]* ]]; then
      echo "Control characters aren't allowed. Try again."
    else
      NEW_PASSWORD=$first
      return
    fi
  done
}

main() {
  [[ -x $LAMPP/bin/mysql ]] || { echo "Missing: $LAMPP/bin/mysql" >&2; exit 1; }
  echo "This removes MariaDB's anonymous accounts and sets the root password."
  echo "You may be asked for your computer (sudo) password first."
  echo
  # Ask for sudo up front, so a failed sudo can't pass for "config not found" below.
  sudo -v || { echo "sudo failed; nothing was changed." >&2; exit 1; }

  local auth_type=""
  if as_root test -e "$PMA_CFG"; then
    auth_type=$(pma_auth_type "$PMA_CFG")
  else
    echo "Note: $PMA_CFG not found; phpMyAdmin's login setting is left alone."
  fi
  if [[ $auth_type == config ]]; then
    echo "phpMyAdmin currently logs in automatically as root. Afterwards it will show"
    echo "a login page instead (a backup of its config is kept as config.inc.php$BACKUP_SUFFIX)."
    echo
  fi

  read_new_password
  [[ $auth_type == config ]] && pma_backup "$PMA_CFG"

  # SQL goes into a private temp file so the password never shows on a command line.
  SQL=$(mktemp)
  trap 'rm -f "$SQL"' EXIT
  build_sql "$NEW_PASSWORD" > "$SQL"
  unset NEW_PASSWORD

  sudo -v  # refresh, so the phpMyAdmin switch after the MySQL step needs no new prompt
  echo
  echo "Enter the CURRENT MySQL root password (press Enter if root has none yet):"
  "$LAMPP/bin/mysql" -u root -p < "$SQL"

  # Only after the password change worked, so a failure never locks phpMyAdmin out.
  if [[ $auth_type == config ]]; then
    pma_use_login_page "$PMA_CFG"
    echo "phpMyAdmin now shows a login page."
  fi

  echo
  echo "Done. To list the remaining accounts, enter the NEW root password:"
  "$LAMPP/bin/mysql" -u root -p -e "
    SELECT CONCAT(QUOTE(user), '@', QUOTE(host)) AS account,
           IF(authentication_string = '' AND password = '', 'NO PASSWORD', 'has password') AS password
    FROM mysql.user ORDER BY user, host;"
  echo "Log in to phpMyAdmin as 'root' with the new password."
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
