from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.app.api.organizations_common import (
    build_active_organizations_page_context,
    build_distribution_stats_page_context,
    build_group_distribution_page_context,
    build_new_organization_page_context,
    build_organization_detail_page_context,
    build_study_directions_page_context,
    build_timeline_stats_page_context,
    templates,
)
from src.app.schemas.organizations import (
    ActiveOrganizationsFilters,
    DistributionStatsFilters,
    GroupDistributionFilters,
    StudyDirectionsFilters,
)

router = APIRouter(prefix="/organizations", tags=["Organization Pages"])


@router.get("/active", response_class=HTMLResponse)
@router.get("/active/page", response_class=HTMLResponse, include_in_schema=False)
async def active_organizations_page(
    request: Request,
    filters: Annotated[ActiveOrganizationsFilters, Query()],
):
    context = await build_active_organizations_page_context(
        request,
        filters,
        custom_sort_requested=(
            "sort_by" in request.query_params or "sort_dir" in request.query_params
        ),
    )
    context.update({"active_tab": "active-organizations"})
    return templates.TemplateResponse(request, "organizations/active.html", context)


@router.get("/study-directions", response_class=HTMLResponse)
async def study_directions_page(
    request: Request,
    filters: Annotated[StudyDirectionsFilters, Query()],
):
    context = await build_study_directions_page_context(
        request,
        filters,
        custom_sort_requested=(
            "sort_by" in request.query_params or "sort_dir" in request.query_params
        ),
    )
    context.update({"active_tab": "study-directions"})
    return templates.TemplateResponse(request, "organizations/study_directions.html", context)


@router.get("/groups", response_class=HTMLResponse)
async def groups_page(
    request: Request,
    filters: Annotated[GroupDistributionFilters, Query()],
):
    context = await build_group_distribution_page_context(
        request,
        filters,
        custom_sort_requested=(
            "sort_by" in request.query_params or "sort_dir" in request.query_params
        ),
    )
    context.update({"active_tab": "groups"})
    return templates.TemplateResponse(request, "organizations/groups.html", context)


@router.get("/distribution-stats", response_class=HTMLResponse)
async def distribution_stats_page(
    request: Request,
    filters: Annotated[DistributionStatsFilters, Query()],
):
    context = await build_distribution_stats_page_context(request, filters)
    context.update({"active_tab": "distribution-stats"})
    return templates.TemplateResponse(request, "organizations/distribution_stats.html", context)


@router.get("/timeline-stats", response_class=HTMLResponse)
async def timeline_stats_page(
    request: Request,
    filters: Annotated[DistributionStatsFilters, Query()],
):
    context = await build_timeline_stats_page_context(request, filters)
    context.update({"active_tab": "timeline-stats"})
    return templates.TemplateResponse(request, "organizations/timeline_stats.html", context)


@router.get("/new", response_class=HTMLResponse)
async def new_organization_page(request: Request):
    if not bool(getattr(request.state, "can_edit", False)):
        return RedirectResponse(url="/organizations/active", status_code=303)
    context = await build_new_organization_page_context(request)
    return templates.TemplateResponse(request, "organizations/detail.html", context)


@router.get("/{organization_id}", response_class=HTMLResponse)
async def organization_detail_page(request: Request, organization_id: int):
    context = await build_organization_detail_page_context(request, organization_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return templates.TemplateResponse(request, "organizations/detail.html", context)
