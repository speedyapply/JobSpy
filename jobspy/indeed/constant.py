from jobspy.model import CompensationInterval, Country, JobType

jobs_per_page = 100

job_search_query = """
    query GetJobData {{
        jobSearch(
            {what}
            {location}
            limit: {limit}
            {cursor}
            sort: RELEVANCE
            {filters}
        ) {{
            pageInfo {{
                nextCursor
            }}
            results {{
                job {{
                    key
                    title
                    sourceEmployerName
                    dateOnIndeed
                    description {{
                        html
                    }}
                    location {{
                        countryCode
                        admin1Code
                        city
                    }}
                    compensation {{
                        estimated {{
                            currencyCode
                            baseSalary {{
                                unitOfWork
                                range {{
                                    ... on Range {{ min max }}
                                    ... on AtLeast {{ min }}
                                    ... on AtMost {{ max }}
                                    ... on Exactly {{ value }}
                                }}
                            }}
                        }}
                        baseSalary {{
                            unitOfWork
                            range {{
                                ... on Range {{ min max }}
                                ... on AtLeast {{ min }}
                                ... on AtMost {{ max }}
                                ... on Exactly {{ value }}
                            }}
                        }}
                        currencyCode
                    }}
                    attributes {{
                        key
                    }}
                    employer {{
                        relativeCompanyPageUrl
                        name
                        ugcStats {{
                            ratings {{
                                overallRating {{
                                    value
                                    count
                                }}
                            }}
                        }}
                        dossier {{
                            employerDetails {{
                                addresses
                                industry
                                employeesLocalizedLabel
                                revenueLocalizedLabel
                                briefDescription
                            }}
                            images {{
                                squareLogoUrl
                            }}
                            links {{
                                corporateWebsite
                            }}
                        }}
                    }}
                    recruit {{
                        viewJobUrl
                    }}
                }}
            }}
        }}
    }}
"""

headers = {
    "content-type": "application/json",
    "indeed-api-key": "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8",
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1",
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

default_distance = 50

job_type_codes = {
    JobType.FULL_TIME: ("CF3CP",),
    JobType.PART_TIME: ("75GKK",),
    JobType.CONTRACT: ("NJXCK", "T9BXE", "T65DZ"),
    JobType.INTERNSHIP: ("VDTG7",),
    JobType.TEMPORARY: ("4HKF7", "CJWTS"),
    JobType.PER_DIEM: ("TQKYQ",),
    JobType.VOLUNTEER: ("UXQZ8",),
}
job_types_by_code = {
    code: job_type for job_type, codes in job_type_codes.items() for code in codes
}
permanent_key = "5QWDV"
full_time_is_permanent_in = Country.JAPAN

remote_key = "DSQF7"
hybrid_key = "PAXZC"

pay_intervals = {
    "HOUR": CompensationInterval.HOURLY,
    "DAY": CompensationInterval.DAILY,
    "WEEK": CompensationInterval.WEEKLY,
    "MONTH": CompensationInterval.MONTHLY,
    "YEAR": CompensationInterval.YEARLY,
}

country_codes = {
    Country.ARGENTINA: "AR",
    Country.AUSTRALIA: "AU",
    Country.AUSTRIA: "AT",
    Country.BAHRAIN: "BH",
    Country.BELGIUM: "BE",
    Country.BRAZIL: "BR",
    Country.CANADA: "CA",
    Country.CHILE: "CL",
    Country.CHINA: "CN",
    Country.COLOMBIA: "CO",
    Country.COSTARICA: "CR",
    Country.CZECHREPUBLIC: "CZ",
    Country.DENMARK: "DK",
    Country.ECUADOR: "EC",
    Country.EGYPT: "EG",
    Country.FINLAND: "FI",
    Country.FRANCE: "FR",
    Country.GERMANY: "DE",
    Country.GREECE: "GR",
    Country.HONGKONG: "HK",
    Country.HUNGARY: "HU",
    Country.INDIA: "IN",
    Country.INDONESIA: "ID",
    Country.IRELAND: "IE",
    Country.ISRAEL: "IL",
    Country.ITALY: "IT",
    Country.JAPAN: "JP",
    Country.KUWAIT: "KW",
    Country.LUXEMBOURG: "LU",
    Country.MALAYSIA: "MY",
    Country.MEXICO: "MX",
    Country.MOROCCO: "MA",
    Country.NETHERLANDS: "NL",
    Country.NEWZEALAND: "NZ",
    Country.NIGERIA: "NG",
    Country.NORWAY: "NO",
    Country.OMAN: "OM",
    Country.PAKISTAN: "PK",
    Country.PANAMA: "PA",
    Country.PERU: "PE",
    Country.PHILIPPINES: "PH",
    Country.POLAND: "PL",
    Country.PORTUGAL: "PT",
    Country.QATAR: "QA",
    Country.ROMANIA: "RO",
    Country.SAUDIARABIA: "SA",
    Country.SINGAPORE: "SG",
    Country.SOUTHAFRICA: "ZA",
    Country.SOUTHKOREA: "KR",
    Country.SPAIN: "ES",
    Country.SWEDEN: "SE",
    Country.SWITZERLAND: "CH",
    Country.TAIWAN: "TW",
    Country.THAILAND: "TH",
    Country.TURKEY: "TR",
    Country.UKRAINE: "UA",
    Country.UNITEDARABEMIRATES: "AE",
    Country.UK: "GB",
    Country.USA: "US",
    Country.URUGUAY: "UY",
    Country.VENEZUELA: "VE",
    Country.VIETNAM: "VN",
}
subdomains = {Country.MALAYSIA: "malaysia", Country.UK: "uk", Country.USA: "www"}
countries = {code: country for country, code in country_codes.items()} | {
    "BD": "Bangladesh",
    "BG": "Bulgaria",
    "CY": "Cyprus",
    "EE": "Estonia",
    "HR": "Croatia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "MT": "Malta",
    "SK": "Slovakia",
    "SI": "Slovenia",
}

languages = {
    "AR": "es",
    "AT": "de",
    "BE": "nl",
    "BR": "pt",
    "CH": "de",
    "CL": "es",
    "CN": "zh",
    "CO": "es",
    "CR": "es",
    "CZ": "cs",
    "DE": "de",
    "DK": "da",
    "EC": "es",
    "ES": "es",
    "FI": "fi",
    "FR": "fr",
    "GR": "el",
    "HU": "hu",
    "ID": "id",
    "IL": "he",
    "IT": "it",
    "JP": "ja",
    "KR": "ko",
    "LU": "fr",
    "MA": "fr",
    "MX": "es",
    "NL": "nl",
    "NO": "nb",
    "PA": "es",
    "PE": "es",
    "PL": "pl",
    "PT": "pt",
    "RO": "ro",
    "SE": "sv",
    "TH": "th",
    "TR": "tr",
    "TW": "zh",
    "UA": "uk",
    "UY": "es",
    "VE": "es",
    "VN": "vi",
}
