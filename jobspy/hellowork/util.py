from jobspy.model import RemoteType, JobType


def convert_old_hours_to_api(hours: int) -> str:
    """
    Converts hours to string to respect HelloWork search query API
    in order to filter job offers before these hours.
    :param hours: Hours to filter job offers
    :return: Character representation of hours
    """
    if hours <= 24:
        return "h"
    elif hours <= 72:
        return "d"
    elif hours <= 148:
        return "h"
    else:
        return "m"


def convert_years_of_experience_to_api(years: int) -> str:
    if years < 1:
        return "0-1y"
    elif years <= 3:
        return "2-3y"
    elif years <= 5:
        return "4-5y"
    elif years <= 10:
        return "5-10y"
    else:
        return "gt10"


def convert_api_to_remote_type(remote_api: str) -> RemoteType:
    if 'occasionnel' in remote_api:
        return RemoteType.OCCASIONAL
    elif 'partiel' in remote_api:
        return RemoteType.PARTIAL
    elif 'complet' in remote_api:
        return RemoteType.FULL


def convert_remote_to_api(remote_type: RemoteType) -> str:
    if remote_type == RemoteType.FULL:
        return "Complet"
    elif remote_type == RemoteType.PARTIAL:
        return "Partial"
    elif remote_type == RemoteType.OCCASIONAL:
        return "Occasionnel"
    else:
        return "Pas_teletravail"


def convert_type_job_to_api(job_type: JobType) -> str:
    internal_mapping = {
        JobType.PERMANENT: "CDI",
        JobType.CONTRACT: "CDD",
        JobType.TEMPORARY: "Travail_temp",
        JobType.INTERNSHIP: "Stage",
        JobType.FREELANCE: "Freelance",
        JobType.APPRENTICESHIP: "Alternance"
    }
    return internal_mapping.get(job_type)


def convert_work_time_to_api(job_type: JobType) -> str:
    internal_mapping = {
        JobType.FULL_TIME: "ft",
        JobType.PART_TIME: "pt"
    }

    return internal_mapping.get(job_type)


def convert_api_to_job_type(job_type: str) -> JobType:
    internal_mapping = {
        "Temps complet": JobType.FULL_TIME,
        "Temps partiel": JobType.PART_TIME,
        "CDI": JobType.PERMANENT,
        "CDD": JobType.CONTRACT,
        "Intérim": JobType.TEMPORARY,
        "Stage": JobType.INTERNSHIP,
        "Freelance": JobType.FREELANCE,
        "Indépendant": JobType.FREELANCE,
        "Alternance": JobType.APPRENTICESHIP
    }

    return internal_mapping.get(job_type)