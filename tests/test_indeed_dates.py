import unittest
from datetime import date
from unittest.mock import Mock, patch

from jobspy import scrape_jobs
from jobspy.indeed import Indeed
from jobspy.indeed.model import Job
from jobspy.model import ScraperInput, Site


def job(key: str, posted: object = 1700000000000) -> dict[str, object]:
    return {
        "key": key,
        "title": "Data Engineer",
        "sourceEmployerName": "Acme",
        "dateOnIndeed": posted,
        "description": {"html": "<p>Build pipelines</p>"},
        "employer": None,
        "location": {"countryCode": "US", "admin1Code": "NY", "city": "New York"},
        "recruit": {"viewJobUrl": None},
        "attributes": [],
        "compensation": {"baseSalary": None, "currencyCode": None, "estimated": None},
    }


class IndeedDateTests(unittest.TestCase):
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

    def scrape(self, jobs: list[dict[str, object]]) -> tuple[Indeed, list]:
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {
                "jobSearch": {
                    "pageInfo": {"nextCursor": None},
                    "results": [{"job": item} for item in jobs],
                }
            }
        }
        session = Mock()
        session.post.return_value = response
        scraper = Indeed()
        with patch("jobspy.indeed.create_session", return_value=session):
            results = scraper.scrape(ScraperInput(site_name=Site.INDEED))
        session.post.assert_called_once()
        return scraper, results

    def test_missing_and_null_dates_keep_jobs_and_other_fields(self) -> None:
        missing = job("missing")
        del missing["dateOnIndeed"]
        scraper, results = self.scrape([missing, job("null", None)])
        self.assertIsNone(scraper.error)
        self.assertEqual([item.id for item in results], ["in-missing", "in-null"])
        for item in results:
            self.assertIsNone(item.date_posted)
            self.assertEqual(item.title, "Data Engineer")
            self.assertEqual(item.company, "Acme")
            self.assertEqual(
                item.job_url, f"https://www.indeed.com/viewjob?jk={item.id[3:]}"
            )

    def test_present_date_and_utc_boundary(self) -> None:
        _, results = self.scrape(
            [job("before", 1700006399999), job("after", 1700006400000)]
        )
        self.assertEqual(
            [item.date_posted for item in results],
            [date(2023, 11, 14), date(2023, 11, 15)],
        )

    def test_zero_keeps_job_and_existing_utc_date_semantics(self) -> None:
        raw = job("zero", 0)
        self.assertEqual(Job.model_validate(raw).dateOnIndeed, 0)
        _, results = self.scrape([raw])
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].date_posted)

    def test_invalid_date_skips_only_that_job(self) -> None:
        scraper, results = self.scrape([job("bad", "yesterday"), job("valid")])
        self.assertIsNone(scraper.error)
        self.assertEqual([item.id for item in results], ["in-valid"])
        self.assertEqual(results[0].date_posted, date(2023, 11, 14))

    def test_other_required_field_stays_required(self) -> None:
        bad = job("bad")
        del bad["title"]
        _, results = self.scrape([bad, job("valid")])
        self.assertEqual([item.id for item in results], ["in-valid"])

    def test_public_dataframe_retains_undated_result(self) -> None:
        missing = job("missing")
        del missing["dateOnIndeed"]
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {
                "jobSearch": {
                    "pageInfo": {"nextCursor": None},
                    "results": [{"job": missing}],
                }
            }
        }
        session = Mock()
        session.post.return_value = response
        with patch("jobspy.indeed.create_session", return_value=session):
            rows = scrape_jobs(site_name="indeed", results_wanted=1, verbose=0)
        session.post.assert_called_once()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["title"], "Data Engineer")
        self.assertIsNone(rows.iloc[0]["date_posted"])


if __name__ == "__main__":
    unittest.main()
