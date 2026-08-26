from __future__ import annotations

import re

from src.app.config import settings


class DadataValidationError(ValueError):
    """Raised when lookup input cannot be sent to Dadata."""


def normalize_inn(value: str | None) -> str:
    if len(value or "") > settings.DADATA_QUERY_MAX_LENGTH:
        raise DadataValidationError(
            f"Запрос к Dadata не должен быть длиннее {settings.DADATA_QUERY_MAX_LENGTH} символов."
        )
    normalized = re.sub(r"\D+", "", value or "")
    if not normalized:
        raise DadataValidationError("Введите ИНН.")
    if len(normalized) != 10:
        raise DadataValidationError("Для организации ИНН должен состоять из 10 цифр.")
    return normalized


def normalize_text(value: object) -> str | None:
    prepared = str(value or "").strip()
    return prepared or None
