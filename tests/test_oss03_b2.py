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


class IdentityTests(OfflineTest):
    def test_invalid_source_id_is_rejected(self):
        for value in (True, False, None, 0, -1, 1.5, "1.0", "bad", {}, "١"):
            with self.subTest(value=value):
                jobs, _ = self.glassdoor([search([posting(value), posting(102)])])
                self.assertEqual([j.id for j in jobs], ["gd-102"])

    def test_numeric_representations_deduplicate(self):
        jobs, _ = self.glassdoor(
            [search([posting(101), posting("101"), posting(" 101 ")])]
        )
        self.assertEqual([j.id for j in jobs], ["gd-101"])

    def test_failed_representation_does_not_consume_identity(self):
        bad = posting()
        bad["job"]["jobTitleText"] = None
        jobs, _ = self.glassdoor([search([bad, posting(), posting()])])
        self.assertEqual([j.id for j in jobs], ["gd-101"])

    def test_blank_titles_do_not_consume_identity(self):
        for title in ("", "   "):
            with self.subTest(title=title):
                jobs, _ = self.glassdoor([search([posting(title=title), posting()])])
                self.assertEqual(
                    [(j.id, j.title) for j in jobs], [("gd-101", "Engineer")]
                )

    def test_cursor_progress_uses_encountered_ids(self):
        bad = posting()
        bad["job"]["jobTitleText"] = None
        jobs, graph = self.glassdoor([search([bad], "next"), search([posting()])])
        self.assertEqual([j.id for j in jobs], ["gd-101"])
        self.assertEqual(
            [c.args[2]["pageNumber"] for c in graph.call_args_list], [1, 2]
        )
        self.assertEqual(
            [c.args[2]["pageCursor"] for c in graph.call_args_list], [None, "next"]
        )

    def test_repeated_invalid_page_stops(self):
        bad = posting()
        bad["job"]["jobTitleText"] = None
        jobs, graph = self.glassdoor([search([bad], "two"), search([bad], "three", 3)])
        self.assertEqual(jobs, [])
        self.assertEqual(graph.call_count, 2)

    def test_offset_and_limit_are_preserved(self):
        jobs, graph = self.glassdoor(
            [search([posting(101), posting(101), posting(102), posting(103)])],
            offset=1,
            results_wanted=1,
        )
        self.assertEqual([j.id for j in jobs], ["gd-102"])
        graph.assert_called_once()
