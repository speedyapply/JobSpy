import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jobspy import scrape_jobs
from jobspy.linkedin import LinkedIn
from jobspy.model import Compensation, CompensationInterval, Country, ScraperInput


class LinkedInSalaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network_guards = [
            patch("socket.socket.connect", side_effect=AssertionError("network")),
            patch(
                "requests.sessions.Session.request",
                side_effect=AssertionError("network"),
            ),
            patch(
                "curl_cffi.requests.Session.request",
                side_effect=AssertionError("network"),
            ),
        ]
        self.network_mocks = []
        for guard in self.network_guards:
            self.network_mocks.append(guard.start())
            self.addCleanup(guard.stop)

    def tearDown(self) -> None:
        for network_mock in self.network_mocks:
            network_mock.assert_not_called()

    def test_guessed_amounts_keep_cents_and_k_on_the_right_side(self) -> None:
        hourly = CompensationInterval.HOURLY
        monthly = CompensationInterval.MONTHLY
        yearly = CompensationInterval.YEARLY
        cases = [
            ("$25.50 - $30.75 per hour", hourly, 25.5, 30.75),
            ("$25.25 - $25.75", hourly, 25.25, 25.75),
            ("$4,500.50 - $5,200.75 a month", monthly, 4500.5, 5200.75),
            ("$120,000.50 - $150,000.75", yearly, 120000.5, 150000.75),
            ("$120.5k - $150.5k", yearly, 120500, 150500),
            ("$1.5k - $2.5k", monthly, 1500, 2500),
            ("$1.005k - $1.015k", monthly, 1005, 1015),
            ("$85.5-95.5k", yearly, 85500, 95500),
            ("$90,000 - $120k", yearly, 90000, 120000),
            ("$90k - $120,000", yearly, 90000, 120000),
            ("$1,000 - $1.5k", monthly, 1000, 1500),
            ("$80-100k", yearly, 80000, 100000),
            ("$80k - 100", yearly, 80000, 100000),
            ("$80K – $100K", yearly, 80000, 100000),
            ("$100,000 - $150,000", yearly, 100000, 150000),
            ("$25 - $35", hourly, 25, 35),
            ("$1 - $2", hourly, 1, 2),
            ("$1k - $2k", monthly, 1000, 2000),
        ]
        for text, interval, low, high in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    LinkedIn._guess_salary(text),
                    Compensation(
                        interval=interval,
                        min_amount=low,
                        max_amount=high,
                        currency="USD",
                    ),
                )

    def test_raw_lower_bound_below_one_stays_rejected(self) -> None:
        for text in (
            "$0.55 - $0.70 per mile",
            "$0.5k - $1k",
            "$0.999 - $2",
            "$0.999k - $1k",
        ):
            with self.subTest(text=text):
                self.assertEqual(LinkedIn._guess_salary(text), Compensation())

    def test_invalid_and_out_of_limit_ranges_are_rejected(self) -> None:
        for text in (
            "$150k - $120k",
            "$500k - $900k",
            "$300 - $400",
            "$25.50 - $25.50",
            "$650k - $700.5k",
            "competitive pay",
            None,
        ):
            with self.subTest(text=text):
                self.assertEqual(LinkedIn._guess_salary(text), Compensation())

    def details(self, *, structured: bool, country: Country) -> tuple[dict, Mock]:
        salary = (
            '<div class="compensation__salary">$117,000.00/yr - $234,000.00/yr</div>'
            if structured
            else ""
        )
        html = (
            f"{salary}<div class='show-more-less-html__markup'>"
            "<p>Pay: $25.50 - $30.75 per hour</p></div>"
        )
        scraper = LinkedIn()
        scraper.scraper_input = ScraperInput(
            site_name="linkedin", fetch_description=True, country_indeed=country
        )
        scraper.session = Mock()
        scraper.session.get.return_value = SimpleNamespace(
            status_code=200,
            url="https://www.linkedin.com/jobs/view/1",
            text=html,
        )
        result = scraper._fetch_details("1")
        return result, scraper.session.get

    def test_description_fallback_keeps_cents(self) -> None:
        result, get = self.details(structured=False, country=Country.USA)
        get.assert_called_once()
        self.assertEqual(result["interval"], CompensationInterval.HOURLY)
        self.assertEqual((result["min_amount"], result["max_amount"]), (25.5, 30.75))
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["salary_source"], "description")

    def test_structured_pay_takes_precedence(self) -> None:
        result, get = self.details(structured=True, country=Country.USA)
        get.assert_called_once()
        self.assertEqual(result["interval"], CompensationInterval.YEARLY)
        self.assertEqual((result["min_amount"], result["max_amount"]), (117000, 234000))
        self.assertIsNone(result["salary_source"])

    def test_description_guess_remains_us_only(self) -> None:
        result, get = self.details(structured=False, country=Country.UK)
        get.assert_called_once()
        self.assertIsNone(result["min_amount"])
        self.assertIsNone(result["salary_source"])

    def test_public_dataframe_keeps_description_cents(self) -> None:
        card = (
            '<div class="base-search-card" data-entity-urn="urn:li:job:1">'
            '<h3 class="base-search-card__title">Engineer</h3>'
            '<h4 class="base-search-card__subtitle">Acme</h4>'
            '<span class="job-search-card__location">New York, NY</span></div>'
        )
        details = (
            '<div class="show-more-less-html__markup">'
            "<p>Pay: $25.50 - $30.75 per hour</p></div>"
        )
        session = Mock()
        session.get.side_effect = [
            SimpleNamespace(status_code=200, text=card),
            SimpleNamespace(
                status_code=200,
                url="https://www.linkedin.com/jobs/view/1",
                text=details,
            ),
        ]
        with patch("jobspy.linkedin.create_session", return_value=session):
            rows = scrape_jobs(
                site_name="linkedin",
                fetch_description=True,
                results_wanted=1,
                verbose=0,
            )
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows.iloc[0]["min_amount"], rows.iloc[0]["max_amount"]), (25.5, 30.75)
        )
        self.assertEqual(rows.iloc[0]["salary_source"], "description")


if __name__ == "__main__":
    unittest.main()
