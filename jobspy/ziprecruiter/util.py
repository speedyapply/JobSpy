from jobspy.model import JobType


def add_params(scraper_input) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "search": scraper_input.search_term,
        "location": scraper_input.location,
    }
    if scraper_input.hours_old:
        params["days"] = max(scraper_input.hours_old // 24, 1)

    job_type_map = {JobType.FULL_TIME: "full_time", JobType.PART_TIME: "part_time"}
    if scraper_input.job_type:
        job_type = scraper_input.job_type
        params["employment_type"] = job_type_map.get(job_type, job_type.value[0])

    if scraper_input.easy_apply:
        params["zipapply"] = 1
    if scraper_input.is_remote:
        params["remote"] = 1
    if scraper_input.distance:
        params["radius"] = scraper_input.distance

    return {k: v for k, v in params.items() if v is not None}


def get_job_type_enum(job_type_str: str) -> list[JobType] | None:
    for job_type in JobType:
        if job_type_str in job_type.value:
            return [job_type]
    return None