from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from boletin.config import AppConfig, RuntimeContext, ScheduleConfig, Settings, ThemeConfig

logger = logging.getLogger(__name__)


@dataclass
class RemoteBulletin:
    id: str
    user_id: str
    title: str
    short_label: str
    audience: str
    focus: str
    queries: list[tuple[str, str]]
    analysis_axes: list[str]
    schedule_weekday: str
    schedule_hour: int
    schedule_minute: int
    emails: list[str]
    active: bool = True

    def theme_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (self.short_label or "boletin").lower()).strip("_")
        return f"{slug[:24]}_{self.id[:8]}"

    def to_theme(self) -> ThemeConfig:
        return ThemeConfig(
            id=self.theme_id(),
            title=self.title,
            short_label=self.short_label,
            audience=self.audience or "",
            focus=self.focus or "",
            queries=self.queries,
            analysis_axes=self.analysis_axes,
        )


def supabase_configured(secrets: Settings) -> bool:
    if not secrets.supabase_url:
        return False
    if secrets.supabase_service_role_key:
        return True
    return bool(
        secrets.supabase_anon_key
        and secrets.supabase_worker_email
        and secrets.supabase_worker_password
    )


def _auth_headers(secrets: Settings) -> dict[str, str]:
    base = secrets.supabase_url.rstrip("/")
    if secrets.supabase_service_role_key:
        key = secrets.supabase_service_role_key.strip()
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    anon = secrets.supabase_anon_key.strip()
    email = secrets.supabase_worker_email.strip().lower()
    password = secrets.supabase_worker_password
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{base}/auth/v1/token?grant_type=password",
            headers={"apikey": anon, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Supabase login sin access_token.")
    return {
        "apikey": anon,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _parse_queries(raw: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in raw or []:
        if isinstance(item, dict):
            q = str(item.get("q") or item.get("query") or "").strip()
            topic = str(item.get("topic") or "GENERAL").strip() or "GENERAL"
            if q:
                out.append((q, topic))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]), str(item[1])))
    return out


def _from_row(row: dict[str, Any]) -> RemoteBulletin:
    emails = [
        str(r.get("email", "")).strip().lower()
        for r in (row.get("bulletin_recipients") or [])
        if r.get("email")
    ]
    emails = list(dict.fromkeys(e for e in emails if e))
    return RemoteBulletin(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        title=str(row.get("title") or "Boletín"),
        short_label=str(row.get("short_label") or "Boletín"),
        audience=str(row.get("audience") or ""),
        focus=str(row.get("focus") or ""),
        queries=_parse_queries(row.get("queries")),
        analysis_axes=[str(x) for x in (row.get("analysis_axes") or []) if str(x).strip()],
        schedule_weekday=str(row.get("schedule_weekday") or "monday").lower(),
        schedule_hour=int(row.get("schedule_hour") if row.get("schedule_hour") is not None else 7),
        schedule_minute=int(row.get("schedule_minute") if row.get("schedule_minute") is not None else 30),
        emails=emails,
        active=bool(row.get("active", True)),
    )


def fetch_active_bulletins(secrets: Settings) -> list[RemoteBulletin]:
    if not supabase_configured(secrets):
        return []
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    with httpx.Client(timeout=45.0) as client:
        resp = client.get(
            f"{base}/rest/v1/bulletins",
            headers=headers,
            params={
                "active": "eq.true",
                "select": "*,bulletin_recipients(email)",
                "order": "created_at.asc",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    bulletins = [_from_row(r) for r in rows]
    usable = [b for b in bulletins if b.emails and b.queries]
    skipped = len(bulletins) - len(usable)
    if skipped:
        logger.info("Omitidos %s boletín(es) sin correos o sin búsquedas.", skipped)
    return usable


def runtime_for_bulletin(base: RuntimeContext, remote: RemoteBulletin) -> RuntimeContext:
    theme = remote.to_theme()
    app = AppConfig(
        author_name=base.app.author_name,
        emails=list(remote.emails),
        schedule=ScheduleConfig(
            weekday=remote.schedule_weekday,
            hour=remote.schedule_hour,
            minute=remote.schedule_minute,
            timezone=base.app.schedule.timezone,
        ),
        active_theme=theme.id,
        drive=base.app.drive,
        github_pages=base.app.github_pages,
        themes={theme.id: theme},
    )
    return RuntimeContext(app=app, secrets=base.secrets)


def fetch_bulletin_by_id(secrets: Settings, bulletin_id: str) -> RemoteBulletin | None:
    if not supabase_configured(secrets):
        return None
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    with httpx.Client(timeout=45.0) as client:
        resp = client.get(
            f"{base}/rest/v1/bulletins",
            headers=headers,
            params={
                "id": f"eq.{bulletin_id}",
                "select": "*,bulletin_recipients(email)",
                "limit": "1",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    if not rows:
        return None
    remote = _from_row(rows[0])
    if not remote.emails or not remote.queries:
        return None
    return remote


def fetch_pending_send_requests(secrets: Settings) -> list[dict[str, Any]]:
    if not supabase_configured(secrets):
        return []
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{base}/rest/v1/send_requests",
            headers=headers,
            params={
                "status": "eq.pending",
                "select": "id,bulletin_id,user_id,created_at",
                "order": "created_at.asc",
                "limit": "20",
            },
        )
        if resp.status_code == 404:
            logger.warning("Tabla send_requests no existe; ejecuta supabase/send_requests.sql")
            return []
        resp.raise_for_status()
        return resp.json() or []


def update_send_request(
    secrets: Settings,
    request_id: str,
    *,
    status: str,
    error: str | None = None,
) -> None:
    if not supabase_configured(secrets):
        return
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    payload: dict[str, Any] = {
        "status": status,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is not None:
        payload["error"] = error
    with httpx.Client(timeout=30.0) as client:
        resp = client.patch(
            f"{base}/rest/v1/send_requests",
            headers={**headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{request_id}"},
            json=payload,
        )
        resp.raise_for_status()


def already_sent_remote(secrets: Settings, bulletin_id: str, periodo_inicio: str) -> bool:
    """True si ya hay un run publicado en Supabase para ese boletín/periodo."""
    if not supabase_configured(secrets):
        return False
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{base}/rest/v1/bulletin_runs",
                headers=headers,
                params={
                    "bulletin_id": f"eq.{bulletin_id}",
                    "periodo_inicio": f"eq.{periodo_inicio}",
                    "status": "eq.published",
                    "select": "id",
                    "limit": "1",
                },
            )
            resp.raise_for_status()
            return bool(resp.json())
    except Exception as exc:
        logger.warning("No se pudo consultar runs previos: %s", exc)
        return False


def record_run(
    secrets: Settings,
    *,
    bulletin_id: str,
    user_id: str,
    periodo_inicio: str,
    periodo_fin: str,
    noticias: int,
    pdf_url: str = "",
    drive_url: str = "",
    status: str = "published",
) -> None:
    if not supabase_configured(secrets):
        return
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    payload = {
        "bulletin_id": bulletin_id,
        "user_id": user_id,
        "periodo_inicio": periodo_inicio,
        "periodo_fin": periodo_fin,
        "noticias": noticias,
        "pdf_url": pdf_url or None,
        "drive_url": drive_url or None,
        "status": status,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/rest/v1/bulletin_runs",
                headers={**headers, "Prefer": "return=minimal"},
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("No se pudo registrar run en Supabase: %s", exc)
