import re

from jobspy.model import CompensationInterval, Country, JobType
from jobspy.seek.model import Market

jobs_per_page = 100
km_per_mile = 1.609344
max_distance_km = 100
remote_arrangement = "3"
private_advertiser = "Private Advertiser"
rate_limited = "RATE_LIMITED"


markets = {
    country: Market(
        site_key=site_key,
        zone=zone,
        domain=domain,
        currency=currency,
        currency_symbol=currency_symbol,
    )
    for country, site_key, zone, domain, currency, currency_symbol in (
        (Country.AUSTRALIA, "AU-Main", "anz-1", "au.seek.com", "AUD", "$"),
        (Country.NEWZEALAND, "NZ-Main", "anz-2", "nz.seek.com", "NZD", "$"),
        (Country.HONGKONG, "HK-Main", "asia-1", "hk.jobsdb.com", "HKD", "$"),
        (Country.THAILAND, "TH-Main", "asia-3", "th.jobsdb.com", "THB", "฿"),
        (Country.INDONESIA, "ID-Main", "asia-4", "id.jobstreet.com", "IDR", "Rp"),
        (Country.MALAYSIA, "MY-Main", "asia-5", "my.jobstreet.com", "MYR", "RM"),
        (Country.PHILIPPINES, "PH-Main", "asia-6", "ph.jobstreet.com", "PHP", "₱"),
        (Country.SINGAPORE, "SG-Main", "asia-7", "sg.jobstreet.com", "SGD", "$"),
    )
}

job_type_codes = {
    JobType.FULL_TIME: 242,
    JobType.PART_TIME: 243,
    JobType.CONTRACT: 244,
    JobType.TEMPORARY: 244,
}

job_type_labels = {
    "Full time": [JobType.FULL_TIME],
    "Part time": [JobType.PART_TIME],
    "Contract/Temp": [JobType.CONTRACT, JobType.TEMPORARY],
}

pay_intervals = {
    "hour": CompensationInterval.HOURLY,
    "month": CompensationInterval.MONTHLY,
    "year": CompensationInterval.YEARLY,
}

salary_pattern = re.compile(
    r"(?P<symbol>[^\d\s]+)\xa0?(?P<low>\d(?:[\d.,]*\d)?)"
    r"(?: – (?P=symbol)\xa0?(?P<high>\d(?:[\d.,]*\d)?))? per (?P<unit>hour|month|year)"
)
thousands_separator = re.compile(r"[.,](?=\d{3}(?!\d))")

details_alias = """
    j%s: jobDetails(id: "%s") {
        job {
            content(platform: WEB)
        }
        companyProfile(zone: $zone) {
            overview {
                description {
                    full
                }
                industry
                primaryLocation
                size {
                    description
                }
                website {
                    url
                }
            }
            reviewsSummary {
                overallRating {
                    value
                    numberOfReviews {
                        value
                    }
                }
            }
        }
    }
"""
