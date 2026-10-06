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
                        label
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

countries = {country.indeed_domain_value[1]: country for country in Country}

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
