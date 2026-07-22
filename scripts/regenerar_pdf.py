"""Regenera el PDF desde un markdown de boletín ya generado (sin llamar al LLM)."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boletin.models import BoletinSemanal, NoticiaAnalizada
from boletin.pdf_generator import generate_pdf

TEMA_MAP = {
    "JUNAEB / PAE": "JUNAEB_PAE",
    "JUNJI / Integra": "JUNJI_INTEGRA",
    "MINEDUC": "MINEDUC",
    "Educación": "OTRO_EDUCACION",
}


def parse_md(path: Path) -> BoletinSemanal:
    text = path.read_text(encoding="utf-8")
    m_period = re.search(
        r"Periodo cubierto:\*\*\s*(\d{2}/\d{2}/\d{4})\s*[–-]\s*(\d{2}/\d{2}/\d{4})",
        text,
    )
    m_gen = re.search(r"Generado:\*\*\s*(\d{2}/\d{2}/\d{4})", text)
    if not m_period or not m_gen:
        raise ValueError("No se pudo leer periodo/fecha del markdown")

    def dmy(s: str) -> date:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))

    blocks = re.split(r"\n###\s+", text)
    noticias: list[NoticiaAnalizada] = []
    for block in blocks[1:]:
        if block.startswith("Síntesis") or "## Síntesis" in block[:40]:
            continue
        lines = block.strip().splitlines()
        if not lines:
            continue
        title_line = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        body = "\n".join(lines[1:])

        tema_m = re.search(r"\*\*Tema:\*\*\s*(.+)", body)
        fuente_m = re.search(r"\*\*Fuente y fecha:\*\*\s*(.+?)\s*—\s*(.+)", body)
        link_m = re.search(r"\*\*Link:\*\*\s*(\S+)", body)
        resumen_m = re.search(
            r"\*\*Resumen\*\*\s*\n(.+?)(?=\n\*\*Comentario|\Z)", body, re.S
        )
        coment_m = re.search(
            r"\*\*Comentario técnico-político[^*\n]*\*\*\s*\n(.+?)(?=\n\*\*Riesgos|\Z)",
            body,
            re.S,
        )
        riesgos_m = re.search(
            r"\*\*Riesgos[^*\n]*\*\*\s*\n(.+?)(?=\n\*\*Oportunidades|\Z)", body, re.S
        )
        oport_m = re.search(
            r"\*\*Oportunidades[^*\n]*\*\*\s*\n(.+?)(?=\n---+|\n###|\n## |\Z)",
            body,
            re.S,
        )
        if not all([tema_m, fuente_m, link_m, resumen_m, coment_m, riesgos_m, oport_m]):
            continue

        tema_label = tema_m.group(1).strip()
        noticias.append(
            NoticiaAnalizada(
                titular=title_line,
                fuente=fuente_m.group(1).strip(),
                fecha=fuente_m.group(2).strip(),
                link=link_m.group(1).strip(),
                resumen=resumen_m.group(1).strip(),
                comentario_pae=coment_m.group(1).strip(),
                riesgos=riesgos_m.group(1).strip(),
                oportunidades=oport_m.group(1).strip(),
                tema=TEMA_MAP.get(tema_label, "OTRO_EDUCACION"),  # type: ignore[arg-type]
                relevancia=5,
            )
        )

    sint_m = re.search(
        r"## Síntesis semanal[^\n]*\n\n(.+?)(?=\n---|\Z)", text, re.S
    )
    sintesis = sint_m.group(1).strip() if sint_m else ""
    # Quitar nota al pie
    sintesis = re.sub(r"\n*_Boletín automático.*$", "", sintesis).strip()

    return BoletinSemanal(
        periodo_inicio=dmy(m_period.group(1)),
        periodo_fin=dmy(m_period.group(2)),
        generado_el=dmy(m_gen.group(1)),
        noticias=noticias,
        sintesis=sintesis,
    )


def main() -> None:
    md = ROOT / "output" / "boletin_pae_2026-07-13_2026-07-19.md"
    if len(sys.argv) > 1:
        md = Path(sys.argv[1])
    boletin = parse_md(md)
    out = md.with_suffix(".pdf")
    generate_pdf(boletin, out)
    # Copia a Downloads si existe la carpeta
    downloads = Path.home() / "Downloads" / out.name
    downloads.write_bytes(out.read_bytes())
    print(f"PDF: {out}")
    print(f"Copia: {downloads}")
    print(f"Noticias: {len(boletin.noticias)}")


if __name__ == "__main__":
    main()
