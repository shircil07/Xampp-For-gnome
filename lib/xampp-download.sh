# Download and verify the XAMPP installer. Sourced by setup.sh (bash, set -euo pipefail).
#
# To move to another XAMPP version: change these three values. The SHA-256 must come from a
# download you checked against the MD5/SHA-1 on https://www.apachefriends.org/download.html
# (Apache Friends publishes no SHA-256).
XAMPP_FILE=xampp-linux-x64-8.2.12-0-installer.run
XAMPP_URL="https://downloads.sourceforge.net/project/xampp/XAMPP%20Linux/8.2.12/$XAMPP_FILE"
XAMPP_SHA256=df0774e7a6d0d0754a5f0132015411234b5f953df2365b693d3758fc35a30374

# Runs a command as the user who called sudo, so the download never runs as root.
xampp_as_user() { runuser -u "$REAL_USER" -- "$@"; }

# xampp_download DEST: fetch $XAMPP_URL to DEST (as the user). A failed download leaves nothing behind.
xampp_download() {
  local dest=$1 part="$1.part"
  xampp_as_user mkdir -p -- "$(dirname -- "$dest")"
  if xampp_as_user curl --fail --location --proto =https --proto-redir =https --tlsv1.2 \
       --retry 3 --connect-timeout 30 --progress-bar --output "$part" -- "$XAMPP_URL" \
     && xampp_as_user mv -f -- "$part" "$dest"; then
    return 0
  fi
  rm -f -- "$part"
  return 1
}

# xampp_verified_copy SRC WORKDIR: copy SRC into the private WORKDIR, check the copy against
# $XAMPP_SHA256 and print its path. Checking the copy (not SRC) means the file that runs is the
# file that was checked, even though SRC sits in a folder the user can write to.
xampp_verified_copy() {
  local copy="$2/$XAMPP_FILE"
  install -m 0700 -- "$1" "$copy"
  if [[ $(sha256sum -- "$copy" | cut -d' ' -f1) != "$XAMPP_SHA256" ]]; then
    rm -f -- "$copy"
    return 1
  fi
  printf '%s\n' "$copy"
}
