from jobspy.model import CompensationInterval, JobType

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
