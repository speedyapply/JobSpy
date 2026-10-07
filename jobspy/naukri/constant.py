from datetime import timedelta, timezone

from jobspy.model import JobType

jobs_per_page = 20

headers = {"appid": "109", "systemid": "Naukri"}
job_page_headers = {"appid": "121", "systemid": "Naukri"}

search_params = {
    "noOfResults": jobs_per_page,
    "urlType": "search_by_keyword",
    "searchType": "adv",
}
internship_params = {"qproductJobSource": 2, "qinternshipFlag": "true"}

job_type_labels = {
    "Full Time": JobType.FULL_TIME,
    "Part Time": JobType.PART_TIME,
    "Temporary/Contractual": JobType.CONTRACT,
}

india_time = timezone(timedelta(hours=5, minutes=30))

nkparam_public_key = (
    "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBALrlQ+djR0RjJwBF1xuisHmdFv334MImK6LgzJhmLhN7"
    "B5yuEyaKoasgXQk3+OQglsOaBxEJ0j5PcTL3nbOvt80CAwEAAQ=="
)
