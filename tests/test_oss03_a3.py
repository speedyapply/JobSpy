"""Regression fixtures adapted from the audited source tests; no live network."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jobspy
import jobspy.linkedin as li
from jobspy.model import JobPost, ScraperInput


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


class OptionalTests(OfflineTest):
    def test_missing_and_blank_company_keep_the_job(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                jobs, _ = self.linkedin(card(company=value))
                self.assertEqual(len(jobs), 1)
                self.assertIsNone(jobs[0].company)
                self.assertIsNone(jobs[0].company_url)

    def test_unknown_location_has_unknown_remote_status(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                jobs, _ = self.linkedin(card(location=value))
                self.assertEqual(len(jobs), 1)
                self.assertIsNone(jobs[0].location)
                self.assertIsNone(jobs[0].is_remote)

    def test_remote_title_still_provides_a_signal(self):
        jobs, _ = self.linkedin(card(location=None, title="Remote Engineer"))
        self.assertEqual(len(jobs), 1)
        self.assertIs(jobs[0].is_remote, True)

    def test_invalid_title_is_rejected_without_enrichment(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                jobs, session = self.linkedin(card(title=value), fetch_description=True)
                self.assertEqual(jobs, [])
                session.get.assert_called_once()

    def test_complete_card_and_country_contract(self):
        jobs, _ = self.linkedin(card())
        self.assertEqual((jobs[0].title, jobs[0].company), ("Engineer", "Example"))
        self.assertEqual(jobs[0].location.display_location(), "Recife, Brazil")
        self.assertIs(jobs[0].is_remote, False)
        self.assertEqual(str(jobs[0].date_posted), "2026-10-01")
        jobs, _ = self.linkedin(card(location="Reykjavik, Iceland"))
        self.assertEqual(jobs[0].location.display_location(), "Reykjavik, Iceland")

    def test_public_frame_preserves_optional_nulls(self):
        session = Mock()
        session.get.return_value = response(card(company=None, location=None))
        with patch("jobspy.linkedin.create_session", return_value=session):
            frame = jobspy.scrape_jobs(site_name="linkedin", results_wanted=1)
        self.assertEqual(frame.id.tolist(), ["li-101"])
        self.assertEqual(list(frame.columns), list(JobPost.model_fields))
        self.assertTrue(frame[["company", "location", "is_remote"]].isna().all().all())
