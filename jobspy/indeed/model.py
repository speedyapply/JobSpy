from pydantic import AliasPath, BaseModel, Field


class Range(BaseModel):
    min: float | None = None
    max: float | None = None
    value: float | None = None


class Salary(BaseModel):
    unitOfWork: str | None
    range: Range


class Estimate(BaseModel):
    baseSalary: Salary | None
    currencyCode: str | None


class IndeedCompensation(Estimate):
    estimated: Estimate | None


class Attribute(BaseModel):
    key: str | None


class IndeedLocation(BaseModel):
    countryCode: str | None = None
    admin1Code: str | None = None
    city: str | None = None


class Employer(BaseModel):
    name: str | None = None
    relativeCompanyPageUrl: str | None = None
    value: float | None = Field(
        default=None,
        validation_alias=AliasPath("ugcStats", "ratings", "overallRating", "value"),
    )
    count: int | None = Field(
        default=None,
        validation_alias=AliasPath("ugcStats", "ratings", "overallRating", "count"),
    )
    addresses: list[str | None] | None = Field(
        default=None,
        validation_alias=AliasPath("dossier", "employerDetails", "addresses"),
    )
    industry: str | None = Field(
        default=None,
        validation_alias=AliasPath("dossier", "employerDetails", "industry"),
    )
    employeesLocalizedLabel: str | None = Field(
        default=None,
        validation_alias=AliasPath(
            "dossier", "employerDetails", "employeesLocalizedLabel"
        ),
    )
    revenueLocalizedLabel: str | None = Field(
        default=None,
        validation_alias=AliasPath(
            "dossier", "employerDetails", "revenueLocalizedLabel"
        ),
    )
    briefDescription: str | None = Field(
        default=None,
        validation_alias=AliasPath("dossier", "employerDetails", "briefDescription"),
    )
    squareLogoUrl: str | None = Field(
        default=None, validation_alias=AliasPath("dossier", "images", "squareLogoUrl")
    )
    corporateWebsite: str | None = Field(
        default=None, validation_alias=AliasPath("dossier", "links", "corporateWebsite")
    )


class Job(BaseModel):
    key: str | None
    title: str
    sourceEmployerName: str | None
    dateOnIndeed: int | None = None
    html: str | None = Field(validation_alias=AliasPath("description", "html"))
    employer: Employer | None
    location: IndeedLocation
    viewJobUrl: str | None = Field(validation_alias=AliasPath("recruit", "viewJobUrl"))
    attributes: list[Attribute]
    compensation: IndeedCompensation


class Result(BaseModel):
    job: dict[str, object] | None


class JobSearch(BaseModel):
    nextCursor: str | None = Field(validation_alias=AliasPath("pageInfo", "nextCursor"))
    results: list[Result]
