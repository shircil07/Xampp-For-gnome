"""Talking to the root helper through pkexec (GUI side, no GTK imports)."""

from .paths import DEFAULT, Paths

# pkexec: 126 = the user dismissed the dialog, 127 = not authorized, or the
# helper binary itself is missing/not executable.
_CANCELLED = 126
_NOT_AUTHORIZED = 127


class HelperError(Exception):
    pass


class Cancelled(HelperError):
    pass


def argv_for(*args: str, paths: Paths = DEFAULT) -> list[str]:
    return ["pkexec", str(paths.helper), *args]


def interpret(returncode: int, stdout: str, stderr: str) -> str:
    if returncode == _CANCELLED:
        raise Cancelled("authentication cancelled")
    if returncode == _NOT_AUTHORIZED:
        raise HelperError("Not authorized, or the XAMPP Panel helper is missing")
    if returncode != 0:
        lines = [line for line in (stderr or stdout).splitlines() if line.strip()]
        raise HelperError(lines[-1].strip() if lines else f"the helper failed (exit code {returncode})")
    return stdout
