from __future__ import annotations

import csv
import json
from pathlib import Path

from media_analyzer.models import AnalysisReport


def write_json(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path


def write_markdown(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Radiografía mediática: {report.topic}",
        "",
        f"**Territorio:** {report.territory_label}  ",
        f"**Periodo:** {report.period_start} – {report.period_end}  ",
        f"**Documentos:** {report.coverage.documents_included}",
        "",
        "## Resumen ejecutivo",
        "",
        report.executive_summary,
        "",
        "## Hallazgos",
        "",
    ]
    for f in report.findings:
        lines.append(f"- {f}")
    lines.extend(["", "## Actores y sentimiento", ""])
    for a in report.actors:
        lines.append(
            f"- **{a.name}** — menciones: {a.mentions}, score: {a.average_score:+.2f}, "
            f"labels: {a.sentiment}"
        )
        for q in a.sample_quotes[:2]:
            lines.append(f"  - “{q}”")
    lines.extend(["", "## Narrativas", ""])
    for n in report.narratives:
        lines.append(f"### {n.title}")
        lines.append(n.description)
        for e in n.evidence[:3]:
            lines.append(f"  - {e}")
        lines.append("")
    lines.extend(["", "## Cobertura por fuente", ""])
    for k, v in (report.coverage.by_source or {}).items():
        lines.append(f"- {k}: {v}")
    if report.warnings:
        lines.extend(["", "## Advertencias", ""])
        for w in report.warnings:
            lines.append(f"- {w}")
    lines.extend(["", "## Fuentes (muestra)", ""])
    for d in report.documents[:30]:
        lines.append(f"- [{d.title}]({d.url}) — {d.publisher} · {d.source_type}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_csv(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "id",
                "source_type",
                "title",
                "publisher",
                "url",
                "published_at",
                "excerpt",
            ]
        )
        for d in report.documents:
            w.writerow(
                [
                    d.id,
                    d.source_type,
                    d.title,
                    d.publisher,
                    d.url,
                    d.published_at.isoformat() if d.published_at else "",
                    (d.excerpt or "")[:300],
                ]
            )
    return path


def write_html(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    actors_html = "".join(
        f"<li><strong>{a.name}</strong> — {a.mentions} menciones · score {a.average_score:+.2f}</li>"
        for a in report.actors
    )
    findings_html = "".join(f"<li>{f}</li>" for f in report.findings)
    warnings_html = "".join(f"<li>{w}</li>" for w in report.warnings)
    sources_html = "".join(
        f'<li><a href="{d.url}">{d.title}</a> <span>({d.publisher} · {d.source_type})</span></li>'
        for d in report.documents[:40]
        if d.url
    )
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Radiografía · {report.topic}</title>
<style>
body{{font-family:Georgia,serif;max-width:900px;margin:32px auto;padding:0 16px;color:#0f172a}}
h1,h2{{font-family:system-ui,sans-serif}} .muted{{color:#64748b}} .card{{background:#f8fafc;padding:16px;border-radius:10px;margin:16px 0}}
</style></head><body>
<h1>Radiografía mediática</h1>
<p class="muted">{report.topic} · {report.territory_label} · {report.period_start} – {report.period_end}</p>
<div class="card"><h2>Resumen</h2><p>{report.executive_summary}</p></div>
<div class="card"><h2>Hallazgos</h2><ul>{findings_html}</ul></div>
<div class="card"><h2>Actores</h2><ul>{actors_html}</ul></div>
<div class="card"><h2>Advertencias</h2><ul>{warnings_html}</ul></div>
<div class="card"><h2>Fuentes</h2><ul>{sources_html}</ul></div>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def write_pdf(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    from fpdf import FPDF

    def _latin(text: str) -> str:
        # Helvetica core fonts: transliterar a Latin-1
        replacements = {
            "«": '"',
            "»": '"',
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "–": "-",
            "—": "-",
            "…": "...",
            "ñ": "n",
            "Ñ": "N",
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "Á": "A",
            "É": "E",
            "Í": "I",
            "Ó": "O",
            "Ú": "U",
            "ü": "u",
            "Ü": "U",
        }
        out = text or ""
        for a, b in replacements.items():
            out = out.replace(a, b)
        return out.encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    usable = pdf.epw

    def write_block(text: str, *, bold: bool = False, size: int = 10, h: float = 5) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(usable, h, _latin(text))

    write_block(f"Radiografia mediatica: {report.topic}", bold=True, size=16, h=8)
    write_block(
        f"Territorio: {report.territory_label} | Periodo: {report.period_start} - {report.period_end}",
        size=11,
        h=6,
    )
    pdf.ln(2)
    write_block("Resumen ejecutivo", bold=True, size=12, h=8)
    write_block(report.executive_summary)
    pdf.ln(2)
    write_block("Hallazgos", bold=True, size=12, h=8)
    for f in report.findings:
        write_block(f"- {f}")
    pdf.ln(1)
    write_block("Actores", bold=True, size=12, h=8)
    for a in report.actors[:12]:
        write_block(f"- {a.name}: {a.mentions} menciones, score {a.average_score:+.2f}")
    pdf.ln(1)
    write_block("Advertencias", bold=True, size=12, h=8)
    for w in report.warnings:
        write_block(f"- {w}")
    pdf.output(str(path))
    return path


def write_all_exports(report: AnalysisReport, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "json": write_json(report, output_dir / "report.json"),
        "markdown": write_markdown(report, output_dir / "report.md"),
        "csv": write_csv(report, output_dir / "documents.csv"),
        "html": write_html(report, output_dir / "report.html"),
        "pdf": write_pdf(report, output_dir / "report.pdf"),
    }
