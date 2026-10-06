"""Open xampp-repair in a terminal emulator (no GTK imports, so it is testable)."""

import shlex
import shutil

from .paths import DEFAULT, Paths

# Tried in order; each with the option that runs a command.
TERMINALS = (
    ("gnome-terminal", ("--",)),
    ("ptyxis", ("--",)),
    ("kgx", ("--",)),
    ("x-terminal-emulator", ("-e",)),
)


def repair_command(paths: Paths = DEFAULT) -> list[str]:
    """sudo + xampp-repair, then wait so a sudo error stays readable before the window closes."""
    script = f"sudo {shlex.quote(str(paths.repair))}; printf '\\nPress Enter to close. '; read _"
    return ["sh", "-c", script]


def terminal_argv(command: list[str], which=shutil.which, terminals=TERMINALS) -> list[str] | None:
    for name, run_option in terminals:
        path = which(name)
        if path:
            return [path, *run_option, *command]
    return None
