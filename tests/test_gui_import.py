import importlib.util
import os
import py_compile
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src/xampp_panel"
HAS_GTK4 = False
if importlib.util.find_spec("gi"):
    import gi
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        HAS_GTK4 = True
    except ValueError:
        pass


class GuiCompileTest(unittest.TestCase):
    def test_gui_modules_compile(self):
        for name in ("watch", "window", "app", "main", "tray"):
            path = SRC / f"{name}.py"
            if path.exists():
                py_compile.compile(str(path), doraise=True)

    def test_launchers_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("xampp-panel", "xampp-helper"):
                path = SRC.parent.parent / "bin" / name
                self.assertTrue(path.read_text().startswith("#!/usr/bin/python3 -I\n"), name)
                py_compile.compile(str(path), doraise=True, cfile=os.path.join(tmp, name + ".pyc"))

    @unittest.skipUnless(HAS_GTK4, "GTK 4 / libadwaita not available")
    def test_window_imports(self):
        import xampp_panel.window  # noqa: F401
