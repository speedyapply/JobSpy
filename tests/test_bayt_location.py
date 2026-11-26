import unittest

from jobspy.bayt import Bayt
from jobspy.bayt.constant import all_countries


class BaytLocationTests(unittest.TestCase):
    def test_location_slugs(self):
        for location, expected in [
            ("مسقط، سلطنة عمان", ("oman", "muscat")),
            ("دبي, الامارات", ("uae", "dubai")),
            ("الرياض، السعودية", ("saudi-arabia", "riyadh")),
            ("عمّان، الأردن", ("jordan", "amman")),
            ("قطر", ("qatar", None)),
            ("Dubai, UAE", ("uae", "dubai")),
            (None, (all_countries, None)),
        ]:
            with self.subTest(location=location):
                self.assertEqual(Bayt._location(location), expected)
