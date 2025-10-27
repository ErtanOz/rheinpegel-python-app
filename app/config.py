from functools import lru_cache
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    source_url: AnyHttpUrl = (
        "https://www.stadt-koeln.de/interne-dienste/hochwasser/pegel_ws.php"
    )
    refresh_seconds: int = 120
    tz: str = "Europe/Berlin"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
        case_sensitive=False,
    )

    @property
    def timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.tz)
        except Exception:
            return ZoneInfo("Europe/Berlin")


@lru_cache
def get_settings() -> Settings:
    return Settings()
