from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast

from src.app.schemas.organizations import (
    DistributionStatsChartItem,
    DistributionStatsChartResponse,
    DistributionStatsFilters,
    DistributionStatsTableResponse,
    DistributionStatsTableRow,
    DistributionStatsYearColumn,
    DistributionStatsYearsResponse,
    DistributionStatsYearValue,
)
from src.app.services.distribution_stats_repository import (
    DistributionStatsRecord,
    get_distribution_stats_repository,
)


def _format_signing_date(value) -> str | None:
    if value is None:
        return None
    return value.strftime("%d.%m.%Y")


def _collect_available_years(records: Iterable[DistributionStatsRecord]) -> list[int]:
    years = {
        year
        for record in records
        for year, count in record.yearly_counts.items()
        if count is not None
    }
    return sorted(years)


def _resolve_years(
    filters: DistributionStatsFilters,
    available_years: list[int],
) -> tuple[int | None, int | None, list[int]]:
    if not available_years:
        return None, None, []

    default_years = available_years
    year_from = filters.year_from if filters.year_from in available_years else default_years[0]
    year_to = filters.year_to if filters.year_to in available_years else default_years[-1]

    if year_from > year_to:
        year_from, year_to = year_to, year_from

    selected_years = [year for year in available_years if year_from <= year <= year_to]
    if not selected_years:
        selected_years = default_years
        year_from = selected_years[0]
        year_to = selected_years[-1]

    return year_from, year_to, selected_years


@dataclass
class PreparedDistributionStatsRow:
    record: DistributionStatsRecord
    year_values: list[DistributionStatsYearValue]
    total_for_period: int


def _build_default_sort_key(prepared_row: PreparedDistributionStatsRow):
    record = prepared_row.record
    return (
        (record.organization_name or "").lower(),
        record.signing_date or date.min,
        record.contract_number or "",
        record.contract_id or 0,
    )


def _build_custom_sort_key(
    prepared_row: PreparedDistributionStatsRow,
    sort_by: str,
) -> object:
    record = prepared_row.record
    if sort_by == "signing_date":
        return record.signing_date or date.min
    if sort_by == "organization_name":
        return (record.organization_name or "").lower()
    if sort_by == "total_for_period":
        return prepared_row.total_for_period
    if sort_by.startswith("year_"):
        try:
            target_year = int(sort_by.removeprefix("year_"))
        except ValueError:
            return _build_default_sort_key(prepared_row)
        for year_value in prepared_row.year_values:
            if year_value.year == target_year:
                return year_value.value
        return 0
    return _build_default_sort_key(prepared_row)


def _is_supported_sort_key(sort_by: str | None, selected_years: list[int]) -> bool:
    if sort_by in {None, "", "organization_name", "signing_date", "total_for_period"}:
        return True
    if isinstance(sort_by, str) and sort_by.startswith("year_"):
        try:
            return int(sort_by.removeprefix("year_")) in selected_years
        except ValueError:
            return False
    return False


def _sort_prepared_rows(
    prepared_rows: list[PreparedDistributionStatsRow],
    filters: DistributionStatsFilters,
    selected_years: list[int],
) -> tuple[str | None, str]:
    prepared_rows.sort(key=_build_default_sort_key)

    normalized_sort_by = (
        filters.sort_by if _is_supported_sort_key(filters.sort_by, selected_years) else None
    )
    normalized_sort_dir: Literal["asc", "desc"] = "desc" if filters.sort_dir == "desc" else "asc"

    if normalized_sort_by:
        prepared_rows.sort(
            key=lambda item: cast(
                Any,
                _build_custom_sort_key(item, normalized_sort_by),
            ),
            reverse=normalized_sort_dir == "desc",
        )

    return normalized_sort_by, normalized_sort_dir


async def _fetch_records(session) -> list[DistributionStatsRecord]:
    repository = get_distribution_stats_repository()
    return await repository.fetch_records(session)


def _matches_organization_status(
    record: DistributionStatsRecord,
    organization_status: str,
) -> bool:
    if organization_status == "active":
        return record.is_active_organization
    if organization_status == "inactive":
        return not record.is_active_organization
    return True


def _matches_actual_contract_status(
    record: DistributionStatsRecord,
    actual_contract_status: str,
) -> bool:
    if actual_contract_status == "with_actual_contract":
        return record.has_actual_contract
    if actual_contract_status == "without_actual_contract":
        return not record.has_actual_contract
    return True


def _matches_filters(
    record: DistributionStatsRecord,
    filters: DistributionStatsFilters,
) -> bool:
    return _matches_organization_status(
        record,
        filters.organization_status,
    ) and _matches_actual_contract_status(
        record,
        filters.actual_contract_status,
    )


async def fetch_distribution_stats_years(session) -> DistributionStatsYearsResponse:
    records = await _fetch_records(session)
    available_years = _collect_available_years(records)
    if not available_years:
        return DistributionStatsYearsResponse()

    return DistributionStatsYearsResponse(
        available_years=available_years,
        default_year_from=available_years[0],
        default_year_to=available_years[-1],
    )


async def fetch_distribution_stats_table(
    session,
    filters: DistributionStatsFilters,
) -> DistributionStatsTableResponse:
    records = await _fetch_records(session)
    available_years = _collect_available_years(records)
    selected_year_from, selected_year_to, selected_years = _resolve_years(
        filters,
        available_years,
    )

    prepared_rows: list[PreparedDistributionStatsRow] = []
    for record in records:
        if not _matches_filters(record, filters):
            continue
        year_values = [
            DistributionStatsYearValue(year=year, value=record.yearly_counts.get(year, 0))
            for year in selected_years
        ]
        total_for_period = sum(item.value for item in year_values)
        if total_for_period <= 0:
            continue
        prepared_rows.append(
            PreparedDistributionStatsRow(
                record=record,
                year_values=year_values,
                total_for_period=total_for_period,
            )
        )

    normalized_sort_by, normalized_sort_dir = _sort_prepared_rows(
        prepared_rows,
        filters,
        selected_years,
    )

    rows = [
        DistributionStatsTableRow(
            organization_id=prepared_row.record.organization_id,
            contract_id=prepared_row.record.contract_id,
            contract_number=prepared_row.record.contract_number,
            signing_date=_format_signing_date(prepared_row.record.signing_date),
            logotype_id=prepared_row.record.logotype_id,
            organization_name=prepared_row.record.organization_name,
            year_values=prepared_row.year_values,
            total_for_period=prepared_row.total_for_period,
        )
        for prepared_row in prepared_rows
    ]

    columns = [
        DistributionStatsYearColumn(
            key="contract_number",
            label="Номер договора",
            kind="text",
        ),
        DistributionStatsYearColumn(
            key="signing_date",
            label="Дата заключения",
            kind="text",
        ),
        DistributionStatsYearColumn(
            key="logotype",
            label="Логотип",
            kind="logo",
        ),
        DistributionStatsYearColumn(
            key="organization_name",
            label="Наименование организации",
            kind="text",
        ),
        *[
            DistributionStatsYearColumn(
                key=f"year_{year}",
                label=str(year),
                kind="year",
                year=year,
            )
            for year in selected_years
        ],
        DistributionStatsYearColumn(
            key="total_for_period",
            label="За все время",
            kind="total",
        ),
    ]

    return DistributionStatsTableResponse(
        available_years=available_years,
        selected_year_from=selected_year_from,
        selected_year_to=selected_year_to,
        organization_status=filters.organization_status,
        actual_contract_status=filters.actual_contract_status,
        sort_by=normalized_sort_by,
        sort_dir=cast(Literal["asc", "desc"], normalized_sort_dir),
        years=selected_years,
        columns=columns,
        rows=rows,
        total_rows=len(rows),
    )


async def fetch_distribution_stats_chart(
    session,
    filters: DistributionStatsFilters,
) -> DistributionStatsChartResponse:
    table_payload = await fetch_distribution_stats_table(session, filters)
    items = [
        DistributionStatsChartItem(
            organization_id=row.organization_id,
            contract_id=row.contract_id,
            contract_number=row.contract_number,
            organization_name=row.organization_name,
            logotype_id=row.logotype_id,
            year_values=row.year_values,
            total_for_period=row.total_for_period,
        )
        for row in sorted(
            table_payload.rows,
            key=lambda item: (-item.total_for_period, (item.organization_name or "").lower()),
        )
    ]

    return DistributionStatsChartResponse(
        available_years=table_payload.available_years,
        selected_year_from=table_payload.selected_year_from,
        selected_year_to=table_payload.selected_year_to,
        organization_status=table_payload.organization_status,
        actual_contract_status=table_payload.actual_contract_status,
        years=table_payload.years,
        items=items,
        total_items=len(items),
    )
