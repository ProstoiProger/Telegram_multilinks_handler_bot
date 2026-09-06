from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: SecretStr
    redis_url: str = "redis://localhost:6379/0"

    check_concurrency: int = Field(default=300, ge=1, le=2000)
    check_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    check_read_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    check_total_timeout_seconds: float = Field(default=5.0, gt=0, le=120)
    check_retries: int = Field(default=0, ge=0, le=3)
    check_max_redirects: int = Field(default=5, ge=0, le=20)
    check_http2: bool = True

    max_file_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=20 * 1024 * 1024)
    max_urls_per_file: int = Field(default=10_000, ge=1, le=100_000)
    job_ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    recheck_interval_seconds: int = Field(default=1_800, ge=60, le=86_400)
    monitor_dispatch_interval_seconds: int = Field(default=10, ge=5, le=300)
    monitor_lock_timeout_seconds: int = Field(default=700, ge=60, le=3_600)

    @property
    def redis_job_url(self) -> str:
        return self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
