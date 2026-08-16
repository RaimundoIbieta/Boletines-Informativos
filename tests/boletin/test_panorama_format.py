from __future__ import annotations

from datetime import date

from boletin.analyzer import _parse_boletin
from boletin.config import ThemeConfig
from boletin.formatter import to_html_email, to_markdown
from boletin.models import BoletinSemanal, NoticiaAnalizada, SeccionSintesis
from boletin.pdf_generator import generate_pdf


def _panorama_theme() -> ThemeConfig:
    return ThemeConfig(
        id="chile_mundo",
        title="Panorama Quincenal de Chile y el Mundo",
        short_label="Chile y Mundo · 15/fin",
        sections=["Economía", "Social", "Política", "Nacional", "Internacional"],
        cadence="semimonthly",
        output_format="panorama_sectional",
    )


def _standard_theme() -> ThemeConfig:
    return ThemeConfig(
        id="pae",
        title="PAE",
        short_label="PAE",
        sections=[],
        cadence="weekly",
        output_format="standard",
    )


def test_theme_panorama_detection():
    assert _panorama_theme().is_panorama is True
    assert _standard_theme().is_panorama is False
    # Heurística: quincenal + secciones sin columna aún migrada
    heuristic = ThemeConfig(
        id="x",
        title="Panorama",
        short_label="X",
        sections=["Economía", "Social"],
        cadence="semimonthly",
        output_format="standard",
    )
    assert heuristic.is_panorama is True


def test_parse_boletin_panorama_schema():
    raw = """
    {
      "noticias": [
        {
          "titular": "Lluvia intensa en la zona central",
          "fuente": "La Tercera",
          "fecha": "2026-08-15",
          "link": "https://www.latercera.com/nacional/noticia/lluvia/",
          "resumen": "Un sistema frontal dejó precipitaciones considerables en la Región Metropolitana.",
          "tema": "Nacional",
          "relevancia": 9
        },
        {
          "titular": "Banco Central mantiene la tasa",
          "fuente": "DF",
          "fecha": "2026-08-12",
          "link": "https://www.df.cl/economia/tasa",
          "resumen": "El instituto emisor dejó la TPM sin cambios.",
          "tema": "Economía",
          "relevancia": 8
        }
      ],
      "sintesis_secciones": [
        {"seccion": "Nacional", "analisis": "El frente de mal tiempo marcó la agenda territorial."},
        {"seccion": "Economía", "analisis": "La política monetaria se mantuvo en modo pausa."}
      ],
      "sintesis": "La primera quincena cerró con clima extremo y una pausa monetaria."
    }
    """
    boletin = _parse_boletin(
        raw,
        date(2026, 8, 1),
        date(2026, 8, 15),
        date(2026, 8, 15),
        _panorama_theme(),
    )
    assert boletin.is_panorama
    assert len(boletin.noticias) == 2
    assert boletin.noticias[0].tema in {"ECONOMIA", "ECONOMÍA", "NACIONAL"}
    assert len(boletin.sintesis_secciones) == 2
    assert boletin.conclusion_title == "Conclusión de la primera quincena"
    assert not boletin.noticias[0].comentario


def test_to_markdown_panorama_structure():
    boletin = BoletinSemanal(
        periodo_inicio=date(2026, 8, 1),
        periodo_fin=date(2026, 8, 15),
        generado_el=date(2026, 8, 15),
        noticias=[
            NoticiaAnalizada(
                titular="Lluvia en la zona central",
                fuente="La Tercera",
                fecha="2026-08-15",
                link="https://example.com/lluvia",
                resumen="Precipitaciones intensas en la RM.",
                tema="NACIONAL",
                relevancia=9,
            ),
            NoticiaAnalizada(
                titular="TPM sin cambios",
                fuente="DF",
                fecha="2026-08-12",
                link="https://example.com/tpm",
                resumen="El BC mantuvo la tasa.",
                tema="ECONOMIA",
                relevancia=8,
            ),
        ],
        sintesis="La primera quincena mezcló clima extremo y pausa monetaria.",
        sintesis_secciones=[
            SeccionSintesis(seccion="Nacional", analisis="El clima dominó la agenda interna."),
            SeccionSintesis(seccion="Economía", analisis="La política monetaria se mantuvo cauta."),
        ],
        theme_id="chile_mundo",
        theme_title="Panorama Quincenal de Chile y el Mundo",
        theme_label="Chile y Mundo · 15/fin",
        sections=["Economía", "Social", "Política", "Nacional", "Internacional"],
        cadence="semimonthly",
        output_format="panorama_sectional",
    )
    md = to_markdown(boletin)
    assert "## Nacional" in md
    assert "**Análisis de la sección Nacional**" in md
    assert "## Conclusión de la primera quincena" in md
    assert "**Comentario**" not in md
    html = to_html_email(boletin)
    assert "Análisis de la sección" in html
    assert "Conclusión de la primera quincena" in html


def test_standard_layout_keeps_comentario(tmp_path):
    boletin = BoletinSemanal(
        periodo_inicio=date(2026, 8, 8),
        periodo_fin=date(2026, 8, 14),
        generado_el=date(2026, 8, 14),
        noticias=[
            NoticiaAnalizada(
                titular="Cambio de gabinete",
                fuente="Emol",
                fecha="2026-08-12",
                link="https://example.com/gabinete",
                resumen="Hubo un ajuste ministerial.",
                comentario="Implica reordenamiento político.",
                riesgos="Incertidumbre de corto plazo.",
                oportunidades="Señal de control.",
                tema="POLITICA",
                relevancia=9,
            )
        ],
        sintesis="Semana marcada por el gabinete.",
        theme_id="politica",
        theme_title="Política Chilena",
        theme_label="Política",
        output_format="standard",
    )
    md = to_markdown(boletin)
    assert "**Comentario**" in md
    assert "**Riesgos**" in md
    pdf_path = tmp_path / "standard.pdf"
    generate_pdf(boletin, pdf_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000


def test_generate_pdf_panorama(tmp_path):
    boletin = BoletinSemanal(
        periodo_inicio=date(2026, 8, 1),
        periodo_fin=date(2026, 8, 15),
        generado_el=date(2026, 8, 15),
        noticias=[
            NoticiaAnalizada(
                titular="Lluvia en la zona central",
                fuente="La Tercera",
                fecha="2026-08-15",
                link="https://example.com/lluvia",
                resumen="Precipitaciones intensas en la RM.",
                tema="NACIONAL",
                relevancia=9,
            )
        ],
        sintesis="Quincena marcada por el frente de mal tiempo.",
        sintesis_secciones=[
            SeccionSintesis(seccion="Nacional", analisis="El clima concentró la atención."),
        ],
        theme_id="chile_mundo",
        theme_title="Panorama Quincenal de Chile y el Mundo",
        theme_label="Chile y Mundo · 15/fin",
        sections=["Economía", "Social", "Política", "Nacional", "Internacional"],
        cadence="semimonthly",
        output_format="panorama_sectional",
    )
    pdf_path = tmp_path / "panorama.pdf"
    generate_pdf(boletin, pdf_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000
