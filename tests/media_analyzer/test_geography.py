from __future__ import annotations

from media_analyzer.geography import detect_geography
from media_analyzer.models import SourceDocument


def test_detect_chile_places():
    docs = [
        SourceDocument(
            id="d1",
            title="Protesta en Providencia y Valparaíso",
            excerpt="Hechos en Concepción y Chile",
            text="La marcha partió en Providencia hacia Las Condes. También hubo eco en Valparaíso.",
        )
    ]
    geos = detect_geography(docs)
    places = {g.place for g in geos}
    assert "Chile" in places
    assert "Providencia" in places or "Valparaíso" in places or "Concepción" in places
    assert any(g.relation == "mentioned_location" for g in geos)
