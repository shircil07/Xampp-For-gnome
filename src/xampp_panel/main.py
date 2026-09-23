"""Entry point. `xampp-panel` opens the panel; `xampp-panel --tray` runs the tray icon."""

import sys


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    if "--tray" in argv[1:]:
        from .tray import run_tray  # GTK 3: must not share a process with GTK 4
        return run_tray()
    from .app import run_app
    return run_app(argv)


if __name__ == "__main__":
    sys.exit(main())
