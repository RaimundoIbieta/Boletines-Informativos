from __future__ import annotations

import logging
import re
import urllib.request
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from boletin.formatter import _tema_label
from boletin.models import BoletinSemanal, NoticiaAnalizada

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent / "assets" / "fonts"
DEJAVU_REGULAR = ASSETS / "DejaVuSans.ttf"
DEJAVU_BOLD = ASSETS / "DejaVuSans-Bold.ttf"
DEJAVU_URLS = {
    DEJAVU_REGULAR: "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf",
    DEJAVU_BOLD: "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf",
}
SYSTEM_FALLBACKS = [
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]

# Paleta institucional
INK = (26, 35, 50)
MUTED = (90, 105, 120)
TEAL = (11, 79, 74)
TEAL_SOFT = (232, 245, 243)
LINE = (220, 228, 234)
RISK_BG = (253, 242, 240)
RISK_ACCENT = (153, 50, 42)
OPP_BG = (240, 247, 244)
OPP_ACCENT = (30, 107, 74)
WHITE = (255, 255, 255)
PAGE_BG = (250, 251, 252)


def _ensure_fonts() -> tuple[Path, Path]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    try:
        for path, url in DEJAVU_URLS.items():
            if path.exists() and path.stat().st_size > 1000:
                continue
            logger.info("Descargando fuente %s…", path.name)
            urllib.request.urlretrieve(url, path)
        return DEJAVU_REGULAR, DEJAVU_BOLD
    except Exception as exc:
        logger.warning("No se pudieron descargar DejaVu (%s); usando fuente del sistema.", exc)
        for candidate in SYSTEM_FALLBACKS:
            if candidate.exists():
                return candidate, candidate
        raise RuntimeError(
            "No hay fuentes Unicode disponibles para generar el PDF."
        ) from exc


def _clean_title(title: str, source: str) -> str:
    t = re.sub(r"\s+", " ", title).strip()
    # Quita sufijos " - Medio" / " | Medio" si repiten la fuente
    t = re.sub(r"\s*[-|–—]\s*[^-|–—]{2,60}$", "", t).strip()
    if source and t.lower().endswith(source.lower()):
        t = t[: -len(source)].rstrip(" -|–—")
    return t or title.strip()


def _short_link_label(url: str) -> str:
    if "news.google.com" in url:
        return "Abrir noticia (Google News)"
    # Host limpio
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    host = m.group(1) if m else "enlace"
    return f"Abrir en {host}"


class BoletinPDF(FPDF):
    def __init__(self, *args, author_name: str = "Raimundo Ibieta", **kwargs):
        super().__init__(*args, **kwargs)
        self._periodo_label = ""
        self._author_name = author_name

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_fill_color(*TEAL)
        self.rect(0, 0, 210, 9, "F")
        self.set_xy(16, 2)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*WHITE)
        self.cell(110, 5, f"Boletín PAE · {self._author_name}", align="L")
        self.cell(0, 5, self._periodo_label, align="R")
        self.set_y(14)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(*LINE)
        self.line(16, self.get_y(), 194, self.get_y())
        self.set_y(-12)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*MUTED)
        self.cell(110, 8, f"Preparado por {self._author_name} · Uso interno", align="L")
        self.cell(0, 8, f"Página {self.page_no()}/{{nb}}", align="R")


def _reset(pdf: BoletinPDF) -> None:
    pdf.set_x(pdf.l_margin)


def _ensure_space(pdf: BoletinPDF, needed: float) -> None:
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()
        _reset(pdf)


def _draw_cover(pdf: BoletinPDF, boletin: BoletinSemanal) -> None:
    inicio = boletin.periodo_inicio.strftime("%d/%m/%Y")
    fin = boletin.periodo_fin.strftime("%d/%m/%Y")
    pdf._periodo_label = f"{inicio} – {fin}"

    # Banda superior
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, 210, 52, "F")

    # Acento lateral
    pdf.set_fill_color(194, 120, 48)
    pdf.rect(0, 0, 4, 52, "F")

    pdf.set_xy(16, 10)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(200, 230, 225)
    pdf.cell(
        0,
        5,
        f"BOLETÍN SEMANAL · {boletin.theme_label.upper()}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.set_x(16)
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*WHITE)
    pdf.multi_cell(178, 8, boletin.theme_title)
    pdf.set_x(16)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(230, 245, 242)
    pdf.cell(0, 6, pdf._author_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(16)
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(210, 235, 230)
    pdf.cell(
        0,
        5,
        f"Periodo {inicio} – {fin}   ·   Generado {boletin.generado_el.strftime('%d/%m/%Y')}   ·   "
        f"{len(boletin.noticias)} noticias",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    pdf.set_y(60)
    _reset(pdf)

    # Intro breve
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        5,
        "Selección de noticias relevantes para el Programa de Alimentación Escolar y "
        "empresas concesionarias: impacto normativo, riesgos operativos y oportunidades comerciales.",
    )
    pdf.ln(4)
    _reset(pdf)


def _topic_chip(pdf: BoletinPDF, tema: str) -> None:
    label = _tema_label(tema).upper()
    pdf.set_font("DejaVu", "B", 7.5)
    w = pdf.get_string_width(label) + 6
    x, y = pdf.get_x(), pdf.get_y()
    pdf.set_fill_color(*TEAL_SOFT)
    pdf.set_text_color(*TEAL)
    pdf.rect(x, y, w, 5.5, style="F")
    pdf.set_xy(x, y + 0.6)
    pdf.cell(w, 4.2, label, align="C")
    pdf.set_xy(pdf.l_margin, y + 7.5)


def _labeled_block(pdf: BoletinPDF, label: str, text: str) -> None:
    _ensure_space(pdf, 18)
    _reset(pdf)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_text_color(*TEAL)
    pdf.cell(0, 5, label.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1.5)
    _reset(pdf)


def _twin_boxes(pdf: BoletinPDF, riesgos: str, oportunidades: str) -> None:
    """Dos columnas: riesgos | oportunidades."""
    _ensure_space(pdf, 28)
    _reset(pdf)

    gap = 4
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    col_w = (usable - gap) / 2
    x0 = pdf.l_margin
    y0 = pdf.get_y()

    def _box(x: float, y: float, title: str, body: str, bg, accent) -> float:
        pdf.set_xy(x, y)
        # medimos alto del texto
        pdf.set_font("DejaVu", "", 8.5)
        lines = pdf.multi_cell(col_w - 8, 4.5, body, dry_run=True, output="LINES")
        text_h = max(len(lines) * 4.5, 9)
        box_h = 8 + text_h + 6

        pdf.set_fill_color(*bg)
        pdf.rect(x, y, col_w, box_h, style="F")
        pdf.set_fill_color(*accent)
        pdf.rect(x, y, 1.8, box_h, style="F")

        pdf.set_xy(x + 4, y + 2.5)
        pdf.set_font("DejaVu", "B", 8)
        pdf.set_text_color(*accent)
        pdf.cell(col_w - 8, 4, title.upper())

        pdf.set_xy(x + 4, y + 8)
        pdf.set_font("DejaVu", "", 8.5)
        pdf.set_text_color(*INK)
        pdf.multi_cell(col_w - 8, 4.5, body)
        return y + box_h

    y1 = _box(x0, y0, "Riesgos", riesgos, RISK_BG, RISK_ACCENT)
    y2 = _box(x0 + col_w + gap, y0, "Oportunidades", oportunidades, OPP_BG, OPP_ACCENT)
    pdf.set_y(max(y1, y2) + 4)
    _reset(pdf)


def _draw_noticia(pdf: BoletinPDF, idx: int, n: NoticiaAnalizada) -> None:
    # Evita títulos huérfanos al pie de página
    if pdf.get_y() > pdf.h - pdf.b_margin - 85:
        pdf.add_page()
        _reset(pdf)

    _reset(pdf)
    content_x = pdf.l_margin + 3
    pdf.set_x(content_x)
    _topic_chip(pdf, n.tema)

    titular = _clean_title(n.titular, n.fuente)
    pdf.set_x(content_x)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*INK)
    pdf.multi_cell(pdf.w - pdf.r_margin - content_x, 5.8, f"{idx}. {titular}")
    pdf.ln(0.8)

    pdf.set_x(content_x)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4.5, f"{n.fuente}  ·  {n.fecha}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_x(content_x)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_text_color(*TEAL)
    label = _short_link_label(n.link)
    pdf.cell(pdf.get_string_width(label) + 1, 5, label, link=n.link)
    pdf.ln(4)

    old_l = pdf.l_margin
    pdf.set_left_margin(content_x)
    _reset(pdf)

    _labeled_block(pdf, "Resumen", n.resumen)
    _labeled_block(pdf, "Comentario", n.comentario)
    _twin_boxes(pdf, n.riesgos, n.oportunidades)

    pdf.set_left_margin(old_l)
    _reset(pdf)

    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)
    _reset(pdf)


def _draw_sintesis(pdf: BoletinPDF, texto: str) -> None:
    if pdf.get_y() > pdf.h - pdf.b_margin - 50:
        pdf.add_page()
        _reset(pdf)

    _reset(pdf)
    x = pdf.l_margin
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("DejaVu", "", 9.5)
    lines = pdf.multi_cell(usable - 12, 5, texto, dry_run=True, output="LINES")
    box_h = 14 + len(lines) * 5 + 8

    if pdf.get_y() + box_h > pdf.h - pdf.b_margin:
        pdf.add_page()
        _reset(pdf)

    y = pdf.get_y()
    pdf.set_fill_color(*TEAL_SOFT)
    pdf.rect(x, y, usable, box_h, style="F")
    pdf.set_fill_color(*TEAL)
    pdf.rect(x, y, 2.5, box_h, style="F")

    pdf.set_xy(x + 6, y + 4)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*TEAL)
    pdf.cell(0, 6, "Síntesis semanal del ecosistema PAE / concesionarias")

    pdf.set_xy(x + 6, y + 12)
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(usable - 12, 5, texto)
    pdf.set_y(y + box_h + 4)


def generate_pdf(
    boletin: BoletinSemanal,
    path: Path,
    *,
    author_name: str = "Raimundo Ibieta",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    regular, bold = _ensure_fonts()

    pdf = BoletinPDF(format="A4", author_name=author_name)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("DejaVu", "", str(regular))
    pdf.add_font("DejaVu", "B", str(bold))
    pdf.set_margins(16, 16, 16)
    pdf.add_page()

    _draw_cover(pdf, boletin)

    for i, n in enumerate(boletin.noticias, start=1):
        _draw_noticia(pdf, i, n)

    _draw_sintesis(pdf, boletin.sintesis.strip())

    pdf.output(str(path))
    return path
