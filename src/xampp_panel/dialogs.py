"""whiptail dialog boxes for xampp-repair. whiptail draws on the terminal and writes the answer to stderr."""

import os
import subprocess
import tempfile

TITLE = "XAMPP repair & configure"


class Dialogs:
    def __init__(self, run=subprocess.run, height: int = 20, width: int = 74):
        self.run = run
        self.size = [str(height), str(width)]

    def _show(self, *args: str) -> subprocess.CompletedProcess:
        return self.run(["whiptail", "--title", TITLE, *args], stderr=subprocess.PIPE, text=True)

    def _answer(self, *args: str) -> str | None:
        proc = self._show(*args)
        return proc.stderr if proc.returncode == 0 else None  # 1 = Cancel, 255 = Esc

    def menu(self, text: str, items: list[tuple[str, str]]) -> str | None:
        flat = [part for item in items for part in item]
        return self._answer("--menu", text, *self.size, str(len(items)), *flat)

    def yesno(self, text: str) -> bool:
        return self._show("--yesno", text, *self.size).returncode == 0

    def msgbox(self, text: str) -> None:
        self._show("--scrolltext", "--msgbox", text, *self.size)

    def passwordbox(self, text: str) -> str | None:
        return self._answer("--passwordbox", text, *self.size)

    def secret(self, title: str, text: str) -> None:
        """Show `text` in a scrolling box without it ever appearing on a process's argv (e.g. a password).

        whiptail's own text arguments land on its argv, which anyone can read from /proc while
        the dialog is open; a file (mode 0600, owned by the caller) does not have that problem.
        """
        fd, path = tempfile.mkstemp(prefix="xampp-repair-", suffix=".txt")  # mode 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.run(["whiptail", "--title", title, "--scrolltext", "--textbox", path, *self.size],
                     stderr=subprocess.PIPE, text=True)
        finally:
            os.unlink(path)
