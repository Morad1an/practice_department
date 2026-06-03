import unittest
from datetime import date
from unittest.mock import patch

from src.app.schemas.organizations import DistributionStatsFilters
from src.app.services.distribution_stats import fetch_distribution_stats_table
from src.app.services.distribution_stats_repository import DistributionStatsRecord


class FakeRepository:
    def __init__(self, records):
        self._records = records

    async def fetch_records(self, session):
        return list(self._records)


class DistributionStatsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sort_by_organization_name_desc(self):
        records = [
            DistributionStatsRecord(
                organization_id=1,
                contract_id=11,
                contract_number="11",
                signing_date=date(2024, 1, 10),
                logotype_id=None,
                organization_name="Бета",
                yearly_counts={2024: 3},
                is_active_organization=True,
                has_actual_contract=True,
            ),
            DistributionStatsRecord(
                organization_id=2,
                contract_id=22,
                contract_number="22",
                signing_date=date(2024, 1, 11),
                logotype_id=None,
                organization_name="Альфа",
                yearly_counts={2024: 5},
                is_active_organization=True,
                has_actual_contract=True,
            ),
        ]

        with patch(
            "src.app.services.distribution_stats.get_distribution_stats_repository",
            return_value=FakeRepository(records),
        ):
            payload = await fetch_distribution_stats_table(
                session=None,
                filters=DistributionStatsFilters(
                    year_from=2024,
                    year_to=2024,
                    sort_by="organization_name",
                    sort_dir="desc",
                ),
            )

        self.assertEqual([row.organization_name for row in payload.rows], ["Бета", "Альфа"])

    async def test_sort_by_year_column_desc(self):
        records = [
            DistributionStatsRecord(
                organization_id=1,
                contract_id=11,
                contract_number="11",
                signing_date=date(2024, 1, 10),
                logotype_id=None,
                organization_name="Альфа",
                yearly_counts={2024: 3, 2025: 7},
                is_active_organization=True,
                has_actual_contract=True,
            ),
            DistributionStatsRecord(
                organization_id=2,
                contract_id=22,
                contract_number="22",
                signing_date=date(2024, 1, 11),
                logotype_id=None,
                organization_name="Бета",
                yearly_counts={2024: 9, 2025: 1},
                is_active_organization=True,
                has_actual_contract=True,
            ),
        ]

        with patch(
            "src.app.services.distribution_stats.get_distribution_stats_repository",
            return_value=FakeRepository(records),
        ):
            payload = await fetch_distribution_stats_table(
                session=None,
                filters=DistributionStatsFilters(
                    year_from=2024,
                    year_to=2025,
                    sort_by="year_2024",
                    sort_dir="desc",
                ),
            )

        self.assertEqual([row.organization_name for row in payload.rows], ["Бета", "Альфа"])

    async def test_filters_inactive_without_actual_contract(self):
        records = [
            DistributionStatsRecord(
                organization_id=1,
                contract_id=11,
                contract_number="11",
                signing_date=date(2024, 1, 10),
                logotype_id=None,
                organization_name="Альфа",
                yearly_counts={2024: 3},
                is_active_organization=True,
                has_actual_contract=True,
            ),
            DistributionStatsRecord(
                organization_id=2,
                contract_id=None,
                contract_number=None,
                signing_date=None,
                logotype_id=None,
                organization_name="Бета",
                yearly_counts={2024: 5},
                is_active_organization=False,
                has_actual_contract=False,
            ),
        ]

        with patch(
            "src.app.services.distribution_stats.get_distribution_stats_repository",
            return_value=FakeRepository(records),
        ):
            payload = await fetch_distribution_stats_table(
                session=None,
                filters=DistributionStatsFilters(
                    year_from=2024,
                    year_to=2024,
                    organization_status="inactive",
                    actual_contract_status="without_actual_contract",
                ),
            )

        self.assertEqual(len(payload.rows), 1)
        self.assertEqual(payload.rows[0].organization_name, "Бета")

    async def test_hides_rows_with_zero_total_for_selected_period(self):
        records = [
            DistributionStatsRecord(
                organization_id=1,
                contract_id=11,
                contract_number="11",
                signing_date=date(2024, 1, 10),
                logotype_id=None,
                organization_name="Альфа",
                yearly_counts={2023: 10, 2024: 0, 2025: 15},
                is_active_organization=True,
                has_actual_contract=True,
            ),
            DistributionStatsRecord(
                organization_id=2,
                contract_id=22,
                contract_number="22",
                signing_date=date(2024, 1, 11),
                logotype_id=None,
                organization_name="Бета",
                yearly_counts={2023: 10, 2024: 4, 2025: 15},
                is_active_organization=True,
                has_actual_contract=True,
            ),
        ]

        with patch(
            "src.app.services.distribution_stats.get_distribution_stats_repository",
            return_value=FakeRepository(records),
        ):
            payload = await fetch_distribution_stats_table(
                session=None,
                filters=DistributionStatsFilters(
                    year_from=2024,
                    year_to=2024,
                ),
            )

        self.assertEqual([row.organization_name for row in payload.rows], ["Бета"])


if __name__ == "__main__":
    unittest.main()
