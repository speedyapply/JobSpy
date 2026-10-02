from __future__ import annotations

import logging
import re
from itertools import cycle

import requests
from curl_cffi import requests as curl_requests
from markdownify import markdownify as md

from jobspy.model import CompensationInterval, JobType, Site


def create_logger(name: str):
    logger = logging.getLogger(f"JobSpy:{name}")
    logger.propagate = False
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler()
        format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        formatter = logging.Formatter(format)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


class RotatingProxySession:
    request_timeout = 15

    def __init__(self, proxies=None):
        if isinstance(proxies, str):
            self.proxy_cycle = cycle([self.format_proxy(proxies)])
        elif isinstance(proxies, list):
            self.proxy_cycle = (
                cycle([self.format_proxy(proxy) for proxy in proxies])
                if proxies
                else None
            )
        else:
            self.proxy_cycle = None

    @staticmethod
    def format_proxy(proxy):
        """Utility method to format a proxy string into a dictionary."""
        if not proxy.startswith(("http://", "https://", "socks5://")):
            proxy = f"http://{proxy}"
        return {"http": proxy, "https": proxy}

    def request(self, method, url, **kwargs):
        if self.proxy_cycle:
            proxy = next(self.proxy_cycle)
            self.proxies = {} if proxy["http"] == "http://localhost" else proxy
        kwargs.setdefault("timeout", self.request_timeout)
        return super().request(method, url, **kwargs)


class RequestsRotating(RotatingProxySession, requests.Session):
    def __init__(self, proxies=None, clear_cookies=False):
        RotatingProxySession.__init__(self, proxies=proxies)
        requests.Session.__init__(self)
        self.clear_cookies = clear_cookies

    def request(self, method, url, **kwargs):
        if self.clear_cookies:
            self.cookies.clear()
        return super().request(method, url, **kwargs)


class TLSRotating(RotatingProxySession, curl_requests.Session):
    def __init__(self, proxies=None):
        RotatingProxySession.__init__(self, proxies=proxies)
        curl_requests.Session.__init__(
            self, impersonate="chrome", allow_redirects=False
        )


def create_session(
    *,
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    is_tls: bool = True,
    clear_cookies: bool = False,
) -> RequestsRotating | TLSRotating:
    """
    Creates a proxy-rotating session: curl_cffi with a browser fingerprint if is_tls,
    else requests (supports clear_cookies).
    """
    if is_tls:
        session = TLSRotating(proxies=proxies)
    else:
        session = RequestsRotating(proxies=proxies, clear_cookies=clear_cookies)

    if ca_cert:
        session.verify = ca_cert

    return session


def set_logger_level(verbose: int):
    """
    Adjusts the logger's level. This function allows the logging level to be changed at runtime.

    Parameters:
    - verbose: int {0, 1, 2} (default=2, all logs)
    """
    if verbose is None:
        return
    level_name = {2: "INFO", 1: "WARNING", 0: "ERROR"}.get(verbose, "INFO")
    level = getattr(logging, level_name.upper(), None)
    if level is not None:
        for logger_name in logging.root.manager.loggerDict:
            if logger_name.startswith("JobSpy:"):
                logging.getLogger(logger_name).setLevel(level)
    else:
        raise ValueError(f"Invalid log level: {level_name}")


def markdown_converter(description_html: str):
    if description_html is None:
        return None
    markdown = md(description_html)
    return markdown.strip()

def plain_converter(decription_html:str):
    from bs4 import BeautifulSoup
    if decription_html is None:
        return None
    soup = BeautifulSoup(decription_html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+',' ',text)
    return text.strip()


def extract_emails_from_text(text: str) -> list[str] | None:
    if not text:
        return None
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    return email_regex.findall(text)


def get_enum_from_job_type(job_type_str: str) -> JobType | None:
    """
    Given a string, returns the corresponding JobType enum member if a match is found.
    """
    res = None
    for job_type in JobType:
        if job_type_str in job_type.value:
            res = job_type
    return res


def remove_attributes(tag):
    for attr in list(tag.attrs):
        del tag[attr]
    return tag


def extract_salary(
    salary_str,
    lower_limit=1000,
    upper_limit=700000,
    hourly_threshold=350,
    monthly_threshold=30000,
    enforce_annual_salary=False,
):
    """
    Extracts salary information from a string and returns the salary interval, min and max salary values, and currency.
    (TODO: Needs test cases as the regex is complicated and may not cover all edge cases)
    """
    if not salary_str:
        return None, None, None, None

    annual_max_salary = None
    min_max_pattern = r"\$(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)\s*[-—–]\s*(?:\$)?(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)"

    def to_int(s):
        return int(float(s.replace(",", "")))

    def convert_hourly_to_annual(hourly_wage):
        return hourly_wage * 2080

    def convert_monthly_to_annual(monthly_wage):
        return monthly_wage * 12

    match = re.search(min_max_pattern, salary_str)

    if match:
        min_salary = to_int(match.group(1))
        max_salary = to_int(match.group(3))
        # Handle 'k' suffix for min and max salaries independently
        if "k" in match.group(2).lower() or "k" in match.group(4).lower():
            min_salary *= 1000
            max_salary *= 1000

        # Convert to annual if less than the hourly threshold
        if min_salary < hourly_threshold:
            interval = CompensationInterval.HOURLY.value
            annual_min_salary = convert_hourly_to_annual(min_salary)
            if max_salary < hourly_threshold:
                annual_max_salary = convert_hourly_to_annual(max_salary)

        elif min_salary < monthly_threshold:
            interval = CompensationInterval.MONTHLY.value
            annual_min_salary = convert_monthly_to_annual(min_salary)
            if max_salary < monthly_threshold:
                annual_max_salary = convert_monthly_to_annual(max_salary)

        else:
            interval = CompensationInterval.YEARLY.value
            annual_min_salary = min_salary
            annual_max_salary = max_salary

        # Ensure salary range is within specified limits
        if not annual_max_salary:
            return None, None, None, None
        if (
            lower_limit <= annual_min_salary <= upper_limit
            and lower_limit <= annual_max_salary <= upper_limit
            and annual_min_salary < annual_max_salary
        ):
            if enforce_annual_salary:
                return interval, annual_min_salary, annual_max_salary, "USD"
            else:
                return interval, min_salary, max_salary, "USD"
    return None, None, None, None


def extract_job_type(description: str):
    if not description:
        return []

    keywords = {
        JobType.FULL_TIME: r"full\s?time",
        JobType.PART_TIME: r"part\s?time",
        JobType.INTERNSHIP: r"internship",
        JobType.CONTRACT: r"contract",
    }

    listing_types = []
    for key, pattern in keywords.items():
        if re.search(pattern, description, re.IGNORECASE):
            listing_types.append(key)

    return listing_types if listing_types else None


def map_str_to_site(site_name: str) -> Site:
    return Site[site_name.upper()]


def get_enum_from_value(value_str):
    for job_type in JobType:
        if value_str in job_type.value:
            return job_type
    raise Exception(f"Invalid job type: {value_str}")


def convert_to_annual(job_data: dict):
    factors = {"hourly": 2080, "daily": 260, "weekly": 52, "monthly": 12}
    factor = factors[job_data["interval"]]
    job_data["min_amount"] = round(job_data["min_amount"] * factor, 2)
    job_data["max_amount"] = round(job_data["max_amount"] * factor, 2)
    job_data["interval"] = "yearly"


desired_order = [
    "id",
    "site",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "date_posted",
    "job_type",
    "salary_source",
    "interval",
    "min_amount",
    "max_amount",
    "currency",
    "is_remote",
    "job_level",
    "job_function",
    "listing_type",
    "emails",
    "description",
    "company_industry",
    "company_url",
    "company_logo",
    "company_url_direct",
    "company_addresses",
    "company_num_employees",
    "company_revenue",
    "company_description",
    # naukri-specific fields
    "skills",
    "experience_range",
    "company_rating",
    "company_reviews_count",
    "vacancy_count",
    "work_from_home_type",
]
