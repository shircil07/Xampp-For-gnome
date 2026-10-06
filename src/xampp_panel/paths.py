"""Every filesystem location the app touches, in one overridable place."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    lampp: Path = Path("/opt/lampp")
    app: Path = Path("/opt/xampp-panel")
    hosts: Path = Path("/etc/hosts")
    proc: Path = Path("/proc")

    @property
    def lampp_script(self) -> Path:
        return self.lampp / "lampp"

    @property
    def httpd_conf(self) -> Path:
        return self.lampp / "etc/httpd.conf"

    @property
    def ssl_conf(self) -> Path:
        return self.lampp / "etc/extra/httpd-ssl.conf"

    @property
    def my_cnf(self) -> Path:
        return self.lampp / "etc/my.cnf"

    @property
    def proftpd_conf(self) -> Path:
        return self.lampp / "etc/proftpd.conf"

    @property
    def vhosts_conf(self) -> Path:
        return self.lampp / "etc/extra/xampp-panel-vhosts.conf"

    @property
    def lean_httpd(self) -> Path:
        return self.lampp / "etc/extra/xampp-panel-lean.conf"

    @property
    def lean_mysql(self) -> Path:
        return self.lampp / "etc/xampp-panel-lean.cnf"

    @property
    def htdocs(self) -> Path:
        return self.lampp / "htdocs"

    @property
    def apachectl(self) -> Path:
        return self.lampp / "bin/apachectl"

    @property
    def mysql_client(self) -> Path:
        return self.lampp / "bin/mysql"

    @property
    def mysql_upgrade(self) -> Path:
        return self.lampp / "bin/mysql_upgrade"

    @property
    def proftpd_bin(self) -> Path:
        return self.lampp / "sbin/proftpd"

    @property
    def phpmyadmin_conf(self) -> Path:
        return self.lampp / "phpmyadmin/config.inc.php"

    @property
    def pma_tables_sql(self) -> Path:
        return self.lampp / "phpmyadmin/sql/create_tables.sql"

    @property
    def helper(self) -> Path:
        return self.app / "bin/xampp-helper"

    @property
    def launcher(self) -> Path:
        return self.app / "bin/xampp-panel"

    @property
    def repair(self) -> Path:
        return self.app / "bin/xampp-repair"

    @property
    def state_file(self) -> Path:
        return self.app / "state/sites.json"

    @property
    def watch_dirs(self) -> tuple[Path, ...]:
        """Directories whose PID/socket files change when services start/stop."""
        return (self.lampp / "logs", self.lampp / "var", self.lampp / "var/mysql")


DEFAULT = Paths()
