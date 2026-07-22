from __future__ import annotations

from datetime import date
from pathlib import Path

from boletin.config import OUTPUT_DIR


def sent_marker_path(bulletin_id: str, periodo_inicio: date) -> Path:
    return OUTPUT_DIR / "sent" / f"{bulletin_id}_{periodo_inicio.isoformat()}.ok"


def already_sent(bulletin_id: str, periodo_inicio: date) -> bool:
    return sent_marker_path(bulletin_id, periodo_inicio).exists()


def mark_sent(bulletin_id: str, periodo_inicio: date, note: str = "") -> None:
    path = sent_marker_path(bulletin_id, periodo_inicio)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(note or "ok", encoding="utf-8")
