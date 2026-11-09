"""Regression fixtures adapted from the audited source tests; no live network."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jobspy.glassdoor as gd
from jobspy.model import ScraperInput


def response(
    text="", data=None, status=200, url="https://www.linkedin.com/jobs/view/101"
):
    return SimpleNamespace(
        text=text, status_code=status, url=url, json=Mock(return_value=data)
    )


def posting(job_id=101, title="Engineer"):
    return {
        "header": {
            "locationName": "Recife",
            "locationType": "C",
            "payCurrency": "BRL",
            "payPeriod": "ANNUAL",
            "payPeriodAdjustedPay": None,
            "adOrderSponsorshipLevel": "ORGANIC",
            "ageInDays": 2,
            "employer": {"id": 701},
            "employerNameFromSearch": "Example",
            "jobTypeKeys": [],
            "remoteWorkTypes": [],
        },
        "job": {"jobTitleText": title, "listingId": job_id},
        "map": {"country": "Brazil"},
        "overview": {"website": "example.invalid"},
    }


def search(items, cursor=None, next_page=2):
    return response(
        data=[
            {
                "data": {
                    "jobListings": {
                        "jobListings": [{"jobview": i} for i in items],
                        "paginationCursors": [
                            {"pageNumber": next_page, "cursor": cursor}
                        ]
                        if cursor
                        else [],
                    }
                }
            }
        ]
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

    def glassdoor(self, pages, **kwargs):
        graph = Mock(side_effect=pages)
        scraper = gd.Glassdoor()
        with (
            patch("jobspy.glassdoor.TLSRotating"),
            patch("jobspy.glassdoor.create_session", return_value=Mock()),
            patch.object(scraper, "_search_variables", return_value={}),
            patch.object(scraper, "_graph", graph),
        ):
            jobs = scraper.scrape(
                ScraperInput(site_name="glassdoor", country_indeed="brazil", **kwargs)
            )
        self.assertIsNone(scraper.error)
        return jobs, graph


class OptionalTests(OfflineTest):
    def test_optional_objects_may_be_missing_or_null(self):
        for field in ("map", "overview"):
            for missing in (False, True):
                with self.subTest(field=field, missing=missing):
                    item = posting()
                    if missing:
                        item.pop(field)
                    else:
                        item[field] = None
                    jobs, _ = self.glassdoor([search([item])])
                    self.assertEqual(len(jobs), 1)
                    self.assertEqual(jobs[0].id, "gd-101")

    def test_nullable_header_fields_may_be_omitted(self):
        for field in (
            "locationName",
            "locationType",
            "payCurrency",
            "payPeriod",
            "payPeriodAdjustedPay",
            "employer",
            "employerNameFromSearch",
        ):
            with self.subTest(field=field):
                item = posting()
                item["header"].pop(field)
                jobs, _ = self.glassdoor([search([item])])
                self.assertEqual(len(jobs), 1)

    def test_invalid_optional_pay_does_not_discard_job(self):
        for pay in (
            {},
            {"p10": 1000},
            {"p90": 2000},
            {"p10": "bad", "p90": 2000},
            {"p10": float("inf"), "p90": 2000},
            {"p10": 2000, "p90": 1000},
            [],
            "bad",
        ):
            with self.subTest(pay=pay):
                item = posting()
                item["header"]["payPeriodAdjustedPay"] = pay
                jobs, _ = self.glassdoor([search([item])])
                self.assertEqual(len(jobs), 1)
                self.assertIsNone(jobs[0].min_amount)
                self.assertIsNone(jobs[0].max_amount)

    def test_invalid_salary_text_does_not_discard_job(self):
        for field in ("payCurrency", "payPeriod"):
            item = posting()
            item["header"][field] = {"bad": "metadata"}
            jobs, _ = self.glassdoor([search([item])])
            self.assertEqual(len(jobs), 1)

    def test_complete_percentiles_keep_upstream_salary_semantics(self):
        item = posting()
        item["header"]["payPeriodAdjustedPay"] = {"p10": 1000.25, "p90": 2000.75}
        jobs, _ = self.glassdoor([search([item])])
        self.assertEqual(
            (jobs[0].min_amount, jobs[0].max_amount, jobs[0].currency),
            (1000.25, 2000.75, "BRL"),
        )
        self.assertEqual(jobs[0].interval.value, "yearly")
        self.assertEqual(jobs[0].model_dump()["salary_source"], "direct_data")

    def test_required_header_structure_is_not_relaxed(self):
        for field in ("ageInDays", "adOrderSponsorshipLevel"):
            item = posting()
            item["header"].pop(field)
            jobs, _ = self.glassdoor([search([item, posting(102)])])
            self.assertEqual([j.id for j in jobs], ["gd-102"])
