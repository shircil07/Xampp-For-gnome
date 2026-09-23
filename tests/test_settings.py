import tempfile
import unittest
from pathlib import Path

from xampp_panel import settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "cfg/xampp-panel/settings.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_when_missing_or_corrupt(self):
        self.assertEqual(settings.load(self.file), {"tray": False})
        self.file.parent.mkdir(parents=True)
        self.file.write_text("{not json")
        self.assertEqual(settings.load(self.file), {"tray": False})
        self.file.write_text("[1, 2]")
        self.assertEqual(settings.load(self.file), {"tray": False})

    def test_round_trip_is_private(self):
        settings.save({"tray": True}, self.file)
        self.assertEqual(settings.load(self.file), {"tray": True})
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)

    def test_unknown_keys_are_dropped(self):
        settings.save({"tray": True, "evil": 1}, self.file)
        self.assertEqual(settings.load(self.file), {"tray": True})

    def test_config_path_honours_xdg(self):
        self.assertEqual(settings.config_path({"XDG_CONFIG_HOME": "/x"}), Path("/x/xampp-panel/settings.json"))
