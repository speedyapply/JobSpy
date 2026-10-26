from typing import Annotated

from pydantic import AliasPath, BaseModel, BeforeValidator, Field, StringConstraints


def validate_listing_id(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdecimal():
        return int(value.strip())
    raise ValueError("invalid listing identity")


ListingId = Annotated[int, BeforeValidator(validate_listing_id), Field(gt=0)]


class Place(BaseModel):
    locationId: int
    locationType: str


class AdjustedPay(BaseModel):
    p10: float
    p90: float


class Header(BaseModel):
    locationName: str | None
    locationType: str | None
    payCurrency: str | None
    payPeriod: str | None
    payPeriodAdjustedPay: AdjustedPay | None
    adOrderSponsorshipLevel: str
    ageInDays: int
    id: int | None = Field(validation_alias=AliasPath("employer", "id"))
    employerNameFromSearch: str | None
    jobTypeKeys: list[str] | None = None
    rating: float | None = None
    remoteWorkTypes: list[str] | None = None


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
    jobTitleText: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1)
    ] = Field(validation_alias=AliasPath("job", "jobTitleText"))
    listingId: ListingId = Field(validation_alias=AliasPath("job", "listingId"))
    country: str | None = Field(validation_alias=AliasPath("map", "country"))
    overview: Overview


class Cursor(BaseModel):
    cursor: str | None
    pageNumber: int | None


class Listing(BaseModel):
    jobview: dict[str, object]
    listingId: ListingId = Field(
        validation_alias=AliasPath("jobview", "job", "listingId")
    )


class JobListings(BaseModel):
    jobListings: list[object] | None = None
    paginationCursors: list[Cursor] | None = None
