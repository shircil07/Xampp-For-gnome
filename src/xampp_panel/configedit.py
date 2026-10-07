"""Pure, reversible text transforms for XAMPP and system config files."""

import re
from pathlib import Path

_BEGIN = "# BEGIN xampp-panel {}"
_END = "# END xampp-panel {}"


def set_block(text: str, block_id: str, body: str | None) -> str:
    """Remove the marked block `block_id`, then (if `body`) append it again at the end."""
    begin, end = _BEGIN.format(block_id), _END.format(block_id)
    pattern = re.compile(rf"(?ms)^{re.escape(begin)}\n.*?^{re.escape(end)}\n?")
    text = pattern.sub("", text)
    if body is None:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}{begin}\n{body.rstrip(chr(10))}\n{end}\n"


def has_block(text: str, block_id: str) -> bool:
    return _BEGIN.format(block_id) in text


# Apache does not allow trailing comments, so the original value goes on a comment line above.
_LISTEN = re.compile(r"(?m)^Listen[ \t]+(\d+)[ \t]*$")
_LOCAL_LISTEN = re.compile(r'(?m)^# xampp-panel: was "Listen (\d+)"\nListen 127\.0\.0\.1:\d+[ \t]*$')


def apache_localhost(text: str, on: bool) -> str:
    if on:
        return _LISTEN.sub(lambda m: f'# xampp-panel: was "Listen {m[1]}"\nListen 127.0.0.1:{m[1]}', text)
    return _LOCAL_LISTEN.sub(lambda m: f"Listen {m[1]}", text)


_MYSQLD = re.compile(r"(?m)^\[mysqld\][ \t]*\n")
_BIND = "# xampp-panel: localhost only\nbind-address=127.0.0.1\n"
# XAMPP's "lampp security" adds skip-networking, which turns TCP off entirely ("port: 0"):
# clients using 127.0.0.1 fail and the panel never sees port 3306. bind-address keeps it local instead.
_SKIP_NET = re.compile(r"(?m)^(skip[-_]networking\b.*)$")
# Older versions kept skip-networking behind this marker to restore it on harden off; that is gone.
_OLD_MARKER = re.compile(r"(?m)^# xampp-panel: was \"skip[-_]networking\b.*\"\n(?=#skip-networking$)")


def mysql_localhost(text: str, on: bool) -> str:
    """on: listen on 127.0.0.1 only. Both ways leave skip-networking commented out: it never comes back."""
    text = _OLD_MARKER.sub("", text.replace(_BIND, ""))
    if not on:
        return text
    text = mysql_networking_on(text)
    new, count = _MYSQLD.subn(lambda m: m[0] + _BIND, text, count=1)
    if count:
        return new
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}[mysqld]\n{_BIND}"


def mysql_networking_off(text: str) -> bool:
    return bool(_SKIP_NET.search(text))


def mysql_networking_on(text: str) -> str:
    """Comments out skip-networking and nothing else: bind-address is harden's business."""
    return _SKIP_NET.sub(lambda m: f"#{m[1]}", text)


def mysql_hardened(text: str) -> bool:
    return _BIND in text


_INIT_MARK = "# xampp-panel: one-time root password reset (removed right after)\n"
_INIT_LINE = re.compile(r"(?m)^" + re.escape(_INIT_MARK) + r"init-file=(.*)\n?")
# Only a plain absolute path: no spaces, newlines or '#' that could break or extend the option file.
_INIT_PATH = re.compile(r"/[A-Za-z0-9_./-]+")


def mysql_init_file(text: str, path: str | None) -> str:
    """path: put the one-time `init-file=` line (MariaDB runs that SQL file once at startup) under
    [mysqld], replacing an earlier one; None: remove it. Lines the panel did not write are kept."""
    text = _INIT_LINE.sub("", text)
    if path is None:
        return text
    if not _INIT_PATH.fullmatch(path):
        raise ValueError(f"unsafe init-file path: {path!r}")
    line = f"{_INIT_MARK}init-file={path}\n"
    new, count = _MYSQLD.subn(lambda m: m[0] + line, text, count=1)
    if count:
        return new
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}[mysqld]\n{line}"


def mysql_init_file_path(text: str) -> str | None:
    """The file named by the panel's one-time init-file line, if one is there."""
    m = _INIT_LINE.search(text)
    return m[1] if m else None


# "lampp security" pastes the PHP meant to compute the FTP password hash into proftpd.conf.
_PROFTPD_BROKEN = re.compile(r"(?ms)^UserPassword[ \t]+daemon[ \t]+<\?.*?^\?>[ \t]*$\n?")
_PROFTPD_PASSWORD = re.compile(r"(?m)^UserPassword[ \t]+daemon[ \t]+.*$\n?")
_SHA512_CRYPT = re.compile(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}")


def proftpd_password_broken(text: str) -> bool:
    return bool(_PROFTPD_BROKEN.search(text))


def proftpd_set_password(text: str, hashed: str) -> str:
    """Set the FTP user daemon's password hash, replacing a broken block or an old line."""
    if not _SHA512_CRYPT.fullmatch(hashed):
        raise ValueError("not a SHA-512 crypt hash")
    line = f"UserPassword daemon {hashed}\n"
    for pattern in (_PROFTPD_BROKEN, _PROFTPD_PASSWORD):
        new, count = pattern.subn(lambda m: line, text, count=1)
        if count:
            return new
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line


PROFTPD_LOCAL = "DefaultAddress 127.0.0.1\nSocketBindTight on"

LEAN_HTTPD = """\
# XAMPP Panel lean mode: few idle processes, plenty for local development.
<IfModule mpm_prefork_module>
    StartServers 2
    MinSpareServers 1
    MaxSpareServers 3
    MaxRequestWorkers 20
    MaxConnectionsPerChild 1000
</IfModule>
"""

LEAN_MYSQL = """\
# XAMPP Panel lean mode: smaller buffers for a single developer.
[mysqld]
innodb_buffer_pool_size=16M
max_connections=30
"""

_VHOST = """
<VirtualHost *:80>
    ServerName {name}.local
    DocumentRoot "{path}"
    <Directory "{path}">
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require local
    </Directory>
</VirtualHost>
"""


def render_vhosts(sites, htdocs: Path) -> str:
    header = (
        "# Managed by XAMPP Panel. Changes here are overwritten.\n"
        "# The first vhost keeps http://localhost (and phpMyAdmin) working.\n"
        "<VirtualHost *:80>\n"
        "    ServerName localhost\n"
        f'    DocumentRoot "{htdocs}"\n'
        "</VirtualHost>\n"
    )
    return header + "".join(_VHOST.format(name=s.name, path=s.path) for s in sites)


def render_hosts(sites) -> str | None:
    return "\n".join(f"127.0.0.1\t{s.name}.local" for s in sites) or None
