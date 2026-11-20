from datetime import datetime
from typing import Annotated

from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    BeforeValidator,
    Field,
    field_validator,
)

from jobspy.ziprecruiter.constant import (
    employment_type_names,
    location_type_names,
    pay_currency_names,
    pay_interval_names,
)


def _named(prefix: str, names: tuple[str, ...]) -> BeforeValidator:
    """The second page layout's number for an enum, as the first layout's name."""
    numbered = {number: prefix + name for number, name in enumerate(names)}
    return BeforeValidator(lambda value: numbered.get(value, value))


class EmploymentType(BaseModel):
    name: Annotated[str, _named("EMPLOYMENT_TYPE_NAME_", employment_type_names)]


class LocationType(BaseModel):
    name: Annotated[str, _named("LOCATION_TYPE_NAME_", location_type_names)]


class ApplyButtonConfig(BaseModel):
    externalApplyUrl: str | None = None


class Pay(BaseModel):
    visible: bool | None = Field(
        default=None, validation_alias=AliasPath("metadata", "visible")
    )
    interval: Annotated[str | None, _named("PAY_INTERVAL_", pay_interval_names)] = None
    min: float | None = None
    max: float | None = None
    currency: Annotated[str | None, _named("PAY_CURRENCY_", pay_currency_names)] = None


class Job(BaseModel):
    listingKey: str | None
    title: str
    postedAtUtc: datetime = Field(
        validation_alias=AliasChoices(
            AliasPath("status", "postedAtUtc", "seconds"),
            AliasPath("status", "postedAtUtc"),
        )
    )
    employmentTypes: list[EmploymentType]
    countryCode: str | None = Field(
        default=None, validation_alias=AliasPath("location", "countryCode")
    )
    city: str | None = Field(
        default=None, validation_alias=AliasPath("location", "city")
    )
    stateCode: str | None = Field(
        default=None, validation_alias=AliasPath("location", "stateCode")
    )
    applyButtonConfig: ApplyButtonConfig
    name: str | None = Field(validation_alias=AliasPath("company", "name"))
    companyUrl: str | None
    logoUrl: str | None = Field(
        default=None, validation_alias=AliasPath("companyLogo", "logoUrl")
    )
    rawCanonicalZipJobPageUrl: str
    jobRedirectPageUrl: str | None = None
    locationTypes: list[LocationType]
    pay: Pay


class JobSearch(BaseModel):
    """`jobKeysMap` (a map by listing key) in the first page layout, `jobCards` (a list) in the second."""

    jobs: list[dict[str, object]] = Field(
        validation_alias=AliasChoices("jobKeysMap", "jobCards")
    )
    jobCount: int

    @field_validator("jobs", mode="before")
    @classmethod
    def _cards(cls, value: object) -> object:
        return list(value.values()) if isinstance(value, dict) else value


class JobDetails(BaseModel):
    htmlFullDescription: str | None
    about: str | None = Field(
        default=None, validation_alias=AliasPath("companyWidget", "about")
    )
    canonicalIndustries: list[str] | None = Field(
        default=None, validation_alias=AliasPath("companyWidget", "canonicalIndustries")
    )
    canonicalWebsite: str | None = Field(
        default=None, validation_alias=AliasPath("companyWidget", "canonicalWebsite")
    )
    companySizeDisplay: str | None = Field(
        default=None, validation_alias=AliasPath("companyWidget", "companySizeDisplay")
    )
    hqLocation: str | None = Field(
        default=None, validation_alias=AliasPath("companyWidget", "hqLocation")
    )
    description: str | None = Field(
        default=None, validation_alias=AliasPath("breakroomCompany", "description")
    )
    rating: float | None = Field(
        default=None, validation_alias=AliasPath("breakroomCompany", "rating")
    )
