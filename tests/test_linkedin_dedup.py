"""Synthetic cards exercise deduplication without contacting any job board."""

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jobspy import scrape_jobs
from jobspy.linkedin import LinkedIn
from jobspy.linkedin.constant import jobs_per_page, max_results
from jobspy.model import JobPost, ScraperInput


def card(
    job_id: int = 101, *, valid: bool = True, namespace: str = "jobPosting"
) -> str:
    title = '<h3 class="base-search-card__title">Engineer</h3>' if valid else ""
    return (
        f'<div class="base-search-card" data-entity-urn="urn:li:{namespace}:{job_id}">'
        f"{title}"
        '<h4 class="base-search-card__subtitle">Example</h4>'
        '<span class="job-search-card__location">New York, NY</span>'
        '<time datetime="2026-10-01"></time></div>'
    )


def response(html: str) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=200, text=html, url="https://www.linkedin.com/jobs/view/101"
    )


class LinkedInDedupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network_mocks = []
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "socket.create_connection",
            "socket.getaddrinfo",
            "requests.sessions.Session.request",
            "curl_cffi.requests.Session.request",
        ):
            guard = patch(target, side_effect=AssertionError("unexpected network"))
            self.network_mocks.append(guard.start())
            self.addCleanup(guard.stop)
        guard = patch("jobspy.linkedin.time.sleep")
        self.sleep = guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self) -> None:
        for network_mock in self.network_mocks:
            network_mock.assert_not_called()

    def run_scrape(self, *pages: str, **kwargs: object) -> tuple[list[JobPost], Mock]:
        session = Mock()
        session.get.side_effect = [response(page) for page in pages]
        scraper = LinkedIn()
        with patch("jobspy.linkedin.create_session", return_value=session):
            jobs = scraper.scrape(ScraperInput(site_name="linkedin", **kwargs))
        self.assertIsNone(scraper.error)
        return jobs, session

    def test_complete_card_contract(self) -> None:
        jobs, session = self.run_scrape(card())
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(
            (job.id, job.title, job.company), ("li-101", "Engineer", "Example")
        )
        self.assertEqual(job.job_url, "https://www.linkedin.com/jobs/view/101")
        self.assertEqual(job.date_posted, date(2026, 10, 1))
        self.assertIsNotNone(job.location)
        self.assertEqual(job.location.display_location(), "New York, NY, USA")
        self.assertIs(job.is_remote, False)
        self.assertIsNone(job.description)
        session.get.assert_called_once()

    def test_invalid_card_does_not_hide_valid_duplicate(self) -> None:
        for first in ("job", "jobPosting"):
            for second in ("job", "jobPosting"):
                with self.subTest(first=first, second=second):
                    jobs, session = self.run_scrape(
                        card(valid=False, namespace=first) + card(namespace=second)
                    )
                    self.assertEqual([job.id for job in jobs], ["li-101"])
                    session.get.assert_called_once()

    def test_invalid_card_on_previous_page_can_be_recovered(self) -> None:
        fillers = [card(i) for i in range(102, 102 + jobs_per_page - 1)]
        jobs, session = self.run_scrape(
            card(valid=False) + "".join(fillers),
            card(),
            offset=13,
            results_wanted=jobs_per_page + 1,
        )
        self.assertEqual(
            [job.id for job in jobs],
            [*(f"li-{i}" for i in range(102, 102 + jobs_per_page - 1)), "li-101"],
        )
        self.assertEqual(
            [call.kwargs["params"]["start"] for call in session.get.call_args_list],
            [13, 13 + jobs_per_page],
        )
        self.sleep.assert_called_once()

    def test_valid_duplicate_is_enriched_only_once(self) -> None:
        details = '<div class="show-more-less-html__markup">Synthetic detail.</div>'
        jobs, session = self.run_scrape(
            card() + card(namespace="job") + card(102),
            details,
            details,
            fetch_description=True,
            results_wanted=2,
        )
        self.assertEqual([job.id for job in jobs], ["li-101", "li-102"])
        self.assertTrue(all("Synthetic detail." in job.description for job in jobs))
        self.assertEqual(session.get.call_count, 3)

    def test_seen_only_page_still_ends_pagination(self) -> None:
        page = card() * jobs_per_page
        jobs, session = self.run_scrape(page, page, results_wanted=2)
        self.assertEqual([job.id for job in jobs], ["li-101"])
        self.assertEqual(session.get.call_count, 2)
        self.sleep.assert_called_once()

    def test_all_invalid_page_remains_bounded_by_existing_limit(self) -> None:
        jobs, session = self.run_scrape(
            card(valid=False) * jobs_per_page,
            offset=max_results - jobs_per_page,
        )
        self.assertEqual(jobs, [])
        session.get.assert_called_once()
        self.sleep.assert_not_called()

    def test_result_limit_and_request_filters_are_preserved(self) -> None:
        jobs, session = self.run_scrape(
            card() + card() + card(102),
            results_wanted=1,
            offset=7,
            search_term="engineer",
            location="New York",
            distance=50,
            easy_apply=True,
            linkedin_company_ids=[123],
            hours_old=24,
        )
        self.assertEqual([job.id for job in jobs], ["li-101"])
        self.assertEqual(
            session.get.call_args.kwargs["params"],
            {
                "keywords": "engineer",
                "location": "New York",
                "distance": 50,
                "f_AL": "true",
                "f_C": "123",
                "f_TPR": "r86400",
                "start": 7,
            },
        )
        session.get.assert_called_once()

    def test_public_frame_recovers_the_valid_card(self) -> None:
        session = Mock()
        session.get.return_value = response(card(valid=False) + card() + card())
        with patch("jobspy.linkedin.create_session", return_value=session):
            frame = scrape_jobs(site_name="linkedin", results_wanted=1, verbose=0)
        self.assertEqual(frame.id.tolist(), ["li-101"])
        self.assertEqual(list(frame.columns), list(JobPost.model_fields))
        self.assertEqual(frame.attrs, {"errors": {}, "warnings": {}})
        self.assertIsNone(frame.iloc[0].salary_source)
        session.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
