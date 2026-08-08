"""Regression tests for defensive parsing in jobspy.util.

Covers the currency_parser / convert_to_annual crashes that previously took down
a whole scrape when a job board returned a non-numeric salary or a partial
compensation dict.
"""
from jobspy.util import currency_parser, convert_to_annual


class TestCurrencyParser:
    def test_non_numeric_returns_none(self):
        # "Negotiable" / "Competitive" used to raise ValueError from float("")
        assert currency_parser("Negotiable") is None
        assert currency_parser("Competitive") is None
        assert currency_parser("") is None
        assert currency_parser("   ") is None

    def test_normal_values_unchanged(self):
        assert currency_parser("$120,000") == 120000.0
        assert currency_parser("$50") == 50.0
        assert currency_parser("80000") == 80000.0


class TestConvertToAnnual:
    def test_missing_interval_is_noop(self):
        job = {"min_amount": 10, "max_amount": 50}  # no "interval"
        convert_to_annual(job)  # previously KeyError
        assert job["min_amount"] == 10 and job["max_amount"] == 50

    def test_none_amount_with_interval(self):
        job = {"interval": "hourly", "min_amount": None, "max_amount": 50}
        convert_to_annual(job)  # previously `None *= 2080` TypeError
        assert job["min_amount"] is None
        assert job["max_amount"] == 50 * 2080
        assert job["interval"] == "yearly"

    def test_hourly_conversion_unchanged(self):
        job = {"interval": "hourly", "min_amount": 10, "max_amount": 50}
        convert_to_annual(job)
        assert job["min_amount"] == 10 * 2080
        assert job["max_amount"] == 50 * 2080
        assert job["interval"] == "yearly"
