from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from boletin.config import Settings
from boletin.supabase_store import _auth_headers, supabase_configured

logger = logging.getLogger(__name__)


def claim_request(
    secrets: Settings,
    worker_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    if not supabase_configured(secrets):
        return None
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    payload: dict[str, Any] = {"p_worker_id": worker_id}
    if request_id:
        payload["p_request_id"] = request_id
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{base}/rest/v1/rpc/claim_media_analysis_request",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            logger.warning("claim_media_analysis_request: %s", resp.text[:300])
            return None
        data = resp.json()
        return data or None


def update_request(
    secrets: Settings,
    request_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    current_stage: str | None = None,
    error: str | None = None,
) -> None:
    if not supabase_configured(secrets):
        return
    payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if status is not None:
        payload["status"] = status
    if progress is not None:
        payload["progress"] = progress
    if current_stage is not None:
        payload["current_stage"] = current_stage
    if error is not None:
        payload["error"] = error[:800]
    if status in {"completed", "partial", "failed"}:
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    base = secrets.supabase_url.rstrip("/")
    headers = {**_auth_headers(secrets), "Prefer": "return=minimal"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.patch(
            f"{base}/rest/v1/media_analysis_requests",
            headers=headers,
            params={"id": f"eq.{request_id}"},
            json=payload,
        )
        resp.raise_for_status()


def fetch_request(secrets: Settings, request_id: str) -> dict[str, Any] | None:
    if not supabase_configured(secrets):
        return None
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{base}/rest/v1/media_analysis_requests",
            headers=headers,
            params={"id": f"eq.{request_id}", "select": "*", "limit": "1"},
        )
        resp.raise_for_status()
        rows = resp.json() or []
        return rows[0] if rows else None


def fetch_inputs(secrets: Settings, request_id: str) -> list[dict[str, Any]]:
    if not supabase_configured(secrets):
        return []
    base = secrets.supabase_url.rstrip("/")
    headers = _auth_headers(secrets)
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"{base}/rest/v1/media_analysis_inputs",
            headers=headers,
            params={"request_id": f"eq.{request_id}", "select": "*"},
        )
        resp.raise_for_status()
        return resp.json() or []


def save_documents(secrets: Settings, request_id: str, documents: list[dict[str, Any]]) -> None:
    if not documents or not supabase_configured(secrets):
        return
    base = secrets.supabase_url.rstrip("/")
    headers = {**_auth_headers(secrets), "Prefer": "return=minimal"}
    rows = []
    for d in documents:
        rows.append(
            {
                "request_id": request_id,
                "source_type": d.get("source_type") or "news",
                "title": d.get("title"),
                "publisher": d.get("publisher"),
                "author": d.get("author"),
                "url": d.get("url"),
                "canonical_url": d.get("canonical_url"),
                "published_at": d.get("published_at"),
                "excerpt": (d.get("excerpt") or "")[:800],
                "content_hash": d.get("content_hash"),
                "included": d.get("included", True),
                "exclusion_reason": d.get("exclusion_reason") or None,
                "engagement": d.get("engagement") or {},
                "metadata": d.get("metadata") or {},
            }
        )
    with httpx.Client(timeout=60.0) as client:
        # Insertar en lotes
        for i in range(0, len(rows), 50):
            resp = client.post(
                f"{base}/rest/v1/media_analysis_documents",
                headers=headers,
                json=rows[i : i + 50],
            )
            resp.raise_for_status()


def save_result(secrets: Settings, request_id: str, user_id: str, report: dict[str, Any]) -> None:
    if not supabase_configured(secrets):
        return
    base = secrets.supabase_url.rstrip("/")
    headers = {**_auth_headers(secrets), "Prefer": "resolution=merge-duplicates,return=minimal"}
    row = {
        "request_id": request_id,
        "user_id": user_id,
        "executive_summary": report.get("executive_summary"),
        "findings": report.get("findings") or [],
        "actors": report.get("actors") or [],
        "narratives": report.get("narratives") or [],
        "trends": report.get("trends") or [],
        "sentiment": report.get("sentiment") or {},
        "geography": report.get("geography") or {},
        "coverage_metrics": report.get("coverage") or {},
        "methodology": report.get("methodology") or {},
        "warnings": report.get("warnings") or [],
        "model_provider": report.get("model_provider"),
        "model_name": report.get("model_name"),
        "prompt_version": report.get("prompt_version") or "media-v1",
    }
    with httpx.Client(timeout=45.0) as client:
        resp = client.post(
            f"{base}/rest/v1/media_analysis_results",
            headers=headers,
            json=row,
        )
        resp.raise_for_status()


def save_artifact_meta(
    secrets: Settings,
    request_id: str,
    user_id: str,
    *,
    kind: str,
    storage_path: str,
    mime_type: str,
    size_bytes: int,
) -> None:
    if not supabase_configured(secrets):
        return
    base = secrets.supabase_url.rstrip("/")
    headers = {**_auth_headers(secrets), "Prefer": "return=minimal"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{base}/rest/v1/media_analysis_artifacts",
            headers=headers,
            json={
                "request_id": request_id,
                "user_id": user_id,
                "kind": kind,
                "storage_path": storage_path,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
            },
        )
        resp.raise_for_status()


def upload_export_files(
    secrets: Settings,
    request_id: str,
    user_id: str,
    output_dir: str | Any,
) -> list[dict[str, Any]]:
    """Sube exportaciones locales al bucket privado media-analysis-results."""
    from pathlib import Path

    if not supabase_configured(secrets):
        return []
    out = Path(output_dir)
    mapping = {
        "report.json": ("json", "application/json"),
        "report.md": ("markdown", "text/markdown"),
        "documents.csv": ("csv", "text/csv"),
        "report.html": ("html", "text/html"),
        "report.pdf": ("pdf", "application/pdf"),
    }
    base = secrets.supabase_url.rstrip("/")
    key = secrets.supabase_service_role_key
    uploaded: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        for name, (kind, mime) in mapping.items():
            path = out / name
            if not path.exists():
                continue
            storage_path = f"{user_id}/{request_id}/{name}"
            data = path.read_bytes()
            resp = client.post(
                f"{base}/storage/v1/object/media-analysis-results/{storage_path}",
                headers={
                    "Authorization": f"Bearer {key}",
                    "apikey": key,
                    "Content-Type": mime,
                    "x-upsert": "true",
                },
                content=data,
            )
            if resp.status_code >= 400:
                logger.warning("Upload %s falló: %s", name, resp.text[:300])
                continue
            save_artifact_meta(
                secrets,
                request_id,
                user_id,
                kind=kind,
                storage_path=storage_path,
                mime_type=mime,
                size_bytes=len(data),
            )
            uploaded.append({"kind": kind, "storage_path": storage_path, "bytes": len(data)})
    return uploaded
