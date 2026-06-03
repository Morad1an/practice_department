from src.app.models.app_user import AppUserOrm
from src.app.models.contract import ContractOrm
from src.app.models.contract_datatype import ContractDatatype
from src.app.models.contract_detailcontactdata import ContractDetailContactData
from src.app.models.contract_detailcontactentity import ContractDetailContactEntity
from src.app.models.contract_detaillegalinformation import ContractDetailLegalInformation
from src.app.models.contract_pdfdocument import ContractPdfDocument
from src.app.models.detailname_contactdata import DetailnameContactData
from src.app.models.detailname_legalinformation import DetailnameLegalInformation
from src.app.models.detailname_settlement import DetailnameSettlement
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detailcontactdata import OrganizationDetailContactData
from src.app.models.organization_detailcontactdata_local import OrganizationDetailContactDataLocal
from src.app.models.organization_detailcontactentity import OrganizationDetailContactEntity
from src.app.models.organization_detailcontactentity_local import (
    OrganizationDetailContactEntityLocal,
)
from src.app.models.organization_detaillegalinformation import OrganizationDetailLegalInformation
from src.app.models.organization_detaillogotype import OrganizationDetailLogotype
from src.app.models.organization_detailstudyfield import OrganizationDetailStudyField
from src.app.models.organization_distributionstatistic import OrganizationDistributionStatistic
from src.app.models.organization_previousname import OrganizationPreviousName
from src.app.models.practice_distributionorder import PracticeDistributionOrder
from src.app.models.practice_distributionorderblock import PracticeDistributionOrderBlock
from src.app.models.university_academicdepartment import UniversityAcademicDepartment
from src.app.models.university_academicfaculty import UniversityAcademicFaculty
from src.app.models.university_studydegree import UniversityStudyDegree
from src.app.models.university_studyfield import UniversityStudyField
from src.app.models.university_studysemester import UniversityStudySemester
from src.app.models.university_studyspeciality import UniversityStudySpeciality
from src.app.models.university_studytimeform import UniversityStudyTimeForm

__all__ = [
    "AppUserOrm",
    "ContractOrm",
    "ContractDatatype",
    "ContractDetailContactData",
    "ContractDetailContactEntity",
    "ContractDetailLegalInformation",
    "ContractPdfDocument",
    "DetailnameContactData",
    "DetailnameLegalInformation",
    "DetailnameSettlement",
    "OrganizationOrm",
    "OrganizationDetailContactData",
    "OrganizationDetailContactDataLocal",
    "OrganizationDetailContactEntity",
    "OrganizationDetailContactEntityLocal",
    "OrganizationDetailLegalInformation",
    "OrganizationDetailLogotype",
    "OrganizationDetailStudyField",
    "OrganizationDistributionStatistic",
    "OrganizationPreviousName",
    "PracticeDistributionOrder",
    "PracticeDistributionOrderBlock",
    "UniversityAcademicDepartment",
    "UniversityAcademicFaculty",
    "UniversityStudyDegree",
    "UniversityStudyField",
    "UniversityStudySemester",
    "UniversityStudySpeciality",
    "UniversityStudyTimeForm",
]
