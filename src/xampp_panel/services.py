"""Which XAMPP services are running, read cheaply from /proc (no subprocesses, no root)."""

import os
import socket
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .paths import DEFAULT, Paths


class State(Enum):
    STOPPED = "stopped"
    STARTING = "starting"   # XAMPP process exists, port not listening yet
    RUNNING = "running"
    CONFLICT = "conflict"   # port is taken by a program that is not XAMPP


@dataclass(frozen=True)
class Service:
    key: str
    title: str
    description: str
    port: int
    process_names: tuple[str, ...]


SERVICES = (
    Service("apache", "Apache", "Web server", 80, ("httpd",)),
    Service("mysql", "MySQL", "Database (MariaDB)", 3306, ("mysqld", "mariadbd")),
    Service("ftp", "ProFTPD", "FTP server", 21, ("proftpd",)),
)
BY_KEY = {s.key: s for s in SERVICES}
_BY_PROCESS = {name: s for s in SERVICES for name in s.process_names}
_LISTEN = "0A"


def listening_ports(paths: Paths = DEFAULT) -> set[int]:
    ports = set()
    for name in ("tcp", "tcp6"):
        try:
            lines = (paths.proc / "net" / name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[3] == _LISTEN:
                ports.add(int(parts[1].rsplit(":", 1)[1], 16))
    return ports


def running_services(paths: Paths = DEFAULT) -> set[str]:
    """Keys of services with a live XAMPP process.

    ProFTPD rewrites its command line ("proftpd: (accepting connections)"), so
    it is matched on process name alone; the others must mention /opt/lampp.
    """
    found: set[str] = set()
    marker = str(paths.lampp).encode()
    try:
        entries = os.scandir(paths.proc)
    except OSError:
        return found
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            base = Path(entry.path)
            try:
                svc = _BY_PROCESS.get((base / "comm").read_text().strip())
                if svc is None or svc.key in found:
                    continue
                if svc.key != "ftp" and marker not in (base / "cmdline").read_bytes():
                    continue
            except OSError:
                continue  # process exited while we looked
            found.add(svc.key)
    return found


def snapshot(paths: Paths = DEFAULT) -> dict[str, State]:
    running = running_services(paths)
    ports = listening_ports(paths)
    result = {}
    for svc in SERVICES:
        if svc.key in running:
            result[svc.key] = State.RUNNING if svc.port in ports else State.STARTING
        else:
            result[svc.key] = State.CONFLICT if svc.port in ports else State.STOPPED
    return result


def log_path(key: str, paths: Paths = DEFAULT, hostname: str | None = None) -> Path | None:
    if key == "apache":
        return paths.lampp / "logs/error_log"
    if key == "mysql":
        return paths.lampp / "var/mysql" / f"{hostname or socket.gethostname()}.err"
    return None
