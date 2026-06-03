from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_ACTIVE_CONTRACT_DATATYPE_NAMES = [
    "Договор о практической подготовке обучающихся",
]


class OrganizationAdd(BaseModel):
    name_long: str | None = None
    name_short: str | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    is_active: bool | None = None
    is_university_department: bool | None = None
    notes: str | None = None
    settlement_id: int | None = None
    data_is_filled: bool | None = None
    website: str | None = None
    logotype_id: int | None = None
    meta_creator_name: str | None = None
    is_sole_proprietor: bool | None = None


class Organization(OrganizationAdd):
    id: int
    model_config = ConfigDict(from_attributes=True)


SortBy = Literal[
    "organization_name",
    "contract_number",
    "signing_date",
    "settlement_name",
]
SortDir = Literal["asc", "desc"]


class ActiveOrganizationsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by organization name",
    )
    contract_numbers: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by contract number",
    )
    settlement_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by settlement name",
    )
    only_active_organizations: bool = Field(default=True)
    only_actual_contracts: bool = Field(default=True)
    only_university_departments: bool = Field(default=False)
    contract_datatype_names: list[str] | None = Field(
        default_factory=lambda: DEFAULT_ACTIVE_CONTRACT_DATATYPE_NAMES.copy(),
        description="Multi-select exact match by contract datatype name",
    )

    sort_by: SortBy = Field(default="organization_name")
    sort_dir: SortDir = Field(default="asc")

    limit: int = Field(default=200, gt=0, le=1000)
    offset: int = Field(default=0, ge=0)


class ActiveOrganizationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    contract_number: str | None = None
    signing_date: date | None = None
    logotype_id: int | None = None

    organization_name: str | None = None
    settlement_name: str | None = None

    study_fields: str | None = None
    phones: str | None = None
    digitals: str | None = None


class ActiveOrganizationsFilterOption(BaseModel):
    value: str
    label: str


class ActiveOrganizationsFilterOptions(BaseModel):
    organizations: list[ActiveOrganizationsFilterOption]
    contract_numbers: list[ActiveOrganizationsFilterOption]
    settlements: list[ActiveOrganizationsFilterOption]


class ActiveOrganizationsTableRequest(BaseModel):
    filters: ActiveOrganizationsFilters = Field(default_factory=ActiveOrganizationsFilters)
    custom_sort_requested: bool = False


StudyDirectionsSortBy = Literal[
    "faculty_name",
    "department_name",
    "study_direction_name",
    "study_direction_code",
    "organization_name",
]


class StudyDirectionsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faculty_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by faculty label",
    )
    department_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by department label",
    )
    study_direction_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by study direction name",
    )
    study_direction_codes: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by study direction code",
    )
    organization_names: list[str] | None = Field(
        default=None,
        description="Multi-select exact match by organization name",
    )

    sort_by: StudyDirectionsSortBy = Field(default="organization_name")
    sort_dir: SortDir = Field(default="asc")

    limit: int = Field(default=200, gt=0, le=1000)
    offset: int = Field(default=0, ge=0)


class StudyDirectionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    logotype_id: int | None = None
    faculty_name: str | None = None
    department_name: str | None = None
    study_direction_name: str | None = None
    study_direction_code: str | None = None
    organization_name: str | None = None
    phones: str | None = None
    digitals: str | None = None


class StudyDirectionsFilterOptions(BaseModel):
    faculties: list[ActiveOrganizationsFilterOption]
    departments: list[ActiveOrganizationsFilterOption]
    study_direction_names: list[ActiveOrganizationsFilterOption]
    study_direction_codes: list[ActiveOrganizationsFilterOption]
    organizations: list[ActiveOrganizationsFilterOption]


class StudyDirectionsTableRequest(BaseModel):
    filters: StudyDirectionsFilters = Field(default_factory=StudyDirectionsFilters)
    custom_sort_requested: bool = False


GroupDistributionSortBy = Literal[
    "department_name",
    "study_direction_code",
    "study_direction_name",
    "study_profile_name",
    "group_name",
    "course",
    "distributed_quantity",
    "organization_name",
    "order_name",
    "signing_date",
    "practice_name",
    "practice_date_begin",
    "practice_date_end",
    "practice_chief_name",
]

DistributionStatsOrganizationStatus = Literal["all", "active", "inactive"]
DistributionStatsActualContractStatus = Literal[
    "all",
    "with_actual_contract",
    "without_actual_contract",
]


class GroupDistributionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semester_id: int | None = Field(
        default=None,
        description="Single-select semester id",
    )

    sort_by: GroupDistributionSortBy = Field(default="department_name")
    sort_dir: SortDir = Field(default="asc")

    limit: int = Field(default=200, gt=0, le=1000)
    offset: int = Field(default=0, ge=0)


class GroupDistributionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int | None = None
    semester_id: int | None = None
    department_name: str | None = None
    study_direction_code: str | None = None
    study_direction_name: str | None = None
    study_profile_name: str | None = None
    group_name: str | None = None
    course: int | None = None
    distributed_quantity: int | None = None
    organization_name: str | None = None
    order_name: str | None = None
    signing_date: str | None = None
    practice_name: str | None = None
    practice_date_begin: str | None = None
    practice_date_end: str | None = None
    practice_chief_name: str | None = None


class GroupDistributionSemesterOption(BaseModel):
    value: int
    label: str
    record_count: int = 0


class GroupDistributionFilterOptions(BaseModel):
    semesters: list[GroupDistributionSemesterOption]


class GroupDistributionTableRequest(BaseModel):
    filters: GroupDistributionFilters = Field(default_factory=GroupDistributionFilters)
    custom_sort_requested: bool = False


class DistributionStatsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    organization_status: DistributionStatsOrganizationStatus = Field(default="all")
    actual_contract_status: DistributionStatsActualContractStatus = Field(default="all")
    sort_by: str | None = None
    sort_dir: SortDir = Field(default="asc")


class DistributionStatsYearsResponse(BaseModel):
    available_years: list[int] = Field(default_factory=list)
    default_year_from: int | None = None
    default_year_to: int | None = None


class DistributionStatsYearColumn(BaseModel):
    key: str
    label: str
    kind: Literal["text", "logo", "year", "total"]
    year: int | None = None


class DistributionStatsYearValue(BaseModel):
    year: int
    value: int = 0


class DistributionStatsTableRow(BaseModel):
    organization_id: int | None = None
    contract_id: int | None = None
    contract_number: str | None = None
    signing_date: str | None = None
    logotype_id: int | None = None
    organization_name: str | None = None
    year_values: list[DistributionStatsYearValue] = Field(default_factory=list)
    total_for_period: int = 0


class DistributionStatsTableResponse(BaseModel):
    available_years: list[int] = Field(default_factory=list)
    selected_year_from: int | None = None
    selected_year_to: int | None = None
    organization_status: DistributionStatsOrganizationStatus = "all"
    actual_contract_status: DistributionStatsActualContractStatus = "all"
    sort_by: str | None = None
    sort_dir: SortDir = "asc"
    years: list[int] = Field(default_factory=list)
    columns: list[DistributionStatsYearColumn] = Field(default_factory=list)
    rows: list[DistributionStatsTableRow] = Field(default_factory=list)
    total_rows: int = 0


class DistributionStatsChartItem(BaseModel):
    organization_id: int | None = None
    contract_id: int | None = None
    contract_number: str | None = None
    organization_name: str | None = None
    logotype_id: int | None = None
    year_values: list[DistributionStatsYearValue] = Field(default_factory=list)
    total_for_period: int = 0


class DistributionStatsChartResponse(BaseModel):
    available_years: list[int] = Field(default_factory=list)
    selected_year_from: int | None = None
    selected_year_to: int | None = None
    organization_status: DistributionStatsOrganizationStatus = "all"
    actual_contract_status: DistributionStatsActualContractStatus = "all"
    years: list[int] = Field(default_factory=list)
    items: list[DistributionStatsChartItem] = Field(default_factory=list)
    total_items: int = 0


class OrganizationCardStudyField(BaseModel):
    id: int
    code: str | None = None
    name: str | None = None
    label: str


class OrganizationCardDocument(BaseModel):
    id: int
    datatype_id: int | None = None
    datatype_label: str | None = None
    name_primary: str | None = None
    name_secondary: str | None = None
    title: str
    subtitle: str | None = None
    signing_date: date | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    is_actual: bool = True
    is_archived: bool = False
    pdf_url: str | None = None
    pdf_filename: str | None = None
    has_pdf: bool = False


class OrganizationCardDocumentGroup(BaseModel):
    datatype_id: int | None = None
    datatype_label: str
    actual_document: OrganizationCardDocument | None = None
    archived_documents: list[OrganizationCardDocument] = Field(default_factory=list)


class OrganizationCardReferenceOption(BaseModel):
    id: int
    label: str


class OrganizationCardContactRow(BaseModel):
    entity_id: int
    data_id: int | None = None
    contact_name: str | None = None
    contact_post: str | None = None
    contact_type: str | None = None
    contact_value: str | None = None
    contact_type_id: int | None = None


class OrganizationCardContactGroup(BaseModel):
    entity_id: int
    contact_name: str | None = None
    contact_post: str | None = None
    contacts: list[OrganizationCardContactRow] = Field(default_factory=list)


class OrganizationCardRequisite(BaseModel):
    id: int
    type_id: int
    label: str
    base_label: str | None = None
    custom_label: str | None = None
    value: str | None = None


class OrganizationCardPage(BaseModel):
    id: int
    name_short: str | None = None
    name_long: str | None = None
    settlement_name: str | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    notes: str | None = None
    website: str | None = None
    map_query: str | None = None
    logo_data_url: str | None = None
    is_active: bool = False
    is_university_department: bool = False
    study_fields: list[OrganizationCardStudyField] = Field(default_factory=list)
    documents: list[OrganizationCardDocument] = Field(default_factory=list)
    document_groups: list[OrganizationCardDocumentGroup] = Field(default_factory=list)
    leader_contacts: list[OrganizationCardContactRow] = Field(default_factory=list)
    organization_contacts: list[OrganizationCardContactRow] = Field(default_factory=list)
    organization_contact_groups: list[OrganizationCardContactGroup] = Field(default_factory=list)
    requisites: list[OrganizationCardRequisite] = Field(default_factory=list)


class OrganizationCardContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: int | None = None
    data_id: int | None = None
    client_entity_key: str | None = None
    contact_name: str | None = None
    contact_post: str | None = None
    contact_type_id: int | None = None
    contact_value: str | None = None


class OrganizationCardRequisiteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    type_id: int | None = None
    value: str | None = None


class OrganizationCardSavePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_short: str | None = None
    name_long: str | None = None
    settlement_name: str | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    notes: str | None = None
    website: str | None = None
    is_active: bool = False
    is_university_department: bool = False
    study_field_ids: list[int] = Field(default_factory=list)
    contacts: list[OrganizationCardContactInput] = Field(default_factory=list)
    requisites: list[OrganizationCardRequisiteInput] = Field(default_factory=list)


class OrganizationCardSaveResult(BaseModel):
    organization_id: int
    message: str
    redirect_url: str | None = None


class OrganizationDocumentCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_primary: str | None = None
    name_secondary: str | None = None
    signing_date: date | None = None
    datatype_id: int
    chief_name: str | None = None
    chief_post: str | None = None


class OrganizationDocumentUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name_primary: str | None = None
    name_secondary: str | None = None
    signing_date: date | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    is_actual: bool = False


class OrganizationDeleteResult(BaseModel):
    organization_id: int
    message: str


class OrganizationHeaderSearchItem(BaseModel):
    organization_id: int
    name_short: str | None = None
    name_long: str | None = None
    settlement_name: str | None = None
    inn: str | None = None
    organization_url: str


class OrganizationHeaderSearchResponse(BaseModel):
    query: str
    items: list[OrganizationHeaderSearchItem] = Field(default_factory=list)
