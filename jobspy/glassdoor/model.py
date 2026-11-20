from pydantic import AliasPath, BaseModel, Field


class Place(BaseModel):
    locationId: int
    locationType: str
    label: str | None = None
    stateName: str | None = None


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
    salarySource: str | None = None


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
    country: str | None = Field(validation_alias=AliasPath("map", "country"))
    overview: Overview


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
