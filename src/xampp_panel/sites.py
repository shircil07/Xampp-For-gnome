"""Per-project sites (name.local → folder) and their root-owned state file."""

import json
import re
from dataclasses import asdict, dataclass

from . import fsutil

_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
# Characters that could break out of an Apache config string, trigger ${VAR}
# expansion, or act as wildcards in an Apache <Directory> block.
UNSAFE_PATH_CHARS = frozenset('"$\\\n\r\t*?[]')


@dataclass(frozen=True)
class Site:
    name: str
    path: str
    uid: int

    @property
    def url(self) -> str:
        return f"http://{self.name}.local/"


def validate_name(name: str) -> bool:
    return bool(_NAME.fullmatch(name))


def load(state_file) -> list[Site]:
    try:
        with open(state_file, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return []
    return [Site(str(d["name"]), str(d["path"]), int(d["uid"])) for d in raw]


def save(state_file, sites: list[Site]) -> None:
    fsutil.atomic_write(state_file, json.dumps([asdict(s) for s in sites], indent=2) + "\n", mode=0o644)
