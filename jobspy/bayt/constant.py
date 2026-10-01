from jobspy.model import JobType

jobs_per_page = 30
all_countries = "international"

# hours_old up to -> jb_last_modification_date_interval
date_intervals = ((24, 3), (24 * 7, 2), (24 * 30, 1))

job_type_codes = {
    JobType.FULL_TIME: 1,
    JobType.INTERNSHIP: 2,
    JobType.CONTRACT: 3,
}

# the country slug is the hyphenated name; Bayt redirects other names it knows
# (united-arab-emirates -> uae, turkey -> turkiye) but not these
country_aliases = {"us": "usa", "ksa": "saudi-arabia"}

schema_job_types = {
    "FULL_TIME": JobType.FULL_TIME,
    "PART_TIME": JobType.PART_TIME,
    "CONTRACTOR": JobType.CONTRACT,
    "TEMPORARY": JobType.TEMPORARY,
    "INTERN": JobType.INTERNSHIP,
}
