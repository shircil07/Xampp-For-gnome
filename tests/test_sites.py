import tempfile
import unittest
from pathlib import Path

from xampp_panel import sites
from xampp_panel.sites import Site


class ValidateNameTest(unittest.TestCase):
    def test_accepts_simple_names(self):
        for name in ("blog", "my-shop", "a", "site2"):
            self.assertTrue(sites.validate_name(name), name)

    def test_rejects_bad_names(self):
        for name in ("", "Blog", "my_shop", "-x", "x-", "a.b", "a b", "x" * 64, "../etc", "a\n"):
            self.assertFalse(sites.validate_name(name), repr(name))


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = Path(self._tmp.name) / "sites.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_means_no_sites(self):
        self.assertEqual(sites.load(self.file), [])

    def test_round_trip_and_world_readable(self):
        data = [Site("blog", "/home/u/Sites/blog", 1000)]
        sites.save(self.file, data)
        self.assertEqual(sites.load(self.file), data)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)

    def test_url(self):
        self.assertEqual(Site("blog", "/x", 1).url, "http://blog.local/")
