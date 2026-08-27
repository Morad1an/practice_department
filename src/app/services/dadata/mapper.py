from __future__ import annotations

from src.app.services.dadata.normalization import normalize_text
from src.app.services.dadata.schemas import DadataOrganizationData

_LOCALITY_TYPE_ABBREVIATIONS = {
    "аул",
    "г",
    "д",
    "кп",
    "п",
    "пгт",
    "рп",
    "с",
    "ст",
    "тер",
    "х",
}


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


def _read_primary_okved(data: dict) -> tuple[str | None, str | None, str | None]:
    raw_code = normalize_text(data.get("okved"))
    raw_type = normalize_text(data.get("okved_type"))
    raw_name = normalize_text(data.get("okved_name"))
    primary: dict | None = None
    okveds = data.get("okveds")
    if isinstance(okveds, list):
        entries = [entry for entry in okveds if isinstance(entry, dict)]
        primary = next((entry for entry in entries if entry.get("main") is True), None)
        if primary is None and raw_code:
            primary = next(
                (entry for entry in entries if normalize_text(entry.get("code")) == raw_code),
                None,
            )
    if primary is not None:
        raw_code = normalize_text(primary.get("code")) or raw_code
        raw_name = normalize_text(primary.get("name")) or raw_name
        raw_type = normalize_text(primary.get("type")) or raw_type
    if not raw_code and not raw_name:
        return None, None, raw_type
    return raw_code, raw_name, raw_type


def _format_locality_name(value: str | None) -> str | None:
    prepared = normalize_text(value)
    if not prepared:
        return None
    parts = prepared.split(None, 1)
    if len(parts) != 2:
        return prepared
    locality_type, name = parts
    normalized_type = locality_type.rstrip(".").lower()
    if normalized_type not in _LOCALITY_TYPE_ABBREVIATIONS:
        return prepared
    return f"{normalized_type}. {name}"


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

    # Dadata returns the locality in the structured address payload. Prefer a
    # city, then a settlement (including villages and other settlement types).
    # Do not use a region as a substitute: it is not a populated locality.
    settlement_name = _format_locality_name(
        normalize_text(_read_path(data, ("address", "data", "city_with_type")))
        or normalize_text(_read_path(data, ("address", "data", "city")))
        or normalize_text(_read_path(data, ("address", "data", "settlement_with_type")))
        or normalize_text(_read_path(data, ("address", "data", "settlement")))
    )

    okved, okved_name, okved_type = _read_primary_okved(data)

    return DadataOrganizationData(
        inn=inn,
        ogrn=normalize_text(data.get("ogrn")),
        kpp=normalize_text(data.get("kpp")),
        okved=okved,
        okved_name=okved_name,
        okved_type=okved_type,
        name_long=normalize_text(_read_path(data, ("name", "full_with_opf"))),
        name_short=normalize_text(_read_path(data, ("name", "short_with_opf"))),
        chief_name=normalize_text(_read_path(data, ("management", "name"))),
        chief_post=normalize_text(_read_path(data, ("management", "post"))),
        legal_address=legal_address,
        settlement_name=settlement_name,
        actual_address=None,
        email=_read_email(data),
        state_status=normalize_text(_read_path(data, ("state", "status"))),
        warnings=warnings,
    )


def missing_fields(data: DadataOrganizationData) -> list[str]:
    fields = [
        "ogrn",
        "kpp",
        "okved",
        "name_long",
        "name_short",
        "chief_name",
        "chief_post",
        "legal_address",
        "actual_address",
        "email",
    ]
    return [field for field in fields if getattr(data, field) is None]
