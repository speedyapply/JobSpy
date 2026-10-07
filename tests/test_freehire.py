from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from jobspy import scrape_jobs
from jobspy.freehire import Freehire
from jobspy.model import Country, JobType, ScraperInput, Site


class FreehireTests(TestCase):
    def make_response(self, payload):
        response = Mock(status_code=200)
        response.json.return_value = payload
        return response

    def test_maps_search_filters_and_job_fields(self):
        session = Mock()
        session.get.return_value = self.make_response(
            {
                "data": [
                    {
                        "public_slug": "python-engineer-acme",
                        "title": "Python Engineer",
                        "company": "Acme",
                        "url": "https://jobs.acme.com/python-engineer",
                        "location": "Remote, US",
                        "description": "Build software",
                        "work_mode": "remote",
                        "skills": ["python"],
                        "posted_at": "2025-02-03T00:00:00Z",
                        "enrichment": {
                            "employment_type": "full_time",
                            "salary_min": 100000,
                            "salary_max": 130000,
                            "salary_currency": "USD",
                            "salary_period": "year",
                        },
                    }
                ],
                "meta": {"total": 1, "limit": 1, "offset": 0},
            }
        )

        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = (
                Freehire()
                .scrape(
                    ScraperInput(
                        site_type=[Site.FREEHIRE],
                        search_term="python",
                        country=Country.USA,
                        is_remote=True,
                        job_type=JobType.FULL_TIME,
                        results_wanted=1,
                    )
                )
                .jobs
            )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_url, "https://jobs.acme.com/python-engineer")
        self.assertEqual(jobs[0].date_posted, date(2025, 2, 3))
        self.assertEqual(jobs[0].job_type, [JobType.FULL_TIME])
        self.assertEqual(jobs[0].compensation.currency, "USD")
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["is_tech"], "tech")
        self.assertEqual(params["q"], "python")
        self.assertEqual(params["work_mode"], "remote")
        self.assertEqual(params["employment_type"], "full_time")
        self.assertEqual(params["countries"], "us")

    def test_uses_full_description_endpoint_when_requested(self):
        session = Mock()
        session.get.return_value = self.make_response(
            {"data": [], "meta": {"total": 0, "limit": 1, "offset": 0}}
        )

        with patch("jobspy.freehire.create_session", return_value=session):
            Freehire().scrape(
                ScraperInput(
                    site_type=[Site.FREEHIRE],
                    country=Country.USA,
                    fetch_description=True,
                    results_wanted=1,
                )
            )

        self.assertEqual(session.get.call_args.args[0], Freehire.agent_search_url)
        self.assertEqual(
            session.get.call_args.kwargs["params"]["description_format"], "markdown"
        )

    def test_resolves_location_to_freehire_city_facet(self):
        session = Mock()
        session.get.side_effect = [
            self.make_response({"data": [{"value": "Berlin", "country": "de"}]}),
            self.make_response(
                {"data": [], "meta": {"total": 0, "limit": 1, "offset": 0}}
            ),
        ]

        with patch("jobspy.freehire.create_session", return_value=session):
            Freehire().scrape(
                ScraperInput(
                    site_type=[Site.FREEHIRE],
                    country=Country.GERMANY,
                    location="Berlin, Germany",
                    results_wanted=1,
                )
            )

        self.assertEqual(session.get.call_args_list[0].args[0], Freehire.cities_url)
        search_params = session.get.call_args_list[1].kwargs["params"]
        self.assertEqual(search_params["cities"], "Berlin")
        self.assertNotIn("countries", search_params)

    def test_paginates_until_results_wanted_is_met(self):
        session = Mock()
        first_page = [
            {
                "public_slug": f"role-{index}",
                "title": "Engineer",
                "company": "Acme",
                "url": f"https://jobs.acme.com/{index}",
            }
            for index in range(100)
        ]
        last_job = {
            "public_slug": "role-100",
            "title": "Engineer",
            "company": "Acme",
            "url": "https://jobs.acme.com/100",
        }
        session.get.side_effect = [
            self.make_response(
                {"data": first_page, "meta": {"total": 101, "limit": 100, "offset": 0}}
            ),
            self.make_response(
                {"data": [last_job], "meta": {"total": 101, "limit": 1, "offset": 100}}
            ),
        ]

        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = (
                Freehire()
                .scrape(
                    ScraperInput(
                        site_type=[Site.FREEHIRE],
                        country=Country.USA,
                        results_wanted=101,
                    )
                )
                .jobs
            )

        self.assertEqual(len(jobs), 101)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["offset"], 100)

    def test_missing_optional_fields_and_url_fallback(self):
        job = Freehire()._process_job(
            {"public_slug": "minimal", "title": "Engineer", "company": "Acme"}
        )
        self.assertEqual(job.job_url, "https://freehire.me/jobs/minimal")
        self.assertIsNone(job.job_url_direct)
        self.assertIsNone(job.compensation)
        self.assertIsNone(job.date_posted)
        self.assertIsNone(job.is_remote)

    def test_plain_full_description_uses_text_parameter(self):
        scraper = Freehire()
        scraper.scraper_input = ScraperInput(
            site_type=[Site.FREEHIRE],
            fetch_description=True,
            description_format="plain",
        )
        self.assertEqual(scraper._search_params()["description_format"], "text")

    def test_preview_description_is_converted(self):
        scraper = Freehire()
        scraper.scraper_input = ScraperInput(
            site_type=[Site.FREEHIRE], description_format="plain"
        )
        job = scraper._process_job(
            {
                "public_slug": "preview",
                "title": "Engineer",
                "company": "Acme",
                "description": "<p>Build <b>software</b></p>",
            }
        )
        self.assertEqual(job.description, "Build software")

    def test_failures_return_empty_results(self):
        for failure in (
            Mock(status_code=429),
            Mock(status_code=503),
            ValueError("JSON"),
        ):
            with self.subTest(failure=failure):
                session = Mock()
                if isinstance(failure, Exception):
                    session.get.side_effect = failure
                else:
                    session.get.return_value = failure
                with patch("jobspy.freehire.create_session", return_value=session):
                    jobs = (
                        Freehire().scrape(ScraperInput(site_type=[Site.FREEHIRE])).jobs
                    )
                self.assertEqual(jobs, [])
                self.assertEqual(session.get.call_count, 1)

    def test_malformed_jobs_are_skipped(self):
        session = Mock()
        session.get.return_value = self.make_response(
            {
                "data": [
                    None,
                    {"public_slug": "missing-title", "company": "Acme"},
                    {
                        "public_slug": "invalid-date",
                        "title": "Engineer",
                        "company": "Acme",
                        "posted_at": "invalid",
                    },
                    {"public_slug": "valid", "title": "Engineer", "company": "Acme"},
                ]
            }
        )
        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = Freehire().scrape(ScraperInput(site_type=[Site.FREEHIRE])).jobs
        self.assertEqual([job.id for job in jobs], ["freehire-valid"])

    def test_unknown_city_does_not_search(self):
        session = Mock()
        session.get.return_value = self.make_response({"data": []})
        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = (
                Freehire()
                .scrape(
                    ScraperInput(site_type=[Site.FREEHIRE], location="Unknown City")
                )
                .jobs
            )
        self.assertEqual(jobs, [])
        self.assertEqual(session.get.call_count, 1)

    def test_repeated_page_stops_without_duplicates(self):
        session = Mock()
        page = [
            {"public_slug": f"role-{index}", "title": "Engineer", "company": "Acme"}
            for index in range(100)
        ]
        session.get.return_value = self.make_response({"data": page})
        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = (
                Freehire()
                .scrape(ScraperInput(site_type=[Site.FREEHIRE], results_wanted=250))
                .jobs
            )
        self.assertEqual(len(jobs), 100)
        self.assertEqual(session.get.call_count, 2)

    def test_offset_respects_deep_pagination_bound(self):
        session = Mock()
        session.get.return_value = self.make_response({"data": []})
        with patch("jobspy.freehire.create_session", return_value=session):
            Freehire().scrape(
                ScraperInput(site_type=[Site.FREEHIRE], offset=9999, results_wanted=10)
            )
        self.assertEqual(session.get.call_args.kwargs["params"]["offset"], 9999)
        self.assertEqual(session.get.call_args.kwargs["params"]["limit"], 1)

    def test_public_dataframe_preserves_mapping(self):
        session = Mock()
        session.get.return_value = self.make_response(
            {
                "data": [
                    {
                        "public_slug": "public",
                        "title": "Engineer",
                        "company": "Acme",
                        "url": "https://jobs.acme.com/public",
                        "skills": ["python", "go"],
                        "enrichment": {
                            "salary_min": 10,
                            "salary_currency": "EUR",
                            "salary_period": "hour",
                        },
                    }
                ]
            }
        )
        with patch("jobspy.freehire.create_session", return_value=session):
            frame = scrape_jobs(
                site_name="freehire",
                results_wanted=1,
                enforce_annual_salary=True,
                verbose=0,
            )
        self.assertEqual(frame.iloc[0]["site"], "freehire")
        self.assertEqual(frame.iloc[0]["company"], "Acme")
        self.assertEqual(frame.iloc[0]["job_url"], "https://jobs.acme.com/public")
        self.assertEqual(frame.iloc[0]["skills"], "python, go")
        self.assertEqual(frame.iloc[0]["min_amount"], 20800)
        self.assertEqual(frame.iloc[0]["currency"], "EUR")

    def test_partial_results_survive_next_page_failure(self):
        session = Mock()
        page = [
            {"public_slug": f"role-{index}", "title": "Engineer", "company": "Acme"}
            for index in range(100)
        ]
        session.get.side_effect = [
            self.make_response({"data": page}),
            Mock(status_code=503),
        ]
        with patch("jobspy.freehire.create_session", return_value=session):
            jobs = (
                Freehire()
                .scrape(ScraperInput(site_type=[Site.FREEHIRE], results_wanted=101))
                .jobs
            )
        self.assertEqual(len(jobs), 100)

    def test_default_search_does_not_include_freehire(self):
        from jobspy.model import JobResponse

        adapters = [
            "LinkedIn",
            "Indeed",
            "ZipRecruiter",
            "Glassdoor",
            "BaytScraper",
            "Naukri",
            "BDJobs",
        ]
        patches = [patch(f"jobspy.{name}") for name in adapters]
        started = []
        try:
            for name, adapter_patch in zip(adapters, patches):
                adapter = adapter_patch.start()
                adapter.__name__ = name
                started.append(adapter_patch)
                adapter.return_value.scrape.return_value = JobResponse(jobs=[])
            with patch("jobspy.Freehire") as freehire:
                scrape_jobs(verbose=0)
                freehire.assert_not_called()
        finally:
            for adapter_patch in reversed(started):
                adapter_patch.stop()
