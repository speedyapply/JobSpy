import datetime
import random
import re
from abc import ABC
from typing import Optional
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
from html_sanitizer import Sanitizer
from time import sleep
from datetime import datetime
from jobspy.model import (
    JobPost,
    Location,
    JobResponse,
    Country,
    Compensation,
    DescriptionFormat,
    Scraper,
    ScraperInput,
    Site, CompensationInterval, ExperienceRange,
)

from jobspy.hellowork.util import *

from jobspy.hellowork.constant import headers

from jobspy.util import (
    markdown_converter,
    plain_converter,
    create_session,
    create_logger,
    currency_parser
)

log = create_logger("LinkedIn")


class HelloWork(Scraper, ABC):
    base_url = "https://www.hellowork.com"
    delay = 3
    band_delay = 4
    jobs_per_page = 30

    def __init__(
            self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes HelloWorkScraper with the HelloWork job search url
        """
        super().__init__(Site.HELLOWORK, proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=ca_cert,
            is_tls=False,
            has_retry=True,
            delay=5,
            clear_cookies=True,
        )
        self.session.headers.update(headers)
        self.scraper_input = None
        self.country = "france"

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes LinkedIn for jobs with scraper_input criteria
        :param scraper_input:
        :return: job_response
        """
        self.scraper_input = scraper_input
        job_list: list[JobPost] = []
        seen_ids = set()

        params = dict(
            k=scraper_input.search_term,
            t=convert_remote_to_api(scraper_input.is_remote) if scraper_input.is_remote else None,
            c=convert_type_job_to_api(scraper_input.job_type) if scraper_input.job_type else None,
            ctt=convert_work_time_to_api(scraper_input.job_type) if scraper_input.job_type else None,
            msa=scraper_input.minimum_wage,
            l=scraper_input.location,
            d=convert_old_hours_to_api(scraper_input.hours_old) if scraper_input.hours_old else None,
            ray=scraper_input.distance,
            e=convert_years_of_experience_to_api(scraper_input.years_of_experience) if scraper_input.years_of_experience else None,
            st='date'
        )

        continue_search = lambda: len(job_list) < scraper_input.results_wanted

        min_page = 1
        max_page = min_page + (scraper_input.results_wanted // self.jobs_per_page)

        start = (scraper_input.offset + (min_page - 1) * self.jobs_per_page) or 0
        end = start + scraper_input.results_wanted

        if scraper_input.offset:
            min_page = start // self.jobs_per_page + 1
            max_page = min_page + scraper_input.results_wanted // num_jobs_per_page

        log.info('HelloWork : scrapper initialized')

        for page in range(min_page, max_page + 1):

            params['p'] = page

            response = self.session.get(
                f"{self.base_url}/fr-fr/emploi/recherche.html",
                params=params,
                timeout=getattr(scraper_input, "request_timeout", 60),
            )

            if response.status_code == 200:
                log.info(f'HelloWork : search page {page}/{max_page}')
            elif response.status_code == 403:
                log.error('Requests may have been blocked by an anti-bot system', exc_info=True)
                return JobResponse(jobs=job_list)
            elif response.status_code == 429:
                time_retry_after = response.headers.get('Retry-After', "Unknown")
                log.error('Too Many Requests sent to this domain. Please retry after %s', time_retry_after,
                          exc_info=True)
                return JobResponse(jobs=job_list)
            elif response.status_code == 500:
                log.error('Internal Server Error', exc_info=True)
                return JobResponse(jobs=job_list)
            elif response.status_code == 502:
                log.error('Bad gateway. Check the data sent before and try again.', exc_info=True)
                return JobResponse(jobs=job_list)
            else:
                log.error('Response status code : %s', response.status_code, exc_info=True)
                return JobResponse(jobs=job_list)
            content = response.content
            soup = BeautifulSoup(content, "html.parser")
            job_cards = soup.find_all('li', {'data-id-storage-target': 'item'})

            if len(job_cards) == 0:
                break

            for job_card in job_cards:
                parsed_job = self._process_job(job_card)
                if parsed_job.id in seen_ids:
                    continue
                seen_ids.add(parsed_job.id)
                job_list.append(parsed_job)

            if continue_search():
                sleep(random.uniform(self.delay, self.band_delay))

            job_list = job_list[start: end]
            print(f'HelloWork : Total of {len(job_list)} jobs scraped')
            return JobResponse(jobs=job_list)

    def _process_job(self, job_card: Tag) -> JobPost:
        id_job = job_card.get('data-id-storage-item-id')
        summary_job = job_card.find('h3')
        title_tag = summary_job.find('p')
        title = title_tag.get_text().encode().decode() if title_tag else None
        company_name_tag = summary_job.find('p').next_sibling.next_element
        company_name = company_name_tag.get_text().encode().decode() if company_name_tag else None
        relative_url_tag = job_card.find('a')
        url = None
        if relative_url_tag:
            relative_url = relative_url_tag.get('href')
            url = urljoin(self.base_url, relative_url)
        details_work_card = job_card.find('div', {'class': "flex gap-3 flex-wrap"})
        location_job = self._set_location(details_work_card)
        job_type_tag = details_work_card.find('div', {'data-cy': 'contractCard'})
        job_type = convert_api_to_job_type(job_type_tag.get_text(strip=True)) if job_type_tag else JobType.OTHER
        duration_work_time_tag = details_work_card.find('div', {'class': 'readonly tag-secondary-s w-fit border-0'},
                                                        string=lambda x: x and 'temps' in x.lower())
        duration_work_time = convert_api_to_job_type(duration_work_time_tag.get_text(strip=True)) if duration_work_time_tag else JobType.FULL_TIME
        remote_type_tag = details_work_card.find('div', {'data-cy': 'contractTag'})
        remote_type = convert_api_to_remote_type(remote_type_tag.get_text(strip=True)) if remote_type_tag else RemoteType.NONE
        job_details = self._fetch_extra_details(url)
        return JobPost(
            id=id_job,
            title=title,
            company_name=company_name,
            date_posted=job_details.get('date_posted'),
            description=job_details.get('description'),
            skills=job_details.get('skills'),
            job_url=url,
            location=location_job,
            job_type=[duration_work_time, job_type],
            compensation=job_details.get('compensation'),
            remote_type=remote_type,
            experience_range=job_details.get('experience')
        )

    def _set_location(self, details_card: Tag) -> Location:
        city_details = details_card.find('div', {'data-cy': "localisationCard"}).get_text(strip=True).encode(
            'utf-8').decode()
        city = city_details[:city_details.rfind('-')]
        has_zip = re.search(r'\d+$', city_details)
        if has_zip:
            zip_code = has_zip.group()
            return Location(country=Country.FRANCE, city=city, state=zip_code)
        return Location(country=Country.FRANCE, city=city)

    def _fetch_extra_details(self, url: str) -> dict:
        """
        Retrieves from a Request HTTP and parse the HTML to fetch
        the description, salary and so on
        :param url: URL of the job offer
        """
        job_details = dict()
        sanitizer_instance = Sanitizer()
        response = self.session.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        description_tag = soup.find('div', {'data-truncate-text-target': 'content'})
        skills_tag = soup.find('div', {'class': 'typo-long-m break-words'})
        if skills_tag:
            skills = skills_tag.prettify(formatter='html')
            match self.scraper_input.description_format:
                case DescriptionFormat.HTML:
                    job_details['description'] = sanitizer_instance.sanitize(skills)
                case DescriptionFormat.MARKDOWN:
                    job_details['description'] = markdown_converter(skills)
                case DescriptionFormat.PLAIN:
                    job_details['description'] = plain_converter(skills)
        if description_tag:
            description = description_tag.prettify(formatter='html')
            match self.scraper_input.description_format:
                case DescriptionFormat.HTML:
                    job_details['description'] = sanitizer_instance.sanitize(description)
                case DescriptionFormat.MARKDOWN:
                    job_details['description'] = markdown_converter(description)
                case DescriptionFormat.PLAIN:
                    job_details['description'] = plain_converter(description)
            if self.scraper_input.description_format == DescriptionFormat.HTML:
                job_details['description'] = sanitizer_instance.sanitize(description)
        job_details['compensation'] = self._get_compensation(soup) or None
        experience_level_tag = soup.find('li', {'class': "block tag-secondary-s border-0 readonly"},
                                         string=lambda x: x and 'Exp' in x)
        if experience_level_tag:
            full_text_experience = experience_level_tag.get_text(strip=True)
            experience_range = re.findall(r'\d+', full_text_experience)
            if len(experience_range) > 0:
                if 'min' in full_text_experience.lower() or len(experience_range) == 1:
                    experience_instance = ExperienceRange(min_year=experience_range[0])
                elif 'max' in full_text_experience.lower():
                    experience_instance = ExperienceRange(max_year=experience_range[1])
                else:
                    experience_instance = ExperienceRange(min_year=experience_range[0], max_year=experience_range[1])
                job_details['experience'] = experience_instance
        year_pattern = re.compile(r'[0-9]{2}/[0-9]{2}/[0-9]{4}')
        date_posted_tag = soup.find('p', {'class': 'block mt-8 sm:mt-12 typo-xs text-grey-500 break-words'})
        if date_posted_tag:
            job_details['date_posted'] = datetime.strptime(re.search(year_pattern, date_posted_tag.get_text()).group(),
                                                           "%d/%m/%Y").date()
        return job_details

    def _get_compensation(self, job_offer_card: Tag) -> Optional[Compensation]:
        salary_information = job_offer_card.find('button', {'data-cy': 'salary-tag-button'}).get_text(strip=True)
        if not salary_information:
            return None
        range_salary = [currency_parser(''.join(salary)) for salary in
                        re.findall(r'(\d+)\s*(\d*,?\d*)', salary_information)]
        if range_salary:
            return Compensation(
                interval=CompensationInterval.YEARLY if 'an' in salary_information else CompensationInterval.MONTHLY,
                min_amount=range_salary[0],
                max_amount=range_salary[1] if len(range_salary) > 1 else range_salary[0],
                currency="EUR"
            )
