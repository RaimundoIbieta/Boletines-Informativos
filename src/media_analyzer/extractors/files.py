from __future__ import annotations

from pathlib import Path


def extract_text_file(path: str | Path, *, max_chars: int = 200_000) -> tuple[str, str]:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Archivo no encontrado: {p}")
    if p.stat().st_size > 5_000_000:
        raise ValueError("Archivo demasiado grande")
    suffix = p.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
        text = p.read_text(encoding="utf-8", errors="ignore")
        return p.name, text[:max_chars]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("Falta pypdf para leer PDF") from exc
        reader = PdfReader(str(p))
        if getattr(reader, "is_encrypted", False):
            raise ValueError("PDF cifrado no soportado")
        parts = []
        for page in reader.pages[:80]:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("PDF sin texto extraíble")
        return p.name, text[:max_chars]
    raise ValueError(f"Extensión no soportada: {suffix}")
