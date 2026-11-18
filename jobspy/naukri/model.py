from pydantic import AliasPath, BaseModel, Field


class Placeholder(BaseModel):
    type: str | None
    label: str


class Salary(BaseModel):
    hideSalary: bool | None
    minimumSalary: int | None
    maximumSalary: int | None
    currency: str | None


class Row(BaseModel):
    createdDate: int


class Shared(BaseModel):
    jobType: str | None = None
    employmentType: str | None = ""
    vacancy: int | None = None
    applyRedirectUrl: str | None = None


class Job(Row, Shared):
    jobId: str
    companyApplyJob: bool | None
    title: str
    companyName: str | None
    staticUrl: str | None
    jdURL: str
    logoPathV3: str | None
    placeholders: list[Placeholder]
    salaryDetail: Salary
    tagsAndSkills: str | None = None
    experienceText: str | None = None
    AggregateRating: float | None = Field(
        default=None, validation_alias=AliasPath("ambitionBoxData", "AggregateRating")
    )
    ReviewsCount: int | None = Field(
        default=None, validation_alias=AliasPath("ambitionBoxData", "ReviewsCount")
    )


class JobDetails(Shared):
    createdDate: str
    description: str | None
    industry: str | None
    functionalArea: str | None
    details: str | None = Field(validation_alias=AliasPath("companyDetail", "details"))
    address: str | None = Field(validation_alias=AliasPath("companyDetail", "address"))


class JobSearch(BaseModel):
    noOfJobs: int
    jobDetails: list[dict[str, object]] | None = None


class Place(BaseModel):
    name: list[str]
    type: str


class Places(BaseModel):
    title: list[Place] = Field(validation_alias=AliasPath("resultList", "title"))
