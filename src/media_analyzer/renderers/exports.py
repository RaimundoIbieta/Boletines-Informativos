from __future__ import annotations

import csv
import json
from pathlib import Path

from media_analyzer.models import AnalysisReport

METHOD_LABELS = {
    "public_api": "API pública",
    "public_search": "Búsqueda pública",
    "media_citation": "Citado por medios",
    "user_supplied": "Aportado por el usuario",
    "unavailable": "No disponible",
}


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
    if report.opinion:
        lines.extend(["", "## Qué se dice del actor", ""])
        for op in report.opinion:
            aud, med = op.audience, op.media
            lines.append(f"### {op.actor}")
            lines.append(
                f"Menciones analizadas: {op.documents_analyzed}. "
                f"Audiencia: {aud.favorable} a favor, {aud.critica} críticas, "
                f"{aud.neutra} sin postura. Medios: {med.favorable} a favor, "
                f"{med.critica} críticas, {med.neutra} sin postura."
            )
            if op.sample_note:
                lines.append(f"- ⚠️ {op.sample_note}")
            elif op.bias_note:
                lines.append(f"- ⚠️ {op.bias_note}")
            if not op.sample_note and aud.opinionated:
                lines.append(
                    f"- **Balance de audiencia:** {aud.favorable_share:.0f}% favorable / "
                    f"{aud.critical_share:.0f}% crítica sobre {aud.opinionated} menciones con opinión."
                )
            for duel in op.duels:
                if duel.conclusive:
                    lines.append(
                        f"- **{duel.actor} vs {duel.rival}:** {duel.actor_votes} a "
                        f"{duel.rival_votes} ({duel.actor_share:.0f}% para {duel.actor}). "
                        f"Gana: {duel.winner}."
                    )
                else:
                    lines.append(
                        f"- **{duel.actor} vs {duel.rival}:** solo {duel.total} comparaciones "
                        f"({duel.actor_votes} a {duel.rival_votes}); insuficiente para concluir."
                    )
            lines.append(
                f"- **Clasificador:** {'modelo Gemini' if op.classifier == 'gemini' else 'léxico'}."
            )
            if op.top_reasons:
                lines.append(f"- **Términos que definen la opinión:** {', '.join(op.top_reasons)}")
            if op.quotes:
                lines.append("")
                lines.append("Citas de respaldo:")
                for q in op.quotes:
                    voice = "audiencia" if q.voice == "audience" else "medio"
                    label = "a favor" if q.stance == "favorable" else "crítica"
                    lines.append(f"  - [{label} · {voice} · {q.source_type}] “{q.text}” {q.url}")
            lines.append("")
        lines.append(
            "_Este balance describe la conversación observada en las fuentes accesibles; "
            "no es una encuesta representativa de la población._"
        )
    trend = report.trend
    if trend and trend.points:
        unit = trend.bucket_label
        lines.extend(["", "## Tendencia y proyección", ""])
        lines.append(
            f"Volumen **{trend.direction}** por {unit}: promedio {trend.average:.1f} piezas, "
            f"pico de {trend.peak_documents} el {trend.peak_period}."
        )
        if trend.tone_direction != "desconocida":
            lines.append(f"Tono hacia el actor principal: **{trend.tone_direction}**.")
        lines.append("")
        lines.append(f"| Desde | Piezas | Favorables | Críticas | Balance |")
        lines.append("| --- | --- | --- | --- | --- |")
        for point in trend.points[-12:]:
            lines.append(
                f"| {point.period_start} | {point.documents} | {point.favorable} | "
                f"{point.critical} | {point.tone_balance:+.0f} |"
            )
        if trend.projectable:
            lines.append("")
            lines.append(f"**Proyección** para los próximos {len(trend.projection)} tramos:")
            lines.append("")
            lines.append("| Desde | Esperado | Mínimo | Máximo |")
            lines.append("| --- | --- | --- | --- |")
            for point in trend.projection:
                lines.append(
                    f"| {point.period_start} | {point.expected:.0f} | "
                    f"{point.low:.0f} | {point.high:.0f} |"
                )
        if trend.note:
            lines.append("")
            lines.append(f"⚠️ {trend.note}")
        if trend.scenarios:
            lines.extend(["", "### Escenarios", ""])
            for scenario in trend.scenarios:
                lines.append(
                    f"- **{scenario.get('nombre')}** "
                    f"(probabilidad {scenario.get('probabilidad')}): "
                    f"{scenario.get('descripcion')}"
                )
                for signal in scenario.get("senales") or []:
                    lines.append(f"  - Señal a vigilar: {signal}")
        lines.append("")
        lines.append(
            "_La proyección extrapola la serie observada; un hecho nuevo puede romperla._"
        )
    lines.extend(["", "## Narrativas", ""])
    for n in report.narratives:
        lines.append(f"### {n.title}")
        lines.append(n.description)
        for e in n.evidence[:3]:
            lines.append(f"  - {e}")
        lines.append("")
    geo_counts = report.geography.get("scope_counts") or {}
    foreign = report.geography.get("foreign_countries") or {}
    if geo_counts:
        lines.extend(["", "## Cobertura geográfica estricta", ""])
        lines.append(
            "Las piezas extranjeras relevantes se conservan y se separan de la "
            "conversación del territorio objetivo."
        )
        lines.extend(
            [
                f"- **Territorio objetivo:** {geo_counts.get('target_territory', 0)}",
                f"- **Objetivo + extranjero:** {geo_counts.get('cross_border', 0)}",
                f"- **Solo contexto internacional:** {geo_counts.get('international', 0)}",
                f"- **Resto del país:** {geo_counts.get('rest_of_country', 0)}",
                f"- **Sin ubicación verificable:** {geo_counts.get('undetermined', 0)}",
            ]
        )
        if foreign:
            lines.append("")
            lines.append(
                "**Países extranjeros mencionados:** "
                + ", ".join(f"{country} ({count})" for country, count in list(foreign.items())[:15])
            )
    lines.extend(["", "## Cobertura por plataforma", ""])
    if report.coverage.platforms:
        lines.append("| Plataforma | Documentos | Cómo se obtuvo |")
        lines.append("| --- | --- | --- |")
        for p in report.coverage.platforms:
            lines.append(f"| {p.label} | {p.documents} | {METHOD_LABELS.get(p.method, p.method)} |")
        lines.append("")
        for p in report.coverage.platforms:
            if p.note:
                lines.append(f"- **{p.label}:** {p.note}")
    else:
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
                "geographic_scope",
                "source_country",
                "target_places",
                "foreign_countries",
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
                    (d.metadata or {}).get("geographic_scope", "undetermined"),
                    (d.metadata or {}).get("source_country", ""),
                    "; ".join((d.metadata or {}).get("target_places") or []),
                    "; ".join((d.metadata or {}).get("foreign_countries") or []),
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
    if report.coverage.platforms:
        rows = "".join(
            f"<tr><td>{p.label}</td><td>{p.documents}</td>"
            f"<td>{METHOD_LABELS.get(p.method, p.method)}<br>"
            f"<small>{p.note}</small></td></tr>"
            for p in report.coverage.platforms
        )
        platforms_html = (
            "<table style='width:100%;border-collapse:collapse' border='1' cellpadding='6'>"
            "<thead><tr><th>Plataforma</th><th>Docs</th><th>Cómo se obtuvo</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        platforms_html = "".join(
            f"<p>{k}: {v}</p>" for k, v in (report.coverage.by_source or {}).items()
        )
    sources_html = "".join(
        f'<li><a href="{d.url}">{d.title}</a> <span>({d.publisher} · {d.source_type})</span></li>'
        for d in report.documents[:40]
        if d.url
    )
    geo_counts = report.geography.get("scope_counts") or {}
    foreign = report.geography.get("foreign_countries") or {}
    geography_html = ""
    if geo_counts:
        country_items = "".join(
            f"<li>{country}: {count}</li>" for country, count in list(foreign.items())[:15]
        )
        geography_html = (
            "<div class='card'><h2>Cobertura geográfica estricta</h2>"
            "<p class='muted'>Clasifica la relación territorial sin eliminar menciones "
            "extranjeras relevantes.</p><ul>"
            f"<li>Territorio objetivo: {geo_counts.get('target_territory', 0)}</li>"
            f"<li>Objetivo + extranjero: {geo_counts.get('cross_border', 0)}</li>"
            f"<li>Solo contexto internacional: {geo_counts.get('international', 0)}</li>"
            f"<li>Resto del país: {geo_counts.get('rest_of_country', 0)}</li>"
            f"<li>Sin ubicación verificable: {geo_counts.get('undetermined', 0)}</li>"
            "</ul>"
            + (f"<h3>Países extranjeros mencionados</h3><ul>{country_items}</ul>" if country_items else "")
            + "</div>"
        )
    opinion_html = ""
    if report.opinion:
        blocks = []
        for op in report.opinion:
            aud = op.audience
            bar = ""
            if aud.opinionated:
                bar = (
                    "<div style='display:flex;height:22px;border-radius:6px;overflow:hidden;"
                    "font:12px system-ui;color:#fff;margin:8px 0'>"
                    f"<div style='width:{aud.favorable_share}%;background:#15803d;text-align:center'>"
                    f"{aud.favorable_share:.0f}% a favor</div>"
                    f"<div style='width:{aud.critical_share}%;background:#b91c1c;text-align:center'>"
                    f"{aud.critical_share:.0f}% crítica</div></div>"
                )
            duels = "".join(
                (
                    f"<li><strong>{d.actor} vs {d.rival}:</strong> {d.actor_votes} a "
                    f"{d.rival_votes} ({d.actor_share:.0f}% para {d.actor}) · "
                    f"gana <strong>{d.winner}</strong></li>"
                )
                if d.conclusive
                else (
                    f"<li><strong>{d.actor} vs {d.rival}:</strong> solo {d.total} "
                    f"comparaciones ({d.actor_votes} a {d.rival_votes}); "
                    "insuficiente para concluir.</li>"
                )
                for d in op.duels
            )
            quote_items = []
            for q in op.quotes:
                stance_label = "a favor" if q.stance == "favorable" else "crítica"
                voice_label = "audiencia" if q.voice == "audience" else "medio"
                link = f'<a href="{q.url}">ver</a>' if q.url else ""
                quote_items.append(
                    f"<li><em>{stance_label}</em> · {voice_label} · {q.source_type}<br>"
                    f"“{q.text}” {link}</li>"
                )
            quotes = "".join(quote_items)
            blocks.append(
                f"<h3>{op.actor}</h3>"
                f"<p class='muted'>{op.documents_analyzed} menciones analizadas · "
                f"audiencia: {aud.favorable} a favor / {aud.critica} críticas / {aud.neutra} sin postura "
                f"· medios: {op.media.favorable} / {op.media.critica} / {op.media.neutra}</p>"
                + (
                    f"<p style='color:#b45309'><strong>Aviso:</strong> {op.sample_note}</p>"
                    if op.sample_note
                    else bar
                )
                + (
                    f"<p style='color:#b45309'><strong>Aviso:</strong> {op.bias_note}</p>"
                    if op.bias_note
                    else ""
                )
                + (f"<ul>{duels}</ul>" if duels else "")
                + (f"<ul>{quotes}</ul>" if quotes else "")
            )
        opinion_html = (
            "<div class='card'><h2>Qué se dice del actor</h2>"
            + "".join(blocks)
            + "<p class='muted'>Describe la conversación observada en las fuentes accesibles; "
            "no es una encuesta representativa de la población.</p></div>"
        )
    trend_html = ""
    trend = report.trend
    if trend and trend.points:
        unit = trend.bucket_label
        shown = trend.points[-12:]
        top = max([p.documents for p in shown] + [p.high for p in trend.projection] + [1])
        bars = []
        for point in shown:
            height = max(2, round(100 * point.documents / top))
            bars.append(
                f"<div title='{point.period_start}: {point.documents}' "
                f"style='flex:1;display:flex;align-items:flex-end'>"
                f"<div style='width:100%;height:{height}px;background:#2563eb'></div></div>"
            )
        for point in trend.projection:
            height = max(2, round(100 * point.expected / top))
            bars.append(
                f"<div title='proyección {point.period_start}: {point.expected:.0f}' "
                f"style='flex:1;display:flex;align-items:flex-end'>"
                f"<div style='width:100%;height:{height}px;background:#93c5fd;"
                f"border-top:2px dashed #2563eb'></div></div>"
            )
        chart = (
            "<div style='display:flex;gap:3px;height:110px;align-items:flex-end;"
            f"margin:12px 0'>{''.join(bars)}</div>"
            f"<p class='muted'>Azul: observado por {unit}. Celeste punteado: proyectado.</p>"
        )
        rows = "".join(
            f"<tr><td>{p.period_start}</td><td>{p.documents}</td><td>{p.favorable}</td>"
            f"<td>{p.critical}</td><td>{p.tone_balance:+.0f}</td></tr>"
            for p in shown
        )
        projection_rows = "".join(
            f"<tr><td>{p.period_start}</td><td>{p.expected:.0f}</td>"
            f"<td>{p.low:.0f} – {p.high:.0f}</td></tr>"
            for p in trend.projection
        )
        scenarios = "".join(
            f"<li><strong>{s.get('nombre')}</strong> "
            f"<span class='muted'>(probabilidad {s.get('probabilidad')})</span><br>"
            f"{s.get('descripcion')}"
            + (
                "<br><small>Señales: " + "; ".join(s.get("senales") or []) + "</small>"
                if s.get("senales")
                else ""
            )
            + "</li>"
            for s in trend.scenarios
        )
        trend_html = (
            "<div class='card'><h2>Tendencia y proyección</h2>"
            f"<p>Volumen <strong>{trend.direction}</strong> por {unit} · "
            f"promedio {trend.average:.1f} · pico {trend.peak_documents} "
            f"el {trend.peak_period}"
            + (
                f" · tono <strong>{trend.tone_direction}</strong>"
                if trend.tone_direction != "desconocida"
                else ""
            )
            + "</p>"
            + chart
            + "<table style='width:100%;border-collapse:collapse' border='1' cellpadding='6'>"
            "<thead><tr><th>Desde</th><th>Piezas</th><th>Favorables</th>"
            "<th>Críticas</th><th>Balance</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            + (
                "<h3>Proyección</h3><table style='width:100%;border-collapse:collapse' "
                "border='1' cellpadding='6'><thead><tr><th>Desde</th><th>Esperado</th>"
                f"<th>Rango</th></tr></thead><tbody>{projection_rows}</tbody></table>"
                if projection_rows
                else ""
            )
            + (
                f"<p style='color:#b45309'><strong>Aviso:</strong> {trend.note}</p>"
                if trend.note
                else ""
            )
            + (f"<h3>Escenarios</h3><ul>{scenarios}</ul>" if scenarios else "")
            + "<p class='muted'>La proyección extrapola la serie observada; "
            "un hecho nuevo puede romperla.</p></div>"
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
{opinion_html}
{trend_html}
{geography_html}
<div class="card"><h2>Cobertura por plataforma</h2>{platforms_html}</div>
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
    if report.opinion:
        pdf.ln(1)
        write_block("Que se dice del actor", bold=True, size=12, h=8)
        for op in report.opinion:
            aud = op.audience
            write_block(f"{op.actor} ({op.documents_analyzed} menciones analizadas)", bold=True)
            write_block(
                f"- Audiencia: {aud.favorable} a favor, {aud.critica} criticas, "
                f"{aud.neutra} sin postura."
            )
            if op.sample_note:
                write_block(f"- AVISO: {op.sample_note}")
            elif op.bias_note:
                write_block(f"- AVISO: {op.bias_note}")
            if not op.sample_note and aud.opinionated:
                write_block(
                    f"- Balance: {aud.favorable_share:.0f}% favorable / "
                    f"{aud.critical_share:.0f}% critica de {aud.opinionated} con opinion."
                )
            write_block(
                f"- Medios: {op.media.favorable} a favor, {op.media.critica} criticas, "
                f"{op.media.neutra} sin postura."
            )
            for duel in op.duels:
                if duel.conclusive:
                    write_block(
                        f"- {duel.actor} vs {duel.rival}: {duel.actor_votes} a "
                        f"{duel.rival_votes} ({duel.actor_share:.0f}% para {duel.actor}). "
                        f"Gana: {duel.winner}."
                    )
                else:
                    write_block(
                        f"- {duel.actor} vs {duel.rival}: solo {duel.total} comparaciones "
                        f"({duel.actor_votes} a {duel.rival_votes}); insuficiente para concluir."
                    )
            for q in op.quotes[:4]:
                stance = "a favor" if q.stance == "favorable" else "critica"
                voice = "audiencia" if q.voice == "audience" else "medio"
                write_block(f'  [{stance} / {voice}] "{q.text[:180]}"')
        write_block(
            "Describe la conversacion observada en las fuentes accesibles; "
            "no es una encuesta representativa."
        )
    trend = report.trend
    if trend and trend.points:
        pdf.ln(1)
        write_block("Tendencia y proyeccion", bold=True, size=12, h=8)
        write_block(
            f"- Volumen {trend.direction} por {trend.bucket_label}: promedio "
            f"{trend.average:.1f}, pico {trend.peak_documents} el {trend.peak_period}."
        )
        if trend.tone_direction != "desconocida":
            write_block(f"- Tono hacia el actor principal: {trend.tone_direction}.")
        for point in trend.projection:
            write_block(
                f"- Proyeccion {point.period_start}: {point.expected:.0f} piezas "
                f"(rango {point.low:.0f} a {point.high:.0f})."
            )
        if trend.note:
            write_block(f"- AVISO: {trend.note}")
        for scenario in trend.scenarios:
            write_block(
                f"- Escenario {scenario.get('nombre')} "
                f"(probabilidad {scenario.get('probabilidad')}): "
                f"{scenario.get('descripcion')}"
            )
        write_block(
            "La proyeccion extrapola la serie observada; un hecho nuevo puede romperla."
        )
    geo_counts = report.geography.get("scope_counts") or {}
    foreign = report.geography.get("foreign_countries") or {}
    if geo_counts:
        pdf.ln(1)
        write_block("Cobertura geografica estricta", bold=True, size=12, h=8)
        write_block(
            "- Territorio objetivo: "
            f"{geo_counts.get('target_territory', 0)} | objetivo + extranjero: "
            f"{geo_counts.get('cross_border', 0)} | internacional: "
            f"{geo_counts.get('international', 0)} | resto del pais: "
            f"{geo_counts.get('rest_of_country', 0)} | sin ubicacion verificable: "
            f"{geo_counts.get('undetermined', 0)}."
        )
        if foreign:
            write_block(
                "- Paises extranjeros mencionados: "
                + ", ".join(
                    f"{country} ({count})" for country, count in list(foreign.items())[:15]
                )
            )
        write_block(
            "Las piezas extranjeras relevantes se conservan y se analizan por separado."
        )
    pdf.ln(1)
    write_block("Cobertura por plataforma", bold=True, size=12, h=8)
    if report.coverage.platforms:
        for p in report.coverage.platforms:
            write_block(
                f"- {p.label}: {p.documents} docs ({METHOD_LABELS.get(p.method, p.method)})"
            )
    else:
        for k, v in (report.coverage.by_source or {}).items():
            write_block(f"- {k}: {v}")
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
