from __future__ import annotations

import logging
import re
from itertools import cycle
import random
import threading
import time

import numpy as np
import requests
import tls_client
import urllib3
from markdownify import markdownify as md
from requests.adapters import HTTPAdapter, Retry

from jobspy.model import CompensationInterval, JobType, Site

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
        if proxy.startswith("http://") or proxy.startswith("https://"):
            return {"http": proxy, "https": proxy}
        if proxy.startswith("socks5://"):
            return {"http": proxy, "https": proxy}
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}


class RateLimiter:
    """
    A thread-safe rate limiter to enforce a delay between operations.

    Args:
        rate_delay_min (int | float | None):
            The minimum time in seconds to wait since the last request.
        rate_delay_max (int | float | None):
            The maximum time in seconds to wait since the last request.
    """
    def __init__(self, rate_delay_min: int | float | None, rate_delay_max: int | float | None):
        self.rate_delay_min = rate_delay_min
        self.rate_delay_max = rate_delay_max
        self.rate_delay_lock = threading.Lock()
        self.last_request_time = 0.0
        self.backoff_until = 0.0

    def enforce_delay(self):
        """
        Enforces a delay to meet the configured rate limit.

        This method is thread-safe. It calculates the required sleep time based on
        the time elapsed since the last request and waits if necessary.
        """
        with self.rate_delay_lock:
            current_time = time.monotonic()
            
            # Check for active backoff
            if self.backoff_until > current_time:
                backoff_wait = self.backoff_until - current_time
                if backoff_wait > 0:
                    time.sleep(backoff_wait)
                    # Reset last request time to now after waiting out backoff
                    self.last_request_time = time.monotonic()
                    return

        if not isinstance(self.rate_delay_min, (int, float)) or not isinstance(self.rate_delay_max, (int, float)):
            return

        with self.rate_delay_lock:

            delay_seconds = random.uniform(self.rate_delay_min, self.rate_delay_max)
            time_elapsed = current_time - self.last_request_time
            sleep_time = delay_seconds - time_elapsed
            
            if sleep_time > 0:
                time.sleep(sleep_time)

            self.last_request_time = time.monotonic()

    def backoff(self, seconds: float = 60.0):
        """
        Triggers a temporary backoff period where enforce_delay will sleep.
        Useful when encountering 429 Too Many Requests or 403 Forbidden.
        """
        with self.rate_delay_lock:
            # Only extend backoff if the new one is further in the future
            new_backoff = time.monotonic() + seconds
            if new_backoff > self.backoff_until:
                self.backoff_until = new_backoff


class RequestsRotating(RotatingProxySession, requests.Session):
    def __init__(self, proxies=None, has_retry=False, delay=1, clear_cookies=False, flaresolverr_url=None):
        RotatingProxySession.__init__(self, proxies=proxies)
        requests.Session.__init__(self)
        self.clear_cookies = clear_cookies
        self.flaresolverr_url = flaresolverr_url
        self.allow_redirects = True
        self.setup_session(has_retry, delay)

    def setup_session(self, has_retry, delay):
        if has_retry:
            retries = Retry(
                total=3,
                connect=3,
                status=3,
                status_forcelist=[500, 502, 503, 504, 429],
                backoff_factor=delay,
            )
            adapter = HTTPAdapter(max_retries=retries)
            self.mount("http://", adapter)
            self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if self.clear_cookies:
            self.cookies.clear()
        
        # Rate Limiting Logic
        if hasattr(self, 'rate_limiter'):
             self.rate_limiter.enforce_delay()

        # Standard Request Logic
        # Apply proxy cycling logic
        if self.proxy_cycle:
            next_proxy = next(self.proxy_cycle)
            if next_proxy["http"] != "http://localhost":
                self.proxies = next_proxy
            else:
                self.proxies = {}
        
        try:
             response = requests.Session.request(self, method, url, **kwargs)
        except Exception as e:
             raise e

        # Check for Cloudflare errors and retry with Flaresolverr if available
        if self.flaresolverr_url and self._is_cloudflare_blocked(response):
            create_logger("Requests").info(f"Cloudflare block detected (status {response.status_code}). Retrying with Flaresolverr...")
            fr_resp = flaresolverr_request(self.flaresolverr_url, method, url, **kwargs)
            if fr_resp and fr_resp.ok:
                # Inject cookies from Flaresolverr into our session for future requests
                if hasattr(fr_resp, 'flaresolverr_cookies'):
                    for cookie in fr_resp.flaresolverr_cookies:
                        self.cookies.set(
                            cookie.get('name', ''),
                            cookie.get('value', ''),
                            domain=cookie.get('domain', ''),
                            path=cookie.get('path', '/')
                        )
                    create_logger("Requests").info(f"Injected {len(fr_resp.flaresolverr_cookies)} cookies from Flaresolverr")
                return fr_resp
            # If Flaresolverr also failed, fall through to return original response

        if hasattr(self, 'rate_limiter') and response.status_code in [429, 403]:
            # Default to 30s backoff, or longer if retry-after header is present
            retry_after_header = response.headers.get("Retry-After")
            retry_after = int(retry_after_header) if retry_after_header and retry_after_header.isdigit() else 30
            if retry_after > 60:
                retry_after = 60 # Cap at 60s to avoid hanging too long
                
            create_logger("Requests").warning(f"Received {response.status_code}. Backing off for {retry_after}s")
            self.rate_limiter.backoff(seconds=retry_after)
             
        return response
    
    def _is_cloudflare_blocked(self, response):
        """Detect if response is a Cloudflare challenge/block"""
        if response.status_code not in [403, 503]:
            return False
        
        # Check response headers for Cloudflare indicators
        headers = {k.lower(): v.lower() for k, v in response.headers.items()} if hasattr(response, 'headers') else {}
        if headers.get('server', '') == 'cloudflare' or 'cf-ray' in headers:
            return True
        
        # Check response content for Cloudflare indicators
        content = response.text.lower() if hasattr(response, 'text') else ''
        cf_indicators = [
            'cloudflare',
            'cf-ray',
            'cf_chl_opt',
            'just a moment',
            'checking your browser',
            'ddos-guard',
            'cf-waf'
        ]
        return any(indicator in content for indicator in cf_indicators)


class TLSRotating(RotatingProxySession, tls_client.Session):
    def __init__(self, proxies=None, rate_delay_min: int | float | None = None, rate_delay_max: int | float | None = None, flaresolverr_url=None):
        RotatingProxySession.__init__(self, proxies=proxies)
        tls_client.Session.__init__(self, random_tls_extension_order=True)
        self.rate_limiter = RateLimiter(rate_delay_min, rate_delay_max)
        self.flaresolverr_url = flaresolverr_url

    def execute_request(self, *args, **kwargs):
        self.rate_limiter.enforce_delay()
        
        if self.proxy_cycle:
            next_proxy = next(self.proxy_cycle)
            if next_proxy["http"] != "http://localhost":
                self.proxies = next_proxy
            else:
                self.proxies = {}
        
        # Try normal request first
        response = tls_client.Session.execute_request(self, *args, **kwargs)
        response.ok = response.status_code in range(200, 400)
        
        # Check for Cloudflare errors and retry with Flaresolverr if available
        if self.flaresolverr_url and self._is_cloudflare_blocked(response):
            create_logger("TLS").info(f"Cloudflare block detected (status {response.status_code}). Retrying with Flaresolverr...")
            
            # Parse method and url from args/kwargs
            method = kwargs.get("method") or (args[0] if len(args) > 0 else "GET")
            url = kwargs.get("url") or (args[1] if len(args) > 1 else None)
            
            # Prepare kwargs for Flaresolverr (remove method/url to avoid duplication)
            kwargs_for_fr = kwargs.copy()
            kwargs_for_fr.pop("method", None)
            kwargs_for_fr.pop("url", None)
            
            fr_resp = flaresolverr_request(self.flaresolverr_url, method, url, **kwargs_for_fr)
            if fr_resp and fr_resp.ok:
                # Inject cookies from Flaresolverr into our session for future requests
                if hasattr(fr_resp, 'flaresolverr_cookies'):
                    for cookie in fr_resp.flaresolverr_cookies:
                        self.cookies.set(
                            cookie.get('name', ''),
                            cookie.get('value', ''),
                            domain=cookie.get('domain', ''),
                            path=cookie.get('path', '/')
                        )
                    create_logger("TLS").info(f"Injected {len(fr_resp.flaresolverr_cookies)} cookies from Flaresolverr")
                return fr_resp
            # If Flaresolverr also failed, fall through to return original response
        
        # Smart Rate Limiting: Trigger backoff on 429 (Too Many Requests) or 403 (Forbidden)
        if response.status_code in [429, 403]:
            create_logger("TLS").warning(f"Received {response.status_code}. Backing off for 30s")
            self.rate_limiter.backoff(seconds=30)
            
        return response
    
    def _is_cloudflare_blocked(self, response):
        """Detect if response is a Cloudflare challenge/block"""
        if response.status_code not in [403, 503]:
            return False
        
        # Check response headers for Cloudflare indicators
        headers = {k.lower(): v.lower() for k, v in response.headers.items()} if hasattr(response, 'headers') else {}
        if headers.get('server', '') == 'cloudflare' or 'cf-ray' in headers:
            return True
        
        # Check response content for Cloudflare indicators
        content = response.text.lower() if hasattr(response, 'text') else ''
        cf_indicators = [
            'cloudflare',
            'cf-ray',
            'cf_chl_opt',
            'just a moment',
            'checking your browser',
            'ddos-guard',
            'cf-waf'
        ]
        return any(indicator in content for indicator in cf_indicators)


def create_session(proxies, ca_cert=None, is_tls=True, has_retry=False, delay=1, rate_delay_min=None, rate_delay_max=None, flaresolverr_url=None):
    """
    Creates a rotating session with the provided proxies.
    If is_tls is True, creates a TLSRotating session.
    If is_tls is False, creates a RequestsRotating session.
    """
    if is_tls:
        session = TLSRotating(proxies=proxies, flaresolverr_url=flaresolverr_url)
    else:
        session = RequestsRotating(proxies=proxies, has_retry=has_retry, delay=delay, clear_cookies=False, flaresolverr_url=flaresolverr_url)

    if ca_cert:
        session.verify = ca_cert
    
    # Initialize RateLimiter if parameters are provided
    if rate_delay_min is not None and rate_delay_max is not None:
         session.rate_limiter = RateLimiter(rate_delay_min, rate_delay_max)

    return session

def flaresolverr_request(flaresolverr_url, method, url, **kwargs):
    """
    Helper to execute requests via Flaresolverr.
    Returns a requests.Response object if successful, or None to fall back.
    """
    # print(f"DEBUG: Flaresolverr request to {flaresolverr_url} for {url}")
    method_upper = method.upper()
    if method_upper not in ["GET", "POST"]:
        return None

    # Flaresolverr supports GET and POST via its v1/request command
    payload = {
        "cmd": f"request.{method_upper.lower()}",
        "url": url,
        "maxTimeout": 60000,
    }
    
    # Handle POST data
    if method_upper == "POST":
        if kwargs.get("data"):
            if isinstance(kwargs["data"], dict):
                from urllib.parse import urlencode
                payload["postData"] = urlencode(kwargs["data"])
            else:
                payload["postData"] = str(kwargs["data"])
        elif kwargs.get("json"):
            import json
            payload["postData"] = json.dumps(kwargs["json"])
            # Start with correct header for JSON
            headers = kwargs.get("headers", {})
            if "Content-Type" not in headers:
                 headers["Content-Type"] = "application/json"
                 # NOTE: We don't update kwargs["headers"] here because we don't pass it to flaresolverr
                 # We only set it for the instruction to Flaresolverr if needed, but Flaresolverr v1 doesn't take headers param easily
                 # except via implicit browser behavior.

    try:
        # Flaresolverr API endpoint is at /v1
        endpoint = flaresolverr_url.rstrip('/') + '/v1'
        fr_resp = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"})
        fr_resp.raise_for_status()
        fr_data = fr_resp.json()
        
        if fr_data.get("status") == "ok":
            solution = fr_data.get("solution", {})
            # Reconstruct a requests.Response object
            resp = requests.Response()
            resp.status_code = solution.get("status", 200)
            resp._content = solution.get("response", "").encode('utf-8')
            resp.url = solution.get("url", url)
            
            # Attach Flaresolverr metadata for session injection
            resp.flaresolverr_cookies = solution.get("cookies", [])
            resp.flaresolverr_user_agent = solution.get("userAgent", "")
            
            return resp
        else:
            create_logger("Flaresolverr").warning(f"Flaresolverr returned status '{fr_data.get('status')}': {fr_data.get('message', '')}. Falling back.")
    except Exception as e:
        create_logger("Flaresolverr").error(f"Flaresolverr request failed: {e}. Falling back.")
    
    return None


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


def currency_parser(cur_str):
    # Remove any non-numerical characters
    # except for ',' '.' or '-' (e.g. EUR)
    cur_str = re.sub("[^-0-9.,]", "", cur_str)
    # Remove any 000s separators (either , or .)
    cur_str = re.sub("[.,]", "", cur_str[:-3]) + cur_str[-3:]

    if "." in list(cur_str[-3:]):
        num = float(cur_str)
    elif "," in list(cur_str[-3:]):
        num = float(cur_str.replace(",", "."))
    else:
        num = float(cur_str)

    return np.round(num, 2)


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
    if job_data["interval"] == "hourly":
        job_data["min_amount"] *= 2080
        job_data["max_amount"] *= 2080
    if job_data["interval"] == "monthly":
        job_data["min_amount"] *= 12
        job_data["max_amount"] *= 12
    if job_data["interval"] == "weekly":
        job_data["min_amount"] *= 52
        job_data["max_amount"] *= 52
    if job_data["interval"] == "daily":
        job_data["min_amount"] *= 260
        job_data["max_amount"] *= 260
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
