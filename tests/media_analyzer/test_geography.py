from __future__ import annotations

from datetime import date

from media_analyzer.geography import classify_geographic_scope, detect_geography
from media_analyzer.models import AnalysisRequest, SourceDocument


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


def _request(**kwargs) -> AnalysisRequest:
    return AnalysisRequest(
        topic="reforma de pensiones",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 15),
        territory_label=kwargs.pop("territory_label", "Chile"),
        **kwargs,
    )


def _doc(doc_id: str, text: str, url: str = "") -> SourceDocument:
    return SourceDocument(id=doc_id, title=text, text=text, url=url)


def test_national_target_document():
    result = classify_geographic_scope(
        [_doc("cl", "Chile debate una nueva reforma de pensiones")], _request()
    )[0]
    assert result.scope == "target_territory"
    assert result.foreign_countries == []


def test_foreign_document_is_kept_and_classified():
    doc = _doc("de", "Alemania debate su reforma de pensiones")
    result = classify_geographic_scope([doc], _request())[0]
    assert result.scope == "international"
    assert result.foreign_countries == ["Alemania"]
    assert doc.included is True
    assert doc.exclusion_reason == ""


def test_target_and_foreign_is_cross_border():
    result = classify_geographic_scope(
        [_doc("mix", "Chile compara su reforma de pensiones con el modelo de Alemania")],
        _request(),
    )[0]
    assert result.scope == "cross_border"
    assert "Alemania" in result.foreign_countries
    assert "Chile" in result.target_places


def test_unknown_location_is_not_inferred():
    result = classify_geographic_scope(
        [_doc("unknown", "La reforma de pensiones divide a los expertos")], _request()
    )[0]
    assert result.scope == "undetermined"
    assert result.confidence == 0.0


def test_geographic_metadata_is_attached_to_document():
    doc = _doc("pe", "Perú discute cambios a las pensiones")
    classify_geographic_scope([doc], _request())
    assert doc.metadata["geographic_scope"] == "international"
    assert doc.metadata["foreign_countries"] == ["Perú"]


def test_regional_target_separates_rest_of_chile():
    request = _request(
        territory_level="regional",
        territory_label="Región Metropolitana",
        region_code="13",
    )
    target, rest = classify_geographic_scope(
        [
            _doc("rm", "La reforma de pensiones genera debate en Santiago"),
            _doc("cl", "Chile debate la reforma de pensiones"),
        ],
        request,
    )
    assert target.scope == "target_territory"
    assert rest.scope == "rest_of_country"


def test_regional_target_with_foreign_context_is_cross_border():
    request = _request(
        territory_level="regional",
        territory_label="Región Metropolitana",
        region_code="13",
    )
    result = classify_geographic_scope(
        [_doc("mix", "Santiago analiza el modelo de pensiones de España")], request
    )[0]
    assert result.scope == "cross_border"
    assert result.foreign_countries == ["España"]


def test_country_matching_uses_word_boundaries():
    """«peru» no puede encontrarse dentro de una palabra más larga."""
    result = classify_geographic_scope(
        [_doc("boundary", "El perusal técnico de la reforma continúa")], _request()
    )[0]
    assert result.foreign_countries == []


def test_foreign_source_about_target_is_cross_border():
    """Una mención de Chile publicada en España se conserva como cruce territorial."""
    doc = _doc(
        "es-source",
        "Chile debate una reforma de pensiones",
        "https://ejemplo.es/noticia",
    )
    result = classify_geographic_scope([doc], _request())[0]
    assert result.scope == "cross_border"
    assert result.source_country == "España"
    assert "España" in result.foreign_countries


def test_chilean_source_without_explicit_place_is_target_conversation():
    doc = _doc(
        "cl-source",
        "Expertos debaten la reforma de pensiones",
        "https://ejemplo.cl/noticia",
    )
    result = classify_geographic_scope([doc], _request())[0]
    assert result.scope == "target_territory"
    assert result.source_country == "Chile"


def test_generic_domain_does_not_invent_source_country():
    doc = _doc(
        "com-source",
        "Expertos debaten la reforma de pensiones",
        "https://ejemplo.com/noticia",
    )
    result = classify_geographic_scope([doc], _request())[0]
    assert result.scope == "undetermined"
    assert result.source_country == ""
