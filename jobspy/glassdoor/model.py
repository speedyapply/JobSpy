import logging

from pydantic import AliasPath, BaseModel, Field, ValidationError, field_validator


class Place(BaseModel):
    locationId: int
    locationType: str


class AdjustedPay(BaseModel):
    p10: float | None = Field(default=None, strict=True, ge=0, allow_inf_nan=False)
    p90: float | None = Field(default=None, strict=True, ge=0, allow_inf_nan=False)


class Header(BaseModel):
    locationName: str | None = None
    locationType: str | None = None
    payCurrency: str | None = None
    payPeriod: str | None = None
    payPeriodAdjustedPay: AdjustedPay | None = None
    adOrderSponsorshipLevel: str
    ageInDays: int
    id: int | None = Field(default=None, validation_alias=AliasPath("employer", "id"))
    employerNameFromSearch: str | None = None
    jobTypeKeys: list[str] | None = None
    rating: float | None = None
    remoteWorkTypes: list[str] | None = None

    @field_validator("payPeriodAdjustedPay", mode="before")
    @classmethod
    def _optional_pay(cls, value: object) -> AdjustedPay | None:
        if value is None:
            return None
        try:
            pay = AdjustedPay.model_validate(value)
            if pay.p10 is not None and pay.p90 is not None and pay.p10 > pay.p90:
                raise ValueError("inverted percentiles")
            return pay
        except (ValidationError, ValueError):
            logging.getLogger("jobspy.glassdoor").warning(
                "invalid percentile pay metadata"
            )
            return None

    @field_validator("payCurrency", "payPeriod", mode="before")
    @classmethod
    def _optional_pay_text(cls, value: object) -> str | None:
        if value is None or isinstance(value, str):
            return value
        logging.getLogger("jobspy.glassdoor").warning("invalid salary text metadata")
        return None


class Overview(BaseModel):
    headquarters: str | None = None
    description: str | None = Field(
        default=None, validation_alias=AliasPath("overview", "description")
    )
    industryName: str | None = Field(
        default=None, validation_alias=AliasPath("primaryIndustry", "industryName")
    )
    revenue: str | None = None
    size: str | None = None
    squareLogoUrl: str | None = None
    website: str | None = None


class JobView(BaseModel):
    header: Header
    jobTitleText: str = Field(validation_alias=AliasPath("job", "jobTitleText"))
    listingId: int = Field(validation_alias=AliasPath("job", "listingId"))
    country: str | None = Field(
        default=None, validation_alias=AliasPath("map", "country")
    )
    overview: Overview | None = None


class Cursor(BaseModel):
    cursor: str | None
    pageNumber: int | None


class Listing(BaseModel):
    jobview: dict[str, object]
    listingId: int | None = Field(
        validation_alias=AliasPath("jobview", "job", "listingId")
    )


class JobListings(BaseModel):
    jobListings: list[object] | None = None
    paginationCursors: list[Cursor] | None = None
