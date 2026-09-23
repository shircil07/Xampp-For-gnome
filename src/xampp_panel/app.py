"""The Adw.Application: single instance, app-level actions (tray, lean mode, quit)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from . import configedit, settings  # noqa: E402
from .paths import DEFAULT as PATHS  # noqa: E402
from .window import MainWindow  # noqa: E402

APP_ID = "io.github.shiron.XamppPanel"
_SNI_WATCHER = "org.kde.StatusNotifierWatcher"  # provided by GNOME's AppIndicator extension


def tray_available() -> bool:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "NameHasOwner", GLib.Variant("(s)", (_SNI_WATCHER,)), GLib.VariantType("(b)"),
                              Gio.DBusCallFlags.NONE, 500, None)
        return reply.unpack()[0]
    except GLib.Error:
        return False


def launch_tray() -> None:
    try:
        Gio.Subprocess.new([str(PATHS.launcher), "--tray"], Gio.SubprocessFlags.NONE)
    except GLib.Error:
        pass


def lean_enabled() -> bool:
    try:
        return configedit.has_block(PATHS.httpd_conf.read_text(), "lean")
    except OSError:
        return False


class PanelApp(Adw.Application):
    def __init__(self):
        flags = getattr(Gio.ApplicationFlags, "DEFAULT_FLAGS", Gio.ApplicationFlags.FLAGS_NONE)
        super().__init__(application_id=APP_ID, flags=flags)
        self.settings = settings.load()

    def do_startup(self):
        Adw.Application.do_startup(self)
        tray = Gio.SimpleAction.new_stateful("tray", None, GLib.Variant.new_boolean(self.settings["tray"]))
        tray.set_enabled(tray_available())
        tray.connect("change-state", self._on_tray)
        self.add_action(tray)

        lean = Gio.SimpleAction.new_stateful("lean", None, GLib.Variant.new_boolean(lean_enabled()))
        lean.connect("change-state", self._on_lean)
        self.add_action(lean)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        if self.settings["tray"] and tray.get_enabled():
            launch_tray()

    def do_activate(self):
        window = self.props.active_window or MainWindow(self)
        window.present()

    def _on_tray(self, action, value):
        action.set_state(value)
        self.settings["tray"] = value.get_boolean()
        settings.save(self.settings)
        if value.get_boolean():
            launch_tray()  # the tray quits by itself when the setting turns off

    def _on_lean(self, action, value):
        on = value.get_boolean()
        window = self.props.active_window
        if window is None:
            return

        def done(_out):
            action.set_state(value)
            window.toast(f"Lean mode {'on' if on else 'off'}. Restart Apache and MySQL to apply.")

        window.call_helper(["lean", "on" if on else "off"], done=done)


def run_app(argv) -> int:
    return PanelApp().run(argv)
