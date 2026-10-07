from jobspy.model import JobType

jobs_per_page = 30
all_countries = "international"

# hours_old up to -> jb_last_modification_date_interval
date_intervals = ((24, 3), (24 * 7, 2), (24 * 30, 1))

job_type_codes = {
    JobType.FULL_TIME: 1,
    JobType.INTERNSHIP: 2,
    JobType.CONTRACT: 3,
    JobType.TEMPORARY: 4,
    JobType.PART_TIME: 5,
}

job_type_labels = {
    "Full time": JobType.FULL_TIME,
    "Part time": JobType.PART_TIME,
    "Contractor": JobType.CONTRACT,
    "Temporary": JobType.TEMPORARY,
    "Internship": JobType.INTERNSHIP,
}

# the country slug is the hyphenated name; Bayt redirects other names it knows
# (united-arab-emirates -> uae, turkey -> turkiye) but not these
country_aliases = {"us": "usa", "ksa": "saudi-arabia"}
