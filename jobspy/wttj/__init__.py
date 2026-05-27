from __future__ import annotations

import math
import urllib.parse
from datetime import datetime
from jobspy.model import (
    Scraper,
    ScraperInput,
    Site,
    JobResponse,
    JobPost,
    Location,
    JobType,
)
from jobspy.util import create_session, create_logger
from jobspy.exception import WttjException

def _map_wttj_job_type(wttj_type: str) -> list[JobType]:
    if not wttj_type:
        return []
    wttj_type = wttj_type.lower()
    mapping = {
        "full_time": JobType.FULL_TIME,
        "part_time": JobType.PART_TIME,
        "internship": JobType.INTERNSHIP,
        "apprenticeship": JobType.INTERNSHIP,
        "contract": JobType.CONTRACT,
        "temporary": JobType.TEMPORARY
    }
    job_type = mapping.get(wttj_type)
    return [job_type] if job_type else []

def _parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return None

log = create_logger("Wttj")

class Wttj(Scraper):
    def __init__(
        self, proxies: list[str] | str | None = None, ca_cert: str | None = None, user_agent: str | None = None
    ):
        """
        Initializes the WTTJ Scraper
        """
        super().__init__(Site.WTTJ, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=self.proxies,
            ca_cert=self.ca_cert,
            is_tls=False,
            has_retry=True,
        )
        if user_agent:
            self.session.headers.update({"User-Agent": user_agent})

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """
        Scrapes WTTJ for jobs using their public Algolia Search API backend.
        """
        job_list: list[JobPost] = []
        seen_urls = set()  # Garantit l'unicité des offres sur l'ensemble du scraping
        
        url = "https://csekhvms53-dsn.algolia.net/1/indexes/wk_cms_jobs_production/query"
        
        page = 0 if not scraper_input.offset else math.floor(scraper_input.offset / 30)
        max_pages = 30
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.welcometothejungle.com",
            "Referer": "https://www.welcometothejungle.com/",
            "x-algolia-application-id": "CSEKHVMS53",
            "x-algolia-api-key": "4bd8f6215d0cc52b26430765769e65a0"
        })
        
        while len(job_list) < scraper_input.results_wanted and page < max_pages:
            log.info(f"Scraping page {page + 1} for WTTJ via Algolia API")
            
            search_query = scraper_input.search_term or ""
            if scraper_input.location:
                search_query = f"{search_query} {scraper_input.location}".strip()

            query_str = f"query={urllib.parse.quote(search_query)}"
            query_str += f"&page={page}"
            query_str += f"&hitsPerPage={min(scraper_input.results_wanted - len(job_list), 30)}"

            payload = f'{{"params":"{query_str}"}}'

            try:
                response = self.session.post(
                    url,
                    data=payload,
                    timeout=scraper_input.request_timeout or 60
                )
                response.raise_for_status()
                
            except Exception as e:
                error_msg = f"Failed to fetch WTTJ jobs via Algolia API on page {page + 1}: {e}"
                if 'response' in locals() and response.text:
                    error_msg += f" | Details: {response.text}"
                log.error(error_msg)
                raise WttjException(error_msg)
            
            data = response.json()
            hits = data.get("hits", [])
            
            if not hits:
                log.info("WTTJ: No more jobs returned by the Algolia backend.")
                break

            for job in hits:
                if len(job_list) >= scraper_input.results_wanted:
                    break

                slug = job.get("slug", "")
                if not slug:
                    continue

                organization = job.get("organization") or {}
                company_slug = organization.get("slug", "unknown")
                
                # Reconstruction immédiate de l'URL pour la validation d'unicité
                full_job_url = f"https://www.welcometothejungle.com/fr/companies/{company_slug}/jobs/{slug}"

                # Si l'URL a déjà été enregistrée (doublon d'indexation d'Algolia), on passe au suivant
                if full_job_url in seen_urls:
                    continue
                seen_urls.add(full_job_url)

                title = job.get("name", "Unknown Title")
                company_name = organization.get("name", "Unknown Company")
                
                logo_dict = organization.get("logo") or {}
                company_logo = logo_dict.get("url") if isinstance(logo_dict, dict) else None
                
                office = job.get("office") or {}
                location_city = office.get("city")
                location_country = office.get("country_code") or office.get("country")
                
                is_remote = job.get("remote") in ["full", "partial"] or job.get("workplace_type") == "remote"
                parsed_job_types = _map_wttj_job_type(job.get("contract_type"))
                date_posted = _parse_date(job.get("published_at") or job.get("created_at"))
                
                job_id = str(job.get("objectID") or job.get("id") or f"wttj-{abs(hash(slug))}")

                job_list.append(JobPost(
                    id=job_id,
                    title=title,
                    company_name=company_name,
                    job_url=full_job_url,
                    location=Location(city=location_city, country=location_country),
                    is_remote=is_remote,
                    job_type=parsed_job_types,
                    date_posted=date_posted,
                    company_logo=company_logo,
                ))
                                    
            page += 1

        return JobResponse(jobs=job_list[:scraper_input.results_wanted])