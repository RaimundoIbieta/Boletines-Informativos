from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
import trafilatura

from media_analyzer.validation import validate_public_http_url

USER_AGENT = "MediaAnalyzer/1.0 (+https://github.com/RaimundoIbieta/Boletines-Informativos)"


def fetch_url_text(url: str, *, max_bytes: int = 2_000_000) -> tuple[str, str]:
    url = validate_public_http_url(url)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(
        headers=headers,
        timeout=25.0,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        # Bloquear redirects a hosts privados
        resp = client.get(url)
        final = str(resp.url)
        validate_public_http_url(final)
        if len(resp.content) > max_bytes:
            raise ValueError("Respuesta demasiado grande")
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "text/" not in ctype and "json" not in ctype:
            raise ValueError(f"Tipo no soportado: {ctype or 'desconocido'}")
        html = resp.text
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    text = trafilatura.extract(html, favor_recall=True) or ""
    if not text.strip():
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
    return title, text[:12000]
