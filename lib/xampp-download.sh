# shellcheck shell=bash
# Find, download and verify the XAMPP installer. Sourced by setup.sh (set -euo pipefail, nullglob).
#
# To move to another XAMPP version: change XAMPP_VERSION and XAMPP_SHA256. The SHA-256 must come
# from a download you checked against the MD5/SHA-1 on https://www.apachefriends.org/download.html
# (Apache Friends publishes no SHA-256). See docs/MAINTAINER.md §12.
XAMPP_VERSION=8.2.12
XAMPP_FILE="xampp-linux-x64-$XAMPP_VERSION-0-installer.run"
XAMPP_URL="https://downloads.sourceforge.net/project/xampp/XAMPP%20Linux/$XAMPP_VERSION/$XAMPP_FILE"
XAMPP_SHA256=df0774e7a6d0d0754a5f0132015411234b5f953df2365b693d3758fc35a30374
XAMPP_ATTEMPTS=4         # a dropped connection resumes where it stopped
XAMPP_RETRY_PAUSE=5      # seconds between attempts
XAMPP_STALL_SECONDS=60   # give up an attempt that receives nothing for this long
# Installers of other versions are never run automatically; names like this are only mentioned
# in a hint (the strict pattern keeps odd characters out of the terminal).
XAMPP_NAME_RE='^xampp-linux-x64-[0-9]+(\.[0-9]+)*-[0-9]+-installer\.run$'

_xampp_error() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; }

# Runs a command as the user who called sudo: downloads and changes in their folders never run as root.
xampp_as_user() { runuser -u "$REAL_USER" -- "$@"; }

# xampp_find_installer DIR...: print the first DIR/$XAMPP_FILE (the pinned, checksummed version).
# Returns 1 if none: other versions are never picked automatically, they need --installer.
xampp_find_installer() {
  local dir
  for dir in "$@"; do
    [[ -f $dir/$XAMPP_FILE ]] && { printf '%s\n' "$dir/$XAMPP_FILE"; return 0; }
  done
  return 1
}

# xampp_other_installers DIR...: print other XAMPP installers in DIRs (for a hint), one per line.
xampp_other_installers() {
  local dir path
  for dir in "$@"; do
    for path in "$dir"/xampp-linux-x64-*-installer.run; do
      [[ -f $path && ${path##*/} != "$XAMPP_FILE" && ${path##*/} =~ $XAMPP_NAME_RE ]] && printf '%s\n' "$path"
    done
  done
  return 0
}

# xampp_download DEST: fetch $XAMPP_URL to DEST as the user, through DEST.part (resumed after a
# dropped connection or an interrupted run). Gives up after $XAMPP_ATTEMPTS and removes DEST.part.
xampp_download() {
  local dest=$1 part="$1.part" attempt
  if ! xampp_as_user mkdir -p -- "$(dirname -- "$dest")"; then
    _xampp_error "cannot create $(dirname -- "$dest") to download XAMPP into."
    return 1
  fi
  for ((attempt = 1; attempt <= XAMPP_ATTEMPTS; attempt++)); do
    # -q: ignore ~/.curlrc; >&2: nothing curl prints may end up in the captured path on stdout.
    if xampp_as_user curl -q --fail --location --proto =https --proto-redir =https --tlsv1.2 \
         --connect-timeout 30 --speed-limit 1 --speed-time "$XAMPP_STALL_SECONDS" \
         --continue-at - --progress-bar --output "$part" -- "$XAMPP_URL" >&2; then
      xampp_as_user mv -f -- "$part" "$dest" && return 0
      _xampp_error "cannot save the download as $dest."
      return 1
    fi
    ((attempt < XAMPP_ATTEMPTS)) && { echo "Download interrupted; trying again ($((attempt + 1))/$XAMPP_ATTEMPTS)…" >&2; sleep "$XAMPP_RETRY_PAUSE"; }
  done
  xampp_as_user rm -f -- "$part" || true
  _xampp_error "the XAMPP download failed. Check your internet connection and run setup.sh again. (Behind a proxy? sudo drops proxy settings: download $XAMPP_FILE from https://www.apachefriends.org yourself and use --installer.)"
  return 1
}

# xampp_verified_copy SRC WORKDIR: copy SRC into the private WORKDIR, check the copy against
# $XAMPP_SHA256 and print its path. The file that runs is the file that was checked, even though
# SRC sits in a folder the user can write to. Returns 1 on a wrong checksum, 2 if the copy failed.
xampp_verified_copy() {
  local copy="$2/$XAMPP_FILE" actual
  install -m 0700 -- "$1" "$copy" || return 2
  actual=$(sha256sum < "$copy") || { rm -f -- "$copy"; return 2; }
  if [[ ${actual%% *} != "$XAMPP_SHA256" ]]; then
    rm -f -- "$copy"
    return 1
  fi
  printf '%s\n' "$copy"
}

# xampp_prepare WORKDIR DOWNLOADS INSTALLER SEARCH_DIR...: decide which installer to run and print
# the path of a private copy of it in WORKDIR. INSTALLER is --installer's value or "" (then search
# DOWNLOADS and SEARCH_DIRs for the pinned version, and download it into DOWNLOADS if it isn't there).
# The pinned version is checked against its SHA-256; another version runs only when given as
# INSTALLER, and is then copied unchecked. Messages go to stderr; stdout is only the path.
xampp_prepare() {
  local workdir=$1 downloads=$2 installer=$3 downloaded=0 run rc=0
  shift 3
  if [[ -z $installer ]]; then
    if ! installer=$(xampp_find_installer "$@" "$downloads"); then
      local other
      while IFS= read -r other; do
        echo "Found $other, but it isn't XAMPP $XAMPP_VERSION. To install it instead: sudo ./setup.sh --installer $other" >&2
      done < <(xampp_other_installers "$@" "$downloads")
      echo "Downloading XAMPP $XAMPP_VERSION ($XAMPP_FILE) into $downloads…" >&2
      xampp_download "$downloads/$XAMPP_FILE" || return 1
      installer="$downloads/$XAMPP_FILE"
      downloaded=1
    fi
  elif [[ ! -f $installer ]]; then
    _xampp_error "--installer: file not found: $installer"
    return 1
  fi
  if [[ $(basename -- "$installer") == "$XAMPP_FILE" ]]; then
    run=$(xampp_verified_copy "$installer" "$workdir") || rc=$?
    case $rc in
      0) echo "Checksum OK." >&2 ;;
      1) if ((downloaded)); then
           xampp_as_user rm -f -- "$installer" || true
           _xampp_error "the downloaded installer was damaged (wrong checksum) and has been deleted. Run setup.sh again."
         else
           _xampp_error "$installer has the wrong checksum: it is incomplete or not the official $XAMPP_FILE. Delete it and run setup.sh again to download it."
         fi
         return 1 ;;
      *) _xampp_error "could not copy $installer to $workdir (disk full?)."
         return 1 ;;
    esac
  else
    run="$workdir/$(basename -- "$installer")"
    if ! install -m 0700 -- "$installer" "$run"; then
      _xampp_error "could not copy $installer to $workdir (disk full?)."
      return 1
    fi
  fi
  printf '%s\n' "$run"
}
