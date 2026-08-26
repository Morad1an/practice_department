import pytest

from src.app.config import Settings


def build_settings(**overrides):
    values = {
        "APP_ENV": "production",
        "DB_NAME": "test",
        "DB_PORT": 3306,
        "DB_HOST": "127.0.0.1",
        "DB_USER": "test",
        "DB_PASS": "test",
        "AUTH_SECRET_KEY": "a" * 32,
        "AUTH_COOKIE_SECURE": True,
        "REDIS_URL": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_configuration_allows_single_dadata_operations_without_redis():
    settings = build_settings()

    settings.validate_runtime_configuration()


@pytest.mark.parametrize("secret", ["", "change_before_use", "too-short"])
def test_production_configuration_rejects_unsafe_auth_secret(secret: str):
    settings = build_settings(AUTH_SECRET_KEY=secret)

    with pytest.raises(ValueError, match="AUTH_SECRET_KEY"):
        settings.validate_runtime_configuration()
