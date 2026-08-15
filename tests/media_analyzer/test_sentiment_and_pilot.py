from __future__ import annotations

from datetime import date
from pathlib import Path

from media_analyzer.extractors.files import extract_text_file
from media_analyzer.models import AnalysisRequest, SourceDocument
from media_analyzer.pipeline import run_analysis
from media_analyzer.sentiment import _heuristic_sentiment, analyze_with_llm


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extract_txt():
    title, text = extract_text_file(FIXTURES / "presidencial_piloto.txt")
    assert "Kast" in text
    assert title.endswith(".txt")


def test_heuristic_sentiment_directed():
    text = "Hay rechazo y crítica hacia Kast tras el escándalo y la polémica."
    obs = _heuristic_sentiment(text, "Kast")
    assert obs.label == "negativo"
    assert "Kast" in obs.evidence or "kast" in obs.evidence.lower()
    assert obs.score < 0


def test_sentiment_cites_existing_documents():
    docs = [
        SourceDocument(
            id="doc_a",
            title="Apoyo a Jara mejora confianza",
            excerpt="Jara recibe apoyo positivo",
            text="La ciudadana muestra confianza y apoyo a Jara en Chile.",
        )
    ]
    req = AnalysisRequest(
        topic="próximo presidente de Chile",
        actors=["Jara", "Kast"],
        period_start=date(2026, 7, 1),
        period_end=date(2026, 8, 14),
        territory_label="Chile",
        enabled_sources=[],
    )
    report = analyze_with_llm(req, docs, gemini_api_key="")
    assert report.actors
    jara = next(a for a in report.actors if a.name == "Jara")
    assert jara.mentions >= 1
    assert jara.sample_quotes
    assert report.sentiment.get("observations", 0) >= 1
    # Evidencia ligada a documentos reales (heurística usa excerpt/text del doc)
    assert any("Jara" in q or "confianza" in q.lower() or "apoyo" in q.lower() for q in jara.sample_quotes)


def test_pilot_presidencial_offline(tmp_path):
    """Caso piloto offline: tema presidencial, actores, territorio nacional, archivos."""
    fixture = FIXTURES / "presidencial_piloto.txt"
    req = AnalysisRequest(
        topic="próximo presidente de Chile",
        actors=["Kast", "Matthei", "Jara"],
        period_start=date(2026, 7, 15),
        period_end=date(2026, 8, 14),
        territory_level="national",
        territory_label="Chile",
        enabled_sources=[],  # solo archivo local
        file_paths=[str(fixture)],
    )
    out = tmp_path / "piloto"
    report = run_analysis(req, gemini_api_key="", output_dir=out)
    assert report.coverage.documents_included >= 1
    assert report.topic.startswith("próximo presidente")
    assert any(a.name in {"Kast", "Matthei", "Jara"} for a in report.actors)
    assert (out / "report.json").exists()
    assert (out / "documents.csv").exists()
    assert (out / "report.html").exists()
    assert (out / "report.pdf").exists()
    # Hallazgos deben referenciar evidencia/cobertura
    assert report.findings
    assert report.warnings  # cobertura parcial redes
    # Geografía chilena detectada
    places = (report.geography or {}).get("top_places") or {}
    assert places or report.geography.get("mentions")
