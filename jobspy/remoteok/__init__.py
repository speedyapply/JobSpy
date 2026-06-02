from __future__ import annotations

from datetime import datetime, timezone

from jobspy.exception import RemoteOKException
from jobspy.model import (
    Compensation,
    JobPost,
    JobResponse,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.remoteok.constant import headers, remoteok_api_url
from jobspy.remoteok.util import (
    matches_search_term,
    parse_date,
    parse_job_url,
    parse_location,
)
from jobspy.util import create_logger, create_session

log = create_logger("RemoteOK")


class RemoteOK(Scraper):
    api_url = remoteok_api_url

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        """
        Initializes RemoteOK scraper with the RemoteOK public API url.
        """
        super().__init__(Site.REMOTEOK, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
        )
        self.session.headers.update(headers)

        if user_agent:
            self.session.headers.update({"User-Agent": user_agent})

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes RemoteOK for jobs with scraper_input criteria.
        :param scraper_input: Information about job search criteria.
        :return: JobResponse containing a list of jobs.
        """
        job_list: list[JobPost] = []
        seconds_old = scraper_input.hours_old * 3600 if scraper_input.hours_old else None
        now_epoch = int(datetime.now(timezone.utc).timestamp())

        try:
            response = self.session.get(
                self.api_url,
                timeout=getattr(scraper_input, "request_timeout", 60),
            )

            if response.status_code != 200:
                raise RemoteOKException(
                    f"RemoteOK response status code {response.status_code}"
                )

            data = response.json()

        except Exception as e:
            log.error(f"RemoteOK: {str(e)}")
            return JobResponse(jobs=[])

        for item in data[1:]:
            try:
                if not matches_search_term(item, scraper_input.search_term):
                    continue

                if seconds_old:
                    epoch = item.get("epoch")
                    if epoch and now_epoch - int(epoch) > seconds_old:
                        continue

                job_post = self._process_job(item)

                if job_post:
                    job_list.append(job_post)

                if len(job_list) >= scraper_input.results_wanted:
                    break

            except Exception as e:
                log.error(f"Error processing RemoteOK job: {str(e)}")

        return JobResponse(jobs=job_list)

    def _process_job(self, job: dict) -> JobPost | None:
        """
        Processes a RemoteOK job item into a JobPost object.
        :param job: RemoteOK job dictionary.
        :return: JobPost object.
        """
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        compensation = None

        if salary_min and salary_max:
            compensation = Compensation(
                min_amount=float(salary_min),
                max_amount=float(salary_max),
                currency="USD",
            )

        return JobPost(
            id=f"remoteok-{job.get('id')}",
            title=job.get("position") or "N/A",
            company_name=job.get("company"),
            location=parse_location(job.get("location")),
            date_posted=parse_date(job.get("date")),
            job_url=parse_job_url(job.get("url") or job.get("apply_url")),
            job_url_direct=parse_job_url(job.get("apply_url")),
            description=job.get("description"),
            company_logo=job.get("company_logo") or job.get("logo"),
            compensation=compensation,
            is_remote=True,
            skills=job.get("tags") or None,
        )