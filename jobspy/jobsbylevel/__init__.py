"""
jobspy.jobsbylevel
~~~~~~~~~~~~~~~~~~

Scraper for jobsbylevel.com (Level), a job board that rates every listing
from Level 1 to Level 4 on how central AI is to the work.

Level publishes its listings as public XML feeds (https://jobsbylevel.com/feeds),
so no HTML scraping is needed: the feed is streamed and parsed incrementally,
and the download stops as soon as enough matching jobs have been collected.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Iterator

import requests

from jobspy.exception import JobsByLevelException
from jobspy.jobsbylevel.constant import (
    catalogue_page_url,
    headers,
    level_meanings,
    max_catalogue_pages,
    recent_feed_max_hours,
    recent_feed_url,
)
from jobspy.jobsbylevel.util import (
    matches_location,
    matches_search_term,
    parse_compensation,
    parse_date,
    parse_datetime,
    parse_job_type,
    parse_location,
    strip_tags,
    text_of,
)
from jobspy.model import (
    DescriptionFormat,
    JobPost,
    JobResponse,
    Scraper,
    ScraperInput,
    Site,
)
from jobspy.util import (
    create_logger,
    create_session,
    extract_emails_from_text,
    markdown_converter,
    plain_converter,
)

log = create_logger("JobsByLevel")


class JobsByLevel(Scraper):
    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        user_agent: str | None = None,
    ):
        """
        Initializes JobsByLevel scraper, which reads the public jobsbylevel.com XML feeds
        """
        super().__init__(Site.JOBSBYLEVEL, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies, ca_cert=ca_cert, is_tls=False, has_retry=True
        )
        self.session.headers.update(headers)
        if user_agent:
            self.session.headers["user-agent"] = user_agent
        self.scraper_input = None

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes jobsbylevel.com for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        results_wanted = scraper_input.results_wanted or 15
        to_skip = scraper_input.offset or 0
        cutoff = None
        if scraper_input.hours_old:
            cutoff = datetime.now(timezone.utc) - timedelta(
                hours=scraper_input.hours_old
            )

        job_list: list[JobPost] = []
        seen_ids: set[str] = set()
        try:
            for job in self._iter_feed_jobs():
                if not self._matches(job, cutoff):
                    continue
                job_id = text_of(job, "id")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                if to_skip > 0:
                    to_skip -= 1
                    continue
                job_post = self._process_job(job, job_id)
                if job_post:
                    job_list.append(job_post)
                if len(job_list) >= results_wanted:
                    break
        except JobsByLevelException as e:
            log.error(str(e))
        except ET.ParseError as e:
            log.error(f"JobsByLevel: could not parse feed: {e}")
        except requests.RequestException as e:
            log.error(f"JobsByLevel: request failed: {e}")
        return JobResponse(jobs=job_list)

    def _feed_urls(self) -> Iterator[str]:
        hours_old = self.scraper_input.hours_old
        if hours_old and hours_old <= recent_feed_max_hours:
            yield recent_feed_url
            return
        if not hours_old:
            # freshest listings first, then fall back to the full catalogue
            yield recent_feed_url
        for page in range(1, max_catalogue_pages + 1):
            yield catalogue_page_url.format(page=page)

    def _iter_feed_jobs(self) -> Iterator[ET.Element]:
        """Streams <job> elements from the relevant feeds without loading them in memory"""
        for url in self._feed_urls():
            log.info(f"fetching {url}")
            response = self.session.get(
                url, stream=True, timeout=self.scraper_input.request_timeout
            )
            try:
                if response.status_code == 404 and url != recent_feed_url:
                    return  # past the last catalogue page
                if not response.ok:
                    raise JobsByLevelException(
                        f"JobsByLevel response status code {response.status_code} for {url}"
                    )
                response.raw.decode_content = True
                for _, element in ET.iterparse(response.raw, events=("end",)):
                    if element.tag == "job":
                        yield element
                        element.clear()
            finally:
                response.close()

    def _matches(self, job: ET.Element, cutoff: datetime | None) -> bool:
        scraper_input = self.scraper_input
        if scraper_input.is_remote and text_of(job, "remote") != "1":
            return False
        if cutoff:
            posted = parse_datetime(text_of(job, "date"))
            if not posted or posted < cutoff:
                return False
        if scraper_input.job_type:
            job_types = parse_job_type(text_of(job, "contract_type")) or []
            if scraper_input.job_type not in job_types:
                return False
        if not matches_location(
            scraper_input.location,
            text_of(job, "location/city"),
            text_of(job, "country"),
        ):
            return False
        return matches_search_term(
            scraper_input.search_term,
            text_of(job, "title"),
            strip_tags(text_of(job, "description")),
        )

    def _process_job(self, job: ET.Element, job_id: str) -> JobPost | None:
        title = text_of(job, "title")
        job_url = text_of(job, "url") or text_of(job, "link")
        if not title or not job_url:
            return None

        description = self._format_description(text_of(job, "description"))
        level = text_of(job, "level")
        if description and level and level.isdigit() and int(level) in level_meanings:
            level_note = (
                f"Level {level}/4 on jobsbylevel.com: {level_meanings[int(level)]}"
            )
            if self.scraper_input.description_format == DescriptionFormat.HTML:
                level_note = f"<p>{level_note}</p>"
            description = f"{description}\n\n{level_note}"

        return JobPost(
            id=f"jbl-{job_id}",
            title=title,
            company_name=text_of(job, "company"),
            company_url=text_of(job, "company_url"),
            job_url=job_url,
            job_url_direct=text_of(job, "apply_url"),
            location=parse_location(
                text_of(job, "location/city"), text_of(job, "country")
            ),
            description=description,
            job_type=parse_job_type(text_of(job, "contract_type")),
            compensation=parse_compensation(job),
            date_posted=parse_date(text_of(job, "date")),
            emails=extract_emails_from_text(description) if description else None,
            is_remote=text_of(job, "remote") == "1",
            job_function=text_of(job, "category"),
        )

    def _format_description(self, description_html: str | None) -> str | None:
        if not description_html:
            return None
        description_format = self.scraper_input.description_format
        if description_format == DescriptionFormat.MARKDOWN:
            return markdown_converter(description_html)
        if description_format == DescriptionFormat.PLAIN:
            return plain_converter(description_html)
        return description_html
