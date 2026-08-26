from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DadataOrganizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inn: str
    ogrn: str | None = None
    kpp: str | None = None
    name_long: str | None = None
    name_short: str | None = None
    chief_name: str | None = None
    chief_post: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    email: str | None = None
    state_status: str | None = None
    source: Literal["dadata"] = "dadata"
    warnings: list[str] = Field(default_factory=list)


class DadataLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inn: str
    force_refresh: bool = False


class DadataLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["queued", "running", "ready", "not_found", "failed", "rate_limited"]
    job_id: str | None = None
    existing_organization_id: int | None = None
    existing_organization_url: str | None = None
    data: DadataOrganizationData | None = None
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None
    retry_after_seconds: float = 0


class DadataRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "queued", "running", "updated", "not_found", "failed", "rate_limited", "skipped"
    ]
    job_id: str | None = None
    organization_id: int | None = None
    processed_organizations_count: int = 0
    updated_fields: list[str] = Field(default_factory=list)
    data: DadataOrganizationData | None = None
    message: str | None = None
    retry_after_seconds: float = 0


class DadataRefreshAllResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["queued", "running", "completed", "skipped", "rate_limited", "failed"]
    job_id: str | None = None
    total_candidates: int = 0
    processed: int = 0
    updated: int = 0
    failed: int = 0
    skipped: int = 0
    message: str | None = None


class DadataJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "queued", "running", "success", "failed", "rate_limited", "not_found", "skipped"
    ]
    job_id: str
    kind: Literal["lookup", "refresh_one", "refresh_all", "refresh_all_item"]
    result: DadataLookupResponse | DadataRefreshResponse | DadataRefreshAllResponse | None = None
    message: str | None = None
    created_at: float
    updated_at: float
