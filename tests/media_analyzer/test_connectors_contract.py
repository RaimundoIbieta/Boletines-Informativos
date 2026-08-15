from __future__ import annotations

from media_analyzer.connectors.collect import ingest_urls
from media_analyzer.validation import validate_public_http_url


def test_ingest_urls_rejects_ssrf(monkeypatch):
    # No debe intentar fetch de localhost
    docs = ingest_urls(["http://127.0.0.1/secret"])
    assert docs == []


def test_connector_contract_validate_url():
    # Contrato: URLs públicas pasan validación sin DNS
    assert validate_public_http_url("https://www.biobiochile.cl/noticia", resolve_dns=False)
