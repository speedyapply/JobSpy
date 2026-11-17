from pydantic import AliasPath, AwareDatetime, BaseModel, Field


class Market(BaseModel):
    site_key: str
    zone: str
    domain: str
    currency: str
    currency_symbol: str


class Arrangement(BaseModel):
    id: str


class Job(BaseModel):
    id: str = Field(pattern=r"^\d+$")
    title: str
    companyName: str | None = None
    advertiser: str | None = Field(
        validation_alias=AliasPath("advertiser", "description")
    )
    listingDate: AwareDatetime
    location: str | None = Field(
        default=None, validation_alias=AliasPath("locations", 0, "label")
    )
    salaryLabel: str | None
    currencyLabel: str | None = None
    workTypes: list[str]
    arrangements: list[Arrangement] = Field(
        validation_alias=AliasPath("workArrangements", "data")
    )
    classification: str | None = Field(
        default=None,
        validation_alias=AliasPath(
            "classifications", 0, "classification", "description"
        ),
    )
    companyUrl: str | None = Field(
        default=None, validation_alias=AliasPath("employer", "companyUrl")
    )
    serpLogoUrl: str | None = Field(
        default=None, validation_alias=AliasPath("branding", "serpLogoUrl")
    )
    jobAdType: str | None = Field(
        default=None, validation_alias=AliasPath("solMetadata", "jobAdType")
    )


class JobSearch(BaseModel):
    data: list[dict[str, object]]
    totalCount: int
    location: dict[str, object] | None = None


class JobDetails(BaseModel):
    content: str | None = Field(
        default=None, validation_alias=AliasPath("job", "content")
    )
    description: str | None = Field(
        default=None,
        validation_alias=AliasPath("companyProfile", "overview", "description", "full"),
    )
    industry: str | None = Field(
        default=None,
        validation_alias=AliasPath("companyProfile", "overview", "industry"),
    )
    primaryLocation: str | None = Field(
        default=None,
        validation_alias=AliasPath("companyProfile", "overview", "primaryLocation"),
    )
    size: str | None = Field(
        default=None,
        validation_alias=AliasPath("companyProfile", "overview", "size", "description"),
    )
    website: str | None = Field(
        default=None,
        validation_alias=AliasPath("companyProfile", "overview", "website", "url"),
    )
    rating: float | None = Field(
        default=None,
        validation_alias=AliasPath(
            "companyProfile", "reviewsSummary", "overallRating", "value"
        ),
    )
    reviews: int | None = Field(
        default=None,
        validation_alias=AliasPath(
            "companyProfile",
            "reviewsSummary",
            "overallRating",
            "numberOfReviews",
            "value",
        ),
    )
