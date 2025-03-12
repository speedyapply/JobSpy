from jobspy.model import CompensationInterval, JobType, Compensation
from jobspy.util import get_enum_from_job_type


def get_job_type(attributes: list) -> list[JobType]:
    """
    Parses the attributes to get list of job types
    :param attributes:
    :return: list of JobType
    """
    job_types: list[JobType] = []
    for attribute in attributes:
        job_type_str = attribute["label"].replace("-", "").replace(" ", "").lower()
        job_type = get_enum_from_job_type(job_type_str)
        if job_type:
            job_types.append(job_type)
    return job_types


def get_compensation(compensation: dict) -> Compensation | None:
    """
    Parses the job to get compensation
    :param compensation:
    :return: compensation object
    """
    if not compensation["baseSalary"] and not compensation["estimated"]:
        return None
    comp = (
        compensation["baseSalary"]
        if compensation["baseSalary"]
        else compensation["estimated"]["baseSalary"]
    )
    if not comp:
        return None
    interval = get_compensation_interval(comp["unitOfWork"])
    if not interval:
        return None
    min_range = comp["range"].get("min")
    max_range = comp["range"].get("max")
    return Compensation(
        interval=interval,
        min_amount=int(min_range) if min_range is not None else None,
        max_amount=int(max_range) if max_range is not None else None,
        currency=(
            compensation["estimated"]["currencyCode"]
            if compensation["estimated"]
            else compensation["currencyCode"]
        ),
    )


def is_job_remote(job: dict, description: str) -> bool:
    """
    Searches the description, location, and attributes to check if job is remote
    """
    remote_keywords = ["remote", "work from home", "wfh"]
    is_remote_in_attributes = any(
        any(keyword in attr["label"].lower() for keyword in remote_keywords)
        for attr in job["attributes"]
    )
    is_remote_in_description = any(
        keyword in description.lower() for keyword in remote_keywords
    )
    is_remote_in_location = any(
        keyword in job["location"]["formatted"]["long"].lower()
        for keyword in remote_keywords
    )
    return is_remote_in_attributes or is_remote_in_description or is_remote_in_location


def get_compensation_interval(interval: str) -> CompensationInterval:
    interval_mapping = {
        "DAY": "DAILY",
        "YEAR": "YEARLY",
        "HOUR": "HOURLY",
        "WEEK": "WEEKLY",
        "MONTH": "MONTHLY",
    }
    mapped_interval = interval_mapping.get(interval.upper(), None)
    if mapped_interval and mapped_interval in CompensationInterval.__members__:
        return CompensationInterval[mapped_interval]
    else:
        raise ValueError(f"Unsupported interval: {interval}")
