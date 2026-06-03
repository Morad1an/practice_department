from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DB_NAME: str
    DB_PORT: int
    DB_HOST: str
    DB_USER: str
    DB_PASS: str
    AUTH_SECRET_KEY: str = "Y7x9Cq2mN5vR8sT1wZ4kL6pA3dF0hJ9uB2nX5eM7rQ1cV8yK"
    AUTH_COOKIE_NAME: str = "diplom_auth"
    AUTH_SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 12
    AUTH_COOKIE_SECURE: bool = False
    CSRF_COOKIE_NAME: str = "diplom_csrf"
    REDIS_URL: str | None = None
    LOGO_CACHE_TTL_SECONDS: int = 86400
    LOGO_BATCH_MAX_IDS: int = 80

    @property
    def DB_URL(self) -> str:
        return str(
            URL.create(
                "mysql+asyncmy",
                username=self.DB_USER,
                password=self.DB_PASS,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            )
        )

    @property
    def is_production_like(self) -> bool:
        return self.APP_ENV.strip().lower() in {"production", "prod", "staging"}

    def validate_runtime_configuration(self) -> None:
        if not self.is_production_like:
            return
        if len(self.AUTH_SECRET_KEY) < 32:
            raise ValueError("AUTH_SECRET_KEY must be set in production-like environments.")
        if not self.AUTH_COOKIE_SECURE:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production-like environments.")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
settings.validate_runtime_configuration()
