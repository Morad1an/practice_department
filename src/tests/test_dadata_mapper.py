import pytest

from src.app.services.dadata.mapper import map_party_response, missing_fields
from src.app.services.dadata.normalization import DadataValidationError, normalize_inn


def test_map_party_response_extracts_supported_fields():
    payload = {
        "suggestions": [
            {
                "data": {
                    "inn": "7719402047",
                    "ogrn": "1157746078984",
                    "kpp": "772301001",
                    "okved": "64.20",
                    "okved_type": "2014",
                    "okveds": [
                        {
                            "code": "64.20",
                            "name": "Деятельность холдинговых компаний",
                            "type": "2014",
                            "main": True,
                        }
                    ],
                    "name": {
                        "full_with_opf": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МОТОРИКА"',
                        "short_with_opf": 'ООО "МОТОРИКА"',
                    },
                    "management": {
                        "name": "Давидюк Андрей Павлович",
                        "post": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
                    },
                    "address": {
                        "value": "г Москва, Волгоградский пр-кт, д 42 к 5",
                        "unrestricted_value": "109316, г Москва, Волгоградский пр-кт, д 42 к 5",
                        "data": {
                            "city_with_type": "г Москва",
                            "city": "Москва",
                            "settlement_with_type": None,
                            "settlement": None,
                        },
                    },
                    "emails": [{"value": "info@example.test"}],
                    "state": {"status": "ACTIVE"},
                }
            }
        ]
    }

    result = map_party_response(payload, requested_inn="7719402047")

    assert result is not None
    assert result.inn == "7719402047"
    assert result.ogrn == "1157746078984"
    assert result.kpp == "772301001"
    assert result.okved == "64.20"
    assert result.okved_name == "Деятельность холдинговых компаний"
    assert result.okved_type == "2014"
    assert result.name_short == 'ООО "МОТОРИКА"'
    assert result.chief_name == "Давидюк Андрей Павлович"
    assert result.chief_post == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    assert result.legal_address == "109316, г Москва, Волгоградский пр-кт, д 42 к 5"
    assert result.settlement_name == "г. Москва"
    assert result.actual_address is None
    assert result.email == "info@example.test"
    assert result.state_status == "ACTIVE"
    assert missing_fields(result) == ["actual_address"]


def test_map_party_response_uses_code_when_primary_name_is_unavailable():
    result = map_party_response(
        {"suggestions": [{"data": {"inn": "7719402047", "okved": "72.19"}}]},
        requested_inn="7719402047",
    )

    assert result is not None
    assert result.okved == "72.19"
    assert result.okved_name is None


def test_map_party_response_falls_back_to_settlement_when_city_is_missing():
    result = map_party_response(
        {
            "suggestions": [
                {
                    "data": {
                        "inn": "7719402047",
                        "address": {
                            "data": {
                                "settlement_with_type": "д Деревня",
                                "settlement": "Деревня",
                            }
                        },
                    }
                }
            ]
        },
        requested_inn="7719402047",
    )

    assert result is not None
    assert result.settlement_name == "д. Деревня"


def test_map_party_response_returns_none_for_empty_suggestions():
    assert map_party_response({"suggestions": []}, requested_inn="7719402047") is None


def test_map_party_response_warns_on_different_inn():
    result = map_party_response(
        {"suggestions": [{"data": {"inn": "7719402047"}}]},
        requested_inn="7707083893",
    )

    assert result is not None
    assert result.warnings


def test_normalize_inn_accepts_only_legal_entity_inn():
    assert normalize_inn(" 771-940-2047 ") == "7719402047"
    with pytest.raises(DadataValidationError):
        normalize_inn("784806113663")


def test_normalize_inn_rejects_overlong_raw_query():
    with pytest.raises(DadataValidationError):
        normalize_inn("x" * 301 + "7719402047")
