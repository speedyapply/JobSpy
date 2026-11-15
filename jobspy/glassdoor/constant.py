from jobspy.model import CompensationInterval, Country, JobType

jobs_per_page = 100
details_per_request = 25

headers = {
    "gd-csrf-token": "Ft6oHEWlRZrxDww95Cpazw:0pGUrkb2y3TyOpAIqF2vbPmUXoXVkD3oEGDVkvfeCerceQ5-n8mBg3BovySUIjmCPHCaW0H2nQVdqzbtsYqf4Q:wcqRqeegRUa9MVLJGyujVXB7vWFPjdaS1CtrrzJq-ok",
}

location_types = {"C": "CITY", "S": "STATE", "N": "COUNTRY"}

job_type_codes = {
    JobType.FULL_TIME: "fulltime",
    JobType.PART_TIME: "parttime",
    JobType.CONTRACT: "contract",
    JobType.INTERNSHIP: "internship",
    JobType.TEMPORARY: "temporary",
}

pay_intervals = {
    "ANNUAL": CompensationInterval.YEARLY,
    "MONTHLY": CompensationInterval.MONTHLY,
    "HOURLY": CompensationInterval.HOURLY,
}

search_query = """
query JobSearchResultsQuery(
    $keyword: String,
    $locationId: Int,
    $locationType: LocationTypeEnum,
    $numJobsToShow: Int!,
    $pageCursor: String,
    $pageNumber: Int,
    $filterParams: [FilterParams],
    $parameterUrlInput: String
) {
    jobListings(
        contextHolder: {
            searchParams: {
                keyword: $keyword,
                locationId: $locationId,
                locationType: $locationType,
                numPerPage: $numJobsToShow,
                pageCursor: $pageCursor,
                pageNumber: $pageNumber,
                filterParams: $filterParams,
                parameterUrlInput: $parameterUrlInput,
                searchType: SR
            }
        }
    ) {
        jobListings {
            jobview {
                header {
                    adOrderSponsorshipLevel
                    ageInDays
                    employer {
                        id
                    }
                    employerNameFromSearch
                    jobTypeKeys
                    locationName
                    locationType
                    payCurrency
                    payPeriod
                    payPeriodAdjustedPay {
                        p10
                        p90
                    }
                    rating
                    remoteWorkTypes
                }
                job {
                    jobTitleText
                    listingId
                }
                map {
                    country
                }
                overview {
                    headquarters
                    overview {
                        description
                    }
                    primaryIndustry {
                        industryName
                    }
                    revenue
                    size
                    squareLogoUrl
                    website
                }
            }
        }
        paginationCursors {
            cursor
            pageNumber
        }
    }
}
"""

details_alias = """
    j%s: jobView(listingId: %s, contextHolder: {queryString: "q", pageTypeEnum: SERP}) {
        job {
            description
        }
    }
"""

domains = {
    Country.ARGENTINA: "www.glassdoor.com.ar",
    Country.AUSTRALIA: "www.glassdoor.com.au",
    Country.AUSTRIA: "www.glassdoor.at",
    Country.BELGIUM: "fr.glassdoor.be",
    Country.BRAZIL: "www.glassdoor.com.br",
    Country.CANADA: "www.glassdoor.ca",
    Country.FRANCE: "www.glassdoor.fr",
    Country.GERMANY: "www.glassdoor.de",
    Country.HONGKONG: "www.glassdoor.com.hk",
    Country.INDIA: "www.glassdoor.co.in",
    Country.IRELAND: "www.glassdoor.ie",
    Country.ITALY: "www.glassdoor.it",
    Country.MALAYSIA: "www.glassdoor.com",
    Country.MEXICO: "www.glassdoor.com.mx",
    Country.NETHERLANDS: "www.glassdoor.nl",
    Country.NEWZEALAND: "www.glassdoor.co.nz",
    Country.SINGAPORE: "www.glassdoor.sg",
    Country.SPAIN: "www.glassdoor.es",
    Country.SWITZERLAND: "de.glassdoor.ch",
    Country.UK: "www.glassdoor.co.uk",
    Country.USA: "www.glassdoor.com",
    Country.VIETNAM: "www.glassdoor.com",
}
# countries searched on the US site: their name and ISO code scope the search
shared_domain = {
    Country.MALAYSIA: ("Malaysia", "MY"),
    Country.VIETNAM: ("Vietnam", "VN"),
}
