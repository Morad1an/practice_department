from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.detailname_legalinformation import DetailnameLegalInformation
from src.app.models.detailname_settlement import DetailnameSettlement
from src.app.models.organization import OrganizationOrm
from src.app.models.organization_detaillegalinformation import OrganizationDetailLegalInformation
from src.app.schemas.organizations import OrganizationHeaderSearchItem


def _normalize_query(value: str | None) -> str:
    return (value or "").strip()


async def search_organizations_for_header(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 8,
) -> list[OrganizationHeaderSearchItem]:
    normalized_query = _normalize_query(query)
    if len(normalized_query) < 2:
        return []

    normalized_limit = max(1, min(limit, 20))
    lowered_query = normalized_query.lower()
    contains_pattern = f"%{lowered_query}%"
    starts_pattern = f"{lowered_query}%"

    inn_sq = (
        select(
            OrganizationDetailLegalInformation.organization_id.label("organization_id"),
            func.max(OrganizationDetailLegalInformation.data).label("inn"),
        )
        .select_from(OrganizationDetailLegalInformation)
        .join(
            DetailnameLegalInformation,
            DetailnameLegalInformation.id == OrganizationDetailLegalInformation.type_id,
        )
        .where(func.lower(DetailnameLegalInformation.name) == "инн")
        .group_by(OrganizationDetailLegalInformation.organization_id)
        .subquery("organization_search_inn_sq")
    )

    name_short_expr = func.lower(func.coalesce(OrganizationOrm.name_short, ""))
    name_long_expr = func.lower(func.coalesce(OrganizationOrm.name_long, ""))
    inn_expr = func.lower(func.coalesce(inn_sq.c.inn, ""))

    statement = (
        select(
            OrganizationOrm.id,
            OrganizationOrm.name_short,
            OrganizationOrm.name_long,
            DetailnameSettlement.name.label("settlement_name"),
            inn_sq.c.inn,
        )
        .select_from(OrganizationOrm)
        .outerjoin(
            DetailnameSettlement,
            DetailnameSettlement.id == OrganizationOrm.settlement_id,
        )
        .outerjoin(inn_sq, inn_sq.c.organization_id == OrganizationOrm.id)
        .where(
            or_(
                name_short_expr.like(contains_pattern),
                name_long_expr.like(contains_pattern),
                inn_expr.like(contains_pattern),
            )
        )
        .order_by(
            case(
                (inn_expr == lowered_query, 0),
                (name_short_expr == lowered_query, 1),
                (name_long_expr == lowered_query, 2),
                (inn_expr.like(starts_pattern), 3),
                (name_short_expr.like(starts_pattern), 4),
                (name_long_expr.like(starts_pattern), 5),
                else_=6,
            ),
            OrganizationOrm.name_short.asc(),
            OrganizationOrm.name_long.asc(),
            OrganizationOrm.id.asc(),
        )
        .limit(normalized_limit)
    )

    result = await session.execute(statement)
    return [
        OrganizationHeaderSearchItem(
            organization_id=row.id,
            name_short=row.name_short,
            name_long=row.name_long,
            settlement_name=row.settlement_name,
            inn=row.inn,
            organization_url=f"/organizations/{row.id}",
        )
        for row in result
    ]
