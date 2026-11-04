from jobspy.model import JobType

jobs_per_page = 100
max_posted_within_days = 90

# `location` text (lowercased, accents and punctuation dropped) -> the feed's city slug
city_slugs = {
    "ho chi minh": "hcm",
    "ho chi minh city": "hcm",
    "hcm": "hcm",
    "hcmc": "hcm",
    "saigon": "hcm",
    "sai gon": "hcm",
    "tp hcm": "hcm",
    "hanoi": "hanoi",
    "ha noi": "hanoi",
    "da nang": "da-nang",
    "danang": "da-nang",
    "hai phong": "hai-phong",
    "haiphong": "hai-phong",
    "binh duong": "binh-duong",
    "bac ninh": "bac-ninh",
    "remote": "remote",
}

city_names = {
    "hcm": "Ho Chi Minh City",
    "hanoi": "Hanoi",
    "da-nang": "Da Nang",
    "hai-phong": "Hai Phong",
    "binh-duong": "Binh Duong",
    "bac-ninh": "Bac Ninh",
}

remote_slugs = {"remote-vn", "remote-global"}

job_types = {
    "full-time": JobType.FULL_TIME,
    "permanent": JobType.FULL_TIME,
    "part-time": JobType.PART_TIME,
    "internship": JobType.INTERNSHIP,
    "full-time-internship": JobType.INTERNSHIP,
    "fixed-term-contract": JobType.CONTRACT,
    "contractor": JobType.CONTRACT,
    "freelance": JobType.CONTRACT,
}
