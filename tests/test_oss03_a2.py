"""Regression fixtures adapted from the audited source tests; no live network."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jobspy.linkedin as li
from jobspy.model import ScraperInput


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


class IdentityTests(OfflineTest):
    def test_proven_namespaces_and_zero_remain_supported(self):
        for namespace in ("job", "jobPosting"):
            for number in ("0", "1", "123"):
                with self.subTest(namespace=namespace, number=number):
                    jobs, session = self.linkedin(card(f"urn:li:{namespace}:{number}"))
                    self.assertEqual([job.id for job in jobs], ["li-" + number])
                    session.get.assert_called_once()

    def test_other_entities_and_malformed_ids_are_not_jobs(self):
        for urn in (
            "urn:li:company:1",
            "urn:li:member:1",
            "urn:li:organization:1",
            "urn:li:jobOther:1",
            "urn:other:job:1",
            "urn:li:job:invented",
            "urn:li:job:1:extra",
            "urn:li:job:-1",
            "urn:li:job:١",
            "urn:li:job:1 ",
            "",
            "1",
        ):
            with self.subTest(urn=urn):
                jobs, session = self.linkedin(card(urn), fetch_description=True)
                self.assertEqual(jobs, [])
                session.get.assert_called_once()

    def test_non_job_card_does_not_steal_a_job_identity(self):
        jobs, _ = self.linkedin(
            card("urn:li:company:1", title="Not a job")
            + card("urn:li:job:1", title="Valid")
        )
        self.assertEqual([(job.id, job.title) for job in jobs], [("li-1", "Valid")])

    def test_valid_duplicates_and_request_limits_are_unchanged(self):
        jobs, session = self.linkedin(
            card() + card() + card("urn:li:job:102"), results_wanted=1, offset=7
        )
        self.assertEqual([job.id for job in jobs], ["li-101"])
        self.assertEqual(session.get.call_args.kwargs["params"]["start"], 7)
        session.get.assert_called_once()
