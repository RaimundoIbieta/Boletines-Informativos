from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from media_analyzer.connectors.collect import (
    _parse_syndication_entries,
    normalize_handle,
)
from media_analyzer.models import AnalysisRequest, SourceDocument
from media_analyzer.pipeline import _x_handles


def _syndication_html(tweets: list[dict]) -> str:
    payload = {
        "props": {
            "pageProps": {
                "timeline": {
                    "entries": [{"content": {"tweet": t}} for t in tweets],
                }
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


def test_normalize_handle_accepts_forms():
    assert normalize_handle("@PresidenteKast") == "PresidenteKast"
    assert normalize_handle("PresidenteKast") == "PresidenteKast"
    assert normalize_handle("https://x.com/Cristiano") == "Cristiano"
    assert normalize_handle("https://twitter.com/usuario/status/123") == "usuario"
    assert normalize_handle("") == ""
    assert normalize_handle("no valido!") == ""
    # Máximo 15 caracteres en X
    assert normalize_handle("a" * 16) == ""


def test_normalize_handle_rejects_reserved_paths():
    """USER_ID aparece en plantillas de embed y no es una cuenta real."""
    for reserved in ("USER_ID", "user_id", "@intent", "https://x.com/search", "i"):
        assert normalize_handle(reserved) == ""


def test_parse_syndication_entries():
    html = _syndication_html(
        [
            {
                "full_text": "Mensaje público de prueba",
                "created_at": "Mon Aug 10 12:00:00 +0000 2026",
                "id_str": "123",
                "user": {"screen_name": "Cuenta"},
                "favorite_count": 10,
            }
        ]
    )
    entries = _parse_syndication_entries(html)
    assert len(entries) == 1
    tweet = entries[0]["content"]["tweet"]
    assert tweet["full_text"] == "Mensaje público de prueba"


def test_parse_syndication_handles_garbage():
    assert _parse_syndication_entries("<html>sin datos</html>") == []
    assert _parse_syndication_entries("") == []


def test_x_handles_from_configuration_and_documents():
    request = AnalysisRequest(
        topic="fútbol",
        period_start=date.today() - timedelta(days=10),
        period_end=date.today(),
        configuration={"x_accounts": ["@Cristiano", "https://x.com/PresidenteKast"]},
    )
    cited = SourceDocument(
        id="x_1",
        source_type="x",
        title="post citado",
        url="https://x.com/GaelYeomans/status/1",
        author="@GaelYeomans",
        published_at=datetime.now(timezone.utc),
    )
    handles = _x_handles(request, [cited])
    assert "Cristiano" in handles
    assert "PresidenteKast" in handles
    assert "GaelYeomans" in handles


def test_x_handles_deduplicates_case_insensitive():
    request = AnalysisRequest(
        topic="tema",
        period_start=date.today() - timedelta(days=5),
        period_end=date.today(),
        configuration={"x_accounts": ["@Cristiano", "cristiano", "CRISTIANO"]},
    )
    assert _x_handles(request, []) == ["Cristiano"]


def test_x_handles_empty_without_config():
    request = AnalysisRequest(
        topic="tema",
        period_start=date.today() - timedelta(days=5),
        period_end=date.today(),
    )
    assert _x_handles(request, []) == []
