from __future__ import annotations

from datetime import date
from pathlib import Path

from boletin.config import OUTPUT_DIR


def sent_marker_path(bulletin_id: str, periodo_inicio: date, periodo_fin: date) -> Path:
# La clave lleva inicio y fin: en modo quincenal el envío del día 15 (1→15)
# y el del último día (1→fin de mes) comparten inicio y se distinguen por el fin.
    return (
        OUTPUT_DIR
        / "sent"
        / f"{bulletin_id}_{periodo_inicio.isoformat()}_{periodo_fin.isoformat()}.ok"
    )


def already_sent(bulletin_id: str, periodo_inicio: date, periodo_fin: date) -> bool:
    return sent_marker_path(bulletin_id, periodo_inicio, periodo_fin).exists()


def mark_sent(
    bulletin_id: str, periodo_inicio: date, periodo_fin: date, note: str = ""
) -> None:
    path = sent_marker_path(bulletin_id, periodo_inicio, periodo_fin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(note or "ok", encoding="utf-8")
