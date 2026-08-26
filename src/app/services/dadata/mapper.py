from __future__ import annotations

from src.app.services.dadata.normalization import normalize_text
from src.app.services.dadata.schemas import DadataOrganizationData


def _read_path(payload: dict, path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _read_email(data: dict) -> str | None:
    emails = data.get("emails")
    if not isinstance(emails, list) or not emails:
        return None
    first_email = emails[0]
    if not isinstance(first_email, dict):
        return None
    value = normalize_text(first_email.get("value"))
    if value:
        return value
    nested_data = first_email.get("data")
    if isinstance(nested_data, dict):
        return normalize_text(nested_data.get("source"))
    return None


def map_party_response(payload: dict, *, requested_inn: str) -> DadataOrganizationData | None:
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        return None

    first = suggestions[0]
    if not isinstance(first, dict):
        return None
    data = first.get("data")
    if not isinstance(data, dict):
        return None

    inn = normalize_text(data.get("inn"))
    warnings: list[str] = []
    if not inn:
        return None
    if inn != requested_inn:
        warnings.append(
            "Dadata вернула организацию с другим ИНН, данные не применялись автоматически."
        )

    legal_address = normalize_text(_read_path(data, ("address", "unrestricted_value")))
    if legal_address is None:
        legal_address = normalize_text(_read_path(data, ("address", "value")))

    return DadataOrganizationData(
        inn=inn,
        ogrn=normalize_text(data.get("ogrn")),
        kpp=normalize_text(data.get("kpp")),
        name_long=normalize_text(_read_path(data, ("name", "full_with_opf"))),
        name_short=normalize_text(_read_path(data, ("name", "short_with_opf"))),
        chief_name=normalize_text(_read_path(data, ("management", "name"))),
        chief_post=normalize_text(_read_path(data, ("management", "post"))),
        legal_address=legal_address,
        actual_address=None,
        email=_read_email(data),
        state_status=normalize_text(_read_path(data, ("state", "status"))),
        warnings=warnings,
    )


def missing_fields(data: DadataOrganizationData) -> list[str]:
    fields = [
        "ogrn",
        "kpp",
        "name_long",
        "name_short",
        "chief_name",
        "chief_post",
        "legal_address",
        "actual_address",
        "email",
    ]
    return [field for field in fields if getattr(data, field) is None]
