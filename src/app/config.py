from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DB_NAME: str
    DB_PORT: int
    DB_HOST: str
    DB_USER: str
    DB_PASS: str
    AUTH_SECRET_KEY: str = ""
    AUTH_COOKIE_NAME: str = "diplom_auth"
    AUTH_SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 12
    AUTH_COOKIE_SECURE: bool = False
    CSRF_COOKIE_NAME: str = "diplom_csrf"
    REDIS_URL: str | None = None
    LOGO_CACHE_TTL_SECONDS: int = 86400
    LOGO_BATCH_MAX_IDS: int = 80
    DADATA_API_KEY: str | None = None
    DADATA_SECRET_KEY: str | None = None
    DADATA_BASE_URL: str = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
    DADATA_QUERY_MAX_LENGTH: int = 300
    DADATA_LOOKUP_TIMEOUT_SECONDS: int = 10
    DADATA_REFRESH_INTERVAL_DAYS: int = 30
    DADATA_MAX_REQUESTS_PER_SECOND: int = 25
    DADATA_FULL_REFRESH_REQUESTS_PER_SECOND: int = 20
    DADATA_DAILY_REQUEST_LIMIT: int = 10000
    DADATA_MAX_CONCURRENT_REQUESTS: int = 10
    DADATA_MAX_NEW_CONNECTIONS_PER_MINUTE: int = 50
    DADATA_REFRESH_BATCH_SIZE: int = 50
    DADATA_FULL_REFRESH_CONCURRENCY: int = 10
    DADATA_JOB_STATUS_TTL_SECONDS: int = 86400
    DADATA_FULL_REFRESH_DAILY_LIMIT: int = 1
    DADATA_FULL_REFRESH_LOCK_TTL_SECONDS: int = 900
    DADATA_ALLOW_MANUAL_FULL_REFRESH_AFTER_SCHEDULED: bool = False
    DADATA_DAILY_REQUEST_RESERVE: int = 200
    DADATA_MAX_RETRIES: int = 3
    DADATA_RETRY_BASE_DELAY_SECONDS: float = 0.5
    DADATA_SCHEDULE_INITIAL_REFRESH: bool = False
    DADATA_FALLBACK_REQUESTS_PER_SECOND: int = 3
    DADATA_MAX_ACTIVE_MANUAL_JOBS_PER_USER: int = 3

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
        if not 1 <= self.DADATA_MAX_REQUESTS_PER_SECOND <= 30:
            raise ValueError("DADATA_MAX_REQUESTS_PER_SECOND must be between 1 and 30.")
        if (
            not 1
            <= self.DADATA_FULL_REFRESH_REQUESTS_PER_SECOND
            <= self.DADATA_MAX_REQUESTS_PER_SECOND
        ):
            raise ValueError("DADATA_FULL_REFRESH_REQUESTS_PER_SECOND must not exceed global RPS.")
        if not 1 <= self.DADATA_MAX_NEW_CONNECTIONS_PER_MINUTE <= 60:
            raise ValueError("DADATA_MAX_NEW_CONNECTIONS_PER_MINUTE must be between 1 and 60.")
        if self.DADATA_REFRESH_INTERVAL_DAYS < 7:
            raise ValueError("DADATA_REFRESH_INTERVAL_DAYS must be at least 7.")
        if self.DADATA_DAILY_REQUEST_LIMIT <= self.DADATA_DAILY_REQUEST_RESERVE:
            raise ValueError("DADATA_DAILY_REQUEST_RESERVE must be below the daily limit.")
        if self.DADATA_REFRESH_BATCH_SIZE < 1 or self.DADATA_MAX_CONCURRENT_REQUESTS < 1:
            raise ValueError("Dadata batch size and concurrency must be positive.")
        if self.DADATA_FULL_REFRESH_CONCURRENCY < 1:
            raise ValueError("DADATA_FULL_REFRESH_CONCURRENCY must be positive.")
        if self.DADATA_FULL_REFRESH_LOCK_TTL_SECONDS < 60:
            raise ValueError("DADATA_FULL_REFRESH_LOCK_TTL_SECONDS must be at least 60.")
        if not 1 <= self.DADATA_FALLBACK_REQUESTS_PER_SECOND <= 5:
            raise ValueError("DADATA_FALLBACK_REQUESTS_PER_SECOND must be between 1 and 5.")
        if self.DADATA_MAX_ACTIVE_MANUAL_JOBS_PER_USER < 1:
            raise ValueError("DADATA_MAX_ACTIVE_MANUAL_JOBS_PER_USER must be positive.")
        if not self.is_production_like:
            return
        if len(self.AUTH_SECRET_KEY) < 32 or self.AUTH_SECRET_KEY == "change_before_use":
            raise ValueError("AUTH_SECRET_KEY must be set in production-like environments.")
        if not self.AUTH_COOKIE_SECURE:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production-like environments.")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
settings.validate_runtime_configuration()
