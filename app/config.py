from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./mypocket.db"
    telegram_bot_token: str = "unset"
    anthropic_api_key: str = "unset"
    whisper_model: str = "small"
    log_level: str = "INFO"
    base_url: str = "http://localhost:8000"
    poll_interval_hours: int = 4
    invite_key_expiry_hours: int = 24
    secret_key: str = "change-me"
    web_password: str = "change-me"
    enable_banking_app_id: str = ""
    enable_banking_key_file: str = ""  # path to RSA private key .pem

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "test"

    model_config = {"env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
