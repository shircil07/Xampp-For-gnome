import configparser
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from xampp_panel.paths import DEFAULT

DATA = Path(__file__).resolve().parent.parent / "data"


class DataFilesTest(unittest.TestCase):
    def test_desktop_entry(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(DATA / "io.github.shiron.XamppPanel.desktop")
        entry = parser["Desktop Entry"]
        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(entry["Exec"], str(DEFAULT.launcher))
        self.assertEqual(entry["Icon"], "io.github.shiron.XamppPanel")
        self.assertEqual(entry["Terminal"], "false")

    def test_polkit_policy_pins_helper_and_requires_admin(self):
        root = ET.parse(DATA / "io.github.shiron.xampppanel.policy").getroot()
        action = root.find("action")
        self.assertEqual(action.get("id"), "io.github.shiron.xampppanel.helper")
        defaults = action.find("defaults")
        self.assertEqual(defaults.findtext("allow_any"), "no")
        self.assertEqual(defaults.findtext("allow_inactive"), "no")
        self.assertEqual(defaults.findtext("allow_active"), "auth_admin_keep")
        annotations = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotations["org.freedesktop.policykit.exec.path"], str(DEFAULT.helper))

    def test_icons_are_valid_svg(self):
        for name in ("io.github.shiron.XamppPanel", "xampp-panel-running", "xampp-panel-stopped"):
            root = ET.parse(DATA / "icons" / f"{name}.svg").getroot()
            self.assertTrue(root.tag.endswith("svg"), name)
