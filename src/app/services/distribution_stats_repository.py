from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import Integer, cast, func, select

from src.app.models.contract import ContractOrm
from src.app.models.contract_datatype import ContractDatatype
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_distributionstatistic import OrganizationDistributionStatistic
from src.app.models.practice_distributionorder import PracticeDistributionOrder
from src.app.models.practice_distributionorderblock import PracticeDistributionOrderBlock

PRACTICAL_TRAINING_CONTRACT_NAME = "Договор о практической подготовке обучающихся"


@dataclass(frozen=True)
class DistributionStatsRecord:
    organization_id: int
    contract_id: int | None
    contract_number: str | None
    signing_date: date | None
    logotype_id: int | None
    organization_name: str
    yearly_counts: dict[int, int]
    is_active_organization: bool = False
    has_actual_contract: bool = False


class DistributionStatsRepository(Protocol):
    async def fetch_records(
        self,
        session,
    ) -> list[DistributionStatsRecord]:
        pass


class SqlDistributionStatsRepository:
    async def fetch_records(self, session) -> list[DistributionStatsRecord]:
        stats_by_organization = await self._fetch_yearly_counts_by_organization(session)
        organization_ids = sorted(stats_by_organization)
        organization_rows = await self._fetch_organization_rows(session, organization_ids)
        contract_rows = await self._fetch_practice_contract_rows(session, organization_ids)

        organizations_by_id = {row["organization_id"]: row for row in organization_rows}
        preferred_contracts_by_organization = self._pick_preferred_contracts(contract_rows)

        records: list[DistributionStatsRecord] = []
        for organization_id, yearly_counts in stats_by_organization.items():
            organization_row = organizations_by_id.get(organization_id, {})
            contract_row = preferred_contracts_by_organization.get(organization_id)
            if not contract_row:
                continue
            records.append(
                DistributionStatsRecord(
                    organization_id=organization_id,
                    contract_id=contract_row.get("contract_id"),
                    contract_number=contract_row.get("contract_number"),
                    signing_date=contract_row.get("signing_date"),
                    logotype_id=organization_row.get("logotype_id"),
                    organization_name=(
                        organization_row.get("organization_name")
                        or f"Организация #{organization_id}"
                    ),
                    yearly_counts=dict(yearly_counts),
                    is_active_organization=bool(
                        organization_row.get("is_active_organization", False)
                    ),
                    has_actual_contract=bool(contract_row.get("is_actual_contract", False)),
                )
            )
        return records

    def _pick_preferred_contracts(self, contract_rows):
        preferred_contracts_by_organization: dict[int, dict] = {}
        for row in contract_rows:
            organization_id = row["organization_id"]
            if organization_id not in preferred_contracts_by_organization:
                preferred_contracts_by_organization[organization_id] = dict(row)
        return preferred_contracts_by_organization

    async def _fetch_yearly_counts_by_organization(
        self,
        session,
    ) -> dict[int, dict[int, int]]:
        stats_by_organization: dict[int, dict[int, int]] = {}
        self._merge_statistics_rows(
            stats_by_organization,
            await self._fetch_aggregated_order_statistics(session),
        )

        has_precalculated_stats = await session.scalar(
            select(func.count()).select_from(OrganizationDistributionStatistic)
        )
        if has_precalculated_stats:
            self._merge_statistics_rows(
                stats_by_organization,
                await self._fetch_precalculated_statistics(session),
                replace=True,
            )

        return stats_by_organization

    @staticmethod
    def _merge_statistics_rows(
        stats_by_organization: dict[int, dict[int, int]],
        rows,
        *,
        replace: bool = False,
    ) -> None:
        for row in rows:
            organization_id = row["organization_id"]
            year = row["year"]
            stat_number = row["stat_number"] or 0
            if organization_id is None or year is None:
                continue
            org_id = int(organization_id)
            year_int = int(year)
            stats = stats_by_organization.setdefault(org_id, {})
            if replace:
                stats[year_int] = int(stat_number)
            else:
                stats[year_int] = stats.get(year_int, 0) + int(stat_number)

    async def _fetch_precalculated_statistics(self, session):
        statement = (
            select(
                OrganizationDistributionStatistic.organization_id.label("organization_id"),
                OrganizationDistributionStatistic.year.label("year"),
                func.sum(func.coalesce(OrganizationDistributionStatistic.stat_number, 0)).label(
                    "stat_number"
                ),
            )
            .where(OrganizationDistributionStatistic.year.is_not(None))
            .group_by(
                OrganizationDistributionStatistic.organization_id,
                OrganizationDistributionStatistic.year,
            )
        )
        result = await session.execute(statement)
        return result.mappings().all()

    async def _fetch_aggregated_order_statistics(self, session):
        parsed_signing_date = func.str_to_date(
            PracticeDistributionOrder.signing_date,
            "%d.%m.%Y",
        )
        signing_year = cast(func.year(parsed_signing_date), Integer)

        statement = (
            select(
                PracticeDistributionOrderBlock.organization_id.label("organization_id"),
                signing_year.label("year"),
                func.sum(func.coalesce(PracticeDistributionOrderBlock.quantity, 0)).label(
                    "stat_number"
                ),
            )
            .select_from(PracticeDistributionOrderBlock)
            .join(
                PracticeDistributionOrder,
                PracticeDistributionOrder.id == PracticeDistributionOrderBlock.order_id,
            )
            .where(
                PracticeDistributionOrderBlock.organization_id.is_not(None),
                parsed_signing_date.is_not(None),
            )
            .group_by(
                PracticeDistributionOrderBlock.organization_id,
                signing_year,
            )
        )
        result = await session.execute(statement)
        return result.mappings().all()

    async def _fetch_organization_rows(self, session, organization_ids: list[int]):
        if not organization_ids:
            return []

        organization_name = func.coalesce(
            OrganizationOrm.name_short,
            OrganizationOrm.name_long,
        )
        statement = (
            select(
                OrganizationOrm.id.label("organization_id"),
                OrganizationOrm.logotype_id.label("logotype_id"),
                organization_name.label("organization_name"),
                OrganizationOrm.is_active.label("is_active_organization"),
            )
            .select_from(OrganizationOrm)
            .where(OrganizationOrm.id.in_(organization_ids))
        )
        result = await session.execute(statement)
        return result.mappings().all()

    async def _fetch_practice_contract_rows(self, session, organization_ids: list[int]):
        if not organization_ids:
            return []

        statement = (
            select(
                ContractOrm.organization_id.label("organization_id"),
                ContractOrm.id.label("contract_id"),
                ContractOrm.name_primary.label("contract_number"),
                ContractOrm.signing_date.label("signing_date"),
                ContractOrm.is_actual.label("is_actual_contract"),
            )
            .select_from(ContractOrm)
            .join(ContractDatatype, ContractDatatype.id == ContractOrm.datatype_id)
            .where(
                ContractOrm.organization_id.in_(organization_ids),
                ContractDatatype.name == PRACTICAL_TRAINING_CONTRACT_NAME,
            )
            .order_by(
                ContractOrm.organization_id.asc(),
                ContractOrm.is_actual.desc(),
                ContractOrm.signing_date.desc(),
                ContractOrm.id.desc(),
            )
        )
        result = await session.execute(statement)
        return result.mappings().all()


_sql_repository = SqlDistributionStatsRepository()


def get_distribution_stats_repository() -> DistributionStatsRepository:
    return _sql_repository
