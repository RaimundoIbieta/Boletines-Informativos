from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from boletin.config import DOCS_DIR
from boletin.models import BoletinSemanal

logger = logging.getLogger(__name__)

DATA_PATH = DOCS_DIR / "data" / "boletines.json"
PDF_DIR = DOCS_DIR / "boletines"


def _load_index() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_index(items: list[dict]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def publish_to_pages(
    boletin: BoletinSemanal,
    pdf_path: Path,
    *,
    drive_view_link: str = "",
    drive_download_link: str = "",
    copy_pdf: bool = True,
    author_name: str = "",
) -> dict:
    """Actualiza el índice del sitio GitHub Pages y opcionalmente copia el PDF."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    stamp = f"{boletin.periodo_inicio.isoformat()}_{boletin.periodo_fin.isoformat()}"
    entry_id = f"{boletin.theme_id}_{stamp}"
    local_pdf_name = f"{entry_id}.pdf"
    local_pdf_rel = f"boletines/{local_pdf_name}"

    if copy_pdf:
        dest = PDF_DIR / local_pdf_name
        shutil.copy2(pdf_path, dest)
        logger.info("PDF publicado en sitio: %s", dest)

    entry = {
        "id": entry_id,
        "theme_id": boletin.theme_id,
        "theme_title": boletin.theme_title,
        "theme_label": boletin.theme_label,
        "author": author_name,
        "periodo_inicio": boletin.periodo_inicio.isoformat(),
        "periodo_fin": boletin.periodo_fin.isoformat(),
        "generado_el": boletin.generado_el.isoformat(),
        "noticias": len(boletin.noticias),
        "pdf_local": local_pdf_rel if copy_pdf else "",
        "drive_view_link": drive_view_link,
        "drive_download_link": drive_download_link,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    items = [e for e in _load_index() if e.get("id") != entry_id]
    items.insert(0, entry)
    _save_index(items)
    logger.info("Índice Pages actualizado (%s entradas)", len(items))
    return entry
