from __future__ import annotations

from datetime import date, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
CONFIG_PATH = ROOT / "config.yaml"
DOCS_DIR = ROOT / "docs"
CREDENTIALS_DIR = ROOT / "credentials"

WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
WEEKDAY_NAMES = {v: k for k, v in WEEKDAY_MAP.items()}


class ThemeConfig(BaseModel):
    id: str
    title: str
    short_label: str
    audience: str = ""
    focus: str = ""
    queries: list[tuple[str, str]] = Field(default_factory=list)
    analysis_axes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_queries(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("queries") or []
        normalized = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                normalized.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict):
                normalized.append(
                    (str(item.get("q") or item.get("query")), str(item.get("topic", "GENERAL")))
                )
        data = {**data, "queries": normalized}
        return data


class ScheduleConfig(BaseModel):
    weekday: str = "monday"
    hour: int = 7
    minute: int = 30
    timezone: str = "America/Santiago"

    @property
    def weekday_index(self) -> int:
        key = self.weekday.strip().lower()
        if key not in WEEKDAY_MAP:
            raise ValueError(
                f"weekday inválido: {self.weekday}. Usa: {', '.join(WEEKDAY_MAP)}"
            )
        return WEEKDAY_MAP[key]


class DriveConfig(BaseModel):
    enabled: bool = True
    folder_name: str = "Boletines Informativos"


class GitHubPagesConfig(BaseModel):
    enabled: bool = True
    publish_pdf: bool = True


class AppConfig(BaseModel):
    author_name: str = "Raimundo Ibieta"
    emails: list[str] = Field(default_factory=lambda: ["raimundoibieta@gmail.com"])
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    active_theme: str = "pae"
    drive: DriveConfig = Field(default_factory=DriveConfig)
    github_pages: GitHubPagesConfig = Field(default_factory=GitHubPagesConfig)
    themes: dict[str, ThemeConfig] = Field(default_factory=dict)

    def theme(self) -> ThemeConfig:
        if self.active_theme not in self.themes:
            raise ValueError(
                f"Temática '{self.active_theme}' no existe. "
                f"Disponibles: {', '.join(self.themes) or '(ninguna)'}"
            )
        return self.themes[self.active_theme]

    def save(self, path: Path = CONFIG_PATH) -> None:
        payload = self.model_dump()
        themes_out = {}
        for tid, theme in self.themes.items():
            t = theme.model_dump()
            t["queries"] = [{"q": q, "topic": topic} for q, topic in theme.queries]
            themes_out[tid] = t
        payload["themes"] = themes_out
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def load_app_config(path: Path = CONFIG_PATH) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Crea config.yaml.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Ensure theme ids match keys
    themes = raw.get("themes") or {}
    for key, theme in themes.items():
        if isinstance(theme, dict) and "id" not in theme:
            theme["id"] = key
    return AppConfig.model_validate(raw)


class Settings(BaseSettings):
    """Secretos y overrides desde .env (no van en config.yaml)."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gmail_user: str = "raimundoibieta@gmail.com"
    gmail_app_password: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Compatibilidad: si no hay config.yaml emails, usar estos
    email_to: str = ""
    author_name: str = ""
    tz: str = ""
    schedule_hour: int | None = None
    schedule_minute: int | None = None

    # Supabase (motor Mac lee boletines/correos/frecuencia de la web)
    supabase_url: str = "https://ryznnccmqyvujrlhriml.supabase.co"
    supabase_service_role_key: str = ""
    supabase_anon_key: str = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ5em5uY2NtcXl2dWpybGhyaW1sIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ3MjY0NjEsImV4cCI6MjEwMDMwMjQ2MX0."
        "lAjWArOOVgs9NnCt9ZBwYEDDAjyaThRBOgQKGMWbX-U"
    )
    supabase_worker_email: str = ""
    supabase_worker_password: str = ""

    @model_validator(mode="before")
    @classmethod
    def _drop_blank_env(cls, data: object) -> object:
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, str):
                    v = v.strip()
                    if not v:
                        continue
                cleaned[k] = v
            return cleaned
        return data

    def has_llm_key(self) -> bool:
        return bool(self.gemini_api_key or self.anthropic_api_key or self.openai_api_key)

    def validate_for_send(self, emails: list[str]) -> None:
        if not self.gmail_user or not self.gmail_app_password:
            raise ValueError(
                "Faltan GMAIL_USER o GMAIL_APP_PASSWORD en .env "
                "(contraseña de aplicación de Gmail)."
            )
        if not emails:
            raise ValueError("No hay destinatarios en config.yaml → emails")
        if not self.has_llm_key():
            raise ValueError(
                "Necesitas GEMINI_API_KEY, ANTHROPIC_API_KEY u OPENAI_API_KEY en .env."
            )


class RuntimeContext(BaseModel):
    """Config de app + secretos, listo para el pipeline."""

    app: AppConfig
    secrets: Settings

    @property
    def author_name(self) -> str:
        return self.secrets.author_name or self.app.author_name

    @property
    def emails(self) -> list[str]:
        if self.app.emails:
            return list(dict.fromkeys(e.strip() for e in self.app.emails if e.strip()))
        if self.secrets.email_to:
            return [self.secrets.email_to]
        return []

    @property
    def theme(self) -> ThemeConfig:
        return self.app.theme()

    @cached_property
    def timezone(self) -> ZoneInfo:
        tz = self.secrets.tz or self.app.schedule.timezone
        return ZoneInfo(tz)

    @property
    def schedule_weekday(self) -> int:
        return self.app.schedule.weekday_index

    @property
    def schedule_hour(self) -> int:
        if self.secrets.schedule_hour is not None:
            return self.secrets.schedule_hour
        return self.app.schedule.hour

    @property
    def schedule_minute(self) -> int:
        if self.secrets.schedule_minute is not None:
            return self.secrets.schedule_minute
        return self.app.schedule.minute

    def period_bounds(self, reference: date | None = None) -> tuple[date, date]:
        today = reference or date.today()
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        return start, end


def get_runtime() -> RuntimeContext:
    return RuntimeContext(app=load_app_config(), secrets=Settings())


# Aliases usados por código legado
def get_settings() -> Settings:
    return Settings()
