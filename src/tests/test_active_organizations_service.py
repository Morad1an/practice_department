import unittest

from sqlalchemy.dialects import mysql

from src.app.schemas.organizations import ActiveOrganizationsFilters
from src.app.services.active_organizations import build_active_organizations_statement


def compile_mysql(statement) -> str:
    return str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class ActiveOrganizationsServiceTests(unittest.TestCase):
    def test_contract_number_sort_uses_numeric_digits(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(
                sort_by="contract_number",
                sort_dir="asc",
            ),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("regexp_replace", sql)
        self.assertIn("[^0-9]", sql)
        self.assertIn("cast", sql)
        self.assertIn("signed integer", sql)
        self.assertIn("order by coalesce(cast(nullif(regexp_replace", sql)

    def test_university_departments_without_contract_type_filter_keep_outer_join(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(
                only_active_organizations=False,
                only_actual_contracts=False,
                only_university_departments=True,
                contract_datatype_names=[],
            ),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("left outer join contract", sql)
        self.assertIn("organization.is_university_department = 1", sql)
        self.assertNotIn("contract.name_primary is not null", sql)
        self.assertNotIn("contract.signing_date is not null", sql)
        self.assertNotIn("contract.is_actual = 1", sql)
        self.assertNotIn("contract.datatype_id in", sql)

    def test_unchecked_active_organizations_filters_inactive_organizations(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(
                only_active_organizations=False,
                only_actual_contracts=True,
            ),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("coalesce(organization.is_active, 0) != 1", sql)
        self.assertIn("contract.is_actual = 1", sql)

    def test_unchecked_actual_contracts_filters_inactive_contracts(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(
                only_active_organizations=True,
                only_actual_contracts=False,
            ),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("organization.is_active = 1", sql)
        self.assertIn("coalesce(contract.is_actual, 0) != 1", sql)
        self.assertIn("contract.name_primary is not null", sql)
        self.assertIn("contract.signing_date is not null", sql)

    def test_university_department_mode_ignores_status_checkboxes(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(
                only_active_organizations=False,
                only_actual_contracts=False,
                only_university_departments=True,
                contract_datatype_names=[],
            ),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("organization.is_university_department = 1", sql)
        self.assertNotIn("organization.is_active = 1", sql)
        self.assertNotIn("coalesce(organization.is_active, 0) != 1", sql)
        self.assertNotIn("contract.is_actual = 1", sql)
        self.assertNotIn("coalesce(contract.is_actual, 0) != 1", sql)

    def test_default_filters_still_require_actual_practice_contract_details(self):
        statement = build_active_organizations_statement(
            ActiveOrganizationsFilters(),
            custom_sort_requested=True,
            paginate=False,
        )

        sql = compile_mysql(statement).lower()

        self.assertIn("contract.name_primary is not null", sql)
        self.assertIn("contract.signing_date is not null", sql)
        self.assertIn("organization.is_active = 1", sql)
        self.assertIn("contract.is_actual = 1", sql)
        self.assertIn("contract.datatype_id in (1)", sql)


if __name__ == "__main__":
    unittest.main()
