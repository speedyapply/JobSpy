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
country_aliases = {
    "us": "usa",
    "ksa": "saudi-arabia",
    "saudi": "saudi-arabia",
    "saudi arabia": "saudi-arabia",
    "السعودية": "saudi-arabia",
    "المملكة العربية السعودية": "saudi-arabia",
    "uae": "uae",
    "united arab emirates": "uae",
    "الإمارات": "uae",
    "الامارات": "uae",
    "oman": "oman",
    "sultanate of oman": "oman",
    "عمان": "oman",
    "سلطنة عمان": "oman",
    "qatar": "qatar",
    "قطر": "qatar",
    "kuwait": "kuwait",
    "الكويت": "kuwait",
    "bahrain": "bahrain",
    "البحرين": "bahrain",
    "egypt": "egypt",
    "مصر": "egypt",
    "jordan": "jordan",
    "الأردن": "jordan",
    "الاردن": "jordan",
    "iraq": "iraq",
    "العراق": "iraq",
    "morocco": "morocco",
    "المغرب": "morocco",
    "turkey": "turkiye",
    "تركيا": "turkiye",
}

city_aliases = {
    "الرياض": "riyadh",
    "جدة": "jeddah",
    "الدمام": "dammam",
    "دبي": "dubai",
    "أبوظبي": "abu-dhabi",
    "ابوظبي": "abu-dhabi",
    "الشارقة": "sharjah",
    "مسقط": "muscat",
    "صلالة": "salalah",
    "الدوحة": "doha",
    "الكويت": "kuwait-city",
    "المنامة": "manama",
    "القاهرة": "cairo",
    "الإسكندرية": "alexandria",
    "عمان": "amman",
    "عمّان": "amman",
    "بغداد": "baghdad",
    "الدار البيضاء": "casablanca",
}
