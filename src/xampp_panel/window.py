"""Main window: Services and Sites pages (GTK 4.6+ / libadwaita 1.1+)."""

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import fsutil, privileged, services, sites  # noqa: E402
from .paths import DEFAULT as PATHS  # noqa: E402
from .services import State  # noqa: E402
from .watch import StatusWatcher  # noqa: E402

FALLBACK_SECONDS = 10
SITES_DIR = Path.home() / "Sites"
STARTER_PHP = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{name}.local</title></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 4rem auto; line-height: 1.5">
<h1>{name}.local works</h1>
<p>Edit <code><?= htmlspecialchars(__FILE__) ?></code> to get started.</p>
<p>PHP <?= PHP_VERSION ?></p>
</body></html>
"""
_DOT_CLASS = {State.RUNNING: "success", State.STARTING: "warning",
              State.CONFLICT: "error", State.STOPPED: "dim-label"}
_STATE_NOTE = {State.STARTING: " · starting…", State.CONFLICT: " · port used by another program"}


def open_uri(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        pass


def _esc(text) -> str:
    return GLib.markup_escape_text(str(text))


def _make_banner(text):
    """Adw.Banner on libadwaita ≥ 1.3, a revealer with a label otherwise."""
    if hasattr(Adw, "Banner"):
        banner = Adw.Banner(title=text)
        return banner, banner.set_revealed
    label = Gtk.Label(label=text, wrap=True, margin_top=8, margin_bottom=8,
                      margin_start=12, margin_end=12, css_classes=["warning"])
    revealer = Gtk.Revealer(child=label)
    return revealer, revealer.set_reveal_child


class ServiceRow(Adw.ActionRow):
    def __init__(self, svc, has_log, on_toggle, on_log):
        super().__init__(title=svc.title)
        self.svc = svc
        self.dot = Gtk.Label(label="●")
        self.add_prefix(self.dot)
        if has_log:
            log = Gtk.Button(icon_name="text-x-generic-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="View log", css_classes=["flat"])
            log.connect("clicked", lambda *_: on_log(svc))
            self.add_suffix(log)
        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._handler = self.switch.connect("notify::active", lambda sw, _p: on_toggle(svc, sw.get_active()))
        self.add_suffix(self.switch)
        self.set_activatable_widget(self.switch)

    def show_state(self, state: State, busy: bool) -> None:
        if busy:
            self.dot.set_css_classes(["warning"])
            self.switch.set_sensitive(False)
            self.set_subtitle(_esc(f"{self.svc.description} · port {self.svc.port} · working…"))
            return
        self.dot.set_css_classes([_DOT_CLASS[state]])
        self.switch.handler_block(self._handler)
        self.switch.set_active(state in (State.RUNNING, State.STARTING))
        self.switch.handler_unblock(self._handler)
        self.switch.set_sensitive(state != State.CONFLICT)
        self.set_subtitle(_esc(f"{self.svc.description} · port {self.svc.port}{_STATE_NOTE.get(state, '')}"))


class LogWindow(Adw.Window):
    def __init__(self, parent, title, load_text):
        super().__init__(transient_for=parent, title=f"{title} log", default_width=760, default_height=480)
        self._load_text = load_text
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                 top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        scroll = Gtk.ScrolledWindow(child=self.view, vexpand=True)
        header = Adw.HeaderBar()
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Reload")
        refresh.connect("clicked", lambda *_: self.reload())
        header.pack_start(refresh)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(scroll)
        self.set_content(box)
        self.set_text(load_text())
        self.connect("map", lambda *_: GLib.idle_add(self._scroll_to_end))

    def reload(self) -> None:
        self.set_text(self._load_text())

    def set_text(self, text) -> None:
        self.view.get_buffer().set_text(text or "The log is empty.")
        GLib.idle_add(self._scroll_to_end)

    def _scroll_to_end(self):
        buffer = self.view.get_buffer()
        end = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.view.scroll_to_mark(end, 0, False, 0, 1)
        return False


class AddSiteWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True, title="Add site", default_width=460)
        self.panel = parent
        self.folder = None
        self._chooser = None

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        self.add_button = Gtk.Button(label="Add", sensitive=False, css_classes=["suggested-action"])
        self.add_button.connect("clicked", self._add)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(self.add_button)

        self.name = Gtk.Entry(placeholder_text="blog", valign=Gtk.Align.CENTER, hexpand=True)
        self.name.connect("changed", self._validate)
        self.name.connect("activate", lambda *_: self.add_button.get_sensitive() and self._add())
        name_row = Adw.ActionRow(title="Name", subtitle="Lowercase letters, numbers and dashes")
        name_row.add_suffix(self.name)

        self.folder_row = Adw.ActionRow(title="Folder")
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._choose)
        self.folder_row.add_suffix(choose)

        group = Adw.PreferencesGroup(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        group.add(name_row)
        group.add(self.folder_row)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(group)
        self.set_content(box)
        self._validate()

    def _validate(self, *_):
        name = self.name.get_text().strip()
        self.add_button.set_sensitive(sites.validate_name(name))
        if self.folder is None:
            self.folder_row.set_subtitle(_esc(f"~/Sites/{name or '<name>'} (created for you)"))

    def _choose(self, *_):
        if hasattr(Gtk, "FileDialog"):  # GTK ≥ 4.10
            dialog = Gtk.FileDialog(title="Choose the site folder")
            dialog.select_folder(self, None, self._chosen_dialog)
        else:
            self._chooser = Gtk.FileChooserNative(title="Choose the site folder", transient_for=self,
                                                  action=Gtk.FileChooserAction.SELECT_FOLDER)
            self._chooser.connect("response", self._chosen_native)
            self._chooser.show()

    def _chosen_dialog(self, dialog, result):
        try:
            self._set_folder(dialog.select_folder_finish(result))
        except GLib.Error:
            pass

    def _chosen_native(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            self._set_folder(chooser.get_file())
        self._chooser = None

    def _set_folder(self, file):
        if file and file.get_path():
            self.folder = Path(file.get_path())
            self.folder_row.set_subtitle(_esc(self.folder))

    def _add(self, *_):
        name = self.name.get_text().strip()
        folder = self.folder or SITES_DIR / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
            index = folder / "index.php"
            if self.folder is None and not index.exists():
                index.write_text(STARTER_PHP.format(name=name))
        except OSError as e:
            self.panel.toast(f"Could not create {folder}: {e.strerror}")
            return
        self.add_button.set_sensitive(False)

        def done(_out):
            self.panel.reload_sites()
            self.panel.toast(f"{name}.local is ready")
            open_uri(f"http://{name}.local/")
            self.close()

        self.panel.call_helper(["site-add", name, str(folder)], done=done,
                               failed=lambda: self.add_button.set_sensitive(True))


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="XAMPP", default_width=580, default_height=660)
        self.busy: set[str] = set()
        self.states: dict[str, State] = {}
        self.rows: dict[str, ServiceRow] = {}
        self.site_rows = []

        stack = Adw.ViewStack()
        stack.add_titled(self._services_page(), "services", "Services").set_icon_name("network-server-symbolic")
        stack.add_titled(self._sites_page(), "sites", "Sites").set_icon_name("folder-symbolic")

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcherTitle(stack=stack, title="XAMPP"))
        menu = Gio.Menu()
        tray_action = app.lookup_action("tray")
        tray_label = "Keep in tray when closed"
        if tray_action is not None and not tray_action.get_enabled():
            tray_label += " (needs the AppIndicator extension)"
        menu.append(tray_label, "app.tray")
        menu.append("Lean mode (uses less memory)", "app.lean")
        menu.append("Quit", "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))

        self.banner, self.show_banner = _make_banner(
            "MySQL root has no password. Run “sudo /opt/lampp/lampp security” to set one.")
        self.toasts = Adw.ToastOverlay(child=stack, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(self.banner)
        box.append(self.toasts)
        self.set_content(box)

        self.watcher = StatusWatcher(PATHS.watch_dirs, self.refresh, FALLBACK_SECONDS)
        # The fallback timer only runs while the window is focused; inotify covers the rest.
        self.connect("notify::is-active", self._on_active_changed)
        self.refresh()
        self.reload_sites()

    # -- pages ------------------------------------------------------------
    def _services_page(self):
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Services")
        buttons = Gtk.Box(spacing=6)
        self.start_button = Gtk.Button(label="Start", valign=Gtk.Align.CENTER, css_classes=["suggested-action"],
                                       tooltip_text="Start Apache and MySQL")
        self.start_button.connect("clicked", lambda *_: self.call_helper(["start", "all"], busy={"apache", "mysql"}))
        self.stop_button = Gtk.Button(label="Stop all", valign=Gtk.Align.CENTER)
        self.stop_button.connect(
            "clicked", lambda *_: self.call_helper(["stop", "all"], busy={s.key for s in services.SERVICES}))
        buttons.append(self.start_button)
        buttons.append(self.stop_button)
        group.set_header_suffix(buttons)
        for svc in services.SERVICES:
            row = ServiceRow(svc, services.log_path(svc.key, PATHS) is not None, self.toggle_service, self.show_log)
            self.rows[svc.key] = row
            group.add(row)
        page.add(group)

        links = Adw.PreferencesGroup(title="Shortcuts")
        for title, target, icon in (
            ("Open localhost", "http://localhost/", "web-browser-symbolic"),
            ("Open phpMyAdmin", "http://localhost/phpmyadmin/", "network-server-symbolic"),
            ("Open htdocs folder", PATHS.htdocs.as_uri(), "folder-symbolic"),
            ("Open Sites folder", SITES_DIR.as_uri(), "folder-symbolic"),
        ):
            row = Adw.ActionRow(title=title, activatable=True)
            row.add_prefix(Gtk.Image(icon_name=icon))
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.connect("activated", lambda _r, t=target: self.open_target(t))
            links.add(row)
        page.add(links)
        return page

    def _sites_page(self):
        page = Adw.PreferencesPage()
        self.sites_group = Adw.PreferencesGroup(
            title="Sites", description="Each site gets its own address, like http://blog.local, "
                                       "served from a folder in your home. Only this computer can open them.")
        add = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
                         tooltip_text="Add site", css_classes=["flat"])
        add.connect("clicked", lambda *_: AddSiteWindow(self).present())
        self.sites_group.set_header_suffix(add)
        page.add(self.sites_group)
        return page

    # -- status -----------------------------------------------------------
    def _on_active_changed(self, *_):
        if self.is_active():
            self.refresh()
            self.watcher.resume()
        else:
            self.watcher.pause()

    def refresh(self):
        previous_mysql = self.states.get("mysql")
        self.states = services.snapshot(PATHS)
        for key, row in self.rows.items():
            row.show_state(self.states[key], key in self.busy)
        self.start_button.set_sensitive(not self.busy)
        self.stop_button.set_sensitive(not self.busy)
        mysql = self.states["mysql"]
        if mysql == State.RUNNING and previous_mysql != State.RUNNING:
            self._check_mysql_password()
        elif mysql != State.RUNNING:
            self.show_banner(False)

    def _check_mysql_password(self):
        """Show the banner if MySQL root accepts a login without a password (runs once per start)."""
        argv = [str(PATHS.mysql_client), "-uroot", "-h127.0.0.1", "--protocol=TCP",
                "--connect-timeout=2", "-e", "SELECT 1"]
        try:
            proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error:
            return

        def finished(p, result):
            try:
                self.show_banner(p.wait_check_finish(result))
            except GLib.Error:
                self.show_banner(False)

        proc.wait_check_async(None, finished)

    # -- actions ----------------------------------------------------------
    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=5))

    def call_helper(self, args, busy=(), done=None, failed=None):
        """Run the root helper asynchronously; the UI never blocks."""
        busy = set(busy)
        self.busy |= busy
        self.refresh()
        try:
            proc = Gio.Subprocess.new(privileged.argv_for(*args),
                                      Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
        except GLib.Error as e:
            self.busy -= busy
            self.toast(e.message)
            if failed:
                failed()
            self.refresh()
            return

        def finished(p, result):
            try:
                _ok, out, err = p.communicate_utf8_finish(result)
            except GLib.Error as e:
                out, err = "", e.message
            code = p.get_exit_status() if p.get_if_exited() else 1
            self.busy -= busy
            try:
                out = privileged.interpret(code, out or "", err or "")
            except privileged.Cancelled:
                if failed:
                    failed()
            except privileged.HelperError as e:
                self.toast(str(e))
                if failed:
                    failed()
            else:
                for line in (err or "").splitlines():
                    if line.startswith("warning:"):
                        message = line[len("warning:"):].strip()
                        if message:
                            self.toast(message[0].upper() + message[1:])
                if done:
                    done(out)
            self.refresh()

        proc.communicate_utf8_async(None, None, finished)

    def toggle_service(self, svc, active: bool):
        self.call_helper(["start" if active else "stop", svc.key], busy={svc.key})

    def show_log(self, svc):
        path = services.log_path(svc.key, PATHS)

        def load():
            try:
                return fsutil.tail(path)
            except FileNotFoundError:
                return "No log entries yet."

        try:
            load()
        except PermissionError:
            def opened(out):
                window = LogWindow(self, svc.title, lambda: out)
                window.reload = lambda: self.call_helper(["log", svc.key], done=window.set_text)
                window.present()

            self.call_helper(["log", svc.key], done=opened)
        except OSError as e:
            self.toast(e.strerror)
        else:
            LogWindow(self, svc.title, load).present()

    def open_target(self, target: str):
        if target == SITES_DIR.as_uri():
            SITES_DIR.mkdir(exist_ok=True)
        open_uri(target)

    # -- sites ------------------------------------------------------------
    def reload_sites(self):
        for row in self.site_rows:
            self.sites_group.remove(row)
        self.site_rows = []
        try:
            mine = [s for s in sites.load(PATHS.state_file) if s.uid == os.getuid()]
        except (OSError, ValueError, KeyError):
            mine = []
        if not mine:
            self._add_site_row(Adw.ActionRow(title="No sites yet", subtitle="Click + to create one."))
        for site in mine:
            row = Adw.ActionRow(title=_esc(f"{site.name}.local"), subtitle=_esc(site.path))
            for icon, tip, action in (
                ("web-browser-symbolic", "Open in browser", lambda _b, s=site: open_uri(s.url)),
                ("folder-open-symbolic", "Open folder", lambda _b, s=site: open_uri(Path(s.path).as_uri())),
                ("user-trash-symbolic", "Remove site (keeps the folder)", lambda _b, s=site: self.remove_site(s)),
            ):
                button = Gtk.Button(icon_name=icon, tooltip_text=tip, valign=Gtk.Align.CENTER, css_classes=["flat"])
                button.connect("clicked", action)
                row.add_suffix(button)
            self._add_site_row(row)

    def _add_site_row(self, row):
        self.sites_group.add(row)
        self.site_rows.append(row)

    def remove_site(self, site):
        def done(_out):
            self.reload_sites()
            self.toast(f"Removed {site.name}.local. Its folder was kept.")

        self.call_helper(["site-remove", site.name], done=done)
