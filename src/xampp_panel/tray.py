"""Tray icon: GTK 3 + AyatanaAppIndicator, in its own lightweight process.

Quits by itself when the "tray" setting is turned off. Refreshes on inotify
events, with a 30 s fallback; there is no busy polling.
"""

import sys

TRAY_ID = "io.github.shiron.XamppPanel.Tray"
FALLBACK_SECONDS = 30


def run_tray() -> int:
    import gi

    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except (ValueError, ImportError):
        print("xampp-panel: the tray needs the gir1.2-ayatanaappindicator3-0.1 package", file=sys.stderr)
        return 1
    from gi.repository import Gio, GLib, Gtk

    from . import privileged, services, settings
    from .paths import DEFAULT as PATHS
    from .services import State
    from .watch import StatusWatcher

    class Tray(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=TRAY_ID)

        def do_startup(self):
            Gtk.Application.do_startup(self)
            self.hold()  # no windows; stay alive until quit
            self.indicator = AppIndicator.Indicator.new(
                "xampp-panel", "xampp-panel-stopped", AppIndicator.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.indicator.set_title("XAMPP")

            menu = Gtk.Menu()
            self.status_item = Gtk.MenuItem(label="XAMPP", sensitive=False)
            menu.append(self.status_item)
            menu.append(Gtk.SeparatorMenuItem())
            for label, callback in (
                ("Start Apache + MySQL", lambda *_: self.helper("start", "all")),
                ("Stop all", lambda *_: self.helper("stop", "all")),
                ("Open control panel", lambda *_: self.open_panel()),
            ):
                item = Gtk.MenuItem(label=label)
                item.connect("activate", callback)
                menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())
            hide = Gtk.MenuItem(label="Hide tray icon")
            hide.connect("activate", lambda *_: self.disable())
            menu.append(hide)
            menu.show_all()
            self.indicator.set_menu(menu)

            self.watcher = StatusWatcher(PATHS.watch_dirs, self.refresh, FALLBACK_SECONDS)
            self.watcher.resume()
            self.settings_monitor = Gio.File.new_for_path(str(settings.config_path())).monitor_file(
                Gio.FileMonitorFlags.NONE, None)
            self.settings_monitor.connect("changed", self._settings_changed)
            self.refresh()

        def do_activate(self):
            pass  # a second launch just finds this instance

        def refresh(self):
            states = services.snapshot(PATHS)
            running = [services.BY_KEY[k].title for k, s in states.items() if s == State.RUNNING]
            if running:
                self.indicator.set_icon_full("xampp-panel-running", "XAMPP running")
                self.status_item.set_label("Running: " + ", ".join(running))
            else:
                self.indicator.set_icon_full("xampp-panel-stopped", "XAMPP stopped")
                self.status_item.set_label("XAMPP is stopped")

        def helper(self, *args):
            try:
                proc = Gio.Subprocess.new(privileged.argv_for(*args),
                                          Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
            except GLib.Error:
                return
            proc.wait_async(None, lambda *_: self.watcher.poke())

        def open_panel(self):
            try:
                Gio.Subprocess.new([str(PATHS.launcher)], Gio.SubprocessFlags.NONE)
            except GLib.Error:
                pass

        def disable(self):
            data = settings.load()
            data["tray"] = False
            settings.save(data)
            self.quit()

        def _settings_changed(self, *_):
            if not settings.load()["tray"]:
                self.quit()

    return Tray().run([sys.argv[0]])
