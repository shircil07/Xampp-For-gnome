# Update Menu, Startup Check and Restore Button — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sudo xampp-update` (phpMyAdmin first), a background update check with a panel bar, and a **Restore previous version** button, so a user whose own code breaks under an updated component can go back quickly.

**Architecture:** A new `xampp_panel/updates/` package holds all logic as small, GTK-free, unit-tested modules (versions, HTTPS transport, verified downloads, link-safe unpacking, PGP check, snapshots/restore points, the phpMyAdmin component, the cached check, the menu). The panel only draws two bars and opens `sudo xampp-update [--restore]` in a terminal, so the root helper's whitelist does not grow. Phases 2 (MariaDB) and 3 (XAMPP) get their own plans after this phase is reviewed and the open probe items in the spec are answered on the target machine.

**Tech Stack:** Python ≥ 3.10 standard library only, whiptail, GTK4/libadwaita (panel only), bash (`setup.sh`), `gpg` (signature check), stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-08-update-menu-design.md`

## Global Constraints

- Python ≥ 3.10, standard library only. No new pip dependencies. Match the surrounding code: short module docstring, comments only where the *why* is not obvious, type hints on public functions.
- Run the whole suite with: `PYTHONPATH=src python3 -m unittest discover -s tests` (must say OK). Tests never touch the real `/opt`, `/etc`, `/var/backups`, the network, `gpg`'s real keyrings, sudo or MySQL: use `Paths(...)` overrides (always pass `backups=`) and fakes.
- Everything that runs as root starts from `/opt/xampp-panel/lib` with `python3 -I`. Subprocesses use argument lists, never a shell.
- Network: HTTPS only (redirects too), TLS 1.2+, size and time caps. A download is **verified before it is unpacked or used**; version strings must match the strict ASCII pattern `\d{1,3}(\.\d{1,3}){1,3}` before they reach a URL or path.
- Snapshots live in `/var/backups/xampp-panel` (root, 0700), never under `/opt/xampp-panel` (`uninstall.sh` deletes that folder). The public list is `/opt/xampp-panel/state/restore-points.json` (0644, no secrets).
- Commits: `git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit ...`. **No** `Co-Authored-By` and no AI attribution in commits or PRs. Never push, never change git identity, never rewrite history.
- Nothing here has been run against a real XAMPP, as root, or with a desktop session: every doc and report must say what was and was not verified.
- Docs follow the project's existing split (README, `docs/USER-GUIDE.md`, `docs/MAINTAINER.md`); update them in the same phase as the code.
- The standing review rule applies at the end (Task 12): parallel review agents for security, dead code/correctness and efficiency; verify every finding against the code; report by severity; fix what the owner approves; a fresh agent reviews the fixes.

## File Structure

| File | Responsibility |
|---|---|
| `src/xampp_panel/updates/config.py` (new) | `UpdateConfig`: every URL, limit, timeout and the pinned PGP fingerprints, injectable |
| `src/xampp_panel/updates/base.py` (new) | `Release`, `Plan`, `Component` protocol, `UpdateError`, `RollbackFailed`, `critical_section` |
| `src/xampp_panel/updates/versions.py` (new) | Strict version parsing, ordering, "installed + newest N" list |
| `src/xampp_panel/updates/http.py`, `releases.py` (new) | HTTPS-only opener; capped `Transport`; `PhpMyAdminSource` |
| `src/xampp_panel/updates/fetcher.py`, `archive.py`, `fsops.py` (new) | Verified resumable download; link-safe unpacking; race-safe owner-preserving copy |
| `src/xampp_panel/updates/gpg.py` (new) | Detached-signature check against pinned fingerprints |
| `src/xampp_panel/updates/restore_points.py`, `snapshots.py` (new) | Public restore-points file; snapshot store with pending/ready states |
| `src/xampp_panel/updates/pma.py` (new) | The phpMyAdmin component: install, rollback, restore, leftovers |
| `src/xampp_panel/updates/check.py`, `panelstate.py` (new) | Cached background check; what the panel's two bars say |
| `src/xampp_panel/updates/app.py` (new), `bin/xampp-update` (new) | The whiptail menu, `--check`, `--restore`, launcher |
| `src/xampp_panel/paths.py`, `settings.py`, `dialogs.py`, `terminal.py` (modify) | New locations; dismissal maps; dialog title; terminal command builders |
| `src/xampp_panel/window.py` (modify) | Update bar, restore bar, two ☰ items |
| `setup.sh`, `uninstall.sh` (modify) | Install/remove the launcher; `gnupg`; cache clean-up |
| `tests/test_update_*.py`, `tests/update_fakes.py` (new); `tests/fakes.py`, `test_paths.py`, `test_settings.py`, `test_dialogs.py`, `test_terminal.py`, `test_scripts.py` (modify) | Unit tests and shared fakes |
| `README.md`, `docs/USER-GUIDE.md`, `docs/MAINTAINER.md` (modify) | Handover-grade documentation |

Baseline before this plan: **259 tests, OK**. After Task 10: **597 tests, OK** (1 skipped, the GTK import test, on machines without GTK 4).

---

### Task 1: Package scaffold, configuration, shared types and version handling

Create the `xampp_panel/updates` package with the injectable `UpdateConfig`, the types every component shares, and strict version parsing/ordering (the "installed + 5 newest" list).

**Human checkpoint (security).** `UpdateConfig.pma_signers` holds the three phpMyAdmin release-signer fingerprints read from phpMyAdmin's own keyring on 2026-10-08. Before committing this task, show the project owner these three lines and ask them to compare each against phpMyAdmin's published verification instructions (https://www.phpmyadmin.net/downloads/ → "Verify its PGP signature"), and **stop until they confirm**:

```
63CB1DF1EF12CF2AC0EE5A329C27B31342B7511D  Michal Čihař
436FF1884B1A0C3FDCBF0D79FEFC65D181AF644A  Marc Delisle
3D06A59ECE730EB71B511C17CE752F178259BD92  Isaac Bennetch (signed 5.2.3)
```

These are the only keys whose signatures the tool will ever trust.

**Files:**
- Create: `src/xampp_panel/updates/__init__.py`
- Create: `src/xampp_panel/updates/config.py`
- Create: `src/xampp_panel/updates/base.py`
- Create: `src/xampp_panel/updates/versions.py`
- Create: `tests/test_update_config.py`
- Create: `tests/test_update_base.py`
- Create: `tests/test_update_versions.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `UpdateConfig` (frozen dataclass, `PMA_SIGNERS`); `UpdateError`, `RollbackFailed(UpdateError)`; `Release(version, url, series=None, date=None, signature_url=None, hash_url=None, hashes={}, notes=())`; `Plan(kind, summary, warnings=())`; `Component` protocol (`key`, `title`, `installed()`, `releases()`, `plan(target)`, `apply(target) -> str`, `restore_note(snapshot) -> str`, `restore() -> str`); `critical_section()`; `versions.is_valid/parse/satisfies/newest_first/pick`, `versions.Entry(version, release, tags)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_config.py`:

`````python
import dataclasses
import unittest

from xampp_panel.updates.config import PMA_SIGNERS, UpdateConfig


class UpdateConfigTest(unittest.TestCase):
    def test_defaults_match_the_design(self):
        config = UpdateConfig()
        self.assertEqual(config.count, 5)
        self.assertEqual(config.check_throttle_seconds, 24 * 3600)
        self.assertEqual(config.cache_max_age_seconds, 7 * 24 * 3600)
        self.assertEqual(config.restore_bar_days, 7)
        self.assertTrue(config.pma_files_url.startswith("https://"))
        self.assertTrue(config.pma_download_base.startswith("https://"))
        self.assertTrue(config.pma_keyring_url.startswith("https://"))

    def test_is_frozen_and_overridable(self):
        config = UpdateConfig(count=3)
        self.assertEqual(config.count, 3)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.count = 9

    def test_phpmyadmin_signers_are_full_fingerprints(self):
        self.assertEqual(len(PMA_SIGNERS), 3)
        for fingerprint in PMA_SIGNERS:
            self.assertRegex(fingerprint, r"^[0-9A-F]{40}$")
        self.assertIn("3D06A59ECE730EB71B511C17CE752F178259BD92", UpdateConfig().pma_signers)

    def test_config_file_is_always_kept_across_a_swap(self):
        self.assertIn("config.inc.php", UpdateConfig().pma_keep)
`````

Create `tests/test_update_base.py`:

`````python
import signal
import unittest

from xampp_panel.updates.base import Plan, Release, RollbackFailed, UpdateError, critical_section


class BaseTypesTest(unittest.TestCase):
    def test_release_defaults(self):
        release = Release("5.2.3", "https://example.org/x")
        self.assertEqual(release.hashes, {})
        self.assertEqual(release.notes, ())
        self.assertIsNone(release.signature_url)

    def test_plan_defaults(self):
        self.assertEqual(Plan("upgrade", ("a",)).warnings, ())

    def test_update_error_carries_a_message(self):
        self.assertEqual(str(UpdateError("nope")), "nope")

    def test_rollback_failure_is_an_update_error(self):
        self.assertTrue(issubclass(RollbackFailed, UpdateError))


class CriticalSectionTest(unittest.TestCase):
    def test_blocks_signals_inside_and_restores_the_mask(self):
        before = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        with critical_section():
            blocked = signal.pthread_sigmask(signal.SIG_BLOCK, set())
            self.assertTrue({signal.SIGINT, signal.SIGHUP, signal.SIGTERM} <= blocked)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), before)

    def test_restores_the_mask_after_an_error(self):
        before = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        with self.assertRaises(RuntimeError):
            with critical_section():
                raise RuntimeError("boom")
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), before)
`````

Create `tests/test_update_versions.py`:

`````python
import unittest

from xampp_panel.updates import versions
from xampp_panel.updates.base import Release


def rel(version, notes=()):
    return Release(version, f"https://example.org/{version}", notes=notes)


class ParseTest(unittest.TestCase):
    def test_valid_versions(self):
        self.assertEqual(versions.parse("5.2.3"), (5, 2, 3))
        self.assertEqual(versions.parse("4.9.0.1"), (4, 9, 0, 1))
        self.assertEqual(versions.parse("8.2"), (8, 2))

    def test_rejects_anything_else(self):
        for bad in ("", "5", "5.2.0-rc1", "5.2.3\n", "5.2.3 ", "v5.2.3", "5..3", "1234.1", "5.2.3.4.5",
                    "../5.2", "5.2;rm", None, 5.2):
            self.assertFalse(versions.is_valid(bad), repr(bad))
            with self.assertRaises(ValueError):
                versions.parse(bad)

    def test_numeric_not_text_ordering(self):
        self.assertGreater(versions.parse("5.10.0"), versions.parse("5.9.9"))


class SatisfiesTest(unittest.TestCase):
    def test_php_ranges_from_phpmyadmin(self):
        self.assertTrue(versions.satisfies("8.2.12", ">=7.2,<8.4"))
        self.assertFalse(versions.satisfies("8.4.1", ">=7.2,<8.4"))
        self.assertFalse(versions.satisfies("7.1.33", ">=7.2,<8.4"))
        self.assertTrue(versions.satisfies("7.4.33", ">=5.5,<8.0"))
        self.assertFalse(versions.satisfies("8.0.30", ">=5.5,<8.0"))

    def test_single_constraints(self):
        self.assertTrue(versions.satisfies("8.2.1", ">=8.2"))
        self.assertTrue(versions.satisfies("8.2.1", "==8.2"))
        self.assertFalse(versions.satisfies("8.3.0", "<=8.2"))

    def test_unsupported_constraint(self):
        for bad in ("~8.2", "", ">=", ">=x.y"):
            with self.assertRaises(ValueError):
                versions.satisfies("8.2.1", bad)


class NewestFirstTest(unittest.TestCase):
    def test_sorts_numerically_and_drops_duplicates(self):
        out = versions.newest_first([rel("5.2.1"), rel("5.10.0"), rel("5.2.3"), rel("5.2.1")])
        self.assertEqual([r.version for r in out], ["5.10.0", "5.2.3", "5.2.1"])

    def test_custom_key(self):
        a = Release("1.0", "https://x/a", date="2026-01-01")
        b = Release("2.0", "https://x/b", date="2025-01-01")
        out = versions.newest_first([a, b], key=lambda r: r.date)
        self.assertEqual([r.version for r in out], ["1.0", "2.0"])


class PickTest(unittest.TestCase):
    RELEASES = [rel(v) for v in ("5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4", "5.1.3", "5.0.4")]

    def test_installed_inside_the_newest_five_is_marked_in_place(self):
        entries = versions.pick(self.RELEASES, "5.2.1", 5)
        self.assertEqual([e.version for e in entries], ["5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4"])
        self.assertEqual([e.tags for e in entries],
                         [("newer",), ("newer",), ("installed",), ("older",), ("older",)])

    def test_installed_outside_the_newest_five_is_added_last(self):
        entries = versions.pick(self.RELEASES, "5.0.4", 3)
        self.assertEqual([e.version for e in entries], ["5.2.3", "5.2.2", "5.2.1", "5.0.4"])
        self.assertIsNone(entries[-1].release)
        self.assertEqual(entries[-1].tags, ("installed",))

    def test_unknown_installed_version_gives_no_relation_tags(self):
        entries = versions.pick(self.RELEASES, None, 2)
        self.assertEqual([e.tags for e in entries], [(), ()])
        entries = versions.pick(self.RELEASES, "garbage", 2)
        self.assertEqual([e.tags for e in entries], [(), ()])

    def test_release_notes_become_tags(self):
        entries = versions.pick([rel("5.2.3", notes=("major upgrade",))], "5.2.1", 5)
        self.assertEqual(entries[0].tags, ("newer", "major upgrade"))

    def test_fewer_releases_than_count(self):
        self.assertEqual(len(versions.pick(self.RELEASES[:2], "5.2.3", 5)), 2)

    def test_entries_keep_their_release_for_installing(self):
        entry = versions.pick(self.RELEASES, "5.2.1", 5)[0]
        self.assertEqual(entry.release.url, "https://example.org/5.2.3")


class AsciiOnlyTest(unittest.TestCase):
    def test_non_ascii_digits_are_not_version_numbers(self):
        for bad in ("5.\u0662.3", "\u0665.2.3", "5.2.\u0663"):  # Arabic-Indic digits
            self.assertFalse(versions.is_valid(bad), bad)

    def test_constraints_are_ascii_only_too(self):
        with self.assertRaises(ValueError):
            versions.satisfies("8.2.1", ">=\u0667.2")
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"`

Expected: FAIL — ImportError: Failed to import test module: test_update_base (FAILED (errors=3)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/__init__.py`:

`````python
"""Updates for phpMyAdmin, MariaDB and XAMPP: versions, downloads, snapshots, restore points.

Design: docs/superpowers/specs/2026-10-08-update-menu-design.md
"""
`````

Create `src/xampp_panel/updates/config.py`:

`````python
"""Every tunable of the update tool in one injectable place (like Paths)."""

from dataclasses import dataclass

# Primary-key fingerprints allowed to sign phpMyAdmin releases. The published keyring is only key
# material: trust comes from this list, checked against gpg's VALIDSIG line.
PMA_SIGNERS = (
    "63CB1DF1EF12CF2AC0EE5A329C27B31342B7511D",  # Michal Čihař
    "436FF1884B1A0C3FDCBF0D79FEFC65D181AF644A",  # Marc Delisle
    "3D06A59ECE730EB71B511C17CE752F178259BD92",  # Isaac Bennetch
)


@dataclass(frozen=True)
class UpdateConfig:
    count: int = 5  # versions listed besides the installed one
    # SourceForge refuses unknown clients, so every request looks like a normal browser.
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 xampp-panel-update"
    http_timeout: float = 10.0  # seconds for a list request
    stall_timeout: float = 30.0  # seconds without a byte during a download
    check_budget: float = 30.0  # seconds for the whole background check
    request_deadline: float = 30.0  # seconds for one whole list request, however slowly it trickles in
    max_response_bytes: int = 2_000_000  # list pages; phpMyAdmin's file list is about 260 KB
    max_download_bytes: int = 200_000_000
    download_attempts: int = 3
    download_min_seconds: float = 120.0  # a download may take at least this long ...
    download_min_bytes_per_second: int = 50_000  # ... and up to size / this speed
    check_throttle_seconds: int = 86_400  # the background check runs at most once a day
    cache_max_age_seconds: int = 7 * 86_400  # an older check result is ignored
    restore_bar_days: int = 7  # how long the panel offers "Restore previous version" after an update
    archive_max_entries: int = 200_000
    archive_max_bytes: int = 1_500_000_000
    pma_min_free_bytes: int = 300_000_000
    pma_files_url: str = "https://www.phpmyadmin.net/files/"
    pma_version_json_url: str = "https://www.phpmyadmin.net/home_page/version.json"
    pma_download_base: str = "https://files.phpmyadmin.net/phpMyAdmin"
    pma_keyring_url: str = "https://files.phpmyadmin.net/phpmyadmin.keyring"
    pma_signers: tuple[str, ...] = PMA_SIGNERS
    # Carried from the old phpMyAdmin folder into the new one (owner and mode kept).
    pma_keep: tuple[str, ...] = ("config.inc.php", "config.inc.php.xampp-panel.bak", "tmp")
    local_probe_url: str = "http://127.0.0.1/phpmyadmin/"
    local_probe_timeout: float = 10.0
`````

Create `src/xampp_panel/updates/base.py`:

`````python
"""Types shared by the update components."""

import contextlib
import signal
from dataclasses import dataclass, field
from typing import Mapping, Protocol


class UpdateError(Exception):
    """A failure with a message meant for the user."""


class RollbackFailed(UpdateError):
    """Going back after a failed update did not work either; the message says how to restore by hand.

    The snapshot is kept, so "Restore previous version" can still be tried.
    """


@dataclass(frozen=True)
class Release:
    """One installable version of a component."""
    version: str
    url: str
    series: str | None = None
    date: str | None = None
    signature_url: str | None = None
    hash_url: str | None = None
    hashes: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()  # shown as tags in the version list, e.g. "major upgrade"


@dataclass(frozen=True)
class Plan:
    """What choosing a release will do, for the confirmation screen."""
    kind: str  # "upgrade", "downgrade" or "reinstall"
    summary: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class Component(Protocol):
    key: str
    title: str

    def installed(self) -> str | None: ...

    def releases(self) -> list[Release]:
        """Every offered release, newest first."""

    def plan(self, target: Release) -> Plan: ...

    def apply(self, target: Release) -> str:
        """Install `target`. Returns a message for the user; raises UpdateError after rolling back."""

    def restore_note(self, snapshot) -> str: ...

    def restore(self) -> str:
        """Go back to the saved version. Returns a message for the user."""


_CRITICAL = {signal.SIGINT, signal.SIGHUP, signal.SIGTERM}


@contextlib.contextmanager
def critical_section():
    """Hold Ctrl-C, hang-up and terminate until a half-done swap is finished; they arrive afterwards."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, _CRITICAL)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
`````

Create `src/xampp_panel/updates/versions.py`:

`````python
"""Version strings: strict parsing, ordering and the "installed + newest N" list."""

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from .base import Release

_VERSION = re.compile(r"\d{1,3}(\.\d{1,3}){1,3}", re.ASCII)  # so "5.2.0-rc1", "5.2.3\n" or Arabic digits never pass
_CONSTRAINT = re.compile(r"(>=|<=|==|>|<)(\d{1,3}\.\d{1,3})(?:\.\d{1,3})*", re.ASCII)


def is_valid(text) -> bool:
    return isinstance(text, str) and _VERSION.fullmatch(text) is not None


def parse(text: str) -> tuple[int, ...]:
    if not is_valid(text):
        raise ValueError(f"not a version number: {text!r}")
    return tuple(int(part) for part in text.split("."))


def satisfies(version: str, spec: str) -> bool:
    """True if `version` meets a constraint list like ">=7.2,<8.4" (compared on major.minor)."""
    have = parse(version)[:2]
    for part in spec.split(","):
        match = _CONSTRAINT.fullmatch(part.strip())
        if match is None:
            raise ValueError(f"unsupported constraint: {part!r}")
        want = tuple(int(number) for number in match.group(2).split("."))
        holds = {">=": have >= want, "<=": have <= want, "==": have == want,
                 ">": have > want, "<": have < want}[match.group(1)]
        if not holds:
            return False
    return True


@dataclass(frozen=True)
class Entry:
    """One line of a version list."""
    version: str
    release: Release | None  # None: the installed version, which is not among the offered releases
    tags: tuple[str, ...]


def newest_first(releases: Iterable[Release], key: Callable[[Release], object] | None = None) -> list[Release]:
    key = key or (lambda release: parse(release.version))
    seen: set[str] = set()
    ordered = []
    for release in sorted(releases, key=key, reverse=True):
        if release.version not in seen:
            seen.add(release.version)
            ordered.append(release)
    return ordered


def _relation(version: str, installed: tuple[int, ...] | None) -> tuple[str, ...]:
    if installed is None:
        return ()
    have = parse(version)
    if have == installed:
        return ("installed",)
    return ("newer",) if have > installed else ("older",)


def pick(releases: Iterable[Release], installed: str | None, count: int,
         key: Callable[[Release], object] | None = None) -> list[Entry]:
    """The `count` newest releases, newest first, each tagged against the installed version.

    The installed version is always shown: in place if it is among them, otherwise as the last line.
    """
    have = parse(installed) if is_valid(installed) else None
    entries = [Entry(release.version, release, (*_relation(release.version, have), *release.notes))
               for release in newest_first(releases, key)[:count]]
    if have is not None and not any("installed" in entry.tags for entry in entries):
        entries.append(Entry(installed, None, ("installed",)))
    return entries
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"` — Expected: `Ran 26 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 285 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/test_update_config.py tests/test_update_base.py tests/test_update_versions.py src/xampp_panel/updates/__init__.py src/xampp_panel/updates/config.py src/xampp_panel/updates/base.py src/xampp_panel/updates/versions.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: update package with config, shared types and strict version handling"
`````

---

### Task 2: HTTPS-only transport and the phpMyAdmin release source

Add an HTTPS-only opener (no plain http/ftp/file handlers, redirects must stay HTTPS), a capped `Transport` with an overall deadline, and `PhpMyAdminSource` that lists stable releases and reads checksums, the keyring and PHP ranges.

`tests/update_fakes.py` is a shared helper module, not a test file; the tests import it as `from update_fakes import ...` (the `tests` folder is on the path when run with `discover -s tests`).

**Files:**
- Create: `src/xampp_panel/updates/http.py`
- Create: `src/xampp_panel/updates/releases.py`
- Create: `tests/update_fakes.py`
- Create: `tests/test_update_http.py`
- Create: `tests/test_update_releases.py`

**Interfaces:**
- Consumes: Task 1: `UpdateConfig`, `UpdateError`, `Release`, `versions.is_valid`.
- Produces: `http.require_https(url)`, `http.make_opener()`, `http.build_request(url, user_agent, headers=None)`; `releases.Transport(config, opener=None, clock=time.monotonic)` with `get/get_text/get_json`; `releases.PhpMyAdminSource(transport, config)` with `releases()`, `sha256_for(release)`, `keyring()`, `php_range(version)`. Test helpers in `tests/update_fakes.py`: `FakeResponse`, `FakeOpener`, `FakeTransport`, `http_error`, `build_tar`.

- [ ] **Step 1: Write the failing tests**

Create `tests/update_fakes.py`:

`````python
"""Fakes shared by the update tests (network, download and sleep never really happen)."""

import io
import tarfile
import urllib.error


class FakeResponse:
    def __init__(self, body: bytes = b"", status: int = 200, headers: dict | None = None):
        self._body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Answers by URL: a FakeResponse, bytes, or an exception to raise. A list is used one entry per call."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request.full_url, dict(request.header_items()), timeout))
        answer = self.answers[request.full_url]
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, bytes):
            return FakeResponse(answer)
        return answer


class FakeTransport:
    """Transport stand-in: {url: bytes | object (for get_json) | exception}."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.requested = []

    def _answer(self, url):
        self.requested.append(url)
        answer = self.answers[url]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def get(self, url, max_bytes=None):
        answer = self._answer(url)
        return answer if isinstance(answer, bytes) else answer.encode()

    def get_text(self, url, max_bytes=None):
        return self.get(url, max_bytes).decode()

    def get_json(self, url, max_bytes=None):
        import json
        answer = self._answer(url)
        return json.loads(answer) if isinstance(answer, (bytes, str)) else answer


def http_error(code: int, url: str = "https://example.org/x") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", {}, None)


def build_tar(members, mode="w:xz"):
    """members: [(name, kind, payload, file_mode)] with kind one of dir/file/sym/hard/dev/fifo."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        for name, kind, payload, file_mode in members:
            info = tarfile.TarInfo(name)
            info.mode = file_mode
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "file":
                data = payload.encode() if isinstance(payload, str) else payload
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif kind == "sym":
                info.type, info.linkname = tarfile.SYMTYPE, payload
                tar.addfile(info)
            elif kind == "hard":
                info.type, info.linkname = tarfile.LNKTYPE, payload
                tar.addfile(info)
            elif kind == "dev":
                info.type = tarfile.CHRTYPE
                tar.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)
    return buffer.getvalue()
`````

Create `tests/test_update_http.py`:

`````python
import unittest
import urllib.error
import urllib.request

from xampp_panel.updates import http
from xampp_panel.updates.base import UpdateError


class RequireHttpsTest(unittest.TestCase):
    def test_https_passes_through(self):
        self.assertEqual(http.require_https("https://files.phpmyadmin.net/x"), "https://files.phpmyadmin.net/x")

    def test_everything_else_is_refused(self):
        for bad in ("http://example.org/x", "ftp://example.org/x", "file:///etc/passwd", "//example.org/x",
                    "HTTPS://example.org/x", "", None):
            with self.assertRaises(UpdateError, msg=repr(bad)):
                http.require_https(bad)


class RedirectTest(unittest.TestCase):
    def setUp(self):
        self.handler = http._HttpsOnlyRedirects()
        self.request = urllib.request.Request("https://example.org/a")

    def test_https_redirect_is_followed(self):
        new = self.handler.redirect_request(self.request, None, 302, "Found", {}, "https://mirror.example.org/a")
        self.assertEqual(new.full_url, "https://mirror.example.org/a")

    def test_redirect_to_plain_http_is_refused(self):
        with self.assertRaises(UpdateError):
            self.handler.redirect_request(self.request, None, 302, "Found", {}, "http://evil.example.org/a")

    def test_redirect_to_a_file_is_refused(self):
        with self.assertRaises(UpdateError):
            self.handler.redirect_request(self.request, None, 302, "Found", {}, "file:///etc/shadow")


class BuildRequestTest(unittest.TestCase):
    def test_sets_user_agent_and_extra_headers(self):
        request = http.build_request("https://example.org/x", "agent/1", {"Range": "bytes=5-"})
        self.assertEqual(request.get_header("User-agent"), "agent/1")
        self.assertEqual(request.get_header("Range"), "bytes=5-")

    def test_refuses_plain_http(self):
        with self.assertRaises(UpdateError):
            http.build_request("http://example.org/x", "agent/1")

    def test_make_opener_has_the_https_only_redirect_handler(self):
        opener = http.make_opener()
        self.assertTrue(any(isinstance(h, http._HttpsOnlyRedirects) for h in opener.handlers))

class OpenerHasNoPlainHandlersTest(unittest.TestCase):
    def test_only_https_can_be_opened(self):
        opener = http.make_opener()
        names = {type(handler).__name__ for handler in opener.handlers}
        for forbidden in ("HTTPHandler", "FTPHandler", "FileHandler", "DataHandler"):
            self.assertNotIn(forbidden, names)
        for url in ("http://example.org/", "file:///etc/hostname", "ftp://example.org/"):
            with self.assertRaises(urllib.error.URLError, msg=url):
                opener.open(url)
`````

Create `tests/test_update_releases.py`:

`````python
import http.client
import json
import unittest

from xampp_panel.updates.base import Release, UpdateError
from xampp_panel.updates.config import UpdateConfig
from xampp_panel.updates.releases import PhpMyAdminSource, Transport

from update_fakes import FakeOpener, FakeResponse, FakeTransport, http_error

# Trimmed from https://www.phpmyadmin.net/files/ as fetched on 2026-10-08 (same row structure).
FILES_PAGE = """
<table><thead><tr><th>Version</th></tr></thead><tbody>
<tr>
  <th scope="row">
    <a href="/files/5.2.3/">5.2.3</a>
  </th>
  <td><time datetime="2025-10-08T04:04:14+00:00">October 8, 2025</time></td>
  <td><a href="https://files.phpmyadmin.net/phpMyAdmin/5.2.3/phpMyAdmin-5.2.3-all-languages.zip" data-sha256="2d2e">zip</a></td>
</tr>
<tr><th scope="row"><a href="/files/5.2.2/">5.2.2</a></th></tr>
<tr><th scope="row"><a href="/files/5.2.1/">5.2.1</a></th></tr>
<tr><th scope="row"><a href="/files/5.2.0/">5.2.0</a></th></tr>
<tr><th scope="row"><a href="/files/5.2.0-rc1/">5.2.0-rc1</a></th></tr>
<tr><th scope="row"><a href="/files/5.1.4/">5.1.4</a></th></tr>
<tr><th scope="row"><a href="/files/4.9.0.1/">4.9.0.1</a></th></tr>
<tr><th scope="row"><a href="/files/5.2.3/">5.2.3 again</a></th></tr>
<tr><th scope="row"><a href="/files/../etc/">decoy</a></th></tr>
<tr><th scope="row"><a href="/files/5.0.0-alpha1/">5.0.0-alpha1</a></th></tr>
</tbody></table>
"""

# Shape of https://www.phpmyadmin.net/home_page/version.json as fetched on 2026-10-08.
VERSION_JSON = json.dumps({
    "version": "5.2.3", "date": "2025-10-08",
    "releases": [
        {"version": "5.2.3", "date": "2025-10-08", "php_versions": ">=7.2,<8.4", "mysql_versions": ">=5.5"},
        {"version": "4.9.11", "date": "2023-02-08", "php_versions": ">=5.5,<8.0", "mysql_versions": ">=5.5"},
    ]})

CONFIG = UpdateConfig()


class TransportTest(unittest.TestCase):
    URL = "https://example.org/list"

    def transport(self, answer):
        opener = FakeOpener({self.URL: answer})
        return Transport(CONFIG, opener), opener

    def test_get_returns_the_body_and_sends_the_user_agent(self):
        transport, opener = self.transport(b"hello")
        self.assertEqual(transport.get(self.URL), b"hello")
        self.assertEqual(opener.requests[0][1]["User-agent"], CONFIG.user_agent)
        self.assertEqual(opener.requests[0][2], CONFIG.http_timeout)

    def test_too_large_answer_is_refused(self):
        transport, _ = self.transport(b"x" * 100)
        with self.assertRaisesRegex(UpdateError, "larger than 50 bytes"):
            transport.get(self.URL, max_bytes=50)

    def test_http_error_names_the_host_and_code(self):
        transport, _ = self.transport(http_error(503))
        with self.assertRaisesRegex(UpdateError, r"example\.org answered 503"):
            transport.get(self.URL)

    def test_network_error_is_explained(self):
        transport, _ = self.transport(OSError("Network is unreachable"))
        with self.assertRaisesRegex(UpdateError, r"Could not reach example\.org"):
            transport.get(self.URL)

    def test_timeout_is_explained(self):
        transport, _ = self.transport(TimeoutError("timed out"))
        with self.assertRaisesRegex(UpdateError, "Could not reach"):
            transport.get(self.URL)

    def test_plain_http_is_refused_before_any_request(self):
        opener = FakeOpener({})
        with self.assertRaises(UpdateError):
            Transport(CONFIG, opener).get("http://example.org/x")
        self.assertEqual(opener.requests, [])

    def test_get_json_parses_and_reports_bad_json(self):
        transport, _ = self.transport(b'{"a": 1}')
        self.assertEqual(transport.get_json(self.URL), {"a": 1})
        transport, _ = self.transport(b"<html>")
        with self.assertRaisesRegex(UpdateError, "not JSON"):
            transport.get_json(self.URL)

    def test_get_text_decodes_leniently(self):
        transport, _ = self.transport(b"caf\xc3\xa9 \xff")
        self.assertTrue(transport.get_text(self.URL).startswith("café"))


class PhpMyAdminSourceTest(unittest.TestCase):
    def source(self, **answers):
        base = {CONFIG.pma_files_url: FILES_PAGE, CONFIG.pma_version_json_url: VERSION_JSON}
        base.update(answers)
        return PhpMyAdminSource(FakeTransport(base), CONFIG)

    def test_lists_stable_releases_once_in_page_order(self):
        releases = self.source().releases()
        self.assertEqual([r.version for r in releases], ["5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4", "4.9.0.1"])

    def test_release_urls(self):
        release = self.source().releases()[0]
        base = "https://files.phpmyadmin.net/phpMyAdmin/5.2.3/phpMyAdmin-5.2.3-all-languages.tar.xz"
        self.assertEqual(release.url, base)
        self.assertEqual(release.signature_url, base + ".asc")
        self.assertEqual(release.hash_url, base + ".sha256")

    def test_unexpected_page_is_an_error_not_an_empty_list(self):
        with self.assertRaisesRegex(UpdateError, "unexpected format"):
            self.source(**{CONFIG.pma_files_url: "<html>maintenance</html>"}).releases()

    def test_network_failure_propagates(self):
        with self.assertRaises(UpdateError):
            self.source(**{CONFIG.pma_files_url: UpdateError("offline")}).releases()

    def test_sha256_for_reads_the_published_file(self):
        digest = "5" * 64
        release = self.source().releases()[0]
        line = f"{digest}  phpMyAdmin-5.2.3-all-languages.tar.xz\n"
        source = self.source(**{release.hash_url: line})
        self.assertEqual(source.sha256_for(release), digest)

    def test_sha256_for_rejects_another_file_name_or_garbage(self):
        release = self.source().releases()[0]
        for text in (f"{'5' * 64}  evil.tar.xz\n", "nothing here", "5" * 63 + "  phpMyAdmin-5.2.3-all-languages.tar.xz"):
            with self.assertRaises(UpdateError, msg=text):
                self.source(**{release.hash_url: text}).sha256_for(release)

    def test_php_range_matches_the_branch(self):
        source = self.source()
        self.assertEqual(source.php_range("5.2.1"), ">=7.2,<8.4")
        self.assertEqual(source.php_range("4.9.0.1"), ">=5.5,<8.0")

    def test_php_range_is_none_when_unknown_or_unreachable(self):
        self.assertIsNone(self.source().php_range("5.1.4"))
        self.assertIsNone(self.source(**{CONFIG.pma_version_json_url: UpdateError("offline")}).php_range("5.2.1"))
        self.assertIsNone(self.source(**{CONFIG.pma_version_json_url: "[1, 2]"}).php_range("5.2.1"))

    def test_keyring_is_fetched_from_the_configured_url(self):
        source = self.source(**{CONFIG.pma_keyring_url: b"-----BEGIN PGP PUBLIC KEY BLOCK-----"})
        self.assertTrue(source.keyring().startswith(b"-----BEGIN PGP"))


class TransportRobustnessTest(unittest.TestCase):
    URL = "https://example.org/list"

    def get(self, answer, **kwargs):
        return Transport(CONFIG, FakeOpener({self.URL: answer}), **kwargs).get(self.URL)

    def test_http_protocol_errors_become_messages(self):
        for error in (http.client.IncompleteRead(b"par"), http.client.BadStatusLine("junk"),
                      http.client.LineTooLong("status line")):
            with self.assertRaisesRegex(UpdateError, r"Could not reach example\.org", msg=repr(error)):
                self.get(error)

    def test_deeply_nested_json_is_not_a_crash(self):
        body = b"[" * 100_000 + b"]" * 100_000
        transport = Transport(CONFIG, FakeOpener({self.URL: body}))
        with self.assertRaisesRegex(UpdateError, "not JSON"):
            transport.get_json(self.URL)

    def test_a_slow_server_is_cut_off_by_the_overall_deadline(self):
        now = [0.0]

        class Trickle(FakeResponse):
            def read(self, amount=-1):
                now[0] += 10  # every chunk takes ten seconds
                return b"x"

        transport = Transport(UpdateConfig(request_deadline=25.0), FakeOpener({self.URL: Trickle()}),
                              clock=lambda: now[0])
        with self.assertRaisesRegex(UpdateError, "took too long"):
            transport.get(self.URL)

    def test_a_page_with_look_alike_digits_does_not_offer_a_fake_newest_version(self):
        page = FILES_PAGE + '<a href="/files/5.\u0662.9/">x</a><a href="/files/\u0665.9.9/">y</a>'
        source = PhpMyAdminSource(FakeTransport({CONFIG.pma_files_url: page}), CONFIG)
        self.assertEqual([r.version for r in source.releases()][0], "5.2.3")
        self.assertTrue(all(r.url.isascii() for r in source.releases()))

    def test_version_json_is_fetched_once(self):
        transport = FakeTransport({CONFIG.pma_files_url: FILES_PAGE, CONFIG.pma_version_json_url: VERSION_JSON})
        source = PhpMyAdminSource(transport, CONFIG)
        source.php_range("5.2.1")
        source.php_range("5.2.2")
        self.assertEqual(transport.requested.count(CONFIG.pma_version_json_url), 1)


class ReadsAsDataArrivesTest(unittest.TestCase):
    def test_the_deadline_is_noticed_per_network_read_not_per_64_kb(self):
        now = [0.0]

        class Slow(FakeResponse):
            def read(self, amount=-1):
                raise AssertionError("read() waits for the whole amount; read1() must be used")

            def read1(self, amount=-1):
                now[0] += 1.0  # one second per trickle of data
                return b"x"

        transport = Transport(UpdateConfig(request_deadline=2.5), FakeOpener({"https://example.org/l": Slow()}),
                              clock=lambda: now[0])
        with self.assertRaisesRegex(UpdateError, "took too long"):
            transport.get("https://example.org/l")
        self.assertLessEqual(now[0], 4.0)


if __name__ == "__main__":
    unittest.main()
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"`

Expected: FAIL — ImportError: Failed to import test module: test_update_http (FAILED (errors=2)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/http.py`:

`````python
"""HTTPS-only requests, redirects included."""

import ssl
import urllib.request

from .base import UpdateError


def require_https(url) -> str:
    if not isinstance(url, str) or not url.startswith("https://"):
        raise UpdateError(f"Refusing an address that is not HTTPS: {url!r}")
    return url


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener() -> urllib.request.OpenerDirector:
    """An opener that can only speak HTTPS (TLS 1.2+): no plain HTTP, FTP, file: or data: handlers."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler(), urllib.request.UnknownHandler(),
                    urllib.request.HTTPSHandler(context=context), _HttpsOnlyRedirects(),
                    urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
        opener.add_handler(handler)
    return opener


def build_request(url: str, user_agent: str, headers: dict | None = None) -> urllib.request.Request:
    return urllib.request.Request(require_https(url), headers={"User-Agent": user_agent, **(headers or {})})
`````

Create `src/xampp_panel/updates/releases.py`:

`````python
"""Release lists from upstream: a capped HTTPS transport and the phpMyAdmin source."""

import http.client
import json
import re
import time
import urllib.error
import urllib.parse

from . import versions
from .base import Release, UpdateError
from .config import UpdateConfig
from .http import build_request, make_opener

_FILE_LINK = re.compile(r'href="/files/([0-9][^"/]*)/"')
_SHA256_LINE = re.compile(r"([0-9a-fA-F]{64})\s+\*?(\S+)")


class Transport:
    """GET with a size cap, a timeout and plain-language errors. Tests replace it with a fake."""

    def __init__(self, config: UpdateConfig = UpdateConfig(), opener=None, clock=time.monotonic):
        self.config = config
        self.opener = opener or make_opener()
        self.clock = clock

    def get(self, url: str, max_bytes: int | None = None) -> bytes:
        limit = max_bytes or self.config.max_response_bytes
        host = urllib.parse.urlsplit(url).hostname
        deadline = self.clock() + self.config.request_deadline
        chunks, size = [], 0
        try:
            with self.opener.open(build_request(url, self.config.user_agent),
                                  timeout=self.config.http_timeout) as response:
                while True:
                    block = getattr(response, "read1", response.read)(65536)  # read1: return as soon as bytes arrive
                    if not block:
                        break
                    size += len(block)
                    if size > limit:
                        raise UpdateError(f"The answer from {host} is larger than {limit} bytes, so it was refused.")
                    if self.clock() > deadline:
                        raise UpdateError(f"{host} took too long to answer, so the request was stopped.")
                    chunks.append(block)
        except urllib.error.HTTPError as e:
            raise UpdateError(f"{host} answered {e.code} for {url}") from e
        except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException) as e:
            raise UpdateError(f"Could not reach {host}: {getattr(e, 'reason', None) or repr(e)}") from e
        return b"".join(chunks)

    def get_text(self, url: str, max_bytes: int | None = None) -> str:
        return self.get(url, max_bytes).decode("utf-8", errors="replace")

    def get_json(self, url: str, max_bytes: int | None = None):
        try:
            return json.loads(self.get(url, max_bytes))
        except (ValueError, RecursionError) as e:  # RecursionError: absurdly nested brackets
            raise UpdateError(f"{urllib.parse.urlsplit(url).hostname} sent something that is not JSON.") from e


class PhpMyAdminSource:
    def __init__(self, transport, config: UpdateConfig = UpdateConfig()):
        self.transport = transport
        self.config = config
        self._version_json = None  # fetched once: the update menu asks for every entry

    def releases(self) -> list[Release]:
        """Every stable release on phpMyAdmin's file list (release candidates and betas are skipped)."""
        page = self.transport.get_text(self.config.pma_files_url)
        found: list[str] = []
        for version in _FILE_LINK.findall(page):
            if versions.is_valid(version) and version not in found:
                found.append(version)
        if not found:
            raise UpdateError("phpMyAdmin's download list has an unexpected format, so nothing was offered.")
        return [self._release(version) for version in found]

    def _release(self, version: str) -> Release:
        url = f"{self.config.pma_download_base}/{version}/phpMyAdmin-{version}-all-languages.tar.xz"
        return Release(version, url, signature_url=url + ".asc", hash_url=url + ".sha256")

    def sha256_for(self, release: Release) -> str:
        """The SHA-256 phpMyAdmin publishes next to the release, checked against the file name."""
        text = self.transport.get_text(release.hash_url, max_bytes=4096)
        match = _SHA256_LINE.match(text.strip())
        expected = release.url.rsplit("/", 1)[-1]
        if match is None or match.group(2) != expected:
            raise UpdateError(f"The checksum file for phpMyAdmin {release.version} has an unexpected format.")
        return match.group(1).lower()

    def keyring(self) -> bytes:
        return self.transport.get(self.config.pma_keyring_url, max_bytes=500_000)

    def php_range(self, version: str) -> str | None:
        """The PHP versions phpMyAdmin says this release's branch supports, e.g. ">=7.2,<8.4"; None if unknown."""
        if self._version_json is None:
            try:
                self._version_json = self.transport.get_json(self.config.pma_version_json_url)
            except UpdateError:
                return None
        data = self._version_json
        want = version.split(".")[:2]
        for entry in data.get("releases", []) if isinstance(data, dict) else []:
            if not isinstance(entry, dict):
                continue
            number, span = entry.get("version"), entry.get("php_versions")
            if versions.is_valid(number) and isinstance(span, str) and number.split(".")[:2] == want:
                return span
        return None
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"` — Expected: `Ran 58 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 317 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/update_fakes.py tests/test_update_http.py tests/test_update_releases.py src/xampp_panel/updates/http.py src/xampp_panel/updates/releases.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: HTTPS-only transport and phpMyAdmin release source"
`````

---

### Task 3: Downloads, safe unpacking and the ownership-preserving copy

Add the resumable verified download, the archive unpacker that never acts through a link, and `copy_owned`, which is safe to run as root over folders that Apache (`daemon`) can write.

These three modules came out of a security review (see the spec's "Security" section): chains of symlinks, folders created outside the target, short downloads accepted as complete, Unicode digits in versions, protocol errors escaping as tracebacks, and a permission window while copying. Each has a regression test; do not simplify the code without keeping those tests green.

**Files:**
- Create: `src/xampp_panel/updates/fetcher.py`
- Create: `src/xampp_panel/updates/archive.py`
- Create: `src/xampp_panel/updates/fsops.py`
- Create: `tests/test_update_fetcher.py`
- Create: `tests/test_update_archive.py`
- Create: `tests/test_update_fsops.py`

**Interfaces:**
- Consumes: Task 1 config/base; Task 2 `http`, `tests/update_fakes.py` (`FakeOpener`, `FakeResponse`, `http_error`, `build_tar`).
- Produces: `fetcher.Fetcher(config, opener=None, sleep, clock).download(url, dest, max_bytes=None) -> Path`, `fetcher.verify_hashes(path, {algorithm: hex})`, `fetcher.file_hash`; `archive.safe_extract(archive, dest, config, strip=1) -> int`; `fsops.copy_owned(src, dst, chown=os.chown)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_fetcher.py`:

`````python
import hashlib
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path

from xampp_panel.updates.base import UpdateError
from xampp_panel.updates.config import UpdateConfig
from xampp_panel.updates.fetcher import Fetcher, file_hash, verify_hashes

from update_fakes import FakeOpener, FakeResponse, http_error

URL = "https://files.example.org/pkg.tar.xz"
BODY = bytes(range(256)) * 40  # 10240 bytes


class FetcherTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.dest = self.dir / "pkg.tar.xz"
        self.sleeps = []

    def tearDown(self):
        self._tmp.cleanup()

    def fetcher(self, answers, **config):
        self.opener = FakeOpener({URL: answers})
        return Fetcher(UpdateConfig(**config), self.opener, sleep=self.sleeps.append)

    def test_downloads_to_the_destination_and_removes_the_part_file(self):
        self.fetcher(FakeResponse(BODY, headers={"Content-Length": str(len(BODY))})).download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)
        self.assertFalse(self.dest.with_name("pkg.tar.xz.part").exists())

    def test_part_file_is_private(self):
        seen = {}
        original = FakeResponse.read

        def peek(response, amount=-1):
            part = self.dest.with_name("pkg.tar.xz.part")
            if part.exists():
                seen["mode"] = part.stat().st_mode & 0o777
            return original(response, amount)

        FakeResponse.read = peek
        try:
            self.fetcher(FakeResponse(BODY)).download(URL, self.dest)
        finally:
            FakeResponse.read = original
        self.assertEqual(seen["mode"], 0o600)

    def test_resumes_from_a_part_file(self):
        part = self.dest.with_name("pkg.tar.xz.part")
        part.write_bytes(BODY[:4000])
        fetcher = self.fetcher(FakeResponse(BODY[4000:], status=206, headers={
            "Content-Length": str(len(BODY) - 4000), "Content-Range": f"bytes 4000-{len(BODY) - 1}/{len(BODY)}"}))
        fetcher.download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)
        self.assertEqual(self.opener.requests[0][1]["Range"], "bytes=4000-")

    def test_server_that_ignores_the_range_restarts_the_file(self):
        self.dest.with_name("pkg.tar.xz.part").write_bytes(b"stale bytes")
        self.fetcher(FakeResponse(BODY, status=200)).download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)

    def test_retries_after_a_dropped_connection_then_succeeds(self):
        fetcher = self.fetcher([OSError("connection reset"), FakeResponse(BODY)])
        fetcher.download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)
        self.assertEqual(self.sleeps, [1])

    def test_gives_up_after_all_attempts_and_leaves_no_part_file(self):
        fetcher = self.fetcher([OSError("down")] * 3, download_attempts=3)
        with self.assertRaisesRegex(UpdateError, r"Could not download from files\.example\.org"):
            fetcher.download(URL, self.dest)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest.with_name("pkg.tar.xz.part").exists())

    def test_client_error_is_not_retried(self):
        fetcher = self.fetcher([http_error(404, URL), FakeResponse(BODY)])
        with self.assertRaisesRegex(UpdateError, "answered 404"):
            fetcher.download(URL, self.dest)
        self.assertEqual(len(self.opener.requests), 1)

    def test_server_error_is_retried(self):
        fetcher = self.fetcher([http_error(503, URL), FakeResponse(BODY)])
        fetcher.download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)

    def test_unsatisfiable_range_discards_the_part_file_and_retries(self):
        self.dest.with_name("pkg.tar.xz.part").write_bytes(b"x" * 50)
        fetcher = self.fetcher([http_error(416, URL), FakeResponse(BODY)])
        fetcher.download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)

    def test_announced_size_over_the_limit_is_refused(self):
        fetcher = self.fetcher(FakeResponse(BODY, headers={"Content-Length": str(len(BODY))}))
        with self.assertRaisesRegex(UpdateError, "larger than expected"):
            fetcher.download(URL, self.dest, max_bytes=1000)
        self.assertFalse(self.dest.with_name("pkg.tar.xz.part").exists())

    def test_streamed_size_over_the_limit_is_refused(self):
        fetcher = self.fetcher(FakeResponse(BODY))  # no Content-Length: the stream itself is counted
        with self.assertRaisesRegex(UpdateError, "larger than expected"):
            fetcher.download(URL, self.dest, max_bytes=1000)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest.with_name("pkg.tar.xz.part").exists())

    def test_plain_http_is_refused(self):
        with self.assertRaises(UpdateError):
            self.fetcher(FakeResponse(BODY)).download("http://files.example.org/pkg.tar.xz", self.dest)


class HashTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "f"
        self.path.write_bytes(b"hello")

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_hash(self):
        self.assertEqual(file_hash(self.path, "sha256"), hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(file_hash(self.path, "md5"), hashlib.md5(b"hello").hexdigest())

    def test_matching_checksums_pass_case_insensitively(self):
        verify_hashes(self.path, {"sha256": hashlib.sha256(b"hello").hexdigest().upper()})
        verify_hashes(self.path, {"md5": hashlib.md5(b"hello").hexdigest(), "sha1": hashlib.sha1(b"hello").hexdigest()})

    def test_one_wrong_checksum_fails(self):
        good = hashlib.md5(b"hello").hexdigest()
        with self.assertRaisesRegex(UpdateError, "SHA1 checksum"):
            verify_hashes(self.path, {"md5": good, "sha1": "0" * 40})

    def test_nothing_to_check_against_fails_closed(self):
        with self.assertRaisesRegex(UpdateError, "No checksum"):
            verify_hashes(self.path, {})

    def test_unknown_algorithm_is_refused(self):
        with self.assertRaisesRegex(UpdateError, "Unknown checksum type"):
            verify_hashes(self.path, {"crc32": "abc"})

class FetcherRobustnessTest(FetcherTest):
    def test_a_short_body_is_retried_and_resumed_not_accepted(self):
        short = FakeResponse(BODY[:4096], headers={"Content-Length": str(len(BODY))})
        rest = FakeResponse(BODY[4096:], status=206, headers={
            "Content-Length": str(len(BODY) - 4096), "Content-Range": f"bytes 4096-{len(BODY) - 1}/{len(BODY)}"})
        self.fetcher([short, rest]).download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)
        self.assertEqual(len(self.opener.requests), 2)
        self.assertEqual(self.opener.requests[1][1]["Range"], "bytes=4096-")

    def test_http_protocol_errors_are_retried_not_tracebacks(self):
        import http.client
        for error in (http.client.IncompleteRead(b"x"), http.client.BadStatusLine("junk")):
            self.dest.unlink(missing_ok=True)
            self.fetcher([error, FakeResponse(BODY)]).download(URL, self.dest)
            self.assertEqual(self.dest.read_bytes(), BODY)

    def test_a_nonsense_content_length_does_not_crash(self):
        self.fetcher(FakeResponse(BODY, headers={"Content-Length": "\u00b2"})).download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)

    def test_a_resume_from_the_wrong_place_starts_over(self):
        self.dest.with_name("pkg.tar.xz.part").write_bytes(BODY[:100])
        wrong = FakeResponse(BODY[500:], status=206, headers={"Content-Range": "bytes 500-10239/10240"})
        self.fetcher([wrong, FakeResponse(BODY)]).download(URL, self.dest)
        self.assertEqual(self.dest.read_bytes(), BODY)

    def test_disk_errors_are_not_retried_and_say_so(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores folder permissions")
        os.chmod(self.dir, 0o500)
        try:
            fetcher = self.fetcher([FakeResponse(BODY), FakeResponse(BODY)])
            with self.assertRaisesRegex(UpdateError, "Could not write the download"):
                fetcher.download(URL, self.dest)
            self.assertEqual(len(self.opener.requests), 1)
        finally:
            os.chmod(self.dir, 0o700)

    def test_a_folder_others_can_use_is_refused(self):
        os.chmod(self.dir, 0o755)
        with self.assertRaisesRegex(UpdateError, "not a private folder"):
            self.fetcher(FakeResponse(BODY)).download(URL, self.dest)
        self.assertEqual(self.opener.requests, [])

    def test_a_download_that_trickles_is_stopped(self):
        now = [0.0]

        class Trickle(FakeResponse):
            def read(self, amount=-1):
                now[0] += 100
                return b"x" * 10

        self.opener = FakeOpener({URL: Trickle()})
        fetcher = Fetcher(UpdateConfig(download_min_seconds=250), self.opener, sleep=self.sleeps.append, clock=lambda: now[0])
        with self.assertRaisesRegex(UpdateError, "taking too long"):
            fetcher.download(URL, self.dest, max_bytes=1000)

    def test_a_checksum_that_is_not_text_is_refused(self):
        self.dest.write_bytes(b"x")
        with self.assertRaisesRegex(UpdateError, "not text"):
            verify_hashes(self.dest, {"sha256": 12345})
`````

Create `tests/test_update_archive.py`:

`````python
import os
import tempfile
import unittest
from pathlib import Path

from xampp_panel.updates.archive import safe_extract
from xampp_panel.updates.base import UpdateError
from xampp_panel.updates.config import UpdateConfig

from update_fakes import build_tar as build


GOOD = [
    ("pkg-1.0", "dir", None, 0o755),
    ("pkg-1.0/README", "file", "Version 1.0\n", 0o600),
    ("pkg-1.0/bin", "dir", None, 0o700),
    ("pkg-1.0/bin/run", "file", "#!/bin/sh\n", 0o4755),
    ("pkg-1.0/lib/data.txt", "file", "x", 0o666),
    ("pkg-1.0/lib/alias", "sym", "data.txt", 0o777),
]


class SafeExtractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.dest = self.dir / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def unpack(self, members, mode="w:xz", config=UpdateConfig(), strip=1):
        archive = self.dir / "a.tar"
        archive.write_bytes(build(members, mode))
        return safe_extract(archive, self.dest, config, strip)

    def test_unpacks_and_strips_the_top_folder(self):
        count = self.unpack(GOOD)
        self.assertEqual(count, 3)
        self.assertEqual((self.dest / "README").read_text(), "Version 1.0\n")
        self.assertTrue((self.dest / "bin/run").is_file())
        self.assertFalse((self.dest / "pkg-1.0").exists())

    def test_modes_are_normalised(self):
        self.unpack(GOOD)
        mode = lambda p: (self.dest / p).stat().st_mode & 0o7777
        self.assertEqual(mode("README"), 0o644)  # was 0600
        self.assertEqual(mode("bin/run"), 0o755)  # was 4755: setuid dropped, executable kept
        self.assertEqual(mode("lib/data.txt"), 0o644)  # was 0666
        self.assertEqual(mode("bin"), 0o755)  # was 0700
        self.assertEqual(mode(""), 0o755)

    def test_internal_symlink_is_kept(self):
        self.unpack(GOOD)
        self.assertTrue((self.dest / "lib/alias").is_symlink())
        self.assertEqual(os.readlink(self.dest / "lib/alias"), "data.txt")

    def test_gzip_archives_work_too(self):
        self.unpack(GOOD, mode="w:gz")
        self.assertTrue((self.dest / "README").is_file())

    def test_strip_zero_keeps_the_top_folder(self):
        self.unpack(GOOD, strip=0)
        self.assertTrue((self.dest / "pkg-1.0/README").is_file())

    def refused(self, members, pattern, **kwargs):
        with self.assertRaisesRegex(UpdateError, pattern):
            self.unpack(members, **kwargs)

    def test_parent_traversal_is_refused(self):
        self.refused([("pkg/../../evil", "file", "x", 0o644)], "leave its folder")

    def test_absolute_path_is_refused(self):
        self.refused([("/etc/evil", "file", "x", 0o644)], "absolute path")

    def test_symlink_pointing_outside_is_refused(self):
        self.refused([("pkg/link", "sym", "../../etc/passwd", 0o777)], "points outside")
        self.refused([("pkg/link", "sym", "/etc/passwd", 0o777)], "points outside")

    def test_symlink_reaching_the_root_through_a_subfolder_is_refused(self):
        self.refused([("pkg/a/b/link", "sym", "../../../x", 0o777)], "points outside")

    def test_writing_through_an_unpacked_symlink_is_refused(self):
        outside = self.dir / "outside"
        outside.mkdir()
        members = [("pkg/a", "sym", "..", 0o777), ("pkg/a/b", "dir", None, 0o755)]
        with self.assertRaises(UpdateError):
            self.unpack(members)
        self.assertEqual(list(outside.iterdir()), [])

    def test_hard_links_devices_and_fifos_are_refused(self):
        self.refused([("pkg/h", "hard", "pkg/README", 0o644)], "not a file or folder")
        self.refused([("pkg/d", "dev", None, 0o644)], "not a file or folder")
        self.refused([("pkg/f", "fifo", None, 0o644)], "not a file or folder")

    def test_too_many_entries_are_refused(self):
        members = [(f"pkg/f{i}", "file", "x", 0o644) for i in range(5)]
        self.refused(members, "too many entries", config=UpdateConfig(archive_max_entries=3))

    def test_unpacked_size_limit(self):
        members = [("pkg/big", "file", b"x" * 1000, 0o644)]
        self.refused(members, "more than expected", config=UpdateConfig(archive_max_bytes=500))

    def test_duplicate_file_is_refused(self):
        self.refused([("pkg/a", "file", "1", 0o644), ("pkg/a", "file", "2", 0o644)], "twice")

    def test_damaged_archive(self):
        archive = self.dir / "a.tar"
        whole = build([("pkg/big", "file", os.urandom(20000), 0o644)])
        archive.write_bytes(whole[:len(whole) // 2])
        with self.assertRaisesRegex(UpdateError, "damaged"):
            safe_extract(archive, self.dest)

    def test_not_an_archive(self):
        archive = self.dir / "a.tar"
        archive.write_bytes(b"this is not an archive at all")
        with self.assertRaisesRegex(UpdateError, "damaged"):
            safe_extract(archive, self.dest)

    def test_destination_must_be_empty(self):
        self.dest.mkdir()
        (self.dest / "keep").write_text("x")
        archive = self.dir / "a.tar"
        archive.write_bytes(build(GOOD))
        with self.assertRaisesRegex(UpdateError, "not an empty folder"):
            safe_extract(archive, self.dest)
        self.assertEqual((self.dest / "keep").read_text(), "x")

class ArchiveEscapeTest(SafeExtractTest):
    """Findings from the security review: chains of links, folders created outside, odd errors."""

    def setUp(self):
        super().setUp()
        self.base = self.dir / "base"
        (self.base / "a/b").mkdir(parents=True)
        self.victim = self.base / "victim"
        self.victim.mkdir(mode=0o700)
        os.chmod(self.victim, 0o700)
        self.dest = self.base / "a/b/out"
        self.outside = self.base / "a/b"

    CHAIN = [
        ("pkg/x", "sym", ".", 0o777),
        ("pkg/y1", "sym", "x/..", 0o777),  # text says ".", but x is a link to the root, so this is its parent
        ("pkg/y2", "sym", "y1/..", 0o777),
        ("pkg/y3", "sym", "y2/..", 0o777),
        ("pkg/v", "sym", "y3/victim", 0o777),
        ("pkg/v", "dir", None, 0o755),
    ]

    def test_a_chain_of_links_cannot_chmod_a_folder_outside(self):
        with self.assertRaises(UpdateError):
            self.unpack(self.CHAIN)
        self.assertEqual(self.victim.stat().st_mode & 0o777, 0o700)

    def test_the_same_chain_ending_in_a_file_is_refused_too(self):
        members = self.CHAIN[:-1] + [("pkg/v/evil", "file", "x", 0o644)]
        with self.assertRaises(UpdateError):
            self.unpack(members)
        self.assertEqual(list(self.victim.iterdir()), [])

    def test_a_link_that_only_becomes_dangerous_later_is_refused(self):
        members = [("pkg/x", "sym", ".", 0o777), ("pkg/a", "sym", "b/..", 0o777),  # b does not exist yet
                   ("pkg/b", "sym", "x", 0o777), ("pkg/a", "dir", None, 0o755)]
        before = self.outside.stat().st_mode & 0o777
        with self.assertRaises(UpdateError):
            self.unpack(members)
        self.assertEqual(self.outside.stat().st_mode & 0o777, before)

    def test_no_folder_is_created_outside_before_the_refusal(self):
        members = [("pkg/x", "sym", ".", 0o777), ("pkg/y", "sym", "x/..", 0o777),
                   ("pkg/y/escaped-dir/f", "file", "x", 0o644)]
        with self.assertRaises(UpdateError):
            self.unpack(members)
        self.assertFalse((self.outside / "escaped-dir").exists())

    def test_a_folder_entry_over_a_file_or_link_is_refused(self):
        with self.assertRaisesRegex(UpdateError, "folder where a link or file"):
            self.unpack([("pkg/a", "file", "x", 0o644), ("pkg/a", "dir", None, 0o755)])

    def test_a_damaged_gzip_archive_is_a_clear_error(self):
        archive = self.dir / "a.tar"
        whole = build([("pkg/f", "file", os.urandom(20000), 0o644)], "w:gz")
        archive.write_bytes(whole[:len(whole) // 2])
        with self.assertRaisesRegex(UpdateError, "damaged"):
            safe_extract(archive, self.dest)

    def test_a_destination_that_is_a_file_is_a_clear_error(self):
        self.dest.write_text("x")
        archive = self.dir / "a.tar"
        archive.write_bytes(build(GOOD))
        with self.assertRaisesRegex(UpdateError, "not an empty folder"):
            safe_extract(archive, self.dest)

    def test_folders_are_readable_whatever_the_umask(self):
        old = os.umask(0o077)
        try:
            self.unpack(GOOD)
        finally:
            os.umask(old)
        for name in ("", "bin", "lib"):
            self.assertEqual((self.dest / name).stat().st_mode & 0o777, 0o755, name)

    def test_running_out_of_disk_space_is_explained(self):
        import errno
        from unittest import mock
        with mock.patch("shutil.copyfileobj", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with self.assertRaisesRegex(UpdateError, "not enough free disk space"):
                self.unpack(GOOD)


class LaterLinkTest(ArchiveEscapeTest):
    def test_a_link_made_dangerous_by_a_later_link_is_refused(self):
        members = [("pkg/l", "sym", "d/..", 0o777), ("pkg/d", "sym", ".", 0o777)]
        with self.assertRaisesRegex(UpdateError, "ends up outside"):
            self.unpack(members)
`````

Create `tests/test_update_fsops.py`:

`````python
import os
import tempfile
import unittest
from pathlib import Path

from xampp_panel.updates.fsops import copy_owned


class CopyOwnedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "src"
        (self.src / "sub").mkdir(parents=True)
        (self.src / "a.txt").write_text("a")
        os.chmod(self.src / "a.txt", 0o640)
        (self.src / "sub/b.txt").write_text("b")
        os.symlink("a.txt", self.src / "link")
        self.calls = []

    def tearDown(self):
        self._tmp.cleanup()

    def chown(self, path, uid, gid, **kwargs):
        self.calls.append((Path(path).relative_to(self.dir / "dst"), uid, gid, kwargs.get("follow_symlinks", True)))

    def test_copies_a_tree_with_modes_and_links(self):
        copy_owned(self.src, self.dir / "dst", self.chown)
        dst = self.dir / "dst"
        self.assertEqual((dst / "a.txt").read_text(), "a")
        self.assertEqual((dst / "a.txt").stat().st_mode & 0o777, 0o640)
        self.assertEqual((dst / "sub/b.txt").read_text(), "b")
        self.assertTrue((dst / "link").is_symlink())
        self.assertEqual(os.readlink(dst / "link"), "a.txt")

    def test_owner_and_group_of_every_entry_are_applied(self):
        copy_owned(self.src, self.dir / "dst", self.chown)
        uid, gid = os.getuid(), os.getgid()
        names = {str(rel) for rel, *_ in self.calls}
        self.assertEqual(names, {".", "a.txt", "sub", "sub/b.txt", "link"})
        self.assertTrue(all((u, g) == (uid, gid) for _, u, g, _ in self.calls))
        self.assertIn((Path("link"), uid, gid, False), self.calls)  # the link itself, not its target

    def test_a_single_file(self):
        copy_owned(self.src / "a.txt", self.dir / "copy.txt", lambda *a, **k: None)
        self.assertEqual((self.dir / "copy.txt").read_text(), "a")

    def test_special_files_are_refused(self):
        fifo = self.dir / "fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(OSError, "not a file, folder or link"):
            copy_owned(fifo, self.dir / "fifo2", lambda *a, **k: None)

class CopyOwnedSafetyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.src = self.dir / "src"
        (self.src / "sub").mkdir(parents=True)
        (self.src / "secret").write_text("s")
        os.chmod(self.src / "secret", 0o600)
        (self.src / "sub/f").write_text("f")
        os.chmod(self.src / "sub", 0o750)

    def tearDown(self):
        self._tmp.cleanup()

    def test_nothing_is_wider_than_the_original_at_any_moment(self):
        seen = {}

        def chown(path, uid, gid, **kwargs):
            seen[Path(path).name] = os.stat(path, follow_symlinks=False).st_mode & 0o777

        copy_owned(self.src, self.dir / "dst", chown)
        self.assertEqual(seen["secret"], 0o600)  # still private when ownership is applied
        self.assertEqual(seen["sub"], 0o700)  # the folder only gets its real mode last
        self.assertEqual((self.dir / "dst/secret").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.dir / "dst/sub").stat().st_mode & 0o777, 0o750)

    def test_times_are_kept(self):
        os.utime(self.src / "sub/f", ns=(1_000_000_000, 2_000_000_000))
        copy_owned(self.src, self.dir / "dst", lambda *a, **k: None)
        self.assertEqual((self.dir / "dst/sub/f").stat().st_mtime_ns, 2_000_000_000)

    def test_a_link_to_a_folder_is_copied_as_a_link_not_followed(self):
        other = self.dir / "other"
        other.mkdir()
        (other / "private.txt").write_text("not yours")
        os.symlink(other, self.src / "pointer")
        copy_owned(self.src, self.dir / "dst", lambda *a, **k: None)
        self.assertTrue((self.dir / "dst/pointer").is_symlink())
        self.assertFalse((self.dir / "dst/pointer").resolve() == (self.dir / "dst/pointer"))
        self.assertEqual(list((self.dir / "dst").glob("pointer/*"))[0].name, "private.txt")  # via the link only
        self.assertFalse((self.dir / "dst/private.txt").exists())

    def test_a_folder_swapped_for_a_link_while_copying_is_refused(self):
        import shutil
        from unittest import mock
        victim = self.dir / "victim"
        victim.mkdir()
        (victim / "loot").write_text("root's file")
        real_open = os.open
        swapped = []

        def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
            if path == "sub" and dir_fd is not None and not swapped:
                swapped.append(True)
                shutil.rmtree(self.src / "sub")
                os.symlink(victim, self.src / "sub")  # the attacker wins the race right after lstat
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch("os.open", swapping_open):
            with self.assertRaises(OSError):
                copy_owned(self.src, self.dir / "dst", lambda *a, **k: None)
        self.assertFalse((self.dir / "dst/sub/loot").exists())

    def test_a_special_file_inside_a_folder_is_refused_without_hanging(self):
        os.mkfifo(self.src / "pipe")
        with self.assertRaisesRegex(OSError, "not a file, folder or link"):
            copy_owned(self.src, self.dir / "dst", lambda *a, **k: None)
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"`

Expected: FAIL — ImportError: Failed to import test module: test_update_archive (FAILED (errors=3)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/fetcher.py`:

`````python
"""Resumable HTTPS downloads and checksum verification."""

import hashlib
import http.client
import os
import time
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Mapping

from .base import UpdateError
from .config import UpdateConfig
from .http import build_request, make_opener

CHUNK = 1 << 16
_ALGORITHMS = {"sha256": hashlib.sha256, "sha1": hashlib.sha1, "md5": hashlib.md5}
_TOO_LARGE = "The download is larger than expected, so it was refused."


def file_hash(path, algorithm: str) -> str:
    digest = _ALGORITHMS[algorithm]()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_hashes(path, expected: Mapping[str, str]) -> None:
    """Every expected checksum must match. Nothing to check against counts as a failure."""
    if not expected:
        raise UpdateError("No checksum is available for this download, so it will not be used.")
    for algorithm, want in expected.items():
        if algorithm not in _ALGORITHMS:
            raise UpdateError(f"Unknown checksum type {algorithm!r}.")
        if not isinstance(want, str):
            raise UpdateError(f"The {algorithm.upper()} checksum is not text, so the download was refused.")
        if file_hash(path, algorithm) != want.lower():
            raise UpdateError(f"The download does not match its {algorithm.upper()} checksum, so it was refused.")


def _require_private(folder: Path) -> None:
    """Downloads are checked and then used as root, so nobody else may be able to touch them in between."""
    info = os.stat(folder)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise UpdateError(f"{folder} is not a private folder, so nothing is downloaded into it.")


class Fetcher:
    def __init__(self, config: UpdateConfig = UpdateConfig(), opener=None, sleep=time.sleep, clock=time.monotonic):
        self.config = config
        self.opener = opener or make_opener()
        self.sleep = sleep
        self.clock = clock

    def download(self, url: str, dest, max_bytes: int | None = None) -> Path:
        """Download `url` to `dest` (in a private folder). A dropped connection resumes from the `.part`
        file within this call; when every attempt fails the `.part` file is deleted."""
        dest = Path(dest)
        limit = max_bytes or self.config.max_download_bytes
        _require_private(dest.parent)
        part = dest.with_name(dest.name + ".part")
        host = urllib.parse.urlsplit(url).hostname
        deadline = self.clock() + max(self.config.download_min_seconds, limit / self.config.download_min_bytes_per_second)
        failure: Exception | None = None
        for attempt in range(self.config.download_attempts):
            if attempt:
                self.sleep(attempt)
            try:
                self._attempt(url, part, limit, deadline)
            except UpdateError:
                part.unlink(missing_ok=True)
                raise
            except urllib.error.HTTPError as e:
                if e.code == 416:  # the .part file is not a prefix of the file any more
                    part.unlink(missing_ok=True)
                elif 400 <= e.code < 500:
                    part.unlink(missing_ok=True)
                    raise UpdateError(f"{host} answered {e.code} for {url}") from e
                failure = e
                continue
            except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException) as e:
                failure = e
                continue
            os.replace(part, dest)
            return dest
        part.unlink(missing_ok=True)  # never leave a possibly corrupt .part behind
        raise UpdateError(f"Could not download from {host}: {getattr(failure, 'reason', None) or repr(failure)}")

    def _attempt(self, url: str, part: Path, limit: int, deadline: float) -> None:
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        request = build_request(url, self.config.user_agent, headers)
        with self.opener.open(request, timeout=self.config.stall_timeout) as response:
            if offset:
                if getattr(response, "status", 200) != 206:
                    offset = 0  # the server sent the whole file again
                elif not str(response.headers.get("Content-Range", "")).startswith(f"bytes {offset}-"):
                    part.unlink(missing_ok=True)
                    raise urllib.error.URLError("the server resumed from the wrong place")
            length = response.headers.get("Content-Length")
            announced = int(length) if length and length.isascii() and length.isdigit() else None
            if announced is not None and offset + announced > limit:
                raise UpdateError(_TOO_LARGE)
            flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if offset else os.O_TRUNC)
            try:
                out = os.fdopen(os.open(part, flags, 0o600), "ab" if offset else "wb")
            except OSError as e:
                raise UpdateError(f"Could not write the download into {part.parent}: {e.strerror or e}") from e
            total = offset
            with out:
                while True:
                    if self.clock() > deadline:
                        raise UpdateError("The download is taking too long, so it was stopped.")
                    block = getattr(response, "read1", response.read)(CHUNK)  # returns as soon as bytes arrive;
                    # network errors surface here and are retried
                    if not block:
                        break
                    total += len(block)
                    if total > limit:
                        raise UpdateError(_TOO_LARGE)
                    try:
                        out.write(block)
                    except OSError as e:
                        raise UpdateError(f"Could not write the download into {part.parent}: {e.strerror or e}") from e
            if announced is not None and total != offset + announced:
                raise urllib.error.URLError("the connection closed before the whole file arrived")
`````

Create `src/xampp_panel/updates/archive.py`:

`````python
"""Safe unpacking of release archives (.tar.xz / .tar.gz).

Integrity comes from the checksum (and signature) checked BEFORE this runs: tarfile stops at the
end-of-archive marker and never verifies the compression trailer. This module only makes sure that
whatever the archive contains stays inside the destination.
"""

import errno
import lzma
import os
import posixpath
import shutil
import stat
import tarfile
import zlib
from pathlib import Path, PurePosixPath

from .base import UpdateError
from .config import UpdateConfig


def _relative_name(name: str, strip: int) -> str | None:
    """The path inside the destination, or None for the stripped top folder itself."""
    if name.startswith("/"):
        raise UpdateError(f"The archive contains an absolute path ({name}), so it was refused.")
    parts = [part for part in PurePosixPath(name).parts if part not in ("", ".")]
    if ".." in parts:
        raise UpdateError(f"The archive tries to leave its folder ({name}), so it was refused.")
    return "/".join(parts[strip:]) or None


def _link_escapes(rel: str, link: str) -> bool:
    if posixpath.isabs(link):
        return True
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(rel), link))
    return joined == ".." or joined.startswith("../")


def _make_folder(path: str) -> None:
    os.mkdir(path, 0o755)
    os.chmod(path, 0o755)  # not reduced by the umask: Apache must be able to read what is unpacked


def _ensure_parents(root: str, rel: str) -> None:
    """Create the folders above `rel` one at a time. A link or file where a folder should be is refused,
    so nothing is ever created or changed through a link (chains of links included)."""
    current = root
    for part in rel.split("/")[:-1]:
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            _make_folder(current)
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise UpdateError(f"The archive writes through a link or file ({part}), so it was refused.")


def safe_extract(archive, dest, config: UpdateConfig = UpdateConfig(), strip: int = 1) -> int:
    """Unpack `archive` into the new folder `dest`, dropping `strip` leading path components.

    Only files, folders and links that stay inside `dest` are accepted. Files end up 0644 (0755 if they
    were executable), folders 0755, owned by whoever runs this. Returns the number of files.
    On failure `dest` may be half filled: the caller deletes it.
    """
    dest = Path(dest)
    try:
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            raise UpdateError(f"{dest} already exists and is not an empty folder.")
        dest.mkdir(parents=True, exist_ok=True)
        os.chmod(dest, 0o755)
        root = os.path.realpath(dest)
        entries = files = total = 0
        links: list[str] = []
        with tarfile.open(archive, "r:*") as tar:
            for member in tar:
                entries += 1
                if entries > config.archive_max_entries:
                    raise UpdateError("The archive has too many entries, so it was refused.")
                rel = _relative_name(member.name, strip)
                if rel is None:
                    continue
                _ensure_parents(root, rel)
                target = os.path.join(root, rel)
                if member.isdir():
                    try:
                        info = os.lstat(target)
                    except FileNotFoundError:
                        _make_folder(target)
                    else:
                        if not stat.S_ISDIR(info.st_mode):
                            raise UpdateError(f"The archive has a folder where a link or file already is ({member.name}).")
                        os.chmod(target, 0o755)
                elif member.isreg():
                    total += member.size
                    if total > config.archive_max_bytes:
                        raise UpdateError("The archive unpacks to more than expected, so it was refused.")
                    try:
                        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    except FileExistsError:
                        raise UpdateError(f"The archive lists {member.name} twice, so it was refused.") from None
                    with os.fdopen(fd, "wb") as out, tar.extractfile(member) as source:
                        shutil.copyfileobj(source, out)
                    os.chmod(target, 0o755 if member.mode & 0o111 else 0o644)
                    files += 1
                elif member.issym():
                    # Checked twice: by its text, and by where it really lands now that earlier links exist.
                    landing = os.path.realpath(os.path.join(root, os.path.dirname(rel), member.linkname))
                    if _link_escapes(rel, member.linkname) or (landing != root and not landing.startswith(root + os.sep)):
                        raise UpdateError(f"The archive has a link that points outside its folder ({member.name}).")
                    os.symlink(member.linkname, target)
                    links.append(target)
                else:
                    raise UpdateError(f"The archive contains something that is not a file or folder ({member.name}).")
        for link in links:  # a link can become dangerous only when a LATER link exists: look again at the end
            landing = os.path.realpath(link)
            if landing != root and not landing.startswith(root + os.sep):
                raise UpdateError(f"The archive has a link that ends up outside its folder ({os.path.relpath(link, root)}).")
    except (tarfile.TarError, EOFError, lzma.LZMAError, zlib.error) as e:
        raise UpdateError(f"The archive is damaged: {e}") from e
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise UpdateError("There is not enough free disk space to unpack the download.") from e
        raise UpdateError(f"Could not unpack the download: {e.strerror or e}") from e
    return files
`````

Create `src/xampp_panel/updates/fsops.py`:

`````python
"""File-tree helpers for snapshots."""

import os
import shutil
import stat
from pathlib import Path

_FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK  # NONBLOCK: a swapped-in FIFO must not hang the copy
_SPECIAL = "cannot copy {}: it is not a file, folder or link"


def copy_owned(src, dst, chown=os.chown) -> None:
    """Copy a file, link or folder tree with its owner, group, mode and times, like `cp -a` (but without
    ACLs, extended attributes or hard links, which become separate copies).

    Safe to run as root over folders that others can write (Apache's `daemon` owns phpMyAdmin's cache):
    nothing is followed through a link, an entry swapped for another kind while copying is refused, and
    what is copied stays private (0700 / 0600) until its real owner and mode are applied last.
    """
    src, dst = Path(src), Path(dst)
    info = os.lstat(src)
    if stat.S_ISDIR(info.st_mode):
        fd = os.open(src, _FOLDER)
        try:
            _copy_folder(fd, dst, chown)
        finally:
            os.close(fd)
    elif stat.S_ISREG(info.st_mode):
        _copy_file(os.open(src, _FILE), dst, chown)
    elif stat.S_ISLNK(info.st_mode):
        _copy_link(os.readlink(src), dst, info, chown)
    else:
        raise OSError(_SPECIAL.format(src))


def _copy_link(target: str, dst: Path, info, chown) -> None:
    os.symlink(target, dst)
    chown(dst, info.st_uid, info.st_gid, follow_symlinks=False)


def _finish(dst: Path, info, chown) -> None:
    chown(dst, info.st_uid, info.st_gid)
    os.chmod(dst, stat.S_IMODE(info.st_mode))  # after chown, which clears set-uid/set-gid bits
    os.utime(dst, ns=(info.st_atime_ns, info.st_mtime_ns))


def _copy_file(fd: int, dst: Path, chown) -> None:
    """Copy the open file `fd` (closed here) to `dst`."""
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError(_SPECIAL.format(dst.name))
        out = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, "wb") as target:
            shutil.copyfileobj(source, target)
    _finish(dst, info, chown)


def _copy_folder(fd: int, dst: Path, chown) -> None:
    """Copy the folder open as `fd` to a new folder `dst`, reading children relative to `fd`."""
    info = os.fstat(fd)
    os.mkdir(dst, 0o700)
    for name in sorted(os.listdir(fd)):
        child = dst / name
        entry = os.lstat(name, dir_fd=fd)
        if stat.S_ISLNK(entry.st_mode):
            _copy_link(os.readlink(name, dir_fd=fd), child, entry, chown)
        elif stat.S_ISDIR(entry.st_mode):
            sub = os.open(name, _FOLDER, dir_fd=fd)
            try:
                _copy_folder(sub, child, chown)
            finally:
                os.close(sub)
        elif stat.S_ISREG(entry.st_mode):
            _copy_file(os.open(name, _FILE, dir_fd=fd), child, chown)
        else:
            raise OSError(_SPECIAL.format(child.name))
    _finish(dst, info, chown)
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_*.py"` — Expected: `Ran 174 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 433 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/test_update_fetcher.py tests/test_update_archive.py tests/test_update_fsops.py src/xampp_panel/updates/fetcher.py src/xampp_panel/updates/archive.py src/xampp_panel/updates/fsops.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: resumable verified downloads, link-safe unpacking and race-safe owner-preserving copy"
`````

---

### Task 4: PGP signature verification

Verify a detached signature with a throwaway `gpg` home folder and accept it only when `VALIDSIG` names a pinned primary-key fingerprint.

The unit tests use gpg's real status-line format captured on 2026-10-08. The real-`gpg` step below also checks the real thing against the genuine phpMyAdmin 5.2.3 release; do not skip it.

**Files:**
- Create: `src/xampp_panel/updates/gpg.py`
- Create: `tests/test_update_gpg.py`

**Interfaces:**
- Consumes: Task 1: `UpdateError`, `PMA_SIGNERS`.
- Produces: `gpg.Gpg(run=subprocess.run, binary="gpg").verify(data, signature, keyring_bytes, allowed_fingerprints) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_gpg.py`:

`````python
import os
import subprocess
import unittest
from pathlib import Path

from xampp_panel.updates.base import UpdateError
from xampp_panel.updates.gpg import Gpg

BENNETCH = "3D06A59ECE730EB71B511C17CE752F178259BD92"
# What `gpg --status-fd 1 --verify` really printed for phpMyAdmin 5.2.3 on 2026-10-08.
GOOD_STATUS = (
    "[GNUPG:] NEWSIG\n"
    "[GNUPG:] KEY_CONSIDERED 3D06A59ECE730EB71B511C17CE752F178259BD92 0\n"
    "[GNUPG:] SIG_ID abc 2025-10-07 1759869786\n"
    "[GNUPG:] KEY_CONSIDERED 3D06A59ECE730EB71B511C17CE752F178259BD92 0\n"
    "[GNUPG:] GOODSIG CE752F178259BD92 Isaac Bennetch <bennetch@gmail.com>\n"
    f"[GNUPG:] VALIDSIG {BENNETCH} 2025-10-07 1759869786 0 4 0 1 10 00 {BENNETCH}\n"
    "[GNUPG:] TRUST_UNDEFINED 0 pgp\n"
)


class ScriptedRun:
    """Answers the gpg --import call and the gpg --verify call in turn."""

    def __init__(self, import_code=0, verify_code=0, verify_out=GOOD_STATUS, error=None):
        self.import_code, self.verify_code, self.verify_out, self.error = import_code, verify_code, verify_out, error
        self.calls = []
        self.home_modes = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.error:
            raise self.error
        home = argv[argv.index("--homedir") + 1]
        self.home_modes.append(os.stat(home).st_mode & 0o777)
        if "--import" in argv:
            self.keys_seen = Path(argv[-1]).read_bytes()
            return subprocess.CompletedProcess(argv, self.import_code, "", "")
        return subprocess.CompletedProcess(argv, self.verify_code, self.verify_out, "")


class GpgTest(unittest.TestCase):
    def verify(self, run, allowed=(BENNETCH,)):
        return Gpg(run).verify("/tmp/data", "/tmp/data.asc", b"KEYS", allowed)

    def test_good_signature_by_a_pinned_key_returns_the_fingerprint(self):
        run = ScriptedRun()
        self.assertEqual(self.verify(run), BENNETCH)
        self.assertEqual(run.keys_seen, b"KEYS")

    def test_uses_a_private_throwaway_home_and_a_clean_environment(self):
        run = ScriptedRun()
        self.verify(run)
        self.assertEqual(run.home_modes, [0o700, 0o700])
        argv, kwargs = run.calls[1]
        self.assertEqual(argv[:1], ["gpg"])
        self.assertIn("--batch", argv)
        self.assertIn("--no-autostart", argv)  # no gpg-agent may be left running afterwards
        self.assertEqual(argv[-2:], ["/tmp/data.asc", "/tmp/data"])  # signature first, then the data
        self.assertEqual(kwargs["env"]["LANG"], "C.UTF-8")
        self.assertNotIn("HOME", kwargs["env"])
        self.assertFalse(os.path.exists(argv[argv.index("--homedir") + 1]))  # deleted afterwards

    def test_fingerprints_may_be_given_with_spaces_and_lower_case(self):
        spaced = "3d06 a59e ce73 0eb7 1b51 1c17 ce75 2f17 8259 bd92"
        self.assertEqual(self.verify(ScriptedRun(), allowed=(spaced,)), BENNETCH)

    def test_signature_by_an_unpinned_key_is_refused(self):
        other = "A" * 40
        with self.assertRaisesRegex(UpdateError, "not trusted"):
            self.verify(ScriptedRun(), allowed=(other,))

    def test_subkey_signature_is_judged_by_the_primary_key(self):
        subkey = "B" * 40
        status = GOOD_STATUS.replace(f"VALIDSIG {BENNETCH}", f"VALIDSIG {subkey}")
        self.assertEqual(self.verify(ScriptedRun(verify_out=status)), BENNETCH)

    def test_bad_expired_or_revoked_signatures_are_refused(self):
        for bad in ("BADSIG", "EXPKEYSIG", "REVKEYSIG", "EXPSIG", "ERRSIG"):
            status = GOOD_STATUS + f"[GNUPG:] {bad} CE752F178259BD92 x\n"
            with self.assertRaisesRegex(UpdateError, "not valid", msg=bad):
                self.verify(ScriptedRun(verify_out=status))

    def test_nonzero_exit_is_refused_even_with_good_looking_output(self):
        with self.assertRaisesRegex(UpdateError, "not valid"):
            self.verify(ScriptedRun(verify_code=1))

    def test_no_signature_status_at_all_is_refused(self):
        with self.assertRaisesRegex(UpdateError, "not valid"):
            self.verify(ScriptedRun(verify_out="[GNUPG:] NO_PUBKEY CE752F178259BD92\n"))

    def test_goodsig_without_validsig_is_refused(self):
        status = "[GNUPG:] GOODSIG CE752F178259BD92 someone\n"
        with self.assertRaisesRegex(UpdateError, "tied to a key"):
            self.verify(ScriptedRun(verify_out=status))

    def test_unreadable_keyring_is_refused(self):
        with self.assertRaisesRegex(UpdateError, "could not be read"):
            self.verify(ScriptedRun(import_code=2))

    def test_missing_gpg_tells_the_user_how_to_install_it(self):
        with self.assertRaisesRegex(UpdateError, "sudo apt install gnupg"):
            self.verify(ScriptedRun(error=FileNotFoundError("gpg")))

    def test_hung_gpg_is_reported(self):
        with self.assertRaisesRegex(UpdateError, "did not finish"):
            self.verify(ScriptedRun(error=subprocess.TimeoutExpired("gpg", 120)))
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_gpg.py" -v`

Expected: FAIL — ImportError: Failed to import test module: test_update_gpg (FAILED (errors=1)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/gpg.py`:

`````python
"""Verify detached PGP signatures against pinned key fingerprints."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from .base import UpdateError

_BAD_STATUSES = ("BADSIG", "EXPKEYSIG", "REVKEYSIG", "EXPSIG", "ERRSIG")
_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


class Gpg:
    def __init__(self, run=subprocess.run, binary: str = "gpg"):
        self.run = run
        self.binary = binary

    def _gpg(self, argv: list[str]) -> subprocess.CompletedProcess:
        try:
            return self.run([self.binary, *argv], capture_output=True, text=True, timeout=120, env=_ENV)
        except FileNotFoundError:
            raise UpdateError("gpg is not installed, so signatures cannot be checked: sudo apt install gnupg") from None
        except subprocess.TimeoutExpired:
            raise UpdateError("gpg did not finish in time while checking the signature.") from None

    def verify(self, data, signature, keyring: bytes, allowed: Iterable[str]) -> str:
        """Check that `signature` is a good signature of `data` made by a key whose primary
        fingerprint is in `allowed`. Returns that fingerprint, or raises UpdateError.

        The keyring is only key material in a throwaway home folder; what is trusted is `allowed`.
        """
        pinned = {fingerprint.replace(" ", "").upper() for fingerprint in allowed}
        with tempfile.TemporaryDirectory(prefix="xampp-gpg-") as home:
            os.chmod(home, 0o700)
            keys = Path(home) / "keys.asc"
            keys.write_bytes(keyring)
            # --no-autostart: checking a signature needs no agent, and a started one would outlive
            # the throwaway home folder as a stray background process.
            base = ["--homedir", home, "--batch", "--no-tty", "--no-autostart"]
            if self._gpg([*base, "--import", str(keys)]).returncode != 0:
                raise UpdateError("The signing keys could not be read, so the signature was not trusted.")
            proc = self._gpg([*base, "--status-fd", "1", "--verify", str(signature), str(data)])
        statuses = [line.split()[1:] for line in (proc.stdout or "").splitlines() if line.startswith("[GNUPG:] ")]
        names = [fields[0] for fields in statuses if fields]
        if proc.returncode != 0 or "GOODSIG" not in names or any(name in names for name in _BAD_STATUSES):
            raise UpdateError("The signature on the download is not valid, so it was refused.")
        for fields in statuses:
            if fields and fields[0] == "VALIDSIG" and len(fields) >= 10:
                primary = fields[-1].upper()  # the last field is the primary key, whichever subkey signed
                if primary in pinned:
                    return primary
                raise UpdateError(f"The download is signed by a key that is not trusted ({primary}), so it was refused.")
        raise UpdateError("The signature could not be tied to a key, so the download was refused.")
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_gpg.py" -v` — Expected: `Ran 12 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 445 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Check the verifier against the genuine phpMyAdmin release**

The unit tests use a fake `gpg`. This step runs the real one. It needs network access and `gpg` on the machine. Run from the repository root (use your system `gpg`; the class looks for it on a fixed system `PATH`, so on a normal Zorin/Ubuntu install `gpg` is found without any argument):

`````bash
S=$(mktemp -d) && cd "$S" && python3 -I - <<'EOF'
import sys, urllib.request
sys.path.insert(0, "$PWD/src")
from xampp_panel.updates.gpg import Gpg
from xampp_panel.updates.config import PMA_SIGNERS
from xampp_panel.updates.base import UpdateError
base = "https://files.phpmyadmin.net/phpMyAdmin/5.2.3/phpMyAdmin-5.2.3-all-languages.tar.xz"
def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    open(dest, "wb").write(data); return data
fetch(base, "pma.tar.xz"); fetch(base + ".asc", "pma.asc")
ring = fetch("https://files.phpmyadmin.net/phpmyadmin.keyring", "ring")
gpg = Gpg()
print("good signature ->", gpg.verify("pma.tar.xz", "pma.asc", ring, PMA_SIGNERS))
for label, allowed, name in (("unpinned key", ["A" * 40], "pma.tar.xz"), ("tampered file", PMA_SIGNERS, "tampered.tar.xz")):
    if name == "tampered.tar.xz":
        data = bytearray(open("pma.tar.xz", "rb").read()); data[1000] ^= 1; open(name, "wb").write(data)
    try:
        gpg.verify(name, "pma.asc", ring, allowed)
        print(label, "-> WRONGLY ACCEPTED")
    except UpdateError as e:
        print(label, "-> refused:", e)
EOF
cd - >/dev/null; rm -rf "$S"
`````

Expected (verified in the build sandbox on 2026-10-08):

`````
good signature -> 3D06A59ECE730EB71B511C17CE752F178259BD92
unpinned key -> refused: The download is signed by a key that is not trusted (3D06A59E…), so it was refused.
tampered file -> refused: The signature on the download is not valid, so it was refused.
`````

If `gpg` starts a background `gpg-agent` (check with `pgrep gpg-agent`), stop: `--no-autostart` must prevent that.

- [ ] **Step 6: Commit**

`````bash
git add tests/test_update_gpg.py src/xampp_panel/updates/gpg.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: verify detached PGP signatures against pinned fingerprints"
`````

---

### Task 5: Paths, settings keys, dialog title, restore points and snapshots

Add the new locations to `Paths` (snapshots live in `/var/backups/xampp-panel`, outside the folder `uninstall.sh` deletes), the "Later"/"Hide" settings maps, a title option for the whiptail dialogs, the public restore-points file and the snapshot store.

Existing tests in `test_settings.py` pinned `{"tray": False}`; they change to the three-key shape. `Paths.backups` is a dataclass field (not derived from `app`) on purpose, and every new test passes its own `backups=` so nothing can touch the real `/var/backups`.

**Files:**
- Create: `src/xampp_panel/updates/restore_points.py`
- Create: `src/xampp_panel/updates/snapshots.py`
- Create: `tests/test_update_snapshots.py`
- Modify: `src/xampp_panel/paths.py`
- Modify: `src/xampp_panel/settings.py`
- Modify: `src/xampp_panel/dialogs.py`
- Modify: `tests/test_paths.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_dialogs.py`

**Interfaces:**
- Consumes: Task 1 `UpdateError`.
- Produces: `Paths.backups`, `.pma_dir`, `.php_bin`, `.updater`, `.update_cache`, `.restore_points`; settings keys `dismissed_updates` and `dismissed_restore` (string-to-string maps); `Dialogs(..., title=TITLE)`; `restore_points.RestorePoint/load/save/recent`; `snapshots.Snapshots(paths, clock)` with `get/points/require_no_pending/begin/commit/abort/discard`, `Snapshot`, `PENDING`, `READY`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_snapshots.py`:

`````python
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from xampp_panel.paths import Paths
from xampp_panel.updates import restore_points
from xampp_panel.updates.base import UpdateError
from xampp_panel.updates.restore_points import RestorePoint
from xampp_panel.updates.snapshots import PENDING, READY, Snapshots

T0 = datetime(2026, 10, 8, 20, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


class SnapshotsBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "app/state").mkdir(parents=True)
        self.paths = Paths(lampp=self.root / "lampp", app=self.root / "app", backups=self.root / "backups")
        self.clock = Clock()
        self.snaps = Snapshots(self.paths, self.clock)

    def tearDown(self):
        self._tmp.cleanup()


class RestorePointsFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "restore-points.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_and_world_readable(self):
        point = RestorePoint("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3", "2026-10-08T20:00:00+00:00")
        restore_points.save(self.file, [point])
        self.assertEqual(restore_points.load(self.file), [point])
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)

    def test_missing_damaged_or_odd_files_mean_no_points(self):
        self.assertEqual(restore_points.load(self.file), [])
        for text in ("{not json", "[]", '{"restore_points": 5}', '{"restore_points": [1, "x"]}',
                     '{"restore_points": [{"component": "a"}]}'):
            self.file.write_text(text)
            self.assertEqual(restore_points.load(self.file), [], text)

    def test_bad_entries_are_skipped_good_ones_kept(self):
        good = {"component": "a", "title": "A", "from_version": "1.0", "to_version": "2.0", "created": "x"}
        self.file.write_text(json.dumps({"restore_points": [good, {"component": 3}]}))
        self.assertEqual([p.component for p in restore_points.load(self.file)], ["a"])

    def test_recent_keeps_only_the_last_days(self):
        def point(created):
            return RestorePoint("a", "A", "1.0", "2.0", created)
        now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        points = [point("2026-10-14T00:00:00+00:00"), point("2026-10-07T00:00:00+00:00"),
                  point("garbage"), point("2026-10-10T12:00:00")]  # naive time counts as UTC
        kept = restore_points.recent(points, now, 7)
        self.assertEqual([p.created for p in kept], ["2026-10-14T00:00:00+00:00", "2026-10-10T12:00:00"])


class SnapshotsTest(SnapshotsBase):
    def test_nothing_before_the_first_update(self):
        self.assertIsNone(self.snaps.get("phpmyadmin"))
        self.assertEqual(self.snaps.points(), [])

    def test_begin_creates_a_private_pending_snapshot(self):
        snap = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3", {"parked": "/x"})
        self.assertEqual(snap.status, PENDING)
        for folder in (self.paths.backups, self.paths.backups / "phpmyadmin", snap.folder):
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700, folder)
        self.assertEqual((snap.folder / "manifest.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.snaps.get("phpmyadmin"), snap)
        self.assertEqual(self.snaps.points(), [])  # not a restore point until it finishes
        self.assertFalse(self.paths.restore_points.exists())

    def test_commit_makes_a_restore_point_and_publishes_it(self):
        snap = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3", {"parked": "/x"})
        done = self.snaps.commit(snap)
        self.assertEqual(done.status, READY)
        self.assertEqual(self.snaps.get("phpmyadmin").data, {"parked": "/x"})
        expected = [RestorePoint("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3", snap.created)]
        self.assertEqual(self.snaps.points(), expected)
        self.assertEqual(restore_points.load(self.paths.restore_points), expected)
        self.assertEqual(self.paths.restore_points.stat().st_mode & 0o777, 0o644)

    def test_a_new_commit_deletes_the_older_snapshot(self):
        first = self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.0", "5.2.1"))
        second = self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        self.assertFalse(first.folder.exists())
        self.assertTrue(second.folder.exists())
        self.assertEqual(self.snaps.get("phpmyadmin").from_version, "5.2.1")

    def test_older_restore_point_survives_while_a_new_update_is_pending(self):
        first = self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.0", "5.2.1"))
        pending = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        self.assertTrue(first.folder.exists())
        self.assertEqual(self.snaps.get("phpmyadmin"), pending)
        self.snaps.abort(pending)
        self.assertEqual(self.snaps.get("phpmyadmin").to_version, "5.2.1")

    def test_a_pending_snapshot_blocks_the_next_update_with_advice(self):
        self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        with self.assertRaisesRegex(UpdateError, "did not finish.*Restore previous version"):
            self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")

    def test_abort_forgets_the_snapshot(self):
        snap = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        self.snaps.abort(snap)
        self.assertIsNone(self.snaps.get("phpmyadmin"))

    def test_discard_removes_everything_and_updates_the_index(self):
        self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        self.snaps.discard("phpmyadmin")
        self.assertIsNone(self.snaps.get("phpmyadmin"))
        self.assertEqual(restore_points.load(self.paths.restore_points), [])

    def test_components_do_not_interfere(self):
        self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        self.snaps.commit(self.snaps.begin("mariadb", "MySQL (MariaDB)", "10.4.32", "11.8.9"))
        self.assertEqual([p.component for p in self.snaps.points()], ["mariadb", "phpmyadmin"])
        self.snaps.discard("mariadb")
        self.assertEqual([p.component for p in self.snaps.points()], ["phpmyadmin"])

    def test_damaged_manifests_are_ignored(self):
        good = self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        for number, text in enumerate(("{oops", '{"component": "phpmyadmin"}', '[]',
                                       json.dumps({"component": "other", "title": "t", "from_version": "1",
                                                   "to_version": "2", "created": "c", "status": "ready"}),
                                       json.dumps({"component": "phpmyadmin", "title": "t", "from_version": "1",
                                                   "to_version": "2", "created": "c", "status": "weird"}),
                                       json.dumps({"component": "phpmyadmin", "title": "t", "from_version": "1",
                                                   "to_version": "2", "created": "c", "status": "ready",
                                                   "data": {"k": 5}}))):
            folder = self.paths.backups / "phpmyadmin" / f"9999{number}"  # sorts after the good one
            folder.mkdir()
            (folder / "manifest.json").write_text(text)
        self.assertEqual(self.snaps.get("phpmyadmin"), good)

    def test_pending_snapshot_from_a_killed_run_is_found(self):
        snap = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        again = Snapshots(self.paths, self.clock).get("phpmyadmin")
        self.assertEqual(again.status, PENDING)
        self.assertEqual(again.folder, snap.folder)


class NestedJsonTest(SnapshotsBase):
    def test_absurdly_nested_files_are_ignored_not_crashes(self):
        good = self.snaps.commit(self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        deep = "[" * 100_000 + "]" * 100_000
        folder = self.paths.backups / "phpmyadmin" / "99999"
        folder.mkdir()
        (folder / "manifest.json").write_text(deep)
        self.assertEqual(self.snaps.get("phpmyadmin"), good)
        self.paths.restore_points.write_text(deep)
        self.assertEqual(restore_points.load(self.paths.restore_points), [])


class IndexIsBestEffortTest(SnapshotsBase):
    def test_a_failing_index_write_does_not_fail_the_commit(self):
        from unittest import mock
        snap = self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        with mock.patch("xampp_panel.updates.snapshots.restore_points.save", side_effect=OSError("read-only")):
            done = self.snaps.commit(snap)
        self.assertEqual(done.status, READY)
        self.assertEqual(self.snaps.get("phpmyadmin").status, READY)

    def test_require_no_pending(self):
        self.snaps.require_no_pending("phpmyadmin", "phpMyAdmin")  # nothing yet: fine
        self.snaps.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        with self.assertRaisesRegex(UpdateError, "did not finish"):
            self.snaps.require_no_pending("phpmyadmin", "phpMyAdmin")


if __name__ == "__main__":
    unittest.main()
`````

Modify `tests/test_paths.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/test_paths.py
+++ b/tests/test_paths.py
@@ -26,3 +26,18 @@
         self.assertEqual(p.mysql_upgrade, Path("/l/bin/mysql_upgrade"))
         self.assertEqual(p.proftpd_bin, Path("/l/sbin/proftpd"))
         self.assertEqual(p.repair, Path("/a/bin/xampp-repair"))
+
+
+class UpdatePathsTest(unittest.TestCase):
+    def test_update_paths(self):
+        p = Paths(lampp=Path("/l"), app=Path("/a"), backups=Path("/b"))
+        self.assertEqual(p.pma_dir, Path("/l/phpmyadmin"))
+        self.assertEqual(p.php_bin, Path("/l/bin/php"))
+        self.assertEqual(p.updater, Path("/a/bin/xampp-update"))
+        self.assertEqual(p.update_cache, Path("/a/cache"))
+        self.assertEqual(p.restore_points, Path("/a/state/restore-points.json"))
+        self.assertEqual(p.backups, Path("/b"))
+
+    def test_snapshots_live_outside_the_folder_uninstall_removes(self):
+        self.assertEqual(DEFAULT.backups, Path("/var/backups/xampp-panel"))
+        self.assertNotIn(DEFAULT.app, DEFAULT.backups.parents)
`````

Modify `tests/test_settings.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/test_settings.py
+++ b/tests/test_settings.py
@@ -5,6 +5,9 @@
 from xampp_panel import settings
 
 
+DEFAULT_ALL = {"tray": False, "dismissed_updates": {}, "dismissed_restore": {}}
+
+
 class SettingsTest(unittest.TestCase):
     def setUp(self):
         self._tmp = tempfile.TemporaryDirectory()
@@ -14,21 +17,21 @@
         self._tmp.cleanup()
 
     def test_defaults_when_missing_or_corrupt(self):
-        self.assertEqual(settings.load(self.file), {"tray": False})
+        self.assertEqual(settings.load(self.file), DEFAULT_ALL)
         self.file.parent.mkdir(parents=True)
         self.file.write_text("{not json")
-        self.assertEqual(settings.load(self.file), {"tray": False})
+        self.assertEqual(settings.load(self.file), DEFAULT_ALL)
         self.file.write_text("[1, 2]")
-        self.assertEqual(settings.load(self.file), {"tray": False})
+        self.assertEqual(settings.load(self.file), DEFAULT_ALL)
 
     def test_round_trip_is_private(self):
         settings.save({"tray": True}, self.file)
-        self.assertEqual(settings.load(self.file), {"tray": True})
+        self.assertEqual(settings.load(self.file), {**DEFAULT_ALL, "tray": True})
         self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
 
     def test_unknown_keys_are_dropped(self):
         settings.save({"tray": True, "evil": 1}, self.file)
-        self.assertEqual(settings.load(self.file), {"tray": True})
+        self.assertEqual(settings.load(self.file), {**DEFAULT_ALL, "tray": True})
 
     def test_config_path_honours_xdg(self):
         self.assertEqual(settings.config_path({"XDG_CONFIG_HOME": "/x"}), Path("/x/xampp-panel/settings.json"))
@@ -36,6 +39,25 @@
     def test_wrongly_typed_values_are_rejected(self):
         self.file.parent.mkdir(parents=True)
         self.file.write_text('{"tray": "false"}')
-        self.assertEqual(settings.load(self.file), {"tray": False})
+        self.assertEqual(settings.load(self.file), DEFAULT_ALL)
         self.file.write_text('{"tray": 1}')
-        self.assertEqual(settings.load(self.file), {"tray": False})
+        self.assertEqual(settings.load(self.file), DEFAULT_ALL)
+
+    def test_dismissed_maps_round_trip(self):
+        data = {"tray": False, "dismissed_updates": {"phpmyadmin": "5.2.3"},
+                "dismissed_restore": {"phpmyadmin": "2026-10-08T20:00:00+00:00"}}
+        settings.save(data, self.file)
+        self.assertEqual(settings.load(self.file), data)
+
+    def test_dismissed_maps_must_be_string_to_string(self):
+        self.file.parent.mkdir(parents=True)
+        for bad in ('{"dismissed_updates": {"phpmyadmin": 5}}', '{"dismissed_updates": ["x"]}',
+                    '{"dismissed_updates": {"a": {"b": "c"}}}', '{"dismissed_restore": "x"}'):
+            self.file.write_text(bad)
+            self.assertEqual(settings.load(self.file), DEFAULT_ALL, bad)
+
+    def test_defaults_are_never_shared_between_loads(self):
+        first = settings.load(self.file)
+        first["dismissed_updates"]["phpmyadmin"] = "9.9.9"
+        self.assertEqual(settings.load(self.file)["dismissed_updates"], {})
+        self.assertEqual(settings.DEFAULTS["dismissed_updates"], {})
`````

Modify `tests/test_dialogs.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/test_dialogs.py
+++ b/tests/test_dialogs.py
@@ -25,6 +25,11 @@
         self.assertEqual(kwargs["stderr"], subprocess.PIPE)
         self.assertNotIn("stdout", kwargs)  # whiptail draws on the terminal
 
+    def test_title_can_be_changed(self):
+        run = Run(stderr="1")
+        Dialogs(run, title="XAMPP updates").menu("Pick:", [("1", "One")])
+        self.assertEqual(run.calls[0][0][:3], ["whiptail", "--title", "XAMPP updates"])
+
     def test_cancel_returns_none(self):
         self.assertIsNone(Dialogs(Run(returncode=1)).menu("Pick:", [("1", "One")]))
         self.assertIsNone(Dialogs(Run(returncode=255)).passwordbox("Password:"))
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"`

Expected: FAIL — TypeError: Dialogs.__init__() got an unexpected keyword argument 'title' (FAILED (failures=6, errors=5, skipped=1)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/restore_points.py`:

`````python
"""The public list of restore points (/opt/xampp-panel/state/restore-points.json).

The root tool writes it; the panel reads it without root, like sites.json. It holds no secrets.
"""

import json
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .. import fsutil


@dataclass(frozen=True)
class RestorePoint:
    component: str  # e.g. "phpmyadmin"
    title: str  # e.g. "phpMyAdmin"
    from_version: str  # the version the restore brings back
    to_version: str  # the version the update installed
    created: str  # ISO 8601 with offset


_FIELDS = [f.name for f in fields(RestorePoint)]


def load(path) -> list[RestorePoint]:
    """Tolerant read: a missing, damaged or oddly shaped file means "no restore points"."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError, RecursionError):
        return []
    items = data.get("restore_points") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [RestorePoint(**{name: item[name] for name in _FIELDS})
            for item in items if isinstance(item, dict) and all(isinstance(item.get(name), str) for name in _FIELDS)]


def save(path, points: Iterable[RestorePoint]) -> None:
    payload = {"restore_points": [asdict(point) for point in points]}
    fsutil.atomic_write(path, json.dumps(payload, indent=2) + "\n", mode=0o644)


def recent(points: Iterable[RestorePoint], now: datetime, days: int) -> list[RestorePoint]:
    """The restore points created within the last `days` days (unreadable dates are dropped)."""
    cutoff = now - timedelta(days=days)
    keep = []
    for point in points:
        try:
            when = datetime.fromisoformat(point.created)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if cutoff <= when <= now + timedelta(days=1):  # a clock that was ahead must not extend the bar
            keep.append(point)
    return keep
`````

Create `src/xampp_panel/updates/snapshots.py`:

`````python
"""One snapshot per component, kept so "Restore previous version" can go back.

A snapshot is a folder under paths.backups/<component>/<timestamp>/ holding manifest.json. The
component stores whatever else it needs (a path, a copy) and records it in the manifest's `data`.
The public index (restore-points.json) lists only snapshots whose update finished.
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .. import fsutil
from ..paths import DEFAULT, Paths
from . import restore_points
from .base import UpdateError

MANIFEST = "manifest.json"
PENDING = "pending"  # the update started and has not finished (or the tool was killed half way)
READY = "ready"  # the update finished: a restore point


@dataclass(frozen=True)
class Snapshot:
    component: str
    title: str
    from_version: str
    to_version: str
    created: str
    status: str
    folder: Path
    data: Mapping[str, str] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Snapshots:
    def __init__(self, paths: Paths = DEFAULT, clock=_utc_now):
        self.paths = paths
        self.clock = clock

    # -- reading ----------------------------------------------------------
    def _folders(self, key: str) -> list[Path]:
        base = self.paths.backups / key
        try:
            return sorted(entry for entry in base.iterdir() if entry.is_dir())
        except OSError:
            return []

    @staticmethod
    def _read(folder: Path, key: str) -> Snapshot | None:
        try:
            raw = json.loads((folder / MANIFEST).read_text())
        except (OSError, ValueError, RecursionError):
            return None
        names = ("component", "title", "from_version", "to_version", "created", "status")
        if not isinstance(raw, dict) or any(not isinstance(raw.get(name), str) for name in names):
            return None
        data = raw.get("data", {})
        if raw["component"] != key or raw["status"] not in (PENDING, READY) or not isinstance(data, dict) \
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
            return None
        return Snapshot(*(raw[name] for name in names), folder=folder, data=data)

    def get(self, key: str) -> Snapshot | None:
        """The newest snapshot of a component, finished or not."""
        for folder in reversed(self._folders(key)):
            snapshot = self._read(folder, key)
            if snapshot is not None:
                return snapshot
        return None

    def points(self) -> list[restore_points.RestorePoint]:
        """The restore points: the newest snapshot of each component, if its update finished."""
        try:
            keys = sorted(entry.name for entry in self.paths.backups.iterdir() if entry.is_dir())
        except OSError:
            return []
        found = []
        for key in keys:
            snapshot = self.get(key)
            if snapshot is not None and snapshot.status == READY:
                found.append(restore_points.RestorePoint(
                    snapshot.component, snapshot.title, snapshot.from_version, snapshot.to_version, snapshot.created))
        return found

    # -- writing (root) ---------------------------------------------------
    def _write_manifest(self, snapshot: Snapshot) -> None:
        payload = {"component": snapshot.component, "title": snapshot.title,
                   "from_version": snapshot.from_version, "to_version": snapshot.to_version,
                   "created": snapshot.created, "status": snapshot.status, "data": dict(snapshot.data)}
        fsutil.atomic_write(snapshot.folder / MANIFEST, json.dumps(payload, indent=2) + "\n", mode=0o600)

    def _write_index(self) -> None:
        """Publish the list for the panel. Best effort: the snapshots themselves are what counts."""
        try:
            index = self.paths.restore_points
            index.parent.mkdir(parents=True, exist_ok=True)
            restore_points.save(index, self.points())
        except OSError:
            pass

    def require_no_pending(self, key: str, title: str) -> None:
        """Refuse to start while an earlier update of this component never finished."""
        earlier = self.get(key)
        if earlier is not None and earlier.status == PENDING:
            raise UpdateError(f"An earlier update of {title} did not finish. "
                              "Choose \"Restore previous version\" first to put things back.")

    def begin(self, key: str, title: str, from_version: str, to_version: str,
              data: Mapping[str, str] | None = None) -> Snapshot:
        """Start a snapshot for an update that is about to change things."""
        self.require_no_pending(key, title)
        now = self.clock()
        for folder in (self.paths.backups, self.paths.backups / key):
            folder.mkdir(mode=0o700, exist_ok=True)
            os.chmod(folder, 0o700)
        folder = self.paths.backups / key / now.strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(mode=0o700)
        snapshot = Snapshot(key, title, from_version, to_version, now.isoformat(timespec="seconds"),
                            PENDING, folder, dict(data or {}))
        self._write_manifest(snapshot)
        return snapshot

    def commit(self, snapshot: Snapshot) -> Snapshot:
        """The update finished: this snapshot becomes the restore point and older ones are deleted."""
        done = Snapshot(snapshot.component, snapshot.title, snapshot.from_version, snapshot.to_version,
                        snapshot.created, READY, snapshot.folder, snapshot.data)
        self._write_manifest(done)
        for folder in self._folders(snapshot.component):
            if folder != snapshot.folder:
                shutil.rmtree(folder, ignore_errors=True)
        self._write_index()
        return done

    def abort(self, snapshot: Snapshot) -> None:
        """The update failed and was rolled back: forget this snapshot."""
        shutil.rmtree(snapshot.folder, ignore_errors=True)

    def discard(self, key: str) -> None:
        """A restore finished: the component has no restore point any more."""
        for folder in self._folders(key):
            shutil.rmtree(folder, ignore_errors=True)
        self._write_index()
`````

Modify `src/xampp_panel/paths.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/src/xampp_panel/paths.py
+++ b/src/xampp_panel/paths.py
@@ -11,6 +11,8 @@
     hosts: Path = Path("/etc/hosts")
     proc: Path = Path("/proc")
     runtime: Path = Path("/run/xampp-panel")  # tmpfs: xampp-repair's short-lived files, gone at reboot
+    # Snapshots for "Restore previous version". Outside `app` on purpose: uninstall.sh removes `app`.
+    backups: Path = Path("/var/backups/xampp-panel")
 
     @property
     def lampp_script(self) -> Path:
@@ -73,6 +75,14 @@
         return self.lampp / "phpmyadmin/sql/create_tables.sql"
 
     @property
+    def pma_dir(self) -> Path:
+        return self.lampp / "phpmyadmin"
+
+    @property
+    def php_bin(self) -> Path:
+        return self.lampp / "bin/php"
+
+    @property
     def helper(self) -> Path:
         return self.app / "bin/xampp-helper"
 
@@ -85,6 +95,20 @@
         return self.app / "bin/xampp-repair"
 
     @property
+    def updater(self) -> Path:
+        return self.app / "bin/xampp-update"
+
+    @property
+    def update_cache(self) -> Path:
+        """Root-only scratch folder for downloads (emptied after every update)."""
+        return self.app / "cache"
+
+    @property
+    def restore_points(self) -> Path:
+        """World-readable list of restore points, so the panel can offer a Restore button without root."""
+        return self.app / "state/restore-points.json"
+
+    @property
     def state_file(self) -> Path:
         return self.app / "state/sites.json"
 
`````

Modify `src/xampp_panel/settings.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/src/xampp_panel/settings.py
+++ b/src/xampp_panel/settings.py
@@ -1,12 +1,13 @@
 """Per-user preferences in ~/.config/xampp-panel/settings.json."""
 
+import copy
 import json
 import os
 from pathlib import Path
 
 from . import fsutil
 
-DEFAULTS = {"tray": False}
+DEFAULTS = {"tray": False, "dismissed_updates": {}, "dismissed_restore": {}}
 
 
 def config_path(env=None) -> Path:
@@ -22,11 +23,19 @@
         data = {}
     if not isinstance(data, dict):
         data = {}
-    return {key: data[key] if isinstance(data.get(key), type(default)) else default for key, default in DEFAULTS.items()}
+    return {key: _valid(data.get(key), default) for key, default in DEFAULTS.items()}
+
+
+def _valid(value, default):
+    """`value` if it has the right type (for maps: string keys and string values), else a copy of `default`."""
+    if isinstance(value, type(default)):
+        if not isinstance(value, dict) or all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
+            return value
+    return copy.deepcopy(default)
 
 
 def save(data: dict, path=None) -> None:
     path = Path(path or config_path())
     path.parent.mkdir(parents=True, exist_ok=True)
-    clean = {key: data.get(key, default) for key, default in DEFAULTS.items()}
+    clean = {key: _valid(data.get(key, default), default) for key, default in DEFAULTS.items()}
     fsutil.atomic_write(path, json.dumps(clean, indent=2) + "\n", mode=0o600)
`````

Modify `src/xampp_panel/dialogs.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/src/xampp_panel/dialogs.py
+++ b/src/xampp_panel/dialogs.py
@@ -12,12 +12,13 @@
 
 
 class Dialogs:
-    def __init__(self, run=subprocess.run, height: int = 20, width: int = 74):
+    def __init__(self, run=subprocess.run, height: int = 20, width: int = 74, title: str = TITLE):
         self.run = run
         self.size = [str(height), str(width)]
+        self.title = title
 
     def _show(self, *args: str) -> subprocess.CompletedProcess:
-        return self.run(["whiptail", "--title", TITLE, *args], stderr=subprocess.PIPE, text=True)
+        return self.run(["whiptail", "--title", self.title, *args], stderr=subprocess.PIPE, text=True)
 
     def _answer(self, *args: str) -> str | None:
         proc = self._show(*args)
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"` — Expected: `Ran 469 tests` … `OK (skipped=1)`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 469 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/test_update_snapshots.py src/xampp_panel/updates/restore_points.py src/xampp_panel/updates/snapshots.py src/xampp_panel/paths.py src/xampp_panel/settings.py src/xampp_panel/dialogs.py tests/test_paths.py tests/test_settings.py tests/test_dialogs.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: restore points, snapshot store, new paths, dismissal settings and dialog title"
`````

---

### Task 6: The phpMyAdmin component

Download, verify, swap the phpMyAdmin folder, verify again and roll back automatically on any failure; restore the saved folder on demand; survive a killed run.

Order inside `apply` is the safety argument; keep it: preflight → settle/refuse a pending snapshot → sweep leftovers → download → checksum → signature → unpack → version check → `snapshots.begin` → swap (signals held) → verify → commit. Any failure after `begin` puts the old folder back before the error is reported. `restore` verifies the saved version before it deletes the newer one.

**Files:**
- Create: `src/xampp_panel/updates/pma.py`
- Create: `tests/test_update_pma.py`

**Interfaces:**
- Consumes: Tasks 1–5: `Release`, `Plan`, `UpdateError`, `RollbackFailed`, `critical_section`, `versions`, `PhpMyAdminSource`, `Fetcher`, `verify_hashes`, `archive.safe_extract`, `copy_owned`, `Gpg`, `Snapshots`, `Paths.pma_dir/php_bin/update_cache`.
- Produces: `pma.PhpMyAdminComponent(source, fetcher, gpg, snapshots, paths, config, run, clock, say, probe, apache_running, chown)` implementing the `Component` protocol (key `phpmyadmin`, title `phpMyAdmin`); `pma.version_in(folder) -> str | None`; `pma.probe_http(url, timeout)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_pma.py`:

`````python
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from xampp_panel.paths import Paths
from xampp_panel.updates import restore_points
from xampp_panel.updates.base import RollbackFailed, UpdateError
from xampp_panel.updates.config import UpdateConfig
from xampp_panel.updates.pma import PhpMyAdminComponent
from xampp_panel.updates.releases import PhpMyAdminSource
from xampp_panel.updates.snapshots import PENDING, Snapshots

from update_fakes import FakeTransport, build_tar

CONFIG = UpdateConfig(pma_min_free_bytes=1)
NEW = "5.2.3"
BASE = "https://files.phpmyadmin.net/phpMyAdmin/{v}/phpMyAdmin-{v}-all-languages.tar.xz"
FILES_PAGE = "".join(f'<a href="/files/{v}/">{v}</a>' for v in ("5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4"))
VERSION_JSON = json.dumps({"releases": [{"version": "5.2.3", "php_versions": ">=7.2,<8.4"}]})


def readme(version):
    return f"phpMyAdmin - Readme\n===================\n\nVersion {version}\n"


def tarball(version=NEW, readme_version=None):
    top = f"phpMyAdmin-{version}-all-languages"
    return build_tar([
        (top, "dir", None, 0o755),
        (f"{top}/README", "file", readme(readme_version or version), 0o644),
        (f"{top}/index.php", "file", "<?php // new\n", 0o644),
        (f"{top}/libraries/new.txt", "file", "new", 0o644),
        (f"{top}/config.sample.inc.php", "file", "<?php // sample\n", 0o644),
    ])


class FakeFetcher:
    def __init__(self, files):
        self.files, self.downloads = files, []

    def download(self, url, dest, max_bytes=None):
        self.downloads.append((url, Path(dest).name, max_bytes))
        Path(dest).write_bytes(self.files[url])
        return Path(dest)


class FakeGpg:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def verify(self, data, signature, keyring, allowed):
        self.calls.append((Path(data).name, Path(signature).name, keyring, tuple(allowed)))
        if self.error:
            raise self.error
        return "3D06A59ECE730EB71B511C17CE752F178259BD92"


class PhpRun:
    """Stands in for bin/php: `-v` prints a version, `-l` lints."""

    def __init__(self, php="8.2.12", lint_code=0, lint_error=None):
        self.php, self.lint_code, self.lint_error, self.calls = php, lint_code, lint_error, []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(map(str, argv)))
        if argv[1] == "-v":
            return subprocess.CompletedProcess(argv, 0, f"PHP {self.php} (cli)\n", "")
        if self.lint_error:
            raise self.lint_error
        out = "No syntax errors detected" if self.lint_code == 0 else "Parse error: unexpected end"
        return subprocess.CompletedProcess(argv, self.lint_code, out, "")


class PmaBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "app/state").mkdir(parents=True)
        self.paths = Paths(lampp=self.root / "lampp", app=self.root / "app", backups=self.root / "backups")
        self.live = self.paths.pma_dir
        self.make_live("5.2.1")
        self.messages, self.chowned = [], []

    def tearDown(self):
        self._tmp.cleanup()

    def make_live(self, version):
        d = self.live
        (d / "libraries").mkdir(parents=True)
        (d / "tmp").mkdir()
        (d / "README").write_text(readme(version))
        (d / "index.php").write_text("<?php // old\n")
        (d / "libraries/old.txt").write_text("old")
        (d / "config.inc.php").write_text("<?php // my config\n")
        os.chmod(d / "config.inc.php", 0o640)
        (d / "config.inc.php.xampp-panel.bak").write_text("bak")
        (d / "tmp/cache.txt").write_text("cache")

    def component(self, version=NEW, tar=None, sha=None, gpg_error=None, run=None, apache=False, status=200,
                  config=CONFIG):
        tar = tarball(version) if tar is None else tar
        url = BASE.format(v=version)
        digest = sha or hashlib.sha256(tar).hexdigest()
        self.transport = FakeTransport({
            config.pma_files_url: FILES_PAGE, config.pma_version_json_url: VERSION_JSON,
            url + ".sha256": f"{digest}  phpMyAdmin-{version}-all-languages.tar.xz\n",
            config.pma_keyring_url: b"KEYRING"})
        self.fetcher = FakeFetcher({url: tar, url + ".asc": b"SIGNATURE"})
        self.gpg = FakeGpg(gpg_error)
        self.run = run or PhpRun()
        self.probed = []
        self.snapshots = Snapshots(self.paths)
        self.component_ = PhpMyAdminComponent(
            PhpMyAdminSource(self.transport, config), self.fetcher, self.gpg, self.snapshots, self.paths, config,
            run=self.run, clock=lambda: 1_700_000_000, say=self.messages.append,
            probe=lambda u, t: self.probed.append(u) or status, apache_running=lambda: apache,
            chown=lambda path, uid, gid, **kw: self.chowned.append((Path(path).name, uid, gid)))
        self.target = next(r for r in self.component_.releases() if r.version == version)
        return self.component_

    def leftovers(self):
        return sorted(p.name for p in self.live.parent.iterdir() if p.name != "phpmyadmin" and p.name.startswith("phpmyadmin"))

    def assertOldIsLive(self):
        self.assertEqual(self.component_.installed(), "5.2.1")
        self.assertEqual((self.live / "libraries/old.txt").read_text(), "old")


class InstalledAndPlanTest(PmaBase):
    def test_installed_reads_the_readme(self):
        self.assertEqual(self.component().installed(), "5.2.1")

    def test_installed_is_none_without_a_readme(self):
        comp = self.component()
        (self.live / "README").unlink()
        self.assertIsNone(comp.installed())

    def test_releases_are_newest_first(self):
        self.assertEqual([r.version for r in self.component().releases()], ["5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4"])

    def test_plan_for_an_upgrade_names_the_safety_steps(self):
        plan = self.component().plan(self.target)
        self.assertEqual(plan.kind, "upgrade")
        text = " ".join(plan.summary)
        for needle in ("SHA-256", "PGP", "config.inc.php", "restore point", "5.2.1"):
            self.assertIn(needle, text)
        self.assertEqual(plan.warnings, ())

    def test_plan_kinds(self):
        comp = self.component()
        by_version = {r.version: r for r in comp.releases()}
        self.assertEqual(comp.plan(by_version["5.2.1"]).kind, "reinstall")
        down = comp.plan(by_version["5.2.0"])
        self.assertEqual(down.kind, "downgrade")
        self.assertIn("older phpMyAdmin", down.warnings[0])

    def test_plan_refuses_a_release_that_does_not_support_this_php(self):
        comp = self.component(run=PhpRun(php="8.4.1"))
        with self.assertRaisesRegex(UpdateError, r"needs PHP >=7\.2,<8\.4, but this XAMPP has PHP 8\.4\.1"):
            comp.plan(self.target)

    def test_plan_allows_a_release_whose_php_range_is_unknown(self):
        comp = self.component(run=PhpRun(php="8.4.1"))
        by_version = {r.version: r for r in comp.releases()}
        self.assertEqual(comp.plan(by_version["5.1.4"]).kind, "downgrade")


class ApplyTest(PmaBase):
    def test_upgrade_swaps_the_folder_and_keeps_the_config(self):
        comp = self.component()
        message = comp.apply(self.target)
        self.assertEqual(comp.installed(), "5.2.3")
        self.assertTrue((self.live / "libraries/new.txt").is_file())
        self.assertFalse((self.live / "libraries/old.txt").exists())
        self.assertEqual((self.live / "config.inc.php").read_text(), "<?php // my config\n")
        self.assertEqual((self.live / "config.inc.php").stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.live / "config.inc.php.xampp-panel.bak").read_text(), "bak")
        self.assertEqual((self.live / "tmp/cache.txt").read_text(), "cache")
        self.assertIn("5.2.1 → 5.2.3", message)
        self.assertIn("Restore previous version", message)

    def test_owner_and_group_of_the_kept_files_are_carried_over(self):
        self.component().apply(self.target)
        uid, gid = os.getuid(), os.getgid()
        names = {name for name, u, g in self.chowned}
        self.assertTrue({"config.inc.php", "config.inc.php.xampp-panel.bak", "tmp", "cache.txt"} <= names)
        self.assertTrue(all((u, g) == (self.live.stat().st_uid, self.live.stat().st_gid) for _, u, g in self.chowned))

    def test_download_is_verified_before_use(self):
        comp = self.component()
        comp.apply(self.target)
        name = f"phpMyAdmin-{NEW}-all-languages.tar.xz"
        self.assertEqual([d[:2] for d in self.fetcher.downloads],
                         [(BASE.format(v=NEW), name), (BASE.format(v=NEW) + ".asc", name + ".asc")])
        self.assertEqual(self.gpg.calls, [(name, name + ".asc", b"KEYRING", CONFIG.pma_signers)])
        self.assertIn("Checking the PGP signature…", self.messages)

    def test_the_old_folder_is_saved_as_a_restore_point(self):
        self.component().apply(self.target)
        snap = self.snapshots.get("phpmyadmin")
        self.assertEqual((snap.from_version, snap.to_version, snap.status), ("5.2.1", NEW, "ready"))
        saved = Path(snap.data["parked"])
        self.assertEqual(saved.name, "phpmyadmin.before-5.2.1-20231114221320")
        self.assertEqual((saved / "libraries/old.txt").read_text(), "old")
        points = restore_points.load(self.paths.restore_points)
        self.assertEqual([(p.component, p.from_version, p.to_version) for p in points], [("phpmyadmin", "5.2.1", NEW)])

    def test_nothing_is_left_behind_but_the_saved_copy(self):
        self.component().apply(self.target)
        self.assertEqual(self.leftovers(), ["phpmyadmin.before-5.2.1-20231114221320"])
        self.assertEqual(list(self.paths.update_cache.iterdir()), [])
        self.assertEqual(self.paths.update_cache.stat().st_mode & 0o777, 0o700)

    def test_a_second_update_deletes_the_first_saved_copy(self):
        comp = self.component()
        comp.apply(self.target)
        first_copy = Path(self.snapshots.get("phpmyadmin").data["parked"])
        comp = self.component(version="5.2.2")
        comp.apply(self.target)
        self.assertEqual(comp.installed(), "5.2.2")
        self.assertFalse(first_copy.exists())
        self.assertEqual(self.leftovers(), ["phpmyadmin.before-5.2.3-20231114221320"])
        self.assertEqual(self.snapshots.get("phpmyadmin").from_version, "5.2.3")

    def test_downgrade_works_like_an_upgrade(self):
        comp = self.component(version="5.2.0")
        comp.apply(self.target)
        self.assertEqual(comp.installed(), "5.2.0")

    def test_apache_is_not_probed_when_it_is_stopped(self):
        self.component(apache=False).apply(self.target)
        self.assertEqual(self.probed, [])

    def test_apache_is_probed_when_it_runs(self):
        self.component(apache=True).apply(self.target)
        self.assertEqual(self.probed, [CONFIG.local_probe_url])


class ApplyFailureTest(PmaBase):
    def assertUntouched(self):
        self.assertOldIsLive()
        self.assertEqual((self.live / "config.inc.php").read_text(), "<?php // my config\n")
        self.assertEqual(self.leftovers(), [])
        self.assertIsNone(self.snapshots.get("phpmyadmin"))
        self.assertEqual(list(self.paths.update_cache.iterdir()), [])

    def test_wrong_checksum_changes_nothing(self):
        comp = self.component(sha="0" * 64)
        with self.assertRaisesRegex(UpdateError, "SHA256 checksum"):
            comp.apply(self.target)
        self.assertUntouched()
        self.assertEqual(self.gpg.calls, [])  # refused before the signature was even looked at

    def test_bad_signature_changes_nothing(self):
        comp = self.component(gpg_error=UpdateError("The signature on the download is not valid"))
        with self.assertRaisesRegex(UpdateError, "not valid"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_a_download_that_is_another_version_is_refused(self):
        comp = self.component(tar=tarball(NEW, readme_version="5.2.0"))
        with self.assertRaisesRegex(UpdateError, "is not phpMyAdmin 5.2.3 \\(it says 5.2.0\\)"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_a_damaged_archive_changes_nothing(self):
        tar = tarball()
        comp = self.component(tar=tar[: len(tar) // 2], sha=hashlib.sha256(tar[: len(tar) // 2]).hexdigest())
        with self.assertRaisesRegex(UpdateError, "damaged"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_a_pending_earlier_update_blocks_this_one(self):
        self.component()
        self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.0", "5.2.1")
        with self.assertRaisesRegex(UpdateError, "did not finish"):
            self.component_.apply(self.target)
        self.assertOldIsLive()
        self.assertEqual(self.leftovers(), [])

    def test_php_syntax_error_rolls_back(self):
        comp = self.component(run=PhpRun(lint_code=255))
        with self.assertRaisesRegex(UpdateError, "(?s)Parse error.*previous phpMyAdmin has been put back"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_web_server_not_answering_rolls_back(self):
        comp = self.component(apache=True, status=500)
        with self.assertRaisesRegex(UpdateError, r"does not answer.*status 500"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_web_server_not_reachable_rolls_back(self):
        comp = self.component(apache=True, status=None)
        with self.assertRaisesRegex(UpdateError, r"status none"):
            comp.apply(self.target)
        self.assertUntouched()

    def test_config_changed_during_the_attempt_survives_the_rollback(self):
        comp = self.component(run=PhpRun(lint_code=1))
        original = comp._verify

        def verify_then_edit(version):
            (self.live / "config.inc.php").write_text("<?php // edited meanwhile\n")
            original(version)

        comp._verify = verify_then_edit
        with self.assertRaises(UpdateError):
            comp.apply(self.target)
        self.assertEqual((self.live / "config.inc.php").read_text(), "<?php // edited meanwhile\n")
        self.assertOldIsLive()

    def test_second_rename_failing_undoes_the_first(self):
        comp = self.component()
        real = Path.rename

        def flaky(path, target):
            if Path(target) == self.live and ".new-" in path.name:
                raise OSError("no space left on device")
            return real(path, target)

        with mock.patch.object(Path, "rename", flaky):
            with self.assertRaisesRegex(UpdateError, "no space left on device"):
                comp.apply(self.target)
        self.assertUntouched()

    def test_ctrl_c_during_verification_rolls_back_and_propagates(self):
        comp = self.component(run=PhpRun(lint_error=KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            comp.apply(self.target)
        self.assertUntouched()

    def test_failed_rollback_keeps_the_snapshot_and_explains_how_to_restore_by_hand(self):
        comp = self.component(run=PhpRun(lint_code=1))
        comp._exchange = mock.Mock(side_effect=OSError("disk on fire"))
        with self.assertRaises(RollbackFailed) as ctx:
            comp.apply(self.target)
        text = str(ctx.exception)
        self.assertIn("disk on fire", text)
        self.assertIn("sudo mv", text)
        self.assertIn("phpmyadmin.before-5.2.1", text)
        self.assertEqual(self.snapshots.get("phpmyadmin").status, PENDING)

    def test_missing_folder_symlink_and_low_disk_are_refused_up_front(self):
        comp = self.component()
        low = self.component(config=UpdateConfig(pma_min_free_bytes=10 ** 18))
        with self.assertRaisesRegex(UpdateError, "Not enough free disk space"):
            low.apply(self.target)
        self.assertIsNone(self.snapshots.get("phpmyadmin"))
        link = self.root / "elsewhere"
        self.live.rename(link)
        os.symlink(link, self.live)
        with self.assertRaisesRegex(UpdateError, "normal folder"):
            comp.apply(self.target)
        self.live.unlink()
        link.rename(self.live)
        shutil.rmtree(self.live)
        with self.assertRaisesRegex(UpdateError, "was not found"):
            comp.apply(self.target)


class RestoreTest(PmaBase):
    def updated(self):
        comp = self.component()
        comp.apply(self.target)
        return comp

    def test_restore_brings_the_old_version_back_and_keeps_current_settings(self):
        comp = self.updated()
        (self.live / "config.inc.php").write_text("<?php // changed after the update\n")
        (self.live / "tmp/newer.txt").write_text("cache made by the new version")
        message = comp.restore()
        self.assertEqual(comp.installed(), "5.2.1")
        self.assertEqual((self.live / "libraries/old.txt").read_text(), "old")
        self.assertFalse((self.live / "libraries/new.txt").exists())
        self.assertEqual((self.live / "config.inc.php").read_text(), "<?php // changed after the update\n")
        self.assertEqual((self.live / "config.inc.php").stat().st_mode & 0o777, 0o640)
        self.assertTrue((self.live / "tmp/newer.txt").exists())
        self.assertIn("5.2.1", message)

    def test_restore_consumes_the_restore_point(self):
        comp = self.updated()
        comp.restore()
        self.assertIsNone(self.snapshots.get("phpmyadmin"))
        self.assertEqual(restore_points.load(self.paths.restore_points), [])
        self.assertEqual(self.leftovers(), [])
        with self.assertRaisesRegex(UpdateError, "no saved phpMyAdmin"):
            comp.restore()

    def test_restore_after_an_update_killed_between_the_two_renames(self):
        comp = self.component()
        snap = self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", NEW,
                                    {"parked": str(self.live.with_name("phpmyadmin.before-5.2.1-X"))})
        self.live.rename(self.live.with_name("phpmyadmin.before-5.2.1-X"))  # live folder is gone
        self.assertFalse(self.live.exists())
        comp.restore()
        self.assertEqual(comp.installed(), "5.2.1")
        self.assertIsNone(self.snapshots.get("phpmyadmin"))

    def test_restore_refuses_when_the_saved_copy_is_gone(self):
        comp = self.updated()
        shutil.rmtree(self.snapshots.get("phpmyadmin").data["parked"])
        with self.assertRaisesRegex(UpdateError, "saved phpMyAdmin folder is missing"):
            comp.restore()
        self.assertEqual(comp.installed(), NEW)

    def test_restore_refuses_a_manifest_that_points_somewhere_else(self):
        comp = self.component()
        victim = self.root / "precious"
        victim.mkdir()
        (victim / "file").write_text("x")
        self.snapshots.commit(self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", NEW, {"parked": str(victim)}))
        with self.assertRaisesRegex(UpdateError, "missing"):
            comp.restore()
        self.assertTrue((victim / "file").exists())
        self.assertEqual(comp.installed(), "5.2.1")

    def test_restore_note_explains_what_will_happen(self):
        comp = self.updated()
        note = comp.restore_note(self.snapshots.get("phpmyadmin"))
        for needle in ("5.2.3", "5.2.1", "config.inc.php", "No database data"):
            self.assertIn(needle, note)

    def test_restore_with_nothing_saved(self):
        with self.assertRaisesRegex(UpdateError, "no saved phpMyAdmin"):
            self.component().restore()


class VerifyBeforeUnpackTest(PmaBase):
    def test_nothing_is_unpacked_when_the_checksum_or_signature_fails(self):
        for kwargs in ({"sha": "0" * 64}, {"gpg_error": UpdateError("bad signature")}):
            comp = self.component(**kwargs)
            with mock.patch("xampp_panel.updates.pma.archive.safe_extract") as extract:
                with self.assertRaises(UpdateError):
                    comp.apply(self.target)
            extract.assert_not_called()

    def test_a_php_constraint_we_do_not_understand_does_not_block_the_update(self):
        weird = json.dumps({"releases": [{"version": "5.2.3", "php_versions": ">=7.2 || ^8"}]})
        comp = self.component()
        self.transport.answers[CONFIG.pma_version_json_url] = weird
        self.assertEqual(comp.plan(self.target).kind, "upgrade")


class KilledRunAndRollbackTest(PmaBase):
    def killed_before_the_renames(self):
        comp = self.component()
        self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", NEW,
                             {"parked": str(self.live.with_name("phpmyadmin.before-5.2.1-X"))})
        (self.live.parent / "phpmyadmin.new-X").mkdir()  # the unpacked copy the killed run left behind
        return comp

    def test_restore_after_a_kill_before_the_renames_clears_the_snapshot_and_the_leftovers(self):
        comp = self.killed_before_the_renames()
        message = comp.restore()
        self.assertIn("nothing to restore", message)
        self.assertIsNone(self.snapshots.get("phpmyadmin"))
        self.assertEqual(self.leftovers(), [])
        self.assertOldIsLive()

    def test_an_update_after_such_a_kill_just_works(self):
        comp = self.killed_before_the_renames()
        comp.apply(self.target)
        self.assertEqual(comp.installed(), NEW)
        self.assertEqual(self.snapshots.get("phpmyadmin").status, "ready")
        self.assertEqual(self.leftovers(), ["phpmyadmin.before-5.2.1-20231114221320"])

    def test_a_really_half_done_update_blocks_before_anything_is_downloaded(self):
        comp = self.component()
        saved = self.live.with_name("phpmyadmin.before-5.2.1-X")
        saved.mkdir()
        self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", NEW, {"parked": str(saved)})
        (self.live / "README").write_text(readme(NEW))  # the new version is live: the swap really happened
        with self.assertRaisesRegex(UpdateError, "did not finish"):
            comp.apply(self.target)
        self.assertEqual(self.fetcher.downloads, [])

    def test_a_second_interrupt_during_the_rollback_keeps_the_snapshot_and_the_old_folder(self):
        comp = self.component(run=PhpRun(lint_code=1))  # verification fails, so the rollback starts
        with mock.patch.object(comp, "_carry_over", side_effect=[None, KeyboardInterrupt()]):
            with self.assertRaises(RollbackFailed) as ctx:
                comp.apply(self.target)
        self.assertIn("sudo mv", str(ctx.exception))
        self.assertEqual(comp.installed(), NEW)
        self.assertEqual(self.snapshots.get("phpmyadmin").status, PENDING)
        self.assertTrue((self.live.parent / "phpmyadmin.before-5.2.1-20231114221320").is_dir())

    def test_the_manual_recovery_steps_cover_a_missing_live_folder(self):
        comp = self.component(run=PhpRun(lint_code=1))
        comp._exchange = mock.Mock(side_effect=OSError("disk on fire"))
        with self.assertRaises(RollbackFailed) as ctx:
            comp.apply(self.target)
        self.assertIn(f"only if {self.live} still exists", str(ctx.exception))

    def test_old_saved_and_half_made_folders_are_swept(self):
        comp = self.component()
        for name in ("phpmyadmin.new-OLD", "phpmyadmin.replaced-OLD", "phpmyadmin.before-9.9.9-OLD"):
            (self.live.parent / name).mkdir()
        keep = self.live.parent / "phpmyadmin-backup-by-hand"  # not ours: never touched
        keep.mkdir()
        comp.apply(self.target)
        self.assertEqual(self.leftovers(), ["phpmyadmin-backup-by-hand", "phpmyadmin.before-5.2.1-20231114221320"])

    def test_discarding_a_restore_point_on_top_of_an_older_one_leaves_no_saved_folder_behind(self):
        first = self.component()
        first.apply(self.target)  # 5.2.1 -> 5.2.3, saved as before-5.2.1
        second = self.component(version="5.2.2", run=PhpRun(lint_code=1))
        second._exchange = mock.Mock(side_effect=OSError("boom"))
        with self.assertRaises(RollbackFailed):
            second.apply(self.target)  # pending snapshot on top of the ready one
        del second._exchange
        second.run = PhpRun()
        second.restore()
        self.assertEqual(second.installed(), NEW)
        self.assertEqual([n for n in self.leftovers() if ".before-" in n], [])

    def test_restore_keeps_the_newer_version_and_the_restore_point_if_the_old_one_fails_its_checks(self):
        comp = self.component()
        comp.apply(self.target)
        comp.run = PhpRun(lint_code=1)
        with self.assertRaisesRegex(UpdateError, "did not pass its checks.*restore point was kept"):
            comp.restore()
        self.assertEqual(comp.installed(), NEW)
        snapshot = self.snapshots.get("phpmyadmin")
        self.assertEqual(snapshot.status, "ready")
        self.assertTrue(Path(snapshot.data["parked"]).is_dir())
        self.assertEqual([p.component for p in restore_points.load(self.paths.restore_points)], ["phpmyadmin"])
        comp.run = PhpRun()  # and the restore can simply be tried again
        comp.restore()
        self.assertEqual(comp.installed(), "5.2.1")

    def test_a_restore_point_that_cannot_be_finished_does_not_make_a_good_update_look_failed(self):
        comp = self.component()
        with mock.patch.object(self.snapshots, "commit", side_effect=OSError(28, "No space left on device")):
            message = comp.apply(self.target)
        self.assertIn("is installed, but the restore point could not be finished", message)
        self.assertEqual(comp.installed(), NEW)
        self.assertIn("phpmyadmin.before-5.2.1", message)


if __name__ == "__main__":
    unittest.main()
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_pma.py" -v`

Expected: FAIL — ImportError: Failed to import test module: test_update_pma (FAILED (errors=1)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/pma.py`:

`````python
"""phpMyAdmin: download, verify, swap the folder, verify again; restore the saved folder."""

import http.client
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

from .. import services
from ..paths import DEFAULT, Paths
from . import archive, versions
from .base import Plan, Release, RollbackFailed, UpdateError, critical_section
from .config import UpdateConfig
from .fetcher import Fetcher, verify_hashes
from .fsops import copy_owned
from .gpg import Gpg
from .releases import PhpMyAdminSource
from .snapshots import PENDING, Snapshot, Snapshots

_README_VERSION = re.compile(r"^Version\s+(\d+(?:\.\d+){1,3})\s*$", re.M | re.A)
_PHP_VERSION = re.compile(r"PHP (\d+\.\d+\.\d+)")
_WEB_OK = (200, 301, 302, 303)
SIGNATURE_MAX_BYTES = 65_536


def _say(message: str) -> None:
    print(message, file=sys.stderr)


def version_in(folder) -> str | None:
    """The phpMyAdmin version a folder says it is (its README), read as text; None if unknown."""
    try:
        text = (Path(folder) / "README").read_text(errors="replace")
    except OSError:
        return None
    match = _README_VERSION.search(text)
    return match.group(1) if match else None


def probe_http(url: str, timeout: float) -> int | None:
    """Status of a GET to the local web server (redirects are not followed); None if it does not answer."""
    parts = urllib.parse.urlsplit(url)
    try:
        connection = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
        try:
            connection.request("GET", parts.path or "/")
            return connection.getresponse().status
        finally:
            connection.close()
    except (OSError, http.client.HTTPException):
        return None


class PhpMyAdminComponent:
    key = "phpmyadmin"
    title = "phpMyAdmin"

    def __init__(self, source: PhpMyAdminSource, fetcher: Fetcher, gpg: Gpg, snapshots: Snapshots,
                 paths: Paths = DEFAULT, config: UpdateConfig = UpdateConfig(), run=subprocess.run,
                 clock=time.time, say=_say, probe=probe_http, apache_running=None, chown=os.chown):
        self.source = source
        self.fetcher = fetcher
        self.gpg = gpg
        self.snapshots = snapshots
        self.paths = paths
        self.config = config
        self.run = run
        self.clock = clock
        self.say = say
        self.probe = probe
        self.chown = chown
        self.apache_running = apache_running or (lambda: "apache" in services.running_services(paths))

    # -- what is installed and what is on offer ---------------------------
    def installed(self) -> str | None:
        return version_in(self.paths.pma_dir)

    def releases(self) -> list[Release]:
        return versions.newest_first(self.source.releases())

    def _php_version(self) -> str | None:
        try:
            proc = self.run([str(self.paths.php_bin), "-v"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        match = _PHP_VERSION.match(proc.stdout or "")
        return match.group(1) if match else None

    @staticmethod
    def _php_supported(php: str, span: str) -> bool:
        try:
            return versions.satisfies(php, span)
        except ValueError:
            return True  # a constraint we do not understand: do not block the update on it

    def plan(self, target: Release) -> Plan:
        current = self.installed()
        php, span = self._php_version(), self.source.php_range(target.version)
        if php and span and not self._php_supported(php, span):
            raise UpdateError(f"phpMyAdmin {target.version} needs PHP {span}, but this XAMPP has PHP {php}.")
        kind, warnings = "reinstall", []
        if current and versions.is_valid(current):
            have, want = versions.parse(current), versions.parse(target.version)
            kind = "upgrade" if want > have else "downgrade" if want < have else "reinstall"
        if kind == "downgrade":
            warnings.append(f"This goes back to an older phpMyAdmin ({target.version}).")
        summary = (
            f"Download phpMyAdmin {target.version} and check its SHA-256 checksum and PGP signature.",
            "Keep your config.inc.php (with its owner and permissions) and phpMyAdmin's cache folder.",
            f"Save the current phpMyAdmin ({current or 'unknown version'}) as a restore point.",
            "No database data is touched and Apache does not need to stop.",
        )
        return Plan(kind, summary, tuple(warnings))

    # -- installing -------------------------------------------------------
    def apply(self, target: Release) -> str:
        live = self.paths.pma_dir
        old_version = self.installed()
        self._preflight()
        self._settle_pending()
        self.snapshots.require_no_pending(self.key, self.title)  # before any download, not after
        self._sweep()
        previous = self.snapshots.get(self.key)
        stamp = self._stamp()
        new_dir = live.with_name(f"{live.name}.new-{stamp}")
        parked = live.with_name(f"{live.name}.before-{old_version or 'unknown'}-{stamp}")
        work = self._workdir()
        snapshot = None
        try:
            archive_path = self._download(target, work)
            self.say("Unpacking…")
            archive.safe_extract(archive_path, new_dir, self.config, strip=1)
            found = version_in(new_dir)
            if found != target.version or not (new_dir / "index.php").is_file():
                raise UpdateError(f"The download is not phpMyAdmin {target.version} "
                                  f"(it says {found or 'nothing'}), so it was not used.")
            snapshot = self.snapshots.begin(self.key, self.title, old_version or "unknown", target.version,
                                            {"parked": str(parked)})
            self.say("Switching to the new version…")
            try:
                self._replace(new_dir, parked)
                self._verify(target.version)
            except BaseException as error:
                self._put_back(parked, error)  # always raises
        except RollbackFailed:
            raise  # keep the snapshot: "Restore previous version" can still try
        except BaseException:
            if snapshot is not None:
                self.snapshots.abort(snapshot)
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(new_dir, ignore_errors=True)
        message = (f"phpMyAdmin {old_version or 'unknown'} → {target.version} is installed.\n\n"
                   "The old version is saved. If something stops working, use “Restore previous version”.")
        try:
            self.snapshots.commit(snapshot)
        except OSError as e:
            return (f"phpMyAdmin {old_version or 'unknown'} → {target.version} is installed, but the restore point "
                    f"could not be finished ({e.strerror or e}). The old version is still saved in {parked}; "
                    "“Restore previous version” can use it.")
        if previous is not None:
            self._delete_saved_copy(previous)
        self._sweep()
        return message

    def _preflight(self) -> None:
        live = self.paths.pma_dir
        if live.is_symlink() or not live.is_dir():
            raise UpdateError(f"phpMyAdmin was not found as a normal folder at {live}, so it cannot be updated here.")
        free = shutil.disk_usage(live.parent).free
        if free < self.config.pma_min_free_bytes:
            raise UpdateError(f"Not enough free disk space ({free // 1_000_000} MB free, "
                              f"{self.config.pma_min_free_bytes // 1_000_000} MB needed).")

    def _stamp(self) -> str:
        return time.strftime("%Y%m%d%H%M%S", time.gmtime(self.clock()))

    def _workdir(self) -> Path:
        cache = self.paths.update_cache
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(cache, 0o700)
        return Path(tempfile.mkdtemp(prefix="pma-", dir=cache))

    def _download(self, target: Release, work: Path) -> Path:
        name = f"phpMyAdmin-{target.version}-all-languages.tar.xz"
        path = work / name
        self.say(f"Downloading phpMyAdmin {target.version}…")
        self.fetcher.download(target.url, path, self.config.max_download_bytes)
        self.say("Checking the checksum…")
        verify_hashes(path, {"sha256": self.source.sha256_for(target)})
        self.say("Checking the PGP signature…")
        signature = self.fetcher.download(target.signature_url, work / (name + ".asc"), SIGNATURE_MAX_BYTES)
        self.gpg.verify(path, signature, self.source.keyring(), self.config.pma_signers)
        return path  # only a download that passed both checks is ever handed on to be unpacked

    def _carry_over(self, src: Path, dst: Path) -> None:
        """Copy the keep-list (config, its backup, cache) from `src` into `dst`, owner and mode included."""
        for name in self.config.pma_keep:
            source, target = src / name, dst / name
            if not (source.exists() or source.is_symlink()):
                continue
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            copy_owned(source, target, self.chown)

    def _replace(self, replacement: Path, aside: Path) -> None:
        """Carry the keep-list into `replacement`, move the live folder to `aside` and `replacement` into its place."""
        live = self.paths.pma_dir
        self._carry_over(live, replacement)
        with critical_section():
            live.rename(aside)
            try:
                replacement.rename(live)
            except BaseException:
                aside.rename(live)  # undo the first move
                raise

    def _exchange(self, replacement: Path, keep_aside: bool = False) -> Path:
        """Put `replacement` in the live folder's place. The folder it replaces is deleted, or returned if kept."""
        live = self.paths.pma_dir
        aside = live.with_name(f"{live.name}.replaced-{self._stamp()}")
        self._replace(replacement, aside)
        if not keep_aside:
            shutil.rmtree(aside, ignore_errors=True)
        return aside

    def _manual_steps(self, parked: Path) -> str:
        live = self.paths.pma_dir
        return (f"The old phpMyAdmin is still saved in {parked}.\nTo put it back by hand:\n"
                f"  1. only if {live} still exists:  sudo mv {live} {live}.broken\n"
                f"  2. sudo mv {parked} {live}")

    def _put_back(self, parked: Path, error: BaseException) -> None:
        """After a failed switch: bring the saved folder back, then raise. Never returns normally.

        Signals are held while this runs, so a second Ctrl-C cannot leave a half-done rollback."""
        live = self.paths.pma_dir
        try:
            with critical_section():
                if parked.is_dir():
                    if live.exists():
                        self._exchange(parked)
                    else:
                        parked.rename(live)
        except BaseException as problem:
            raise RollbackFailed(f"The update failed ({error}) and putting the old phpMyAdmin back failed too "
                                 f"({problem}).\n{self._manual_steps(parked)}") from error
        if isinstance(error, Exception):
            reason = str(error) if isinstance(error, UpdateError) else f"{type(error).__name__}: {error}"
            raise UpdateError(f"{reason}\n\nThe previous phpMyAdmin has been put back; nothing was lost.") from error
        raise error  # Ctrl-C and the like, after the old version is back

    def _verify(self, version: str | None) -> None:
        live = self.paths.pma_dir
        found = self.installed()
        if version is not None and found != version:
            raise UpdateError(f"The folder in place says phpMyAdmin {found or 'unknown'}, not {version}.")
        proc = self.run([str(self.paths.php_bin), "-l", str(live / "index.php")],
                        capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise UpdateError(f"PHP rejects phpMyAdmin's index.php: {(proc.stdout or proc.stderr).strip()}")
        if self.apache_running():
            status = self.probe(self.config.local_probe_url, self.config.local_probe_timeout)
            if status not in _WEB_OK:
                raise UpdateError(f"phpMyAdmin does not answer at {self.config.local_probe_url} "
                                  f"(status {status if status is not None else 'none'}).")

    # -- leftovers of killed runs -----------------------------------------
    def _saved_copy(self, snapshot: Snapshot) -> Path | None:
        """The saved folder named in a manifest, accepted only if it is one we could have made."""
        live = self.paths.pma_dir
        path = Path(snapshot.data.get("parked", ""))
        ours = path.parent == live.parent and path.name.startswith(f"{live.name}.before-")
        return path if ours and not path.is_symlink() else None

    def _delete_saved_copy(self, snapshot: Snapshot) -> None:
        path = self._saved_copy(snapshot)
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)

    def _settle_pending(self) -> bool:
        """A run killed before it changed anything leaves a pending snapshot that has nothing to restore.
        Clear it (and its leftovers) so it cannot block updates. True if there was one."""
        snapshot = self.snapshots.get(self.key)
        if snapshot is None or snapshot.status != PENDING:
            return False
        saved = self._saved_copy(snapshot)
        if (saved is None or not saved.is_dir()) and self.installed() == snapshot.from_version:
            self.snapshots.abort(snapshot)
            self._sweep()
            return True
        return False

    def _sweep(self) -> None:
        """Delete half-made or saved phpMyAdmin folders that no restore point refers to."""
        live = self.paths.pma_dir
        snapshot = self.snapshots.get(self.key)
        keep = self._saved_copy(snapshot) if snapshot is not None else None
        try:
            entries = list(live.parent.iterdir())
        except OSError:
            return
        for entry in entries:
            name = entry.name
            if entry.is_symlink() or not entry.is_dir():
                continue
            temporary = name.startswith((f"{live.name}.new-", f"{live.name}.replaced-"))
            if temporary or (name.startswith(f"{live.name}.before-") and entry != keep):
                shutil.rmtree(entry, ignore_errors=True)

    # -- restoring --------------------------------------------------------
    def restore_note(self, snapshot: Snapshot) -> str:
        return (f"phpMyAdmin {snapshot.to_version} is replaced by the saved {snapshot.from_version}.\n"
                "Your config.inc.php is kept as it is now. No database data is affected.")

    def restore(self) -> str:
        snapshot = self.snapshots.get(self.key)
        if snapshot is None:
            raise UpdateError("There is no saved phpMyAdmin version to restore.")
        if self._settle_pending():
            return "The interrupted update had not changed phpMyAdmin, so there was nothing to restore."
        saved = self._saved_copy(snapshot)
        if saved is None or not saved.is_dir():
            raise UpdateError("The saved phpMyAdmin folder is missing, so it cannot be restored. "
                              f"({snapshot.data.get('parked') or 'no location recorded'})")
        live = self.paths.pma_dir
        expected = snapshot.from_version if versions.is_valid(snapshot.from_version) else None
        if live.exists():
            newer = self._exchange(saved, keep_aside=True)
            try:
                self._verify(expected)
            except BaseException as error:
                self._undo_restore(newer, saved)  # the newer version is kept until the old one proves itself
                if isinstance(error, Exception):
                    raise UpdateError(f"The saved phpMyAdmin did not pass its checks ({error}), so the newer "
                                      "version was put back and the restore point was kept.") from error
                raise
            shutil.rmtree(newer, ignore_errors=True)
        else:  # an update that was killed between its two renames
            saved.rename(live)
            self._verify(expected)
        self.snapshots.discard(self.key)
        self._sweep()
        return f"phpMyAdmin {snapshot.from_version} is back in place."

    def _undo_restore(self, newer: Path, saved: Path) -> None:
        live = self.paths.pma_dir
        try:
            with critical_section():
                live.rename(saved)
                newer.rename(live)
        except BaseException as problem:
            raise RollbackFailed(f"Restoring did not work and undoing it failed too ({problem}).\n"
                                 f"The newer phpMyAdmin is in {newer}; the saved one is in {live}.\n"
                                 f"To get back to the newer one: sudo mv {live} {saved} && sudo mv {newer} {live}") from problem
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_pma.py" -v` — Expected: `Ran 47 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 516 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/test_update_pma.py src/xampp_panel/updates/pma.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: phpMyAdmin component with verified install, automatic rollback and restore"
`````

---

### Task 6b: Fix the open findings from the fresh review of the rollback code

A fresh reviewer re-tested the fixes in Task 6 and found seven problems in the rollback and sweep code that those fixes introduced (report: `.superpowers/sdd/2026-10-08-update-menu/work/peer/review-2-recheck.md`, sections N1–N7; each has a failing unittest). Unlike Tasks 1–10 this code was **not** replayed in advance: write the fixes test-first from that report.

**Files:**
- Modify: `src/xampp_panel/updates/pma.py` (and `snapshots.py` only if a fix needs it)
- Modify: `tests/test_update_pma.py`

**Interfaces:**
- Consumes: Task 6 (`PhpMyAdminComponent`, `_put_back`, `_undo_restore`, `_sweep`, `_settle_pending`, `restore`), Task 5 (`Snapshots`).
- Produces: the same public API; behaviour fixed as listed below.

**Required outcomes (acceptance criteria):**

- **N1 / N7** — A signal held by `critical_section` and delivered when the section exits, *after* the rollback or the restore-undo finished, must not be reported as a failed rollback. Re-raise the original error or `KeyboardInterrupt` instead; the manual `mv` commands are printed only when the work really failed (in `_undo_restore` they must never be printed for a false alarm: they would break a working install).
- **N2** — `SystemExit` (SIGTERM/SIGHUP via `repair.exit_on_signals`) arriving during a rollback must still terminate the tool once the rollback is finished; it must never be swallowed into `RollbackFailed`.
- **N3** — `_sweep` removes only folders this tool made: the names must match exactly the generated shapes (`phpmyadmin.new-<14 digits>`, `phpmyadmin.replaced-<14 digits>`, `phpmyadmin.before-<version or unknown>-<14 digits>`), so a user's own copy such as `phpmyadmin.before-my-edits` (MAINTAINER invites copies) is never touched.
- **N4 / N5** — A READY restore point whose saved folder is gone is dropped and the index refreshed when it is noticed (start of `apply`/`restore`, and when the menu opens); a kill after the restore swap but before `snapshots.discard` leaves a state that `restore`/`apply` recognise and clear (live version equals `from_version` and the saved folder is missing).
- **N6** — A pending snapshot whose `from_version` is `"unknown"` is settled when its saved folder is missing (nothing was swapped).

- [ ] **Step 1: Copy each finding's failing test from the report into `tests/test_update_pma.py`** (adapt helper names to the ones in the repo's test file) and run `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_pma.py" -v` — Expected: those tests FAIL.

- [ ] **Step 2: Fix `pma.py` one finding at a time**, re-running the file after each; keep the Task 6 tests green. For N1/N2/N7 wrap only the *work* in the `try`, set a `done` flag as the last statement inside `critical_section`, and treat anything arriving after it as a success followed by the original signal.

- [ ] **Step 3: Run the whole suite** — `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `OK`.

- [ ] **Step 4: Commit**

`````bash
git add src/xampp_panel/updates/pma.py tests/test_update_pma.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "fix: rollback survives late signals, sweep touches only its own folders, stale restore points clear"
`````

---

### Task 7: Background update check and the panel's bar logic

Add the user-level check (cached, throttled, tolerant of a wrong clock or a dead server) and the pure logic that decides what the panel's update bar and restore bar say.

`panelstate.compute(..., installed=...)` takes what is installed *now* from disk: the cache can be a day old and an update or a restore changes what is installed without touching the user's cache.

**Files:**
- Create: `src/xampp_panel/updates/check.py`
- Create: `src/xampp_panel/updates/panelstate.py`
- Create: `tests/test_update_check.py`

**Interfaces:**
- Consumes: Tasks 1–6: `versions`, `Component`, `Status` needs none; `restore_points`, `pma.version_in`, `UpdateConfig`.
- Produces: `check.Status`, `check.cache_path()`, `check.read_cache(path, config, now)`, `check.pending(statuses, dismissed)`, `check.UpdateCheck(components, config, path, clock).run(force=False)`; `panelstate.Bars`, `panelstate.compute(...)`, `panelstate.local_versions(paths)`, `panelstate.dismiss_updates/dismiss_restore`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_check.py`:

`````python
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from xampp_panel.updates import panelstate, restore_points
from xampp_panel.updates.base import Release, UpdateError
from xampp_panel.updates.check import Status, UpdateCheck, cache_path, pending, read_cache
from xampp_panel.updates.config import UpdateConfig
from xampp_panel.updates.restore_points import RestorePoint

CONFIG = UpdateConfig()
DAY = 86_400


class FakeComponent:
    def __init__(self, key, title, installed, offered, error=None):
        self.key, self.title, self._installed, self._offered, self.error = key, title, installed, offered, error
        self.calls = 0

    def installed(self):
        return self._installed

    def releases(self):
        self.calls += 1
        if self.error:
            raise self.error
        return [Release(v, f"https://x/{v}") for v in self._offered]


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class CheckBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "cache/xampp-panel/updates.json"
        self.clock = Clock()

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, *components, config=CONFIG):
        return UpdateCheck(components, config, self.path, self.clock)


class StatusTest(unittest.TestCase):
    def test_update_available_compares_numerically(self):
        self.assertTrue(Status("a", "A", "5.9.0", "5.10.0").update_available)
        self.assertFalse(Status("a", "A", "5.2.3", "5.2.3").update_available)
        self.assertFalse(Status("a", "A", "5.2.4", "5.2.3").update_available)  # newer than anything offered

    def test_unknown_versions_never_claim_an_update(self):
        self.assertFalse(Status("a", "A", None, "5.2.3").update_available)
        self.assertFalse(Status("a", "A", "5.2.1", None).update_available)
        self.assertFalse(Status("a", "A", "weird", "5.2.3").update_available)

    def test_cache_path_honours_xdg(self):
        self.assertEqual(cache_path({"XDG_CACHE_HOME": "/x"}), Path("/x/xampp-panel/updates.json"))


class RunTest(CheckBase):
    def test_checks_and_writes_a_private_cache(self):
        comp = FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.2", "5.2.3", "5.2.0"])
        result = self.check(comp).run()
        self.assertEqual(result["phpmyadmin"], Status("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3"))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["checked_at"], self.clock.now)
        self.assertEqual(data["components"]["phpmyadmin"], {"title": "phpMyAdmin", "installed": "5.2.1",
                                                              "latest": "5.2.3", "latest_at": self.clock.now})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_a_fresh_cache_is_trusted_without_asking_again(self):
        comp = FakeComponent("a", "A", "1.0", ["2.0"])
        self.check(comp).run()
        self.clock.now += DAY - 10
        self.assertEqual(self.check(comp).run()["a"].latest, "2.0")
        self.assertEqual(comp.calls, 1)

    def test_an_old_cache_is_refreshed(self):
        comp = FakeComponent("a", "A", "1.0", ["2.0"])
        self.check(comp).run()
        self.clock.now += DAY + 10
        comp._offered = ["3.0"]
        self.assertEqual(self.check(comp).run()["a"].latest, "3.0")
        self.assertEqual(comp.calls, 2)

    def test_force_ignores_the_throttle(self):
        comp = FakeComponent("a", "A", "1.0", ["2.0"])
        self.check(comp).run()
        self.check(comp).run(force=True)
        self.assertEqual(comp.calls, 2)

    def test_a_failing_component_keeps_its_old_status_and_does_not_hide_the_others(self):
        good = FakeComponent("a", "A", "1.0", ["2.0"])
        bad = FakeComponent("b", "B", "1.0", ["2.0"])
        self.check(good, bad).run()
        self.clock.now += 2 * DAY
        bad.error = UpdateError("offline")
        good._offered = ["3.0"]
        result = self.check(good, bad).run()
        self.assertEqual((result["a"].latest, result["b"].latest), ("3.0", "2.0"))

    def test_everything_failing_writes_nothing(self):
        comp = FakeComponent("a", "A", "1.0", [], error=UpdateError("offline"))
        self.assertIsNone(self.check(comp).run()["a"].latest)  # installed is known, latest is not
        self.assertFalse(self.path.exists())

    def test_everything_failing_leaves_the_old_cache_untouched(self):
        comp = FakeComponent("a", "A", "1.0", ["2.0"])
        self.check(comp).run()
        before = self.path.read_text()
        self.clock.now += 3 * DAY
        comp.error = OSError("no route")
        self.assertEqual(self.check(comp).run()["a"].latest, "2.0")
        self.assertEqual(self.path.read_text(), before)

    def test_no_releases_means_no_latest(self):
        result = self.check(FakeComponent("a", "A", "1.0", [])).run()
        self.assertIsNone(result["a"].latest)

    def test_time_budget_stops_the_check(self):
        slow = FakeComponent("a", "A", "1.0", ["2.0"])
        later = FakeComponent("b", "B", "1.0", ["2.0"])
        original = slow.releases

        def releases():
            self.clock.now += 100  # the first source took longer than the budget
            return original()

        slow.releases = releases
        result = self.check(slow, later).run()
        self.assertEqual(result["a"].latest, "2.0")
        self.assertIsNone(result["b"].latest)  # over budget: not asked, but what is installed is still read
        self.assertEqual(later.calls, 0)

    def test_a_damaged_cache_is_replaced(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        comp = FakeComponent("a", "A", "1.0", ["2.0"])
        self.assertEqual(self.check(comp).run()["a"].latest, "2.0")
        self.assertEqual(json.loads(self.path.read_text())["components"]["a"]["latest"], "2.0")


class ReadCacheTest(CheckBase):
    def write(self, text):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text)

    def test_reads_what_run_wrote(self):
        self.check(FakeComponent("a", "A", "1.0", ["2.0"])).run()
        self.assertEqual(read_cache(self.path, CONFIG, self.clock.now + 5)["a"].latest, "2.0")

    def test_too_old_is_ignored(self):
        self.check(FakeComponent("a", "A", "1.0", ["2.0"])).run()
        self.assertIsNone(read_cache(self.path, CONFIG, self.clock.now + 7 * DAY + 1))
        self.assertIsNotNone(read_cache(self.path, CONFIG, self.clock.now + 7 * DAY - 1))

    def test_missing_or_damaged_is_none(self):
        self.assertIsNone(read_cache(self.path, CONFIG, 0))
        for text in ("{oops", "[]", '{"checked_at": "x", "components": {}}', '{"checked_at": true, "components": {}}',
                     '{"checked_at": 1, "components": []}',
                     '{"checked_at": 1, "components": {"a": {"title": 3, "installed": null, "latest": null}}}',
                     '{"checked_at": 1, "components": {"a": {"title": "A"}}}',
                     '{"checked_at": 1, "components": {"a": {"title": "A", "installed": 5, "latest": null}}}'):
            self.write(text)
            self.assertIsNone(read_cache(self.path, CONFIG, 2), text)


class PendingTest(unittest.TestCase):
    A = Status("a", "A", "1.0", "2.0")
    B = Status("b", "B", "1.0", "1.0")
    C = Status("c", "C", "1.0", "3.0")

    def test_only_available_updates_in_key_order(self):
        statuses = {s.key: s for s in (self.C, self.B, self.A)}
        self.assertEqual([s.key for s in pending(statuses, {})], ["a", "c"])

    def test_later_hides_exactly_the_dismissed_version(self):
        statuses = {"a": self.A}
        self.assertEqual(pending(statuses, {"a": "2.0"}), [])
        self.assertEqual(pending(statuses, {"a": "1.5"}), [self.A])  # a different version brings the bar back
        newer = {"a": Status("a", "A", "1.0", "2.1")}
        self.assertEqual(len(pending(newer, {"a": "2.0"})), 1)


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class PanelStateTest(CheckBase):
    def setUp(self):
        super().setUp()
        self.points = Path(self._tmp.name) / "restore-points.json"
        self.clock.now = NOW.timestamp()

    def bars(self, settings=None, now=NOW):
        defaults = {"dismissed_updates": {}, "dismissed_restore": {}}
        return panelstate.compute({**defaults, **(settings or {})}, self.path, self.points, CONFIG, now)

    def point(self, component="phpmyadmin", created="2026-10-09T08:00:00+00:00", to="5.2.3"):
        return RestorePoint(component, "phpMyAdmin", "5.2.1", to, created)

    def test_nothing_to_show_on_a_fresh_machine(self):
        bars = self.bars()
        self.assertEqual((bars.update_text, bars.restore_text, bars.restore_available), (None, None, False))

    def test_update_bar_text_for_one_and_for_several(self):
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])).run()
        self.assertEqual(self.bars().update_text, "phpMyAdmin 5.2.3 is available (you have 5.2.1).")
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"]),
                   FakeComponent("mariadb", "MySQL (MariaDB)", "10.4.32", ["12.3.3"])).run(force=True)
        self.assertEqual(self.bars().update_text, "Updates available: MySQL (MariaDB) 12.3.3, phpMyAdmin 5.2.3.")

    def test_later_hides_the_update_bar_until_something_newer_exists(self):
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])).run()
        bars = self.bars()
        settings = panelstate.dismiss_updates({"dismissed_updates": {}, "dismissed_restore": {}}, bars)
        self.assertEqual(settings["dismissed_updates"], {"phpmyadmin": "5.2.3"})
        self.assertIsNone(self.bars(settings).update_text)
        self.clock.now += 2 * DAY
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.4"])).run()
        self.assertIn("5.2.4", self.bars(settings, NOW.replace(day=12)).update_text)

    def test_restore_bar_shows_for_a_week_after_the_update(self):
        restore_points.save(self.points, [self.point()])
        bars = self.bars()
        self.assertEqual(bars.restore_text, "phpMyAdmin was updated to 5.2.3. Something not working?")
        self.assertTrue(bars.restore_available)

    def test_restore_bar_goes_away_after_a_week_but_the_menu_item_stays(self):
        restore_points.save(self.points, [self.point(created="2026-10-01T08:00:00+00:00")])
        bars = self.bars()
        self.assertIsNone(bars.restore_text)
        self.assertTrue(bars.restore_available)

    def test_hide_dismisses_only_that_restore_point(self):
        restore_points.save(self.points, [self.point()])
        settings = panelstate.dismiss_restore({"dismissed_updates": {}, "dismissed_restore": {}}, self.bars())
        self.assertIsNone(self.bars(settings).restore_text)
        restore_points.save(self.points, [self.point(created="2026-10-10T09:00:00+00:00", to="5.2.4")])
        self.assertIn("5.2.4", self.bars(settings).restore_text)  # a new update is not hidden by the old Hide

    def test_several_restore_points_share_one_bar(self):
        restore_points.save(self.points, [self.point(), self.point("mariadb", to="12.3.3")])
        self.assertEqual(self.bars().restore_text,
                         "Updated: phpMyAdmin 5.2.3, phpMyAdmin 12.3.3. Something not working?")

    def test_dismissing_does_not_modify_the_given_settings(self):
        settings = {"dismissed_updates": {}, "dismissed_restore": {}}
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])).run()
        panelstate.dismiss_updates(settings, self.bars())
        self.assertEqual(settings["dismissed_updates"], {})


class NestedCacheTest(CheckBase):
    def test_absurdly_nested_cache_is_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[" * 100_000 + "]" * 100_000)
        self.assertIsNone(read_cache(self.path, CONFIG, 0))


class ReviewFindingsTest(CheckBase):
    def test_a_checked_at_in_the_future_does_not_freeze_the_check(self):
        comp = FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])
        self.check(comp).run()
        data = json.loads(self.path.read_text())
        data["checked_at"] = self.clock.now + 30 * DAY
        self.path.write_text(json.dumps(data))
        comp.calls = 0
        self.clock.now += 2 * DAY
        self.check(comp).run()
        self.assertEqual(comp.calls, 1)

    def test_a_checked_at_in_the_future_does_not_keep_the_cache_fresh_forever(self):
        self.check(FakeComponent("a", "A", "1.0", ["2.0"])).run()
        data = json.loads(self.path.read_text())
        data["checked_at"] = self.clock.now + 365 * DAY
        self.path.write_text(json.dumps(data))
        self.assertIsNone(read_cache(self.path, CONFIG, self.clock.now + 60 * DAY))

    def test_infinite_or_nan_times_are_not_trusted(self):
        for bad in ("Infinity", "-Infinity", "NaN"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text('{"checked_at": %s, "components": {}}' % bad)
            self.assertIsNone(read_cache(self.path, CONFIG, 1_000_000), bad)

    def test_installed_is_refreshed_even_when_the_network_part_fails(self):
        comp = FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])
        self.check(comp).run()
        comp._installed, comp.error = "5.2.3", UpdateError("offline")
        self.clock.now += 2 * DAY
        self.check(comp).run()
        entry = json.loads(self.path.read_text())["components"]["phpmyadmin"]
        self.assertEqual((entry["installed"], entry["latest"]), ("5.2.3", "5.2.3"))
        # the failed network part must not make the old list look newly checked
        self.assertEqual(json.loads(self.path.read_text())["checked_at"], 1_000_000.0)

    def test_a_list_that_has_not_been_fetched_for_a_week_is_dropped_but_others_stay(self):
        good = FakeComponent("a", "A", "1.0", ["2.0"])
        dead = FakeComponent("b", "B", "1.0", ["2.0"])
        self.check(good, dead).run()
        for step in range(5):  # a keeps succeeding, b keeps failing, for 10 days
            self.clock.now += 2 * DAY
            dead.error = UpdateError("offline")
            self.check(good, dead).run()
        cached = read_cache(self.path, CONFIG, self.clock.now)
        self.assertEqual(cached["a"].latest, "2.0")
        self.assertNotIn("b", cached)

    def test_later_stays_hidden_when_latest_goes_backwards(self):
        status = {"phpmyadmin": Status("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.2")}
        self.assertEqual(pending(status, {"phpmyadmin": "5.2.3"}), [])
        self.assertEqual(len(pending(status, {"phpmyadmin": "garbage"})), 1)

    def test_update_bar_follows_what_is_installed_now_not_the_cache(self):
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])).run()
        points = Path(self._tmp.name) / "restore-points.json"
        restore_points.save(points, [RestorePoint("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3",
                                                  "2026-10-08T11:59:00+00:00")])
        now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        self.clock.now = now.timestamp() - 600
        self.check(FakeComponent("phpmyadmin", "phpMyAdmin", "5.2.1", ["5.2.3"])).run(force=True)
        settings = {"dismissed_updates": {}, "dismissed_restore": {}}
        stale = panelstate.compute(settings, self.path, points, CONFIG, now)
        self.assertIsNotNone(stale.update_text)  # the cache alone still says 5.2.1 is installed
        fresh = panelstate.compute(settings, self.path, points, CONFIG, now, installed={"phpmyadmin": "5.2.3"})
        self.assertIsNone(fresh.update_text)
        self.assertIn("updated to 5.2.3", fresh.restore_text)
        restored = panelstate.compute(settings, self.path, points, CONFIG, now, installed={"phpmyadmin": "5.2.1"})
        self.assertIn("5.2.3 is available", restored.update_text)

    def test_local_versions_read_the_readme(self):
        from xampp_panel.paths import Paths
        paths = Paths(lampp=Path(self._tmp.name) / "lampp")
        paths.pma_dir.mkdir(parents=True)
        (paths.pma_dir / "README").write_text("phpMyAdmin - Readme\n\nVersion 5.2.1\n")
        self.assertEqual(panelstate.local_versions(paths), {"phpmyadmin": "5.2.1"})

    def test_restore_points_from_the_future_do_not_extend_the_bar(self):
        points = Path(self._tmp.name) / "p.json"
        restore_points.save(points, [RestorePoint("a", "A", "1", "2", "2027-10-08T00:00:00+00:00")])
        bars = panelstate.compute({"dismissed_updates": {}, "dismissed_restore": {}}, self.path, points, CONFIG,
                                  datetime(2026, 10, 8, tzinfo=timezone.utc))
        self.assertIsNone(bars.restore_text)


if __name__ == "__main__":
    unittest.main()
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_check.py" -v`

Expected: FAIL — ImportError: Failed to import test module: test_update_check (FAILED (errors=1)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/check.py`:

`````python
"""The background update check and its cache (~/.cache/xampp-panel/updates.json).

Runs as the normal user (`xampp-update --check`); needs no root.
"""

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from .. import fsutil
from . import versions
from .base import Component, UpdateError
from .config import UpdateConfig

_ERRORS = (UpdateError, OSError, ValueError, RecursionError)


@dataclass(frozen=True)
class Status:
    key: str
    title: str
    installed: str | None
    latest: str | None  # the newest release on offer
    latest_at: float | None = field(default=None, compare=False)  # when `latest` was fetched

    @property
    def update_available(self) -> bool:
        if not (versions.is_valid(self.installed) and versions.is_valid(self.latest)):
            return False
        return versions.parse(self.latest) > versions.parse(self.installed)


def cache_path(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "xampp-panel" / "updates.json"


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _load(path) -> tuple[float, dict[str, Status]] | None:
    """The cache file's time and statuses, or None if it is missing or not what we wrote."""
    try:
        data = json.loads(Path(path).read_text())
        checked_at, components = _number(data["checked_at"]), data["components"]
        if checked_at is None or not isinstance(components, dict):
            return None
        statuses = {}
        for key, item in components.items():
            title, installed, latest = item["title"], item["installed"], item["latest"]
            if not isinstance(title, str) or any(v is not None and not isinstance(v, str) for v in (installed, latest)):
                return None
            latest_at = _number(item.get("latest_at", checked_at))
            statuses[key] = Status(key, title, installed, latest, latest_at)
        return checked_at, statuses
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def read_cache(path, config: UpdateConfig = UpdateConfig(), now: float | None = None) -> dict[str, Status] | None:
    """The cached statuses, unless the file is missing, damaged or older than the config allows.

    A time in the future (a clock that was wrong) counts as too old, and so does a single
    component's `latest` that was last fetched too long ago."""
    loaded = _load(path)
    now = time.time() if now is None else now
    if loaded is None or not 0 <= now - loaded[0] <= config.cache_max_age_seconds:
        return None
    return {key: s for key, s in loaded[1].items()
            if s.latest_at is None or 0 <= now - s.latest_at <= config.cache_max_age_seconds}


def _dismissed(status: Status, dismissed: Mapping[str, str]) -> bool:
    """True if the user said "Later" to this version or to a newer one."""
    seen = dismissed.get(status.key)
    return versions.is_valid(seen) and versions.is_valid(status.latest) \
        and versions.parse(status.latest) <= versions.parse(seen)


def pending(statuses: Mapping[str, Status], dismissed: Mapping[str, str]) -> list[Status]:
    """Statuses worth showing: a newer version exists and the user has not said "Later" to it or a newer one."""
    return sorted((s for s in statuses.values() if s.update_available and not _dismissed(s, dismissed)),
                  key=lambda s: s.key)


class UpdateCheck:
    def __init__(self, components: Sequence[Component], config: UpdateConfig = UpdateConfig(), path=None,
                 clock=time.time):
        self.components = list(components)
        self.config = config
        self.path = Path(path or cache_path())
        self.clock = clock

    def run(self, force: bool = False) -> dict[str, Status]:
        """Check every component (at most once per throttle period unless `force`) and cache the result.

        What is installed is always read fresh (it is local). A component whose list cannot be fetched
        keeps its previous `latest` until that is too old to trust."""
        now = self.clock()
        cached = _load(self.path)
        statuses = dict(cached[1]) if cached else {}
        if cached and not force and 0 <= now - cached[0] < self.config.check_throttle_seconds:
            return statuses
        deadline = now + self.config.check_budget
        reached_network = changed = False
        for component in self.components:
            old = statuses.get(component.key)
            try:
                installed = component.installed()
            except _ERRORS:
                installed = old.installed if old else None
            latest, latest_at = (old.latest, old.latest_at) if old else (None, None)
            if self.clock() <= deadline:
                try:
                    offered = versions.newest_first(component.releases())
                    latest, latest_at = (offered[0].version if offered else None), now
                    reached_network = True
                except _ERRORS:
                    pass
            status = Status(component.key, component.title, installed, latest, latest_at)
            changed = changed or status != old
            statuses[component.key] = status
        if reached_network or (cached and changed):
            self._write(now if reached_network else cached[0], statuses)
        return statuses

    def _write(self, checked_at: float, statuses: Mapping[str, Status]) -> None:
        payload = {"checked_at": checked_at,
                   "components": {key: {"title": s.title, "installed": s.installed, "latest": s.latest,
                                        "latest_at": s.latest_at} for key, s in statuses.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fsutil.atomic_write(self.path, json.dumps(payload, indent=2) + "\n", mode=0o600)
`````

Create `src/xampp_panel/updates/panelstate.py`:

`````python
"""What the panel's update bar and restore bar should say. Pure; the window only draws it."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from . import restore_points
from . import pma
from .check import Status, pending, read_cache
from .config import UpdateConfig
from .restore_points import RestorePoint


@dataclass(frozen=True)
class Bars:
    update_text: str | None  # None: hide the update bar
    restore_text: str | None  # None: hide the restore bar
    restore_available: bool  # any restore point exists: the ☰ item "Restore previous version…" is enabled
    updates: tuple[Status, ...]  # what the update bar is about (for "Later")
    restore_points: tuple[RestorePoint, ...]  # what the restore bar is about (for "Hide")


def _update_text(updates: tuple[Status, ...]) -> str | None:
    if not updates:
        return None
    if len(updates) == 1:
        s = updates[0]
        return f"{s.title} {s.latest} is available (you have {s.installed})."
    return "Updates available: " + ", ".join(f"{s.title} {s.latest}" for s in updates) + "."


def _restore_text(points: tuple[RestorePoint, ...]) -> str | None:
    if not points:
        return None
    if len(points) == 1:
        return f"{points[0].title} was updated to {points[0].to_version}. Something not working?"
    return "Updated: " + ", ".join(f"{p.title} {p.to_version}" for p in points) + ". Something not working?"


def local_versions(paths) -> dict[str, str | None]:
    """What is installed right now, read from disk (two small text files; no root, no network)."""
    return {"phpmyadmin": pma.version_in(paths.pma_dir)}


def compute(settings: Mapping, cache_file, points_file, config: UpdateConfig = UpdateConfig(),
            now: datetime | None = None, installed: Mapping[str, str | None] | None = None) -> Bars:
    """`installed` overrides the cached "installed" versions: the cache can be a day old, and an update
    or a restore changes what is installed without touching the user's cache."""
    now = now or datetime.now(timezone.utc)
    statuses = read_cache(Path(cache_file), config, now.timestamp()) or {}
    if installed is not None:
        statuses = {key: replace(s, installed=installed.get(key, s.installed)) for key, s in statuses.items()}
    updates = tuple(pending(statuses, settings.get("dismissed_updates", {})))
    points = restore_points.load(points_file)
    hidden = settings.get("dismissed_restore", {})
    shown = tuple(p for p in restore_points.recent(points, now, config.restore_bar_days)
                  if hidden.get(p.component) != p.created)
    return Bars(_update_text(updates), _restore_text(shown), bool(points), updates, shown)


def dismiss_updates(settings: Mapping, bars: Bars) -> dict:
    """Settings after "Later": remember the versions that were shown, so only a newer one brings the bar back."""
    return {**settings, "dismissed_updates": {**settings.get("dismissed_updates", {}),
                                              **{s.key: s.latest for s in bars.updates}}}


def dismiss_restore(settings: Mapping, bars: Bars) -> dict:
    """Settings after "Hide": remember which restore points were shown."""
    return {**settings, "dismissed_restore": {**settings.get("dismissed_restore", {}),
                                              **{p.component: p.created for p in bars.restore_points}}}
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_update_check.py" -v` — Expected: `Ran 36 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 552 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add tests/test_update_check.py src/xampp_panel/updates/check.py src/xampp_panel/updates/panelstate.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: background update check, cache and panel bar logic"
`````

---

### Task 8: The `xampp-update` menu, launcher and terminal helpers

Add the whiptail menu (`UpdateApp`) with version lists, confirmations, the restore flow and `--check`/`--restore`, the launcher, and the terminal command builders.

`bin/xampp-update` must be executable in the repository (`chmod +x`) like the other launchers.

**Files:**
- Create: `src/xampp_panel/updates/app.py`
- Create: `bin/xampp-update`
- Create: `tests/test_update_app.py`
- Modify: `src/xampp_panel/terminal.py`
- Modify: `tests/test_terminal.py`
- Modify: `tests/fakes.py`

**Interfaces:**
- Consumes: Tasks 1–7 and the existing `Dialogs`, `repair.single_instance`, `repair.exit_on_signals`.
- Produces: `app.UpdateApp(dialogs, components, snapshots, config, say)` with `main_menu/update_component/restore/check_now/_attempt`; `app.parse_args`, `app.run_check(force, components, path, config)`, `app.default_components`, `app.main`; `terminal.launcher_command(launcher, *args)`, `terminal.update_command(paths, args=())`; `FakeDialogs.menus` in `tests/fakes.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_app.py`:

`````python
import io
import json
import os
import py_compile
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import fakes
from xampp_panel.dialogs import Cancelled
from xampp_panel.paths import Paths
from xampp_panel.updates import app
from xampp_panel.updates.app import UpdateApp
from xampp_panel.updates.base import Plan, Release, UpdateError
from xampp_panel.updates.snapshots import Snapshots

ROOT = Path(__file__).resolve().parent.parent
OFFERED = ("5.2.3", "5.2.2", "5.2.1", "5.2.0", "5.1.4", "5.1.3")


class FakeComponent:
    key = "phpmyadmin"
    title = "phpMyAdmin"

    def __init__(self, installed="5.2.1", offered=OFFERED, apply_error=None, key=None, title=None):
        self._installed, self._offered, self.apply_error = installed, offered, apply_error
        self.key = key or self.key
        self.title = title or self.title
        self.applied, self.restored, self.release_calls, self.releases_error = [], 0, 0, None

    def installed(self):
        return self._installed

    def releases(self):
        self.release_calls += 1
        if self.releases_error:
            raise self.releases_error
        return [Release(v, f"https://x/{v}") for v in self._offered]

    def plan(self, target):
        return Plan("upgrade", ("Download it.", "Keep your config."), ("Careful.",))

    def apply(self, target):
        if self.apply_error:
            raise self.apply_error
        self.applied.append(target.version)
        return f"Updated to {target.version}."

    def restore_note(self, snapshot):
        return f"NOTE {snapshot.from_version}"

    def restore(self):
        self.restored += 1
        return "Restored."


class AppBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "app/state").mkdir(parents=True)
        self.paths = Paths(lampp=root / "lampp", app=root / "app", backups=root / "backups")
        self.snapshots = Snapshots(self.paths)
        self.said = []

    def tearDown(self):
        self._tmp.cleanup()

    def app(self, answers, *components):
        self.dialogs = fakes.FakeDialogs(answers)
        self.components = components or (FakeComponent(),)
        return UpdateApp(self.dialogs, list(self.components), self.snapshots, say=self.said.append)

    def save_restore_point(self, key="phpmyadmin", title="phpMyAdmin", old="5.2.1", new="5.2.3"):
        self.snapshots.commit(self.snapshots.begin(key, title, old, new))


class MenuTest(AppBase):
    def test_lists_components_with_their_status_then_the_fixed_items(self):
        self.assertEqual(self.app(["q"]).main_menu(), 0)
        items = self.dialogs.menus[0]
        self.assertEqual([tag for tag, _ in items], ["1", "2", "3", "q"])
        self.assertEqual(items[0][1].split(), ["phpMyAdmin", "5.2.1", "→", "5.2.3", "available"])
        self.assertEqual([label for _, label in items[1:]], ["Restore previous version…", "Check for updates now", "Quit"])

    def test_up_to_date_and_unreachable_labels(self):
        current = FakeComponent(installed="5.2.3")
        broken = FakeComponent(key="b", title="Other")
        broken.releases_error = UpdateError("Could not reach example.org: offline\nmore detail")
        self.app(["q"], current, broken).main_menu()
        labels = [label for _, label in self.dialogs.menus[0]]
        self.assertEqual(labels[0].split(), ["phpMyAdmin", "5.2.3", "up", "to", "date"])
        self.assertIn("(could not check)", labels[1])

    def test_missing_component_is_labelled(self):
        self.app(["q"], FakeComponent(installed=None)).main_menu()
        self.assertIn("not found", self.dialogs.menus[0][0][1])

    def test_status_is_asked_once_per_menu_session(self):
        component = FakeComponent()
        self.app(["2", "q"], component).main_menu()  # menu shown twice (the restore message in between)
        self.assertEqual(component.release_calls, 1)

    def test_unfinished_update_is_reported_first(self):
        self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        self.app(["q"]).main_menu()
        self.assertIn("did not finish", self.dialogs.messages()[0])
        self.assertIn("Restore previous version", self.dialogs.messages()[0])


class UpdateFlowTest(AppBase):
    def test_choosing_a_version_updates_after_a_confirmation(self):
        app_ = self.app(["1", "1", True, "q"])
        app_.main_menu()
        self.assertEqual(self.components[0].applied, ["5.2.3"])
        self.assertEqual(self.dialogs.messages(), ["Updated to 5.2.3."])

    def test_version_list_shows_installed_plus_the_newest_five_with_tags(self):
        self.app(["1", None, "q"]).main_menu()
        version_menu = self.dialogs.menus[1]
        self.assertEqual(len(version_menu), 5)
        rows = [label.split() for _, label in version_menu]
        self.assertEqual(rows[0], ["5.2.3", "newer"])
        self.assertEqual(rows[2], ["5.2.1", "installed"])
        self.assertEqual(rows[4], ["5.1.4", "older"])

    def test_the_confirmation_shows_the_plan_and_warnings(self):
        self.app(["1", "1", False, "q"]).main_menu()
        confirm = next(text for kind, text in self.dialogs.shown if kind == "yesno")
        for needle in ("5.2.1 → 5.2.3", "(upgrade)", "• Download it.", "• Keep your config.", "! Careful.", "Continue?"):
            self.assertIn(needle, confirm)

    def test_saying_no_changes_nothing(self):
        self.app(["1", "1", False, "q"]).main_menu()
        self.assertEqual(self.components[0].applied, [])

    def test_escape_at_the_confirmation_changes_nothing(self):
        self.app(["1", "1", None, "q"]).main_menu()
        self.assertEqual(self.components[0].applied, [])

    def test_cancel_at_the_version_list_changes_nothing(self):
        self.app(["1", None, "q"]).main_menu()
        self.assertEqual(self.components[0].applied, [])

    def test_picking_the_installed_version_does_nothing(self):
        self.app(["1", "3", "q"]).main_menu()
        self.assertEqual(self.components[0].applied, [])
        self.assertIn("already installed", self.dialogs.messages()[0])

    def test_installed_version_outside_the_newest_five_is_listed_last_and_not_installable(self):
        self.app(["1", "6", "q"], FakeComponent(installed="4.0.0")).main_menu()
        self.assertEqual(self.dialogs.menus[1][-1][1].split(), ["4.0.0", "installed"])
        self.assertEqual(self.components[0].applied, [])

    def test_a_failed_update_is_reported_and_the_menu_continues(self):
        component = FakeComponent(apply_error=UpdateError("Checksum did not match."))
        self.assertEqual(self.app(["1", "1", True, "q"], component).main_menu(), 0)
        self.assertEqual(self.dialogs.messages(), ["That did not work:\n\nChecksum did not match."])

    def test_unexpected_os_errors_are_reported_too(self):
        component = FakeComponent(apply_error=OSError("No space left on device"))
        self.app(["1", "1", True, "q"], component).main_menu()
        self.assertIn("No space left on device", self.dialogs.messages()[0])

    def test_no_versions_on_offer(self):
        self.app(["1", "q"], FakeComponent(offered=())).main_menu()
        self.assertIn("No versions of phpMyAdmin are on offer", self.dialogs.messages()[0])

    def test_status_is_refreshed_after_an_update(self):
        component = FakeComponent()
        self.app(["1", "1", True, "q"], component).main_menu()
        self.assertEqual(self.dialogs.menus[-1][0][0], "1")  # menu rebuilt after the update
        self.assertGreaterEqual(component.release_calls, 3)

    def test_check_now_reports_every_component_and_asks_again(self):
        component = FakeComponent()
        self.app(["3", "q"], component).main_menu()  # 1 component: 1 update, 2 restore, 3 check
        self.assertIn("phpMyAdmin", self.dialogs.messages()[0])
        self.assertIn("5.2.3 available", self.dialogs.messages()[0])
        self.assertGreaterEqual(component.release_calls, 2)  # the menu's first look, then the fresh one


class RestoreTest(AppBase):
    def test_nothing_to_restore(self):
        self.app(["2", "q"]).main_menu()
        self.assertIn("nothing to restore", self.dialogs.messages()[0])
        self.assertEqual(self.components[0].restored, 0)

    def test_restore_asks_once_with_the_note_and_then_restores(self):
        self.save_restore_point()
        self.app(["2", True, "q"]).main_menu()
        confirm = next(text for kind, text in self.dialogs.shown if kind == "yesno")
        for needle in ("Restore phpMyAdmin 5.2.1?", "NOTE 5.2.1", "replaces version 5.2.3"):
            self.assertIn(needle, confirm)
        self.assertEqual(self.components[0].restored, 1)
        self.assertEqual(self.dialogs.messages(), ["Restored."])

    def test_saying_no_keeps_the_new_version(self):
        self.save_restore_point()
        self.app(["2", False, "q"]).main_menu()
        self.assertEqual(self.components[0].restored, 0)

    def test_restore_cli_goes_straight_to_the_confirmation(self):
        self.save_restore_point()
        application = self.app([True])
        application.restore("phpmyadmin")
        self.assertEqual(self.components[0].restored, 1)
        self.assertEqual(self.dialogs.menus, [])  # no menu: one restore point, named by the caller

    def test_a_single_restore_point_needs_no_choice_without_a_key(self):
        self.save_restore_point()
        application = self.app([True])
        application.restore()
        self.assertEqual(self.components[0].restored, 1)

    def test_several_restore_points_ask_which(self):
        self.save_restore_point()
        self.save_restore_point("mariadb", "MySQL", "10.4.32", "11.8.9")
        first, second = FakeComponent(), FakeComponent(key="mariadb", title="MySQL")
        application = self.app(["2", True], first, second)
        application.restore()
        self.assertEqual((first.restored, second.restored), (0, 1))
        self.assertEqual([label for _, label in self.dialogs.menus[0]], ["phpMyAdmin", "MySQL"])

    def test_unknown_component_is_an_error(self):
        self.save_restore_point()
        with self.assertRaisesRegex(UpdateError, "no saved version to restore for “nope”"):
            self.app([]).restore("nope")

    def test_cancelling_the_choice_restores_nothing(self):
        self.save_restore_point()
        self.save_restore_point("mariadb", "MySQL", "10.4.32", "11.8.9")
        first, second = FakeComponent(), FakeComponent(key="mariadb", title="MySQL")
        self.app([None], first, second).restore()
        self.assertEqual((first.restored, second.restored), (0, 0))

    def test_a_pending_snapshot_can_be_restored_too(self):
        self.snapshots.begin("phpmyadmin", "phpMyAdmin", "5.2.1", "5.2.3")
        self.app([True]).restore()
        self.assertEqual(self.components[0].restored, 1)


class ArgumentsTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(app.parse_args([]), ("menu", None, False))
        self.assertEqual(app.parse_args(["--check"]), ("check", None, False))
        self.assertEqual(app.parse_args(["--check", "--force"]), ("check", None, True))
        self.assertEqual(app.parse_args(["--restore"]), ("restore", None, False))
        self.assertEqual(app.parse_args(["--restore", "phpmyadmin"]), ("restore", "phpmyadmin", False))

    def test_everything_else_is_malformed(self):
        for argv in (["--force"], ["--check", "x"], ["--restore", "a", "b"], ["restore"], ["-h"], ["--check", "--restore"]):
            self.assertIsNone(app.parse_args(argv), argv)

    def test_main_prints_usage_for_bad_arguments(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(app.main(["--bogus"]), 2)
        self.assertIn("usage:", err.getvalue())

    def test_main_check_does_not_need_root_and_passes_force_on(self):
        with mock.patch.object(app, "run_check", return_value=0) as run_check, \
                mock.patch.object(os, "geteuid", return_value=1000):
            self.assertEqual(app.main(["--check", "--force"]), 0)
        run_check.assert_called_once_with(True)

    def test_main_refuses_the_menu_without_root(self):
        err = io.StringIO()
        with mock.patch.object(os, "geteuid", return_value=1000), redirect_stderr(err):
            self.assertEqual(app.main([]), 1)
            self.assertEqual(app.main(["--restore"]), 1)
        self.assertIn("sudo xampp-update", err.getvalue())


class RunCheckTest(unittest.TestCase):
    def test_writes_the_cache_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "updates.json"
            self.assertEqual(app.run_check(True, [FakeComponent()], path), 0)
            self.assertEqual(json.loads(path.read_text())["components"]["phpmyadmin"]["latest"], "5.2.3")

    def test_never_fails_loudly(self):
        broken = FakeComponent()
        broken.releases_error = UpdateError("offline")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(app.run_check(True, [broken], Path(tmp) / "updates.json"), 0)


class DefaultComponentsTest(unittest.TestCase):
    def test_phase_one_offers_phpmyadmin(self):
        components = app.default_components()
        self.assertEqual([c.key for c in components], ["phpmyadmin"])


class LauncherTest(unittest.TestCase):
    def test_launcher_matches_the_others(self):
        text = (ROOT / "bin/xampp-update").read_text()
        self.assertTrue(text.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn("from xampp_panel.updates.app import main", text)
        with tempfile.TemporaryDirectory() as tmp:
            py_compile.compile(str(ROOT / "bin/xampp-update"), doraise=True, cfile=os.path.join(tmp, "x.pyc"))


class CheckHardStopTest(unittest.TestCase):
    def test_an_alarm_is_set_during_the_check_and_cleared_after(self):
        with mock.patch.object(app.signal, "alarm") as alarm, tempfile.TemporaryDirectory() as tmp:
            app.run_check(True, [FakeComponent()], Path(tmp) / "u.json")
        self.assertEqual([c.args for c in alarm.call_args_list], [(60,), (0,)])  # check_budget 30 + 30, then off


class FailureReportingTest(AppBase):
    def test_a_failed_rollback_stays_readable_in_the_terminal_after_the_box_closes(self):
        from xampp_panel.updates.base import RollbackFailed
        steps = "Put it back by hand:\n  sudo mv /a /b"
        component = FakeComponent(apply_error=RollbackFailed(steps))
        self.app(["1", "1", True, "q"], component).main_menu()
        self.assertIn("sudo mv /a /b", self.dialogs.messages()[0])
        self.assertTrue(any("sudo mv /a /b" in line for line in self.said))

    def test_an_ordinary_failure_is_not_repeated_in_the_terminal(self):
        component = FakeComponent(apply_error=UpdateError("Checksum did not match."))
        self.app(["1", "1", True, "q"], component).main_menu()
        self.assertFalse(any("Checksum" in line for line in self.said))

    def test_attempt_reports_whether_it_worked(self):
        application = self.app([])
        self.assertTrue(application._attempt(lambda: None))
        self.assertFalse(application._attempt(lambda: (_ for _ in ()).throw(UpdateError("x"))))
        self.assertFalse(application._attempt(lambda: (_ for _ in ()).throw(Cancelled())))


if __name__ == "__main__":
    unittest.main()
`````

Modify `tests/test_terminal.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/test_terminal.py
+++ b/tests/test_terminal.py
@@ -22,3 +22,15 @@
         self.assertEqual(argv[:2], ["sh", "-c"])
         self.assertIn("sudo /a/bin/xampp-repair", argv[2])
         self.assertIn("read", argv[2])
+
+    def test_update_command_runs_the_updater_with_sudo(self):
+        argv = terminal.update_command(Paths(app=Path("/a")))
+        self.assertEqual(argv[:2], ["sh", "-c"])
+        self.assertTrue(argv[2].startswith("sudo /a/bin/xampp-update; printf"))
+        self.assertIn("read", argv[2])
+
+    def test_update_command_passes_arguments_quoted(self):
+        argv = terminal.update_command(Paths(app=Path("/a b")), ("--restore", "phpmyadmin"))
+        self.assertIn("sudo '/a b/bin/xampp-update' --restore phpmyadmin;", argv[2])
+        argv = terminal.update_command(Paths(app=Path("/a")), ("--restore", "x; rm -rf ~"))
+        self.assertIn("'x; rm -rf ~'", argv[2])
`````

Modify `tests/fakes.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/fakes.py
+++ b/tests/fakes.py
@@ -12,6 +12,7 @@
     def __init__(self, answers=()):
         self.answers = list(answers)
         self.shown = []
+        self.menus = []  # the (tag, label) items of every menu shown
 
     def _next(self, kind, text):
         self.shown.append((kind, text))
@@ -20,6 +21,7 @@
         return self.answers.pop(0)
 
     def menu(self, text, items):
+        self.menus.append(list(items))
         return self._next("menu", text)
 
     def yesno(self, text):
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"`

Expected: FAIL — AttributeError: module 'xampp_panel.terminal' has no attribute 'update_command'. Did you mean: 'repair_command'? (FAILED (errors=3, skipped=1)).

- [ ] **Step 3: Write the implementation**

Create `src/xampp_panel/updates/app.py`:

`````python
"""xampp-update: a whiptail menu to update phpMyAdmin (and, later, MariaDB and XAMPP), plus the restore button.

Runs as root (sudo in a terminal the panel opens). `xampp-update --check` is the exception: it runs as
the normal user, writes only the user's own cache file and is what the panel starts in the background.
"""

import os
import shutil
import signal
import sys

from ..dialogs import Cancelled, Dialogs
from ..paths import DEFAULT, Paths
from ..repair import exit_on_signals, single_instance
from . import versions
from .base import Component, RollbackFailed, UpdateError
from .check import UpdateCheck
from .config import UpdateConfig
from .fetcher import Fetcher
from .gpg import Gpg
from .pma import PhpMyAdminComponent
from .releases import PhpMyAdminSource, Transport
from .snapshots import PENDING, Snapshots

TITLE = "XAMPP updates"
USAGE = "usage: sudo xampp-update [--restore [COMPONENT]]   |   xampp-update --check [--force]"
_FAILURES = (UpdateError, OSError, ValueError)


def default_components(paths: Paths = DEFAULT, config: UpdateConfig = UpdateConfig()) -> list[Component]:
    transport = Transport(config)
    snapshots = Snapshots(paths)
    return [PhpMyAdminComponent(PhpMyAdminSource(transport, config), Fetcher(config), Gpg(), snapshots, paths, config)]


class UpdateApp:
    def __init__(self, dialogs, components: list[Component], snapshots: Snapshots,
                 config: UpdateConfig = UpdateConfig(), say=lambda message: print(message, file=sys.stderr)):
        self.dialogs = dialogs
        self.components = components
        self.snapshots = snapshots
        self.config = config
        self.say = say
        self._status_cache: dict[str, tuple[str | None, str | None, str | None]] = {}

    # -- menu -------------------------------------------------------------
    def main_menu(self) -> int:
        self._warn_about_unfinished_updates()
        while True:
            items = self._items()
            actions = {tag: action for tag, _, action in items}
            action = actions.get(self.dialogs.menu("Choose what to do:", [(t, label) for t, label, _ in items]))
            if action is None:
                return 0
            self._attempt(action)

    def _items(self):
        items = [(str(number), self._label(component), lambda c=component: self.update_component(c))
                 for number, component in enumerate(self.components, 1)]
        count = len(self.components)
        items.append((str(count + 1), "Restore previous version…", self.restore))
        items.append((str(count + 2), "Check for updates now", self.check_now))
        items.append(("q", "Quit", None))
        return items

    def _attempt(self, action) -> bool:
        try:
            action()
            return True
        except Cancelled:
            return False
        except _FAILURES as e:
            self.dialogs.msgbox(f"That did not work:\n\n{e}")
            if isinstance(e, RollbackFailed):
                self.say(f"\n{e}\n")  # a message box vanishes when closed; the recovery steps must stay readable
            return False

    def _warn_about_unfinished_updates(self) -> None:
        for component in self.components:
            snapshot = self.snapshots.get(component.key)
            if snapshot is not None and snapshot.status == PENDING:
                self.dialogs.msgbox(
                    f"An earlier update of {component.title} did not finish "
                    f"({snapshot.from_version} → {snapshot.to_version}).\n\n"
                    "Choose “Restore previous version” to put the old version back.")

    # -- status -----------------------------------------------------------
    def _status(self, component: Component):
        """(installed, latest, error) for a component, asked once per menu session."""
        if component.key not in self._status_cache:
            self.say(f"Checking {component.title}…")
            try:
                offered = versions.newest_first(component.releases())
                self._status_cache[component.key] = (component.installed(),
                                                     offered[0].version if offered else None, None)
            except _FAILURES as e:
                self._status_cache[component.key] = (component.installed(), None, str(e).splitlines()[0])
        return self._status_cache[component.key]

    def _label(self, component: Component) -> str:
        installed, latest, error = self._status(component)
        if installed is None:
            note = "not found"
        elif error:
            note = f"{installed}  (could not check)"
        elif latest and versions.is_valid(installed) and versions.parse(latest) > versions.parse(installed):
            note = f"{installed} → {latest} available"
        else:
            note = f"{installed}  up to date"
        return f"{component.title:<22}{note}"[:70]

    def check_now(self) -> None:
        self._status_cache.clear()
        self.dialogs.msgbox("\n".join(self._label(component) for component in self.components))

    # -- updating ---------------------------------------------------------
    def update_component(self, component: Component) -> None:
        installed = component.installed()
        offered = component.releases()
        if not offered:
            raise UpdateError(f"No versions of {component.title} are on offer right now.")
        entries = versions.pick(offered, installed, self.config.count)
        lines = [(str(number), f"{entry.version:<14}{', '.join(entry.tags)}") for number, entry in enumerate(entries, 1)]
        choice = self.dialogs.menu(f"{component.title}: installed {installed or 'unknown'}.\nChoose a version:", lines)
        if choice is None:
            return
        entry = entries[int(choice) - 1]
        if entry.release is None or entry.version == installed:
            self.dialogs.msgbox(f"{component.title} {entry.version} is already installed.")
            return
        plan = component.plan(entry.release)
        text = [f"{component.title}: {installed or 'unknown'} → {entry.version}  ({plan.kind})", ""]
        text += [f"• {line}" for line in plan.summary]
        if plan.warnings:
            text += ["", *[f"! {line}" for line in plan.warnings]]
        text += ["", "Continue?"]
        if not self.dialogs.yesno("\n".join(text)):
            return
        message = component.apply(entry.release)
        self._status_cache.pop(component.key, None)
        self.dialogs.msgbox(message)

    # -- restoring --------------------------------------------------------
    def restore(self, key: str | None = None) -> None:
        """Go back to the saved version of a component (the Restore button ends up here)."""
        saved = [c for c in self.components if self.snapshots.get(c.key) is not None]
        if not saved:
            self.dialogs.msgbox("There is nothing to restore yet.\n\n"
                                "A restore point is saved every time you update something.")
            return
        if key is not None:
            matches = [c for c in saved if c.key == key]
            if not matches:
                raise UpdateError(f"There is no saved version to restore for “{key}”.")
            component = matches[0]
        elif len(saved) == 1:
            component = saved[0]
        else:
            choice = self.dialogs.menu("Restore which one?", [(str(n), c.title) for n, c in enumerate(saved, 1)])
            if choice is None:
                return
            component = saved[int(choice) - 1]
        snapshot = self.snapshots.get(component.key)
        text = (f"Restore {component.title} {snapshot.from_version}?\n\n"
                f"{component.restore_note(snapshot)}\n\n"
                f"This replaces version {snapshot.to_version}, updated on {snapshot.created[:10]}.")
        if not self.dialogs.yesno(text):
            return
        message = component.restore()
        self._status_cache.pop(component.key, None)
        self.dialogs.msgbox(message)


def parse_args(argv: list[str]):
    """('menu', None, False) | ('restore', key or None, False) | ('check', None, force); None if malformed."""
    if argv == []:
        return "menu", None, False
    if argv in (["--check"], ["--check", "--force"]):
        return "check", None, argv == ["--check", "--force"]
    if argv and argv[0] == "--restore" and len(argv) <= 2:
        return "restore", (argv[1] if len(argv) == 2 else None), False
    return None


def run_check(force: bool = False, components=None, path=None, config: UpdateConfig = UpdateConfig()) -> int:
    """The background check: refresh ~/.cache/xampp-panel/updates.json. Never fails loudly."""
    signal.alarm(int(config.check_budget) + 30)  # hard stop: a server that trickles must not keep this running forever
    try:
        UpdateCheck(components if components is not None else default_components(config=config),
                    config, path).run(force=force)
    except _FAILURES as e:
        print(f"update check failed: {e}", file=sys.stderr)
    finally:
        signal.alarm(0)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    parsed = parse_args(argv)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    mode, key, force = parsed
    if mode == "check":
        return run_check(force)
    if os.geteuid() != 0:
        print("xampp-update must run as root: sudo xampp-update", file=sys.stderr)
        return 1
    if shutil.which("whiptail") is None:
        print("whiptail is missing: sudo apt install whiptail", file=sys.stderr)
        return 1
    os.umask(0o022)
    exit_on_signals()
    app = UpdateApp(Dialogs(title=TITLE), default_components(), Snapshots(DEFAULT))
    try:
        with single_instance(DEFAULT.runtime) as only:
            if not only:
                print("xampp-repair or xampp-update is already running in another terminal.", file=sys.stderr)
                return 1
            if mode == "restore":
                return 0 if app._attempt(lambda: app.restore(key)) else 1
            return app.main_menu()
    except KeyboardInterrupt:
        return 130
`````

Create `bin/xampp-update`:

`````python
#!/usr/bin/python3 -I
# Update menu for XAMPP Panel. Run with: sudo xampp-update   (xampp-update --check needs no root)
import sys

sys.path.insert(0, "/opt/xampp-panel/lib")
from xampp_panel.updates.app import main  # noqa: E402

sys.exit(main())
`````

Modify `src/xampp_panel/terminal.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/src/xampp_panel/terminal.py
+++ b/src/xampp_panel/terminal.py
@@ -14,12 +14,22 @@
 )
 
 
-def repair_command(paths: Paths = DEFAULT) -> list[str]:
-    """sudo + xampp-repair, then wait so a sudo error stays readable before the window closes."""
-    script = f"sudo {shlex.quote(str(paths.repair))}; printf '\\nPress Enter to close. '; read _"
+def launcher_command(launcher, *args: str) -> list[str]:
+    """sudo + a launcher (+ arguments), then wait so a sudo error stays readable before the window closes."""
+    command = " ".join(shlex.quote(part) for part in (str(launcher), *args))
+    script = f"sudo {command}; printf '\\nPress Enter to close. '; read _"
     return ["sh", "-c", script]
 
 
+def repair_command(paths: Paths = DEFAULT) -> list[str]:
+    return launcher_command(paths.repair)
+
+
+def update_command(paths: Paths = DEFAULT, args: tuple[str, ...] = ()) -> list[str]:
+    """xampp-update in a terminal: no arguments for the menu, `--restore` to go straight to the restore."""
+    return launcher_command(paths.updater, *args)
+
+
 def terminal_argv(command: list[str], which=shutil.which, terminals=TERMINALS) -> list[str] | None:
     for name, run_option in terminals:
         path = which(name)
`````

- [ ] **Step 4: Make the launcher executable**

Run: `chmod +x bin/xampp-update`

- [ ] **Step 5: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"` — Expected: `Ran 594 tests` … `OK (skipped=1)`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 594 tests` … `OK (skipped=1)`.

- [ ] **Step 6: Commit**

`````bash
git add tests/test_update_app.py src/xampp_panel/updates/app.py bin/xampp-update src/xampp_panel/terminal.py tests/test_terminal.py tests/fakes.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: xampp-update menu with version lists, restore flow and background check"
`````

---

### Task 9: Panel integration: update bar, restore bar and the ☰ items

Show the update bar (Update… / Later), the restore bar (Restore previous version / Hide, for 7 days after an update), and two ☰ items; start `xampp-update --check` in the background when the window opens.

GTK 4 is not available in the build sandbox, so this task is verified by compiling and, on the desktop, by the manual steps below. All decisions live in the tested `panelstate`; the window only draws them.

**Files:**
- Modify: `src/xampp_panel/window.py`

**Interfaces:**
- Consumes: Task 5 `settings`, Task 7 `panelstate`, `check.cache_path`, Task 8 `terminal.update_command`, `Paths.updater/restore_points`.
- Produces: `MainWindow.open_update/open_restore`, update and restore bars, `win.update` and `win.restore` actions.

- [ ] **Step 1: Write the implementation**

Modify `src/xampp_panel/window.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/src/xampp_panel/window.py
+++ b/src/xampp_panel/window.py
@@ -9,9 +9,11 @@
 gi.require_version("Adw", "1")
 from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402
 
-from . import fsutil, privileged, services, sites, terminal  # noqa: E402
+from . import fsutil, privileged, services, settings, sites, terminal  # noqa: E402
 from .paths import DEFAULT as PATHS  # noqa: E402
 from .services import State  # noqa: E402
+from .updates import panelstate  # noqa: E402
+from .updates.check import cache_path as update_cache_path  # noqa: E402
 from .watch import StatusWatcher  # noqa: E402
 
 FALLBACK_SECONDS = 10
@@ -51,6 +53,24 @@
     return revealer, revealer.set_reveal_child
 
 
+def _make_action_bar(buttons):
+    """A one-line message with buttons, shown or hidden as a whole: (widget, show) where show(text or None)."""
+    label = Gtk.Label(wrap=True, xalign=0, hexpand=True, valign=Gtk.Align.CENTER)
+    box = Gtk.Box(spacing=8, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
+    box.append(label)
+    for text, callback in buttons:
+        button = Gtk.Button(label=text, valign=Gtk.Align.CENTER)
+        button.connect("clicked", lambda _b, cb=callback: cb())
+        box.append(button)
+    revealer = Gtk.Revealer(child=box)
+
+    def show(text):
+        label.set_text(text or "")
+        revealer.set_reveal_child(bool(text))
+
+    return revealer, show
+
+
 class ServiceRow(Adw.ActionRow):
     def __init__(self, svc, has_log, on_toggle, on_log):
         super().__init__(title=svc.title)
@@ -228,15 +248,31 @@
         repair_action.connect("activate", lambda *_: self.open_repair())
         self.add_action(repair_action)
         menu.append("Repair & configure…", "win.repair")
+        update_action = Gio.SimpleAction.new("update", None)
+        update_action.connect("activate", lambda *_: self.open_update())
+        self.add_action(update_action)
+        menu.append("Update components…", "win.update")
+        self.restore_action = Gio.SimpleAction.new("restore", None)
+        self.restore_action.connect("activate", lambda *_: self.open_restore())
+        self.restore_action.set_enabled(False)  # enabled while a restore point exists
+        self.add_action(self.restore_action)
+        menu.append("Restore previous version…", "win.restore")
         menu.append("Quit", "app.quit")
         header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))
 
         self.banner, self.show_banner = _make_banner(
             "MySQL root has no password. Use ☰ → Repair & configure to set one.")
+        self.update_bar, self._show_update_bar = _make_action_bar(
+            [("Update…", self.open_update), ("Later", self._dismiss_updates)])
+        self.restore_bar, self._show_restore_bar = _make_action_bar(
+            [("Restore previous version", self.open_restore), ("Hide", self._dismiss_restore)])
+        self.bars = panelstate.Bars(None, None, False, (), ())
         self.toasts = Adw.ToastOverlay(child=stack, vexpand=True)
         box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
         box.append(header)
         box.append(self.banner)
+        box.append(self.update_bar)
+        box.append(self.restore_bar)
         box.append(self.toasts)
         self.set_content(box)
 
@@ -245,6 +281,8 @@
         self.connect("notify::is-active", self._on_active_changed)
         self.refresh()
         self.reload_sites()
+        self._refresh_update_bars()
+        self._start_update_check()
 
     # -- pages ------------------------------------------------------------
     def _services_page(self):
@@ -297,6 +335,7 @@
     def _on_active_changed(self, *_):
         if self.is_active():
             self.refresh()
+            self._refresh_update_bars()  # e.g. the restore bar goes away once a restore is done
             self.watcher.resume()
         else:
             self.watcher.pause()
@@ -335,16 +374,65 @@
     def toast(self, text: str) -> None:
         self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=5))
 
-    def open_repair(self) -> None:
-        argv = terminal.terminal_argv(terminal.repair_command(PATHS))
+    def _open_in_terminal(self, command: list[str], hint: str) -> None:
+        argv = terminal.terminal_argv(command)
         if argv is None:
-            self.toast(f"No terminal found. Run in a terminal: sudo {PATHS.repair}")
+            self.toast(f"No terminal found. Run in a terminal: {hint}")
             return
         try:
             Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
         except GLib.Error as e:
             self.toast(f"Could not open a terminal: {e.message}")
 
+    def open_repair(self) -> None:
+        self._open_in_terminal(terminal.repair_command(PATHS), f"sudo {PATHS.repair}")
+
+    def open_update(self) -> None:
+        self._open_in_terminal(terminal.update_command(PATHS), f"sudo {PATHS.updater}")
+
+    def open_restore(self) -> None:
+        self._open_in_terminal(terminal.update_command(PATHS, ("--restore",)), f"sudo {PATHS.updater} --restore")
+
+    # -- updates ----------------------------------------------------------
+    def _refresh_update_bars(self) -> None:
+        """Re-read the cached update check and the restore points (two small files, so cheap)."""
+        self.bars = panelstate.compute(self.get_application().settings, update_cache_path(), PATHS.restore_points,
+                                       installed=panelstate.local_versions(PATHS))
+        self._show_update_bar(self.bars.update_text)
+        self._show_restore_bar(self.bars.restore_text)
+        self.restore_action.set_enabled(self.bars.restore_available)
+
+    def _start_update_check(self) -> None:
+        """Ask xampp-update (as you, in the background) whether newer versions exist; it checks at most daily."""
+        if not PATHS.updater.exists():
+            return
+        try:
+            proc = Gio.Subprocess.new([str(PATHS.updater), "--check"],
+                                      Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
+        except GLib.Error:
+            return
+
+        def finished(p, result):
+            try:
+                p.wait_finish(result)
+            except GLib.Error:
+                return
+            self._refresh_update_bars()
+
+        proc.wait_async(None, finished)
+
+    def _dismiss_updates(self) -> None:
+        app = self.get_application()
+        app.settings = panelstate.dismiss_updates(app.settings, self.bars)
+        settings.save(app.settings)
+        self._refresh_update_bars()
+
+    def _dismiss_restore(self) -> None:
+        app = self.get_application()
+        app.settings = panelstate.dismiss_restore(app.settings, self.bars)
+        settings.save(app.settings)
+        self._refresh_update_bars()
+
     def call_helper(self, args, busy=(), done=None, failed=None):
         """Run the root helper asynchronously; the UI never blocks."""
         busy = set(busy)
`````

- [ ] **Step 2: Compile-check and run the suite**

Run: `python3 -m py_compile src/xampp_panel/window.py` — Expected: no output (verified).

- [ ] **Step 3: Commit**

`````bash
git add src/xampp_panel/window.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: panel update bar, restore bar and menu items"
`````

---

### Task 10: `setup.sh` and `uninstall.sh`

Install the new launcher and its symlink, make sure `gnupg` is present, and make uninstall remove the user's update cache while leaving the snapshots in `/var/backups/xampp-panel` on purpose.

Written by a second reviewer session and checked here with `bash -n` and the script tests.

**Files:**
- Modify: `setup.sh`
- Modify: `uninstall.sh`
- Modify: `tests/test_scripts.py`

**Interfaces:**
- Consumes: Task 8 `bin/xampp-update`.
- Produces: Installed `/opt/xampp-panel/bin/xampp-update` and `/usr/local/bin/xampp-update` (recorded in the install manifest).

- [ ] **Step 1: Write the failing tests**

Modify `tests/test_scripts.py` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/tests/test_scripts.py
+++ b/tests/test_scripts.py
@@ -48,3 +48,58 @@
     def test_help_names_the_pinned_version(self):
         proc = subprocess.run(["bash", str(ROOT / "setup.sh"), "--help"], capture_output=True, text=True)
         self.assertIn("Default: XAMPP 8.2.12 from this folder", proc.stdout)
+
+    def test_setup_installs_the_update_tool(self):
+        text = (ROOT / "setup.sh").read_text()
+        self.assertIn('"$SRC_DIR/bin/xampp-update"', text)
+        self.assertIn('ln -sfn "$APP_DIR/bin/xampp-update" /usr/local/bin/xampp-update', text)
+        self.assertIn("installed+=(/usr/local/bin/xampp-update)", text)
+        self.assertRegex(text, r"packages=\([^)]*\bgnupg\b")
+        launcher = (ROOT / "bin" / "xampp-update").read_text()
+        self.assertTrue(launcher.startswith("#!/usr/bin/python3 -I\n"))
+        self.assertIn("from xampp_panel.updates.app import main", launcher)
+        self.assertTrue(os.access(ROOT / "bin" / "xampp-update", os.X_OK))
+
+    def test_uninstall_removes_update_cache_and_keeps_snapshots(self):
+        text = (ROOT / "uninstall.sh").read_text()
+        self.assertIn('"$cache_dir/updates.json"', text)
+        self.assertIn('cache_dir="$user_home/.cache/xampp-panel"', text)
+        self.assertIn("! -L $cache_dir", text)  # root must not follow a symlinked cache folder
+        self.assertIn("rmdir --ignore-fail-on-non-empty", text)
+        self.assertIn("/var/backups/xampp-panel", text)
+        self.assertNotRegex(text, r"rm -[a-z]*r[a-z]* [^\n]*/var/backups")  # snapshots are never deleted
+
+    def test_uninstall_cache_cleanup_behaviour(self):
+        # Run the cleanup lines on their own against a temp home (the script itself needs root and /opt).
+        text = (ROOT / "uninstall.sh").read_text()
+        start = text.index('  cache_dir="$user_home/.cache/xampp-panel"')
+        end = text.index("fi\n", text.index("rmdir --ignore-fail-on-non-empty")) + 3
+        snippet = text[start:end]
+        import tempfile
+        with tempfile.TemporaryDirectory() as tmp:
+            home = Path(tmp)
+            run = lambda: subprocess.run(["bash", "-c", "set -euo pipefail\n" + snippet], env={"user_home": str(home), "PATH": os.environ["PATH"]}, capture_output=True, text=True)
+            cache = home / ".cache" / "xampp-panel"
+            cache.mkdir(parents=True)
+            (cache / "updates.json").write_text("{}")
+            self.assertEqual(run().returncode, 0)
+            self.assertFalse(cache.exists(), "empty folder should be removed with the file")
+            cache.mkdir()
+            (cache / "updates.json").write_text("{}")
+            (cache / "other").write_text("keep")
+            self.assertEqual(run().returncode, 0)
+            self.assertFalse((cache / "updates.json").exists())
+            self.assertTrue((cache / "other").exists(), "a folder with other files stays")
+            # a symlinked cache folder is left alone
+            real = home / "elsewhere"
+            real.mkdir()
+            (real / "updates.json").write_text("{}")
+            for item in cache.iterdir():
+                item.unlink()
+            cache.rmdir()
+            cache.symlink_to(real)
+            self.assertEqual(run().returncode, 0)
+            self.assertTrue((real / "updates.json").exists())
+            # nothing there at all is fine
+            cache.unlink()
+            self.assertEqual(run().returncode, 0)
`````

- [ ] **Step 2: Run the tests and watch them fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_scripts.py" -v`

Expected: FAIL — ValueError: substring not found (FAILED (failures=2, errors=1)).

- [ ] **Step 3: Write the implementation**

Modify `setup.sh` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/setup.sh
+++ b/setup.sh
@@ -59,7 +59,7 @@
 apt-cache show gir1.2-adw-1 >/dev/null 2>&1 || die "libadwaita is not available: XAMPP Panel needs Zorin OS 17 / Ubuntu 22.04 or newer."
 
 say "Installing required packages"
-packages=(curl ca-certificates libcrypt1 net-tools acl whiptail python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
+packages=(curl ca-certificates libcrypt1 net-tools acl whiptail python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gnupg)
 if apt-cache show pkexec >/dev/null 2>&1; then packages+=(pkexec); else packages+=(policykit-1); fi
 apt-get update -qq
 DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${packages[@]}"
@@ -118,7 +118,7 @@
 chown -R root:root "$APP_DIR/lib"
 chmod -R u=rwX,go=rX "$APP_DIR/lib"
 python3 -I -m compileall -q "$APP_DIR/lib"
-install -o root -g root -m 0755 "$SRC_DIR/bin/xampp-panel" "$SRC_DIR/bin/xampp-helper" "$SRC_DIR/bin/xampp-repair" "$APP_DIR/bin/"
+install -o root -g root -m 0755 "$SRC_DIR/bin/xampp-panel" "$SRC_DIR/bin/xampp-helper" "$SRC_DIR/bin/xampp-repair" "$SRC_DIR/bin/xampp-update" "$APP_DIR/bin/"
 
 installed=()
 put() { install -D -o root -g root -m 0644 "$SRC_DIR/$1" "$2"; installed+=("$2"); }
@@ -131,6 +131,8 @@
 installed+=(/usr/local/bin/xampp-panel)
 ln -sfn "$APP_DIR/bin/xampp-repair" /usr/local/bin/xampp-repair
 installed+=(/usr/local/bin/xampp-repair)
+ln -sfn "$APP_DIR/bin/xampp-update" /usr/local/bin/xampp-update
+installed+=(/usr/local/bin/xampp-update)
 printf '%s\n' "${installed[@]}" > "$APP_DIR/install-manifest.txt"
 gtk-update-icon-cache -qtf /usr/share/icons/hicolor 2>/dev/null || true
 update-desktop-database -q /usr/share/applications 2>/dev/null || true
`````

Modify `uninstall.sh` (save as a diff, then `git apply --check` and `git apply`):

`````diff
--- a/uninstall.sh
+++ b/uninstall.sh
@@ -65,6 +65,16 @@
 update-desktop-database -q /usr/share/applications 2>/dev/null || true
 if [[ -n ${SUDO_USER:-} ]] && user_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)" && [[ -n $user_home ]]; then
   rm -f -- "$user_home/.config/xampp-panel/settings.json"
+  # The update check's cache. Not through a symlinked folder: this runs as root.
+  cache_dir="$user_home/.cache/xampp-panel"
+  if [[ -d $cache_dir && ! -L $cache_dir ]]; then
+    rm -f -- "$cache_dir/updates.json"
+    rmdir --ignore-fail-on-non-empty -- "$cache_dir" 2>/dev/null || true
+  fi
+fi
+if [[ -d /var/backups/xampp-panel ]]; then
+  echo "Update snapshots in /var/backups/xampp-panel were kept on purpose."
+  echo "Delete that folder yourself when you no longer need them."
 fi
 
 if ((REMOVE_XAMPP)) && [[ -x $LAMPP/uninstall ]]; then
`````

- [ ] **Step 4: Run the task's tests and the whole suite**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p "test_scripts.py" -v` — Expected: `Ran 10 tests` … `OK`.

Run: `PYTHONPATH=src python3 -m unittest discover -s tests` — Expected: `Ran 597 tests` … `OK (skipped=1)`.

- [ ] **Step 5: Commit**

`````bash
git add setup.sh uninstall.sh tests/test_scripts.py
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "feat: install xampp-update and clean its cache on uninstall"
`````

---

### Task 11: Documentation

Bring the three documents in line with the code, in the same phase as the code. Written from the spec and the final code by a second session; **read the result against the code once more** before committing (module names, menu strings, file formats, the "not run on a real XAMPP" statements).

**Files:**
- Modify: `README.md`
- Modify: `docs/USER-GUIDE.md`
- Modify: `docs/MAINTAINER.md`

**Interfaces:**
- Consumes: everything above.
- Produces: user-facing and maintainer-facing documentation of updates, the restore button, the files created and the security model.

- [ ] **Step 1: Apply the documentation diff**

Save the diff below to a file, then `git apply --check` and `git apply` it from the repository root:

`````diff
--- a/README.md
+++ b/README.md
@@ -7,6 +7,7 @@
 - XAMPP only listens on this computer by default. Optional lean mode runs fewer idle processes.
 - Optional tray icon. Nothing runs at boot.
 - Repair & configure menu (☰) for passwords and known XAMPP problems; also available as `sudo xampp-repair`.
+- Update menu (☰): update phpMyAdmin from a list of versions, with a **Restore previous version** button; also `sudo xampp-update`. The panel tells you when a newer version exists.
 
 ## Documentation
 
--- a/docs/USER-GUIDE.md
+++ b/docs/USER-GUIDE.md
@@ -118,6 +118,8 @@
 | Item | What it does |
 |---|---|
 | Repair & configure… | Opens a terminal with the repair menu (below). Asks for your password (sudo). |
+| Update components… | Opens a terminal with the update menu (see “Updates and restore”). Asks for your password (sudo). |
+| Restore previous version… | Goes back to the version you had before the last update. Greyed out when there is nothing to go back to. |
 | Keep in tray when closed | Shows a small XAMPP icon in the top bar with Start/Stop/Open. Needs the AppIndicator extension; the item says so if it's missing. |
 | Lean mode (uses less memory) | Fewer background Apache processes and a smaller MySQL. Restart Apache and MySQL afterwards. |
 | Quit | Closes the panel. Apache and MySQL keep running until you stop them. |
@@ -157,6 +159,90 @@
 
 ---
 
+## Updates and restore
+
+Open it from **☰ → Update components…**, or type `sudo xampp-update` in a terminal. It opens in a
+terminal window with a text menu, like the repair menu (arrow keys, Enter to choose, Esc to cancel).
+
+**Right now the menu updates phpMyAdmin.** Updating MySQL (MariaDB) and PHP + Apache (XAMPP) from here
+is planned for later versions and is not in this one.
+
+### Knowing that an update exists
+
+When the panel opens it looks, in the background, whether a newer phpMyAdmin exists. It asks the
+internet at most once a day, and if you are offline it simply says nothing. If there is one, a bar
+appears at the top, for example “phpMyAdmin 5.2.3 is available (you have 5.2.1).”:
+
+- **Update…** opens the update menu.
+- **Later** hides the bar until an even newer version comes out. Nothing is ever installed unless you choose it.
+
+The “you have” version is read from your disk each time, so the bar goes away by itself after you update
+(or come back after you restore an older version).
+
+The bar never stops you from pressing Start.
+
+### Updating
+
+1. In the menu, choose **phpMyAdmin**. It lists the version you have and the 5 newest ones, newest first.
+   Each line is tagged: `installed`, `newer` or `older`. You may pick an older one too (to go back).
+2. A summary says what will happen. Answer **Yes** to continue. Esc or **No** changes nothing.
+3. The terminal shows the progress: download, checksum, signature, switch. At the end a message says
+   what changed.
+
+What a phpMyAdmin update does:
+
+- Downloads the release from phpMyAdmin's own site and checks it is not damaged (checksum) and really
+  comes from the phpMyAdmin developers (signature). If either check fails, **nothing is installed**.
+- Keeps your `config.inc.php` (and phpMyAdmin's cache folder `tmp`, if it has one), so your settings
+  and the generated `pma` password stay.
+- Puts the new version in place and checks that it works: it reads the right version, PHP accepts its
+  main file and, if Apache is running, the page at `http://127.0.0.1/phpmyadmin/` answers. If any of this
+  fails, the old version is put back automatically.
+- Keeps the old version as a **restore point**. If an earlier update was interrupted, the next one first
+  tidies up after it, or tells you to use **Restore previous version**.
+- Does not touch your databases, and Apache does not need to stop. Needs a few hundred MB of free disk space while it works.
+- Refuses a phpMyAdmin version that needs a different PHP than your XAMPP has, and says which.
+
+### Going back: Restore previous version
+
+If your own code, or phpMyAdmin itself, does not work after an update, you can put the old version back:
+
+- For 7 days after an update the panel shows a bar: “phpMyAdmin was updated to 5.2.3. Something not
+  working?” with **Restore previous version** and **Hide** (Hide keeps it away for that update).
+- At any time, **☰ → Restore previous version…** does the same. It is greyed out while there is nothing to
+  go back to. (In `sudo xampp-update` it is the menu item “Restore previous version…”.)
+
+Both open a terminal with `sudo xampp-update --restore`, show what will be replaced and ask you to confirm
+(Esc or **No** changes nothing).
+
+**What it restores.** For phpMyAdmin: the phpMyAdmin program files you had before the last update. Your
+current `config.inc.php` is kept as it is now, so your settings and the `pma` password stay. After putting
+the old version back, it checks that it works; if it does not, the newer version is put back and the
+restore point is kept.
+
+**What it does not touch.** Your databases and your sites. A phpMyAdmin restore touches no data, in either
+direction. (When MySQL (MariaDB) and XAMPP updates arrive in later versions, restoring those **will** lose any
+database changes made after the update, and the confirmation will say so before you agree.)
+
+**Using it up.** There is one restore point per component, and a restore uses it up: afterwards the bar
+disappears and the menu item goes grey until you update again. A new update replaces the older restore point.
+
+**Where the saved copies live.** A record of each update is kept in `/var/backups/xampp-panel`. For phpMyAdmin the
+old program files themselves are the folder `/opt/lampp/phpmyadmin.before-<version>-<date>` next to the current one.
+Both stay when you uninstall the panel, so you can still go back by hand (the technical reference says how). Delete them
+yourself when you no longer need them.
+
+### Good to know
+
+- This is the first version of the update menu. It has been checked with automated tests only, not yet
+  on a real XAMPP install. Export databases you care about (phpMyAdmin → Export) before updating anything;
+  for phpMyAdmin updates this is only a habit, because they do not change databases.
+- The update menu and the repair menu cannot run at the same time. If one says the other is running,
+  close the other terminal.
+- Uninstalling the panel does **not** delete the saved copies of older versions (see above). `uninstall.sh` says so.
+
+---
+
 ## Everyday tasks
 
 | I want to… | Do this |
@@ -198,6 +284,13 @@
 | FTP won't start; its error mentions `'function'` | **☰ → Repair & configure → Fix FTP config.** |
 | `http://name.local` "can't be reached" | Check the site is listed in the Sites tab. If it is and Chrome still fails, turn off Chrome's "Use secure DNS" or try Firefox. |
 | `name.local` says **Forbidden** | Remove the site and add it again. |
+| phpMyAdmin looks wrong or stopped working after an update | **☰ → Restore previous version…** (see “Updates and restore”). |
+| The update bar never shows up | It needs internet and looks at most once a day. Open `sudo xampp-update` and choose “Check for updates now”. A bar you closed with **Later** stays hidden until a newer version appears. |
+| An update says “The download does not match its SHA-256 checksum” or “The signature … is not valid” | Nothing was installed. Try again later; if it keeps happening, do not work around it. |
+| An update says gpg is not installed | `sudo apt install gnupg` (or re-run `sudo ./setup.sh`, which installs it). |
+| “An earlier update of phpMyAdmin did not finish” | Choose **Restore previous version** first; it puts the old version back. |
+| “phpMyAdmin X needs PHP …” | That version does not work with this XAMPP's PHP. Pick another version in the list. |
+| “xampp-repair or xampp-update is already running in another terminal” | Finish or close the other one, then try again. |
 | Running `xampp-panel` in a remote/SSH terminal says "Gtk couldn't be initialized" | Normal: there's no screen there. Open it from the app menu. |
 
 When asking for help, include the message the panel showed plus the output of:
--- a/docs/MAINTAINER.md
+++ b/docs/MAINTAINER.md
@@ -10,7 +10,9 @@
 - **Design history:** `docs/superpowers/specs/2026-09-23-xampp-panel-design.md` (the spec) and
   `docs/superpowers/plans/2026-09-23-xampp-panel.md` (the task-by-task plan); the repair menu added
   later has its own spec, `docs/superpowers/specs/2026-10-06-repair-menu-design.md`, and plan,
-  `docs/superpowers/plans/2026-10-06-repair-menu.md`
+  `docs/superpowers/plans/2026-10-06-repair-menu.md`; the update menu has its own spec,
+  `docs/superpowers/specs/2026-10-08-update-menu-design.md` (design, three phases) and, for phase 1,
+  `docs/superpowers/plans/2026-10-08-update-menu-phase1.md` (the task-by-task plan, with the manual checklist); phase 1 is described in §14
 
 ---
 
@@ -78,6 +80,7 @@
 | Tray icon (GTK3 + AyatanaAppIndicator) | Optional; status icon plus start/stop menu |
 | Root helper (`xampp-helper`) | The **only** code that runs as root through `pkexec` (graphical password prompt) |
 | Repair tool (`xampp-repair`) | A whiptail menu, run as root via `sudo` in a terminal, for passwords and known XAMPP config problems; also runs once at first install |
+| Update tool (`xampp-update`) | A whiptail menu, run as root via `sudo` in a terminal, that updates phpMyAdmin (phase 1) and restores the previous version; `xampp-update --check` runs as the normal user for the panel's update bar. See §14 |
 
 ---
 
@@ -108,6 +111,9 @@
                                         Dialogs  MysqlAdmin   pmaconfig   Helper
                                        (whiptail) (mysql CLI) (config.inc.php  (harden/integrate/
                                                                 text edits)    lean, lampp start/stop)
+
+      ☰ "Update components…" / "Restore previous version…" ──► terminal running
+                                      `sudo /opt/xampp-panel/bin/xampp-update [--restore]`  (details: §14)
 ```
 
 Design rules:
@@ -124,27 +130,43 @@
 
 | Path | Responsibility |
 |---|---|
-| `src/xampp_panel/paths.py` | `Paths` dataclass: **every** filesystem location in one place (tests override it) |
+| `src/xampp_panel/paths.py` | `Paths` dataclass: **every** filesystem location in one place (tests override it). The update tool's are here too: `backups`, `pma_dir`, `php_bin`, `updater`, `update_cache`, `restore_points` |
 | `src/xampp_panel/fsutil.py` | `atomic_write` (temp file + rename), `backup_once`, `tail` (last 64 KB) |
 | `src/xampp_panel/services.py` | Service list (Apache :80, MySQL :3306, ProFTPD :21), state detection, log paths |
 | `src/xampp_panel/configedit.py` | Pure, reversible text edits for XAMPP/system config files; lean-mode values; vhost and hosts rendering; ProFTPD broken-password detection/repair, MySQL networking detection, the one-time `init-file` line for a root password reset |
 | `src/xampp_panel/sites.py` | `Site(name, path, uid)`, name validation, `sites.json` load/save, `UNSAFE_PATH_CHARS` |
 | `src/xampp_panel/helper.py` | **Root helper**: validation + whitelisted commands |
 | `src/xampp_panel/privileged.py` | Builds the `pkexec` command, turns exit codes into errors |
-| `src/xampp_panel/settings.py` | Per-user settings (`~/.config/xampp-panel/settings.json`, mode 0600) |
+| `src/xampp_panel/settings.py` | Per-user settings (`~/.config/xampp-panel/settings.json`, mode 0600); includes the validated `dismissed_updates` and `dismissed_restore` maps (string → string) |
 | `src/xampp_panel/watch.py` | inotify watcher + pausable fallback timer (shared by panel and tray) |
-| `src/xampp_panel/window.py` | Main window: Services and Sites pages, log viewer, Add-site dialog, ☰ "Repair & configure…" |
+| `src/xampp_panel/window.py` | Main window: Services and Sites pages, log viewer, Add-site dialog, ☰ "Repair & configure…", ☰ "Update components…" and "Restore previous version…" (greyed out unless a restore point exists), the update bar (**Update…** / **Later**) and the restore bar (**Restore previous version** / **Hide**); starts `xampp-update --check` in the background when it opens and re-reads the bars when the window regains focus. What the bars say comes from `updates/panelstate.py` |
 | `src/xampp_panel/app.py` | `Adw.Application`: single instance, menu actions (tray, lean, quit) |
 | `src/xampp_panel/tray.py` | Tray process |
 | `src/xampp_panel/main.py` | Entry point: `--tray` → tray, otherwise panel |
 | `src/xampp_panel/pmaconfig.py` | Pure text `get`/`set` of single-quoted `$cfg['Servers'][$i][...]` settings in phpMyAdmin's `config.inc.php`; never executes the file |
 | `src/xampp_panel/mysqladmin.py` | `MysqlAdmin`: runs XAMPP's `mysql`/`mysql_upgrade` as root, SQL builders (`drop_anonymous_sql`, `set_root_password_sql`, `reset_root_sql`, `pma_account_sql`), password rules, SQL escaping |
-| `src/xampp_panel/dialogs.py` | `Dialogs`: thin whiptail wrapper (menu, yesno, msgbox, passwordbox, `secret`) |
+| `src/xampp_panel/dialogs.py` | `Dialogs`: thin whiptail wrapper (menu, yesno, msgbox, passwordbox, `secret`); optional `title` so the update menu has its own |
 | `src/xampp_panel/health.py` | `HealthCheck`: read-only report (services, configs, MySQL accounts, phpMyAdmin login, sites) with the menu item that fixes each problem |
 | `src/xampp_panel/repair.py` | `RepairApp`: the `xampp-repair` menu, its flows, and `first-install`; `main()` |
-| `src/xampp_panel/terminal.py` | Picks a terminal emulator and builds its argv for "Repair & configure…" (pure, no GTK) |
+| `src/xampp_panel/terminal.py` | Picks a terminal emulator and builds its argv for "Repair & configure…" and the update menu (`launcher_command`, `repair_command`, `update_command`; pure, no GTK) |
 | `lib/xampp-download.sh` | Sourced by `setup.sh`: the pinned XAMPP version (`XAMPP_VERSION`, `XAMPP_SHA256`; file name and URL derive from the version) and `xampp_prepare`, which `setup.sh` calls once: `xampp_find_installer` (the pinned file only), `xampp_other_installers` (other versions, for a hint), `xampp_download` (as the user, HTTPS only, resumable `.part`, retries, stall timeout), `xampp_verified_copy` (private copy, checksum checked on the copy; exit 1 = wrong checksum, 2 = copy failed) |
-| `bin/xampp-panel`, `bin/xampp-helper`, `bin/xampp-repair` | Installed launchers (`#!/usr/bin/python3 -I`) |
+| `src/xampp_panel/updates/` | The update tool, a subpackage so it stays apart from the flat modules above. Free of GTK and unit-tested (`tests/test_update_*.py`). Modules: see the next rows |
+| `updates/config.py` | `UpdateConfig` (frozen dataclass): every URL, `count`, timeouts and deadlines (`http_timeout`, `stall_timeout`, `request_deadline`, `check_budget`, `download_min_seconds` / `download_min_bytes_per_second`), size caps, retries, check throttle and cache age, `restore_bar_days`, free-space minimum, the phpMyAdmin keep-list and the pinned signer fingerprints (`PMA_SIGNERS`). Injectable, like `Paths` |
+| `updates/base.py` | `Release`, `Plan`, `Component` protocol, `UpdateError` (message meant for the user), `RollbackFailed`, `critical_section()` (blocks SIGINT/SIGHUP/SIGTERM during a swap) |
+| `updates/versions.py` | Strict, **ASCII-only** version parsing (`is_valid`, `parse`: `^\d{1,3}(\.\d{1,3}){1,3}$` with `re.ASCII`), PHP-range check (`satisfies`, raises `ValueError` for a constraint it does not know), ordering and `pick`: the installed version plus the newest `count`, tagged `installed` / `newer` / `older` |
+| `updates/http.py` | HTTPS-only URL check and an opener that can only speak HTTPS (TLS 1.2+, certificate checks): no plain-HTTP, FTP, `file:` or `data:` handlers, and redirects must stay HTTPS |
+| `updates/releases.py` | `Transport` (GET that reads as data arrives, with a size cap, a per-request deadline and plain-language errors, including `http.client` errors; JSON/text helpers; deeply nested JSON counts as "not JSON") and `PhpMyAdminSource` (release list, `.sha256`, keyring, PHP range from `version.json`, fetched once per run) |
+| `updates/fetcher.py` | `Fetcher`: refuses a download folder that is not private (owned by the current user, no group/other access), downloads to a `.part` file (`O_NOFOLLOW`), resumes after a dropped or short transfer (checks `Content-Range`, restarts if the server answers wrongly), reads as data arrives so the overall deadline holds, enforces a size cap, turns disk errors into messages, and `verify_hashes` |
+| `updates/archive.py` | `safe_extract`: unpack `.tar.xz`/`.tar.gz`. Refuses absolute paths, `..`, devices, fifos and hard links, too many entries or too much data; creates parent folders one at a time with `lstat` and refuses to go through any link or file; checks every link by its text, by where it lands when created, and again by where it finally lands after unpacking; files are created `O_EXCL\|O_NOFOLLOW` and end up 0644/0755, folders 0755. Does **not** verify the compression trailer (see §10) |
+| `updates/gpg.py` | `Gpg.verify`: detached signature check with a throwaway `gpg` home; accepted only if `VALIDSIG` names a pinned primary-key fingerprint |
+| `updates/fsops.py` | `copy_owned`: copy a tree keeping owner, group, mode and times, safe over folders others can write: reads relative to open folder descriptors with `O_NOFOLLOW`, refuses an entry swapped for another kind, keeps everything 0700/0600 until the real owner and mode are applied last. Does **not** keep ACLs, extended attributes or hard links |
+| `updates/snapshots.py` | `Snapshots`: one snapshot folder per component with `manifest.json` (`begin` / `commit` / `abort` / `discard`, `require_no_pending`), retention, and keeping the public index in step (best effort: a failure to write the index does not fail the update) |
+| `updates/restore_points.py` | `RestorePoint`, tolerant `load`, atomic `save`, `recent` for `restore-points.json` |
+| `updates/pma.py` | `PhpMyAdminComponent`: download, verify, unpack, folder swap, verify, roll back, restore (the restored version is checked and, if it fails, the newer one is put back); clears a pending snapshot that changed nothing and sweeps half-made folders |
+| `updates/check.py` | `UpdateCheck`: installed vs newest per component, throttle, cache read/write (a component that cannot be fetched keeps its last `latest` until it is too old), `pending()` (the "Later" filter) |
+| `updates/panelstate.py` | Pure: what the panel's update bar and restore bar say (`compute`, `dismiss_updates`, `dismiss_restore`) and `local_versions` (what is installed, read from disk); the window only draws it |
+| `updates/app.py` | `UpdateApp` (menu, update and restore flows), `parse_args`, `run_check` (with a hard stop after `check_budget` + 30 s), `main()` |
+| `bin/xampp-panel`, `bin/xampp-helper`, `bin/xampp-repair`, `bin/xampp-update` | Installed launchers (`#!/usr/bin/python3 -I`) |
 | `data/` | `.desktop` file, polkit policy, SVG icons |
 | `tests/` | stdlib `unittest` suite |
 
@@ -161,6 +183,8 @@
 | `/opt/xampp-panel/bin/xampp-helper` | root, 0755 | Root helper launcher |
 | `/opt/xampp-panel/bin/xampp-repair` | root, 0755 | Repair tool launcher |
 | `/usr/local/bin/xampp-repair` | symlink | So `sudo xampp-repair` works in a terminal |
+| `/opt/xampp-panel/bin/xampp-update` | root, 0755 | Update tool launcher |
+| `/usr/local/bin/xampp-update` | symlink | So `sudo xampp-update` works in a terminal; listed in `install-manifest.txt` |
 | `/opt/xampp-panel/state/sites.json` | root, 0644 | List of sites (world-readable so the panel can list them) |
 | `/opt/xampp-panel/install-manifest.txt` | root | Files outside `/opt/xampp-panel` that uninstall must delete |
 | `/usr/share/polkit-1/actions/io.github.shiron.xampppanel.policy` | root, 0644 | Password-prompt policy |
@@ -169,7 +193,13 @@
 | `/usr/share/icons/hicolor/scalable/status/xampp-panel-{running,stopped}.svg` | root, 0644 | Tray icons |
 | `/usr/local/bin/xampp-panel` | symlink | So `xampp-panel` works in a terminal |
 | `/run/xampp-panel/` | root, 0755 (tmpfs) | Created by `xampp-repair`: `repair.lock` (0600, one `xampp-repair` at a time) and, for the seconds a password reset runs, `reset-*/reset.sql` (`root:mysql`, 0710/0640, hash only); gone at reboot |
-| `~/.config/xampp-panel/settings.json` | you, 0600 | Created when you change the tray option |
+| `~/.config/xampp-panel/settings.json` | you, 0600 | Created when you change the tray option or press **Later** / **Hide** on an update bar (keys `dismissed_updates`, `dismissed_restore`: component → string) |
+| `~/.cache/xampp-panel/updates.json` | you, 0600 | Result of the background update check (§14). Removed by `uninstall.sh`, with its folder if empty |
+| `/opt/xampp-panel/state/restore-points.json` | root, 0644 | Public list of restore points so the panel can show its bar without root (§14). No secrets |
+| `/opt/xampp-panel/cache/` | root, 0700 | Scratch folder for downloads (a `pma-*` folder per update); emptied after each update |
+| `/var/backups/xampp-panel/<component>/<timestamp>/manifest.json` | root, folders 0700, file 0600 | The snapshot record of an update. **Outside `/opt/xampp-panel` on purpose:** `uninstall.sh` removes the app folder but keeps these (and says so) |
+| `/opt/lampp/phpmyadmin.before-<version>-<timestamp>` | as the old phpMyAdmin | The old phpMyAdmin folder, renamed, not copied: this is the restore point's content. Kept until the next successful update of phpMyAdmin or a restore. A full old copy of the folder (tens of MB) |
+| `/opt/lampp/phpmyadmin.new-<timestamp>` | root | Only while an update runs (the unpacked new version); removed afterwards |
 
 ### Files it edits (all reversible, all backed up once)
 
@@ -189,6 +219,7 @@
 | same | `UserPassword daemon` replaced with a new hash (`xampp-repair` → "Fix FTP config" only, not `setup.sh`) | none; detected by `configedit.proftpd_password_broken` |
 | `/etc/hosts` | `127.0.0.1  <name>.local` for each site | `# BEGIN xampp-panel sites` |
 | `/opt/lampp/phpmyadmin/config.inc.php` | `auth_type`, `controluser`, `controlpass`, `pmadb` set/updated by `xampp-repair` (text edit via `pmaconfig.py`; owner kept, see `fsutil.atomic_write`) | none; read back with `pmaconfig.get_value` |
+| `/opt/lampp/phpmyadmin/` (the whole folder) | Replaced by `xampp-update`: the old folder is renamed to `phpmyadmin.before-<version>-<timestamp>` and the new one takes its place. `config.inc.php`, its `.xampp-panel.bak` and `tmp` are copied into the new folder first, owner and mode kept (`config.inc.php` stays `daemon`) | none; the `.before-…` folder next to it |
 
 Files it creates inside XAMPP:
 
@@ -264,6 +295,14 @@
 | Anyone using the password prompt remotely | polkit policy: `allow_active = auth_admin_keep`; inactive and remote sessions are denied |
 | A damaged, swapped or planted XAMPP installer run as root by `setup.sh` | Only the pinned, checksummed file (`$XAMPP_FILE`) is picked up automatically, and only from the project folder and `~/Downloads` (not the folder above the project, which may be shared, e.g. `/tmp`). Other versions found there are only named in a hint (only file names matching the strict `xampp-linux-x64-<version>-<n>-installer.run` pattern, so no odd characters in a file name reach the terminal; the path is shell-quoted with `%q` so the suggested command can be pasted); a stray or planted `xampp-linux-x64-99.0-…` is never run. Whatever runs is first copied into a root-only folder under `/root` (`mktemp -d -p /root`, so not `$TMPDIR` and not a noexec `/tmp`); for the pinned version the SHA-256 is checked **on that copy**, which is what runs. Downloads and deletions in `~/Downloads` run as the user (`runuser`); curl is HTTPS-only, also on redirects, TLS 1.2+. A pinned file with a wrong checksum stops the install; it is deleted only if `setup.sh` downloaded it in this run. Another version runs only when given with `--installer` (the user's explicit choice), and then unchecked. curl runs with `-q` (no `~/.curlrc`) and its stdout goes to stderr, so nothing it prints can change the path `setup.sh` runs. |
 | A broken config taking Apache down | `apachectl -t` runs before every site change; on failure the previous vhost file is restored |
+| A tampered or substituted phpMyAdmin download (`xampp-update`, runs as root) | The SHA-256 from phpMyAdmin's `.sha256` file is checked and then the detached PGP signature is verified, both **before** anything is unpacked (`pma.py` `_download` runs before `safe_extract`). The signature must be good **and** its `VALIDSIG` primary-key fingerprint must be one of `PMA_SIGNERS` in `updates/config.py`; the published keyring is only key material in a throwaway `gpg` home. A missing `gpg` or a bad signature stops the update; there is no "continue anyway". Downloads go to a root-only folder (`/opt/xampp-panel/cache/pma-*`, 0700) and `Fetcher` refuses any other kind of folder. Because the compression trailer is never verified (below), the checksum and signature are the **only** integrity check |
+| A network attacker during an update or check | HTTPS only, redirects included, TLS 1.2+ with certificate checks; the opener has no plain-HTTP, FTP, `file:` or `data:` handler (`updates/http.py`). Integrity rests on the hash and signature, not on the host. The one plain-HTTP request, the local health probe of `http://127.0.0.1/phpmyadmin/`, goes straight to the local Apache |
+| A hostile list page or API answer | Size caps, a per-request deadline and per-socket timeouts (`UpdateConfig`); regex on fixed shapes and `json`, no `eval`; a version string must match the strict **ASCII** pattern (digits and dots) before it reaches a URL, path or command; an unexpected page is an error, not an empty list; `http.client` errors, bad `Content-Length` values and absurdly nested JSON become plain messages |
+| A malicious archive | `safe_extract` refuses absolute paths, `..`, devices, fifos, hard links, too many entries and too much unpacked data. It never creates or changes anything through a link: every parent is checked with `lstat` and a link or file where a folder should be is refused, a folder entry over a link is refused, and every symlink is checked by its text, by where it lands when created, and again by where it finally lands after unpacking. Files are created with `O_EXCL\|O_NOFOLLOW`, set-id bits are dropped (0644/0755). Limits: see §10 |
+| Running attacker data as root | Nothing downloaded is executed in phase 1 (phpMyAdmin is PHP files only; `php -l` runs on its `index.php` and only parses it). Everything runs from `/opt/xampp-panel/lib` with `python3 -I`; subprocesses use argument lists, never a shell. Copying the keep-list (`copy_owned`) cannot be steered through a link by Apache's `daemon` user, who owns some of those files |
+| A user-controlled file driving root | The root tool never reads the user's `updates.json` or `settings.json`; it fetches the lists itself. `xampp-update --check` runs as the user and writes only `~/.cache/xampp-panel/updates.json` |
+| Two tools changing XAMPP at once | `xampp-update` takes the same `flock` as `xampp-repair` (`/run/xampp-panel/repair.lock`) |
+| A leftover or half-done update | A snapshot is `pending` until the update is verified. A pending snapshot makes the next update refuse and the menu warn; **Restore previous version** puts the old folder back. The swap itself runs with SIGINT/SIGHUP/SIGTERM blocked |
 
 **Accepted limitation:** every site's PHP runs as `daemon` and can read anything `daemon` can read,
 including your other sites. That's normal for XAMPP and fine on a single-user computer.
@@ -471,6 +510,43 @@
   the next run; after the last failed attempt it is deleted, so a corrupt `.part` can't stick. The
   checksum guards the result either way.
 - **Minimum platform:** GTK 4.6 / libadwaita 1.1 / GLib 2.72. Newer widgets (`Adw.Banner`, `Gtk.FileDialog`) are used only when available.
+- **Update menu: a separate tool, not new `pkexec` commands.** Like `xampp-repair`, `xampp-update` is one
+  program run with `sudo` in a terminal, so the helper's whitelist (the attack surface) does not grow.
+  Cost if wrong: updating needs a terminal and `sudo`; there is no one-click update from the panel.
+- **phpMyAdmin is swapped by rename, not by copy over.** The new version is unpacked beside the old one,
+  the keep-list (`config.inc.php`, its `.bak`, `tmp`) is copied in with its owner, then the old folder is
+  renamed to `phpmyadmin.before-…` and the new one renamed into place (two renames, the second undone if
+  it fails). Cost if wrong: a full old copy stays in `/opt/lampp` until the next update or a restore, and
+  anything in the old folder that is not on the keep-list (hand edits) is **not** carried over; it stays in
+  the `.before-…` folder. If the machine dies between the two renames there is no `phpmyadmin` folder; the
+  next `xampp-update` warns (pending snapshot) and **Restore** renames the saved folder back.
+- **Signer fingerprints are pinned in code (`PMA_SIGNERS`).** Cost if wrong: if phpMyAdmin changes who
+  signs releases, updates are refused ("signed by a key that is not trusted") until the list is updated;
+  the failure is safe. The three fingerprints were read from phpMyAdmin's published keyring on 2026-10-08
+  and are to be confirmed against phpMyAdmin's own published instructions before the first real use.
+- **Both the checksum and the signature are required.** The checksum and the file come from the same host,
+  so the checksum only catches damage; the signature gives the authenticity. Cost if wrong: none for
+  safety, but an upstream without a `.asc` file cannot be updated from.
+- **One restore point per component; a restore uses it up.** A successful update deletes the previous
+  snapshot and its saved folder. Cost if wrong: you cannot go back two steps.
+- **Snapshots live in `/var/backups/xampp-panel`, outside the app folder.** So `uninstall.sh` (which
+  removes `/opt/xampp-panel`) cannot delete someone's only way back. Cost if wrong: leftovers after an
+  uninstall that the user must remove by hand (`uninstall.sh` says so).
+- **The panel learns about restore points from a public file, not from root.** `restore-points.json`
+  (0644, written atomically by the root tool) mirrors the finished snapshots, like `sites.json`. Cost if
+  wrong: if the file and the snapshot folders disagree (someone deleted a folder by hand) the panel offers
+  a restore that then says the saved folder is missing; nothing is changed.
+- **The update check stores plain version strings and the panel decides what to show.** "Later" saves the
+  `latest` it hid in `dismissed_updates`; the bar stays away while the newest version is that one or older and
+  comes back for a newer one. The "installed" version shown is read from disk each time (the cache can be a day old).
+  Cost if wrong: a withdrawn release that was hidden stays hidden until something newer than it appears.
+- **Archive and copy code never follow a link.** `safe_extract` checks every parent with `lstat`; `copy_owned`
+  works on open folder descriptors with `O_NOFOLLOW`. Cost if wrong: a legitimate archive that writes through its own
+  symlink (none seen: the real phpMyAdmin 5.2.3 tarball has no links at all) is refused, and `copy_owned` drops ACLs,
+  extended attributes and hard links.
+- **Browser-like `User-Agent` on every request** (`UpdateConfig.user_agent`). SourceForge (used by the
+  later XAMPP phase) refuses unknown clients. Cost if wrong: a site that blocks it fails with a plain
+  "answered 403" message; change the string in `config.py`.
 
 ---
 
@@ -492,6 +568,14 @@
 | FTP won't start: `unknown configuration directive 'function'` | `sudo xampp-repair` → "Fix FTP config" |
 | Starting `xampp-panel` from SSH/remote terminal fails with "Gtk couldn't be initialized" | Normal: there's no display. Open it from the app menu. Errors are then in `journalctl --user` |
 | `shellcheck` was never run on the scripts | `shellcheck -x setup.sh uninstall.sh lib/xampp-download.sh` |
+| **The update tool has not been run on a real XAMPP, as root, or on the target machine.** It is covered by the unit suite with fakes (network, `gpg`, `php`, Apache, file ownership). A read-only run of the real network code on 2026-10-08 (no root, nothing installed) did work against phpmyadmin.net: release list, `version.json`, download of phpMyAdmin 5.2.3 (7.7 MB), checksum, signature with the pinned key `3D06A59E…BD92`, and `safe_extract` of the real tarball (4314 files, 847 folders, no links). Not checked: `chown` to `daemon`, `bin/php -l`, the local probe, whiptail rendering, a real resume against a server that honours `Range`, the panel's bars on a real desktop, Python 3.10-3.12 | Do the manual checklist in the phase-1 plan (phpMyAdmin up and back) on the target before relying on it, and keep a phpMyAdmin Export of important databases |
+| Only phpMyAdmin can be updated (phase 1). MariaDB and XAMPP updates are designed (spec) but not built | Manual steps in §12 |
+| One restore point per component | Copy `/opt/lampp/phpmyadmin.before-…` elsewhere if you want to keep an older one |
+| A failed download is not resumed by the next run (the `.part` file is deleted after the last attempt); a dropped or short transfer within one run resumes from the `.part` file | Run it again |
+| After `uninstall.sh`, `/var/backups/xampp-panel` and `/opt/lampp/phpmyadmin.before-*` remain | Delete them by hand when no longer needed |
+| The root tool parses network answers in its own process | Accepted: caps, strict parsing, no external parsers (§6) |
+| `safe_extract` does not read the end of the compressed stream, so a damaged gzip/xz *trailer* is not noticed | By design: the checksum and signature are checked first and are the integrity check |
+| `copy_owned` does not keep ACLs, extended attributes (file capabilities) or hard links (they become separate copies) | Nothing in phpMyAdmin's keep-list needs them; check before using it on `htdocs` (phase 3) |
 
 ---
 
@@ -527,6 +611,12 @@
 | Chrome still can't open `.local` while `curl -I http://name.local` works | Chrome "Secure DNS" bypassing `/etc/hosts` | Chrome settings → Privacy → Security → turn off "Use secure DNS", or use Firefox |
 | Tray option greyed out ("needs the AppIndicator extension") | No AppIndicator/StatusNotifier support running in GNOME | Enable the AppIndicator extension in the Extensions app (on Zorin, check Zorin Appearance → Extensions); then reopen the panel |
 | Everything looks wrong after an XAMPP reinstall | XAMPP's config files were replaced | See §12, "Upgrading XAMPP" |
+| Update bar never appears | No internet, checked less than a day ago, cache older than 7 days is ignored, or dismissed with **Later** | `cat ~/.cache/xampp-panel/updates.json`; force a check as your user: `xampp-update --check --force`; hidden versions are in `~/.config/xampp-panel/settings.json` (`dismissed_updates`) |
+| Restore button/bar missing after an update | The update did not finish (snapshot still `pending`), the restore point was used, or the bar's 7 days passed | `cat /opt/xampp-panel/state/restore-points.json`; `sudo ls -R /var/backups/xampp-panel`; the menu item is enabled while the file lists any restore point |
+| `xampp-update`: "An earlier update of phpMyAdmin did not finish" | The tool was killed or lost power mid-update after it had changed something (a pending snapshot that changed nothing is cleared automatically on the next run) | Choose **Restore previous version** (or `sudo xampp-update --restore phpmyadmin`) |
+| An update failed **and** the automatic rollback failed (`RollbackFailed`) | The message prints the exact commands and the snapshot is kept | By hand: (1) only if `/opt/lampp/phpmyadmin` still exists, `sudo mv /opt/lampp/phpmyadmin /opt/lampp/phpmyadmin.broken`; (2) `sudo mv /opt/lampp/phpmyadmin.before-<version>-<timestamp> /opt/lampp/phpmyadmin`; then `ls -ld /opt/lampp/phpmyadmin/config.inc.php` should show owner `daemon` |
+| `xampp-update` refuses with "gpg is not installed" | `gnupg` missing | `sudo apt install gnupg` (setup installs it) |
+| "signed by a key that is not trusted" | phpMyAdmin changed who signs releases, or a tampered download | Do not bypass. Compare the fingerprint with phpMyAdmin's published instructions, then update `PMA_SIGNERS` in `updates/config.py` |
 
 Full manual reset of the config, if the tools themselves are broken:
 
@@ -553,7 +643,7 @@
 ```
 
 `setup.sh` is idempotent: steps already done are skipped or give the same result. Use `--lean` instead of
-`--no-lean` if you use lean mode. For a single changed file, copying it is enough:
+`--no-lean` if you use lean mode. For a single changed file, copying it is enough (files of the update tool go to `lib/xampp_panel/updates/`):
 
 ```bash
 sudo install -o root -g root -m 0644 src/xampp_panel/<file>.py /opt/xampp-panel/lib/xampp_panel/
@@ -568,6 +658,12 @@
 
 If it prints differences, re-run `sudo ./setup.sh --no-lean` (or `--lean`).
 
+### Updating phpMyAdmin (and, later, MariaDB and XAMPP)
+
+Use the update menu: **☰ → Update components…** or `sudo xampp-update` (§14). It does the folder swap,
+keeps `config.inc.php`, verifies the result and keeps a restore point. Phase 1 covers phpMyAdmin only;
+for MariaDB and XAMPP use the manual steps below.
+
 ### Upgrading XAMPP (new version or reinstall)
 
 A new XAMPP installer replaces `/opt/lampp`, including its config files, so the panel's edits disappear.
@@ -677,3 +773,157 @@
    fix_label)` so a failure is reported but doesn't abort `setup.sh`.
 6. Document it: one line in the "Main menu" table (§ design spec or here), and a troubleshooting row
    in §11 / `docs/USER-GUIDE.md` pointing at the new menu item.
+
+### Adding an update component
+
+A component is one class in `src/xampp_panel/updates/` with the `Component` protocol from `updates/base.py`:
+`key`, `title`, `installed()`, `releases()` (newest first), `plan(target)` → `Plan`, `apply(target)` → message,
+`restore_note(snapshot)` and `restore()` → message. `PhpMyAdminComponent` (`updates/pma.py`) is the model.
+
+1. **Source.** Add a source class to `updates/releases.py` that turns an upstream list into `Release` objects.
+   Take every URL and limit from `UpdateConfig` (add fields there, not literals), go through `Transport`, validate
+   every version with `versions.is_valid` and treat an unexpected shape as `UpdateError`, never as an empty list.
+2. **Order of work in `apply`:** preflight (disk, paths) → download into the root-only cache folder → verify
+   (`verify_hashes`, plus a signature where the vendor has one) → only then unpack (`safe_extract`) → check
+   the unpacked version → `Snapshots.begin(...)` (record what you need to undo in its `data`) → swap inside
+   `critical_section()` → verify the live result → `Snapshots.commit(...)`.
+3. **Failure:** anything after `begin` must put the old state back and re-raise as `UpdateError`
+   (`snapshots.abort`). If putting it back fails too, raise `RollbackFailed` with the exact manual commands and
+   leave the snapshot so **Restore previous version** can still try.
+4. **Restore:** `restore()` brings back what the manifest recorded, verifies, and calls `Snapshots.discard(key)`.
+   Validate every path read back from a manifest (`pma.py` `_saved_copy` accepts only its own `*.before-*` folder).
+5. **Register it** in `default_components()` in `updates/app.py`. The menu, the restore menu, the check, the
+   panel bars and the public index pick it up from there.
+6. **Tests** (`tests/test_update_<name>.py`): scripted `FakeDialogs`/fake network from `tests/update_fakes.py`, a
+   temp-dir `Paths`; cover the order of steps, the failure path at every step, cancel at every question, and that
+   nothing is unpacked when a hash or signature fails.
+7. **Document it:** a row in §3, the files in §4, any new threat in §6, and a User guide line.
+
+---
+
+## 14. The update tool (`xampp-update`), phase 1
+
+Spec: `docs/superpowers/specs/2026-10-08-update-menu-design.md`. Plan: `docs/superpowers/plans/2026-10-08-update-menu-phase1.md`.
+Phase 1 = core, phpMyAdmin, the startup check and the restore button. **Verification status:** unit tests with fakes, plus one
+read-only run of the real network code against phpmyadmin.net; not run on a real XAMPP or as root (see §10).
+
+### Commands
+
+| Command | Runs as | What it does |
+|---|---|---|
+| `sudo xampp-update` | root | The menu "Choose what to do:": one line per component (`phpMyAdmin  5.2.1 → 5.2.3 available`, `... up to date`, or `... (could not check)`), **Restore previous version…**, **Check for updates now**, Quit |
+| `sudo xampp-update --restore [COMPONENT]` | root | Straight to the restore choice (skipped when only one restore point exists) and its confirmation; this is what the panel's **Restore previous version** (bar and ☰ item) opens in a terminal |
+| `xampp-update --check [--force]` | you | Refreshes `~/.cache/xampp-panel/updates.json`; at most once a day unless `--force`; never fails loudly; ended by `SIGALRM` after `check_budget` + 30 s if it hangs. The panel starts it in the background when its window opens (only if `/opt/xampp-panel/bin/xampp-update` exists) |
+
+Exit codes: `0` ok, `1` not root / `whiptail` missing / another copy running / a `--restore` that failed or was cancelled, `2` bad arguments, `130` Ctrl-C.
+`--check` exits `0`; if it is still running after `check_budget` + 30 s the alarm ends it silently (no handler is installed, so the exit status is the signal's), and the cache file is written atomically, so it is never left half-written.
+
+### Flow
+
+```
+ panel opens ──► xampp-update --check (your user, background) ──► ~/.cache/xampp-panel/updates.json
+     │                                                                   │
+     ├── update bar  "phpMyAdmin 5.2.3 is available (you have 5.2.1)."  ◄─┘  panelstate.compute()
+     │   [Update…] [Later]            installed version = read from disk (panelstate.local_versions)
+     │                                "Later" -> settings.json dismissed_updates
+     └── restore bar "phpMyAdmin was updated to 5.2.3. Something not working?"
+         [Restore previous version] [Hide]    ◄── /opt/xampp-panel/state/restore-points.json
+                                              (written by root: Snapshots.commit / discard; "Hide" -> dismissed_restore)
+ [Update…] / ☰ "Update components…"        ─► terminal: sudo /opt/xampp-panel/bin/xampp-update
+ [Restore previous version] / ☰ "Restore…" ─► terminal: sudo /opt/xampp-panel/bin/xampp-update --restore
+                                                    │
+                           UpdateApp (updates/app.py, root; one at a time with xampp-repair: flock)
+        Component.apply():  preflight → clear a harmless pending snapshot → download (Fetcher) → sha256 + PGP (Gpg)
+                            → unpack (safe_extract) → check version → Snapshots.begin (pending)
+                            → keep-list copied in, swap inside critical_section() → verify
+                            → Snapshots.commit (ready, older snapshot + its saved folder deleted, index rewritten)
+        any failure after begin: the old folder is put back automatically (snapshot aborted)
+```
+
+### phpMyAdmin component (`updates/pma.py`)
+
+1. **Preflight:** `/opt/lampp/phpmyadmin` must be a normal folder (not a link); free space on its disk at least
+   `pma_min_free_bytes` (300 MB). A pending snapshot from a run that was killed **before** it changed anything is cleared; any other
+   pending snapshot stops the update ("An earlier update of phpMyAdmin did not finish…") before anything is downloaded.
+2. **Plan:** refuses a target whose PHP range (`version.json`, when known for that branch) excludes the installed
+   PHP (`bin/php -v`); a range the code does not understand does not block. The live `version.json` lists two branches (5.2.x, 4.9.x),
+   so older branches have no range and are not checked. Labels the change `upgrade`, `downgrade` or `reinstall`.
+3. **Download** into `/opt/xampp-panel/cache/pma-XXXX/`, check the SHA-256, download the `.asc` (64 KB cap) and
+   verify it with the pinned fingerprints. Then **unpack** to `phpmyadmin.new-<UTC stamp>` (top folder stripped) and
+   check that its `README` says the target version and that `index.php` exists.
+4. **Snapshot** (`pending`, `data = {"parked": "<path of the .before-… folder>"}`), then **swap** with signals
+   blocked: copy the keep-list (`pma_keep`) into the new folder with `copy_owned`, rename live → `phpmyadmin.before-<old version>-<stamp>`,
+   rename new → live (undo the first rename if the second fails).
+5. **Verify:** `README` version equals the target; `bin/php -l index.php` passes; if Apache is running,
+   `http://127.0.0.1/phpmyadmin/` answers 200/301/302/303 within 10 s (plain HTTP to localhost, deliberately
+   not through the HTTPS-only client). Failure → the old folder is renamed back (signals blocked) and an `UpdateError` explains;
+   if even that fails, a `RollbackFailed` message lists the commands and the snapshot stays.
+6. **Commit:** the snapshot becomes `ready`, older snapshot folders and the previous saved phpMyAdmin folder are deleted, the
+   public index is rewritten. Half-made folders (`phpmyadmin.new-*`, `phpmyadmin.replaced-*`) and `.before-*` folders that no restore point
+   refers to are swept away at the start of the next update or restore.
+
+**Restore** accepts only the saved folder named in the manifest if it is a `phpmyadmin.before-*` folder next to the live one. It
+swaps it in (the live folder's keep-list is copied into it first, so the *current* `config.inc.php` stays) and **verifies the restored version**:
+if that fails, the newer version is swapped back and the restore point is kept. Only then is the snapshot discarded (index rewritten). If
+`phpmyadmin` is missing because an update was killed between its two renames, the saved folder is simply renamed back. A restore after a
+run killed before it changed anything says there was nothing to restore.
+
+### Restore points and the public index file
+
+A snapshot is a folder `/var/backups/xampp-panel/<component>/<UTC timestamp>/` (root, 0700) holding `manifest.json` (0600):
+
+```json
+{"component": "phpmyadmin", "title": "phpMyAdmin", "from_version": "5.2.1", "to_version": "5.2.3",
+ "created": "2026-10-08T22:30:00+00:00", "status": "ready", "data": {"parked": "/opt/lampp/phpmyadmin.before-5.2.1-20261008223000"}}
+```
+
+`status` is `pending` from `Snapshots.begin` until the update is verified, then `ready` (`commit`). A restore point
+is the newest snapshot of a component **if it is `ready`**. `abort` deletes the folder of a failed update that was
+rolled back; `discard` deletes all of a component's snapshots after a restore.
+
+`/opt/xampp-panel/state/restore-points.json` (root, 0644, atomic write, best effort) lists the restore points for the panel:
+
+```json
+{"restore_points": [{"component": "phpmyadmin", "title": "phpMyAdmin", "from_version": "5.2.1",
+                     "to_version": "5.2.3", "created": "2026-10-08T22:30:00+00:00"}]}
+```
+
+No secrets. The panel reads it without root with `restore_points.load`, which treats a missing, damaged or
+oddly shaped file as "no restore points". The restore bar shows points from the last `restore_bar_days` (7) days (a `created` more than a day in the
+future is ignored) whose `created` differs from `dismissed_restore[component]`; the ☰ item is enabled while any point exists. The panel re-reads the file when its
+window regains focus, so the bar disappears after a restore. Only the root tool writes the file; if it disagrees with the
+snapshot folders, `xampp-update` trusts the folders.
+
+### Update check cache
+
+`~/.cache/xampp-panel/updates.json` (you, 0600, atomic):
+
+```json
+{"checked_at": 1791500000.0,
+ "components": {"phpmyadmin": {"title": "phpMyAdmin", "installed": "5.2.1", "latest": "5.2.3", "latest_at": 1791500000.0}}}
+```
+
+`checked_at` and `latest_at` are Unix times (seconds). `installed` is read fresh on every run; `latest` is the top of the offered list, so
+the bar and the menu agree. A run within `check_throttle_seconds` (24 h) of the last one does nothing unless `--force`. A component whose list
+cannot be fetched keeps its previous `latest`, until that is older than `cache_max_age_seconds` (7 days) and ignored; the same age limit applies to
+the whole file, and a time in the future (a clock that was wrong) counts as too old. Once `check_budget` (30 s) has passed, the remaining components are not fetched.
+The bar shows a component when `latest` is newer than `installed` and not hidden: `Later` stores the `latest` it hid in `dismissed_updates[component]`, and the
+component stays hidden while `latest` is that version or older.
+
+### Sources and how to change them
+
+All addresses are fields of `UpdateConfig` (`updates/config.py`):
+
+| Use | Field | Default |
+|---|---|---|
+| Release list (parsed with a regex on `href="/files/<ver>/"`) | `pma_files_url` | `https://www.phpmyadmin.net/files/` |
+| PHP range per branch | `pma_version_json_url` | `https://www.phpmyadmin.net/home_page/version.json` |
+| Download, `.sha256`, `.asc` | `pma_download_base` | `https://files.phpmyadmin.net/phpMyAdmin` (`<ver>/phpMyAdmin-<ver>-all-languages.tar.xz`) |
+| Key material | `pma_keyring_url` | `https://files.phpmyadmin.net/phpmyadmin.keyring` |
+| Trust | `pma_signers` (`PMA_SIGNERS`) | three primary-key fingerprints, pinned in `UpdateConfig`; to be confirmed against phpMyAdmin's own published instructions before the first real use |
+| Local health probe | `local_probe_url` | `http://127.0.0.1/phpmyadmin/` |
+
+If phpMyAdmin changes its page format, `PhpMyAdminSource.releases()` raises "unexpected format" instead of offering
+nothing; fix the regex in `updates/releases.py` and the fixture in `tests/test_update_releases.py`.
+Other tunables: `count` (5), `http_timeout`, `stall_timeout`, `request_deadline`, `max_response_bytes`, `max_download_bytes`, `download_attempts`,
+`download_min_seconds`, `download_min_bytes_per_second`, `archive_max_entries`, `archive_max_bytes`, `pma_min_free_bytes`, `pma_keep`.
`````

- [ ] **Step 2: Check the docs against the code**

Open the three files and confirm by reading: module names and file paths exist; the menu and bar strings match `app.py`, `panelstate.py` and `window.py`; the cache and manifest formats match `check.py` and `snapshots.py`; every limitation listed in the review recheck is stated.

- [ ] **Step 3: Commit**

`````bash
git add README.md docs/USER-GUIDE.md docs/MAINTAINER.md
git -c user.name="Shiron Cilia" -c user.email="shircil07@gmail.com" commit -m "docs: updates, restore button and update security model"
`````

---

### Task 12: Review, verification on the target machine and handover

Nothing in this plan was run on a real XAMPP, as root or with a desktop session. This task closes that gap before the work is called done.

- [ ] **Step 1: Full suite and syntax checks**

`````bash
PYTHONPATH=src python3 -m unittest discover -s tests
bash -n setup.sh uninstall.sh
python3 -m py_compile src/xampp_panel/window.py bin/xampp-update
`````

Expected: `Ran 597 tests` … `OK` (1 skipped without GTK 4), no output from the other commands.

- [ ] **Step 2: Parallel review (standing rule)**

Dispatch three read-only review agents on the diff of Tasks 1–11: (a) security (downloads, unpacking, root paths, signature check, restore-point handling, manifest-driven deletes), (b) dead or useless code and correctness bugs (rollback ordering, killed runs, stale state), (c) efficiency and best practices. Verify every finding against the code, report by severity, fix what the owner approves (each fix with a regression test), then have a **fresh** agent review the fixes.

- [ ] **Step 3: Install and check on the target machine (as the owner, with sudo)**

`````bash
sudo ./setup.sh --no-lean             # re-run is safe; installs xampp-update and gnupg
ls -l /opt/xampp-panel/bin/xampp-update /usr/local/bin/xampp-update
xampp-update --check --force            # as your normal user: no password
cat ~/.cache/xampp-panel/updates.json   # phpmyadmin: installed 5.2.1, latest 5.2.3 (or newer)
`````

- [ ] **Step 4: Check the panel**

Open **XAMPP Control Panel**. Expect the bar "phpMyAdmin 5.2.3 is available (you have 5.2.1)." with **Update…** and **Later**. **Later** hides it; reopening the panel keeps it hidden. ☰ shows **Update components…** and a greyed-out **Restore previous version…** (no restore point yet). Note anything that looks wrong in the layout: this is the only GTK code that has not been run.

- [ ] **Step 5: Update phpMyAdmin for real, then go back**

Export any database you care about from phpMyAdmin first (the update does not touch databases, but this is the habit). Then:

`````bash
sudo xampp-update        # 1 phpMyAdmin -> pick 5.2.3 -> read the summary -> yes
# afterwards, in a browser: http://localhost/phpmyadmin/ loads and logs in
ls -ld /opt/lampp/phpmyadmin /opt/lampp/phpmyadmin.before-*
ls -l /opt/lampp/phpmyadmin/config.inc.php      # still daemon:daemon, same mode as before
ls -l /var/backups/xampp-panel/phpmyadmin/*/manifest.json
cat /opt/xampp-panel/state/restore-points.json
`````

Back in the panel: the restore bar "phpMyAdmin was updated to 5.2.3. Something not working?" appears, and the update bar is gone. Click **Restore previous version**: a terminal opens at the confirmation (no menu to find), say yes. Check that `http://localhost/phpmyadmin/` shows 5.2.1 again, `config.inc.php` still has any change you made after the update, and `/opt/xampp-panel/state/restore-points.json` is empty.

- [ ] **Step 6: Failure paths worth seeing once**

`````bash
# a checksum that does not match must stop before anything is unpacked: with the network disconnected mid-download,
# run `sudo xampp-update` and pick a version; expect a plain message and an untouched /opt/lampp/phpmyadmin
# a killed run: start an update, press Ctrl-C during "Downloading", run sudo xampp-update again -> it must still work
sudo ./uninstall.sh      # (optional, on a spare machine) removes the cache; /var/backups/xampp-panel must remain
`````

- [ ] **Step 7: Record what was verified**

Add the results (what ran, what did not, the Python version on the target) to `docs/MAINTAINER.md` §10/§14 and tell the owner plainly if any step above failed or was skipped. Only then is Phase 1 done. Phases 2 (MariaDB) and 3 (XAMPP) start with the read-only probe items listed in the spec and get their own plans.

---

## Phases 2 and 3 (not part of this plan)

Planned separately, after this phase is reviewed and the probe items in the spec's "Facts" section are answered on the target machine: **Phase 2** — MySQL (MariaDB): side-by-side install, rehearsal on a copy of the data, in-place and export/reload paths, `my.cnf` block, `Paths` active slot, host check for the API-provided download URL (redirects stay allowed), rollback. **Phase 3** — PHP + Apache (XAMPP): SourceForge list, typed confirmation, snapshot by rename, carry-over, re-apply panel config, rollback. Both reuse `Snapshots`, `Fetcher`, `archive`, `copy_owned`, `Gpg`-style verification and the restore button unchanged.

## Self-review notes

- Spec coverage: components, version lists in both directions (phpMyAdmin), startup bar and "Later", snapshots and automatic rollback, restore button (Tasks 5–9), security rules (Tasks 2–4, 6), docs (Task 11), setup/uninstall (Task 10). MariaDB and XAMPP are Phases 2–3 by design.

- Every code block in Tasks 1–10 is the exact content of a file that passes the suite in a replay on a clean copy of the repository at the commit before this plan.

