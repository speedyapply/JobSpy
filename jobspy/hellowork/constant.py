from jobspy.model import CompensationInterval, JobType

jobs_per_page = 30
km_per_mile = 1.609344
paris_time = "Europe/Paris"
related_list = "LO-Moteur-Approchant"
description_headings = ("Les missions du poste", "Détail du poste")

date_windows = ((24, "h"), (72, "d"), (168, "w"), (720, "m"))

job_type_params = {
    JobType.FULL_TIME: {"ctt": "ft"},
    JobType.PART_TIME: {"ctt": "pt"},
    JobType.INTERNSHIP: {"c": ["Stage", "Alternance"]},
    JobType.TEMPORARY: {"c": ["CDD", "Travail_temp"]},
    JobType.CONTRACT: {"c": ["Independant", "Franchise", "Freelance"]},
}

job_type_labels = {
    "CDD": JobType.TEMPORARY,
    "Intérim": JobType.TEMPORARY,
    "Stage": JobType.INTERNSHIP,
    "Stage de lycée": JobType.INTERNSHIP,
    "Alternance": JobType.INTERNSHIP,
    "Indépendant": JobType.CONTRACT,
    "Franchise": JobType.CONTRACT,
    "Freelance": JobType.CONTRACT,
    "temps plein": JobType.FULL_TIME,
    "temps partiel": JobType.PART_TIME,
}

pay_intervals = {
    "an": CompensationInterval.YEARLY,
    "mois": CompensationInterval.MONTHLY,
    "jour": CompensationInterval.DAILY,
    "heure": CompensationInterval.HOURLY,
}
