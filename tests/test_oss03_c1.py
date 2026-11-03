"""Regression fixtures adapted from the audited source tests; no live network."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jobspy.linkedin as li
from jobspy.model import Compensation, Country, ScraperInput


def card(
    urn="urn:li:jobPosting:101",
    title="Engineer",
    company="Example",
    location="Recife, Brazil",
):
    heading = (
        f'<h3 class="base-search-card__title">{title}</h3>' if title is not None else ""
    )
    employer = (
        f'<h4 class="base-search-card__subtitle">{company}</h4>'
        if company is not None
        else ""
    )
    place = (
        f'<span class="job-search-card__location">{location}</span>'
        if location is not None
        else ""
    )
    return f'<div class="base-search-card" data-entity-urn="{urn}">{heading}{employer}{place}<time datetime="2026-10-01"></time></div>'


def response(
    text="", data=None, status=200, url="https://www.linkedin.com/jobs/view/101"
):
    return SimpleNamespace(
        text=text, status_code=status, url=url, json=Mock(return_value=data)
    )


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.network = []
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "socket.create_connection",
            "socket.getaddrinfo",
            "requests.sessions.Session.request",
            "curl_cffi.requests.Session.request",
        ):
            guard = patch(target, side_effect=AssertionError("unexpected network"))
            self.network.append(guard.start())
            self.addCleanup(guard.stop)
        guard = patch("jobspy.linkedin.time.sleep")
        self.sleep = guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self):
        for mock in self.network:
            mock.assert_not_called()

    def linkedin(self, html, **kwargs):
        session = Mock()
        session.get.return_value = response(html)
        scraper = li.LinkedIn()
        with patch("jobspy.linkedin.create_session", return_value=session):
            jobs = scraper.scrape(ScraperInput(site_name="linkedin", **kwargs))
        self.assertIsNone(scraper.error)
        return jobs, session


class SalaryTests(OfflineTest):
    def test_known_currencies_periods_and_zero_are_preserved(self):
        symbols = {
            "$": "USD",
            "CA$": "CAD",
            "£": "GBP",
            "€": "EUR",
            "₹": "INR",
            "USD": "USD",
            "CAD": "CAD",
            "GBP": "GBP",
            "EUR": "EUR",
            "INR": "INR",
            "BRL": "BRL",
        }
        for symbol, currency in symbols.items():
            for period, interval in (
                ("yr", "yearly"),
                ("mo", "monthly"),
                ("hr", "hourly"),
            ):
                with self.subTest(symbol=symbol, period=period):
                    pay = li.LinkedIn._parse_salary(
                        f"{symbol}1,000.25/{period} - {symbol}2,000.75/{period}"
                    )
                    self.assertEqual(
                        (
                            pay.min_amount,
                            pay.max_amount,
                            pay.currency,
                            pay.interval.value,
                        ),
                        (1000.25, 2000.75, currency, interval),
                    )
        self.assertEqual(li.LinkedIn._parse_salary("$0.00/yr - $0.00/yr").min_amount, 0)

    def test_inconsistent_or_malformed_ranges_are_unknown(self):
        for text in (
            "$117,000.00/yr - €234,000.00/yr",
            "$117,000.00/yr - $234,000.00/hr",
            "$234,000.00/yr - $117,000.00/yr",
            "$1,2,3.00/yr - $2,3,4.00/yr",
            "$12,34.00/yr - $2000.00/yr",
            "$1,,000.00/yr - $2000.00/yr",
            "$,,.00/yr - $234,000.00/yr",
            "R$1000.00/mo - R$2000.00/mo",
            "UNKNOWN$1000.00/yr - UNKNOWN$2000.00/yr",
            "$1000.00/week - $2000.00/week",
            "$1000.00/mo - $2000.00/month",
            "$-1000.00/yr - $2000.00/yr",
            "$1.000,00/yr - $2.000,00/yr",
            "$1000/yr - $2000/yr",
            "negotiable",
            "",
        ):
            with self.subTest(text=text):
                self.assertEqual(li.LinkedIn._parse_salary(text), Compensation())

    def test_nonfinite_amounts_are_unknown(self):
        huge = "9" * 400 + ".00"
        self.assertEqual(
            li.LinkedIn._parse_salary(f"${huge}/yr - ${huge}/yr"), Compensation()
        )

    def details(self, pay, country=Country.USA):
        html = '<div class="show-more-less-html__markup">Keep description. Pay $100,000 - $200,000.</div>'
        if pay is not None:
            html += f'<div class="compensation__salary">{pay}</div>'
        scraper = li.LinkedIn()
        scraper.scraper_input = ScraperInput(country_indeed=country)
        scraper.session = Mock()
        scraper.session.get.return_value = response(html)
        result = scraper._fetch_details("101")
        scraper.session.get.assert_called_once()
        return result

    def test_invalid_structured_pay_is_not_revived_by_description(self):
        for text in (
            "invalid",
            "$100000.00/yr - $200000.00/hr",
            "$1000.00/yr - €2000.00/yr",
        ):
            with self.subTest(text=text):
                result = self.details(text)
                self.assertIn("Keep description.", result["description"])
                for field in (
                    "min_amount",
                    "max_amount",
                    "interval",
                    "currency",
                    "salary_source",
                ):
                    self.assertIsNone(result[field])

    def test_missing_structured_pay_keeps_us_fallback_only(self):
        result = self.details(None)
        self.assertEqual(
            (result["min_amount"], result["max_amount"], result["salary_source"]),
            (100000, 200000, "description"),
        )
        self.assertIsNone(self.details(None, Country.BRAZIL)["min_amount"])

    def test_salary_runtime_errors_are_not_hidden(self):
        with patch.object(
            li.LinkedIn, "_parse_salary", side_effect=RuntimeError("programming error")
        ):
            with self.assertRaises(RuntimeError):
                self.details("valid")
