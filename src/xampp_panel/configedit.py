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


def mysql_localhost(text: str, on: bool) -> str:
    text = text.replace(_BIND, "")
    if not on:
        return text
    new, count = _MYSQLD.subn(lambda m: m[0] + _BIND, text, count=1)
    if count:
        return new
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}[mysqld]\n{_BIND}"


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
