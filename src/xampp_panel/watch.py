"""Event-driven status updates shared by the panel and the tray.

inotify (Gio.FileMonitor) on XAMPP's PID/socket directories triggers a
refresh; a slow fallback timer (only while resumed) catches crashes that
leave stale files behind. Uses only Gio/GLib, so it works with GTK 3 and 4.
"""

from gi.repository import Gio, GLib

_TRIGGER_SUFFIXES = (".pid", ".sock")
_DEBOUNCE_MS = 300


class StatusWatcher:
    def __init__(self, dirs, callback, fallback_seconds: int):
        self._callback = callback
        self._fallback_seconds = fallback_seconds
        self._debounce = 0
        self._timer = 0
        self._monitors = []
        for d in dirs:
            try:
                monitor = Gio.File.new_for_path(str(d)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            except GLib.Error:
                continue  # unreadable dir (e.g. var/mysql): the fallback timer covers it
            monitor.connect("changed", self._on_changed)
            self._monitors.append(monitor)

    def _on_changed(self, _monitor, file, _other, _event):
        name = file.get_basename() or ""
        if name.endswith(_TRIGGER_SUFFIXES):
            self.poke()

    def poke(self) -> None:
        """Schedule one refresh soon (coalesces bursts of events)."""
        if not self._debounce:
            self._debounce = GLib.timeout_add(_DEBOUNCE_MS, self._fire)

    def _fire(self):
        self._debounce = 0
        self._callback()
        return GLib.SOURCE_REMOVE

    def resume(self) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(self._fallback_seconds, self._tick)

    def pause(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self):
        self._callback()
        return GLib.SOURCE_CONTINUE
