from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from itertools import cycle

import requests
from bs4 import BeautifulSoup
from curl_cffi import CurlOpt
from curl_cffi import requests as curl_requests
from markdownify import markdownify as md

from jobspy.model import DescriptionFormat, JobType, Site


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
            proxies = [proxies]
        elif not isinstance(proxies, (list, tuple)):
            proxies = []
        self.rotates = len(set(proxies)) > 1
        self.proxy_cycle = cycle(map(self.format_proxy, proxies)) if proxies else None

    @staticmethod
    def format_proxy(proxy):
        """Utility method to format a proxy string into a dictionary."""
        if not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://", proxy):
            proxy = f"http://{proxy}"
        return {"http": proxy, "https": proxy}

    def request(self, method, url, **kwargs):
        if self.proxy_cycle:
            proxy = next(self.proxy_cycle)
            self.proxies = {} if proxy["http"] == "http://localhost" else proxy
        kwargs.setdefault("verify", self.verify)
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
            self,
            impersonate="chrome",
            allow_redirects=False,
            curl_options={CurlOpt.SSL_SESSIONID_CACHE: 0} if self.rotates else None,
        )


def create_session(
    *,
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    is_tls: bool = True,
    clear_cookies: bool = False,
    user_agent: str | None = None,
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
    if user_agent:
        session.headers["user-agent"] = user_agent

    return session


def set_logger_level(verbose: int):
    """
    Adjusts the logger's level. This function allows the logging level to be changed at runtime.

    Parameters:
    - verbose: int {0, 1, 2} (0 errors only, 1 adds warnings, 2 all logs)
    """
    if verbose is None:
        return
    level = {1: logging.WARNING, 0: logging.ERROR}.get(verbose, logging.INFO)
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith("JobSpy:"):
            logging.getLogger(logger_name).setLevel(level)


def _as_markup(text: str) -> str:
    return text if "<" in text else f"<!---->{text}"


def markdown_converter(description_html: str):
    if description_html is None:
        return None
    return md(_as_markup(description_html)).strip()


def plain_converter(description_html: str):
    if description_html is None:
        return None
    soup = BeautifulSoup(_as_markup(description_html), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def extract_emails_from_text(text: str) -> list[str] | None:
    if not text:
        return None
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    return list(dict.fromkeys(email_regex.findall(text)))


def format_description(html: str | None, description_format) -> tuple:
    """The description in the format asked for, and the emails in it."""
    emails = extract_emails_from_text(html)
    if description_format == DescriptionFormat.MARKDOWN:
        return markdown_converter(html), emails
    if description_format == DescriptionFormat.PLAIN:
        return plain_converter(html), emails
    return html, emails


def utc_date(epoch: float | None) -> date | None:
    """The UTC date of a Unix time in seconds; None for a missing or zero one."""
    return datetime.fromtimestamp(epoch, timezone.utc).date() if epoch else None


def get_enum_from_job_type(job_type_str: str) -> JobType | None:
    return next((t for t in JobType if job_type_str in t.value), None)


def remove_attributes(tag):
    for attr in list(tag.attrs):
        del tag[attr]
    return tag


salary_range = re.compile(
    r"\$(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)\s*[-—–]\s*(?:\$)?(\d+(?:,\d+)?(?:\.\d+)?)([kK]?)"
)


def extract_salary(salary_str, enforce_annual_salary=False):
    """The first "$min - $max" of a text as (interval, min, max, currency)."""
    lower_limit, upper_limit = 1000, 700000
    hourly_threshold, monthly_threshold = 350, 30000
    match = salary_range.search(salary_str or "")
    if not match:
        return None, None, None, None
    low, high = (int(float(match[i].replace(",", ""))) for i in (1, 3))
    if match[2] or match[4]:
        low, high = low * 1000, high * 1000
    # the interval is guessed from the size of the lower amount
    if low < hourly_threshold:
        interval, below, factor = "hourly", hourly_threshold, 2080
    elif low < monthly_threshold:
        interval, below, factor = "monthly", monthly_threshold, 12
    else:
        interval, below, factor = "yearly", float("inf"), 1
    annual_low, annual_high = low * factor, high * factor
    if high >= below or not (lower_limit <= annual_low < annual_high <= upper_limit):
        return None, None, None, None
    if enforce_annual_salary:
        return "yearly", annual_low, annual_high, "USD"
    return interval, low, high, "USD"


def map_str_to_site(site_name: str) -> Site:
    name = site_name.upper()
    if name == "ZIPRECRUITER":
        return Site.ZIP_RECRUITER
    if name not in Site.__members__:
        valid_sites = ", ".join(site.value for site in Site)
        raise KeyError(
            f"Invalid site name: '{site_name}'. Valid sites are: {valid_sites}"
        )
    return Site[name]


def convert_to_annual(job_data: dict):
    factors = {"hourly": 2080, "daily": 260, "weekly": 52, "monthly": 12}
    factor = factors[job_data["interval"]]
    for amount in ("min_amount", "max_amount"):
        if job_data[amount] is not None:
            job_data[amount] = round(job_data[amount] * factor, 2)
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
    "skills",
    "experience_range",
    "company_rating",
    "company_reviews_count",
    "vacancy_count",
    "work_from_home_type",
]
