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


class DetailTests(OfflineTest):
    def fetch(self, payloads, ids):
        scraper = gd.Glassdoor()
        scraper.scraper_input = ScraperInput()
        graph = Mock(side_effect=payloads)
        with patch.object(scraper, "_graph", graph):
            details = scraper._fetch_details(ids)
        return details, graph

    def test_invalid_alias_does_not_hide_valid_neighbors(self):
        for bad in ({}, {"job": None}, {"job": {"description": []}}, "bad"):
            with self.subTest(bad=bad):
                aliases = {
                    "j101": {"job": {"description": "<p>One</p>"}},
                    "j102": bad,
                    "j103": {"job": {"description": "<p>Three</p>"}},
                }
                result, _ = self.fetch(
                    [response(data=[{"data": aliases}])], ["gd-101", "gd-102", "gd-103"]
                )
                self.assertEqual(set(result), {"gd-101", "gd-103"})
                self.assertIn("Three", result["gd-103"]["description"])

    def test_alias_must_belong_to_requested_id(self):
        aliases = {
            "j999": {"job": {"description": "Wrong"}},
            "j101": {"job": {"description": "Right"}},
        }
        result, _ = self.fetch([response(data=[{"data": aliases}])], ["gd-101"])
        self.assertEqual(set(result), {"gd-101"})

    def test_null_and_missing_descriptions_remain_optional(self):
        aliases = {
            "j101": None,
            "j102": {"job": {}},
            "j103": {"job": {"description": None}},
        }
        result, _ = self.fetch(
            [response(data=[{"data": aliases}])], ["gd-101", "gd-102", "gd-103"]
        )
        self.assertEqual(set(result), {"gd-102", "gd-103"})
        self.assertTrue(all(v["description"] is None for v in result.values()))

    def test_later_batches_survive_bad_aliases(self):
        ids = [f"gd-{i}" for i in range(101, 127)]
        first = {f"j{i}": {"job": {"description": "Valid"}} for i in range(101, 126)}
        first["j102"] = {"job": None}
        result, graph = self.fetch(
            [
                response(data=[{"data": first}]),
                response(data=[{"data": {"j126": {"job": {"description": "Last"}}}}]),
            ],
            ids,
        )
        self.assertEqual(len(result), 25)
        self.assertIn("gd-126", result)
        self.assertEqual(graph.call_count, 2)

    def test_failed_batch_retains_previous_and_stops(self):
        ids = [f"gd-{i}" for i in range(101, 152)]
        first = {f"j{i}": {"job": {"description": "Valid"}} for i in range(101, 126)}
        result, graph = self.fetch(
            [response(data=[{"data": first}]), response(status=429)], ids
        )
        self.assertEqual(len(result), 25)
        self.assertEqual(graph.call_count, 2)

    def test_enrichment_failure_does_not_remove_search_jobs(self):
        payload = response(
            data=[
                {
                    "data": {
                        "j101": {"job": None},
                        "j102": {"job": {"description": "Valid"}},
                    }
                }
            ]
        )
        jobs, _ = self.glassdoor(
            [search([posting(), posting(102)]), payload], fetch_description=True
        )
        self.assertEqual([j.id for j in jobs], ["gd-101", "gd-102"])
        self.assertIsNone(jobs[0].description)
        self.assertIn("Valid", jobs[1].description)
