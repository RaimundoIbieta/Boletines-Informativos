from __future__ import annotations

from html import escape
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from boletin.models import BoletinSemanal, NoticiaAnalizada, SeccionSintesis

TEMA_LABEL = {
    "JUNAEB_PAE": "JUNAEB / PAE",
    "JUNJI_INTEGRA": "JUNJI / Integra",
    "MINEDUC": "MINEDUC",
    "OTRO_EDUCACION": "Educación",
    "MACRO": "Macro",
    "FISCAL": "Fiscal",
    "MERCADOS": "Mercados",
    "LABORAL": "Laboral",
    "COMEX": "Comercio exterior",
    "ECONOMIA": "Economía",
    "ECONOMÍA": "Economía",
    "SOCIAL": "Social",
    "POLITICA": "Política",
    "POLÍTICA": "Política",
    "NACIONAL": "Nacional",
    "INTERNACIONAL": "Internacional",
    "GENERAL": "General",
}


def _tema_label(tema: str) -> str:
    return TEMA_LABEL.get(tema, tema.replace("_", " "))


def _section_groups(boletin: BoletinSemanal) -> list[tuple[str, list[NoticiaAnalizada]]]:
    if not boletin.sections:
        return [("", boletin.noticias)]
    groups: list[tuple[str, list[NoticiaAnalizada]]] = []
    for section in boletin.sections:
        rows = [n for n in boletin.noticias if _tema_label(n.tema).lower() == section.lower()]
        if rows:
            groups.append((section, rows))
    return groups


def _section_analysis_map(boletin: BoletinSemanal) -> dict[str, str]:
    return {
        (s.seccion or "").strip().lower(): s.analisis.strip()
        for s in boletin.sintesis_secciones
        if s.analisis.strip()
    }


def safe_http_url(url: str) -> str:
    """Percent-encodea tildes/unicode para URI ASCII (PDF y HTML)."""
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return raw
    parts = urlsplit(raw)
    try:
        netloc = parts.netloc.encode("idna").decode("ascii")
    except Exception:
        netloc = parts.netloc
    path = quote(unquote(parts.path), safe="/:@!$&'()*+,;=-._~")
    query = quote(unquote(parts.query), safe="=&:@!$&'()*+,;=-._~/%")
    fragment = quote(unquote(parts.fragment), safe="=&:@!$&'()*+,;=-._~/%")
    return urlunsplit((parts.scheme, netloc, path, query, fragment))


def _format_noticia_standard(n: NoticiaAnalizada, idx: int) -> str:
    tema = _tema_label(n.tema)
    return f"""### {idx}. {n.titular}

- **Tema:** {tema}
- **Fuente y fecha:** {n.fuente} — {n.fecha}
- **Link:** {n.link}

**Resumen**
{n.resumen}

**Comentario**
{n.comentario}

**Riesgos**
{n.riesgos}

**Oportunidades**
{n.oportunidades}
"""


def _format_noticia_panorama(n: NoticiaAnalizada, idx: int) -> str:
    return f"""### {idx}. {n.titular}

- **Fuente y fecha:** {n.fuente} — {n.fecha}
- **Link:** {n.link}

**Resumen**
{n.resumen}
"""


def to_markdown(boletin: BoletinSemanal, *, author_name: str = "Raimundo Ibieta") -> str:
    inicio = boletin.periodo_inicio.strftime("%d/%m/%Y")
    fin = boletin.periodo_fin.strftime("%d/%m/%Y")
    gen = boletin.generado_el.strftime("%d/%m/%Y")
    panorama = boletin.is_panorama
    analyses = _section_analysis_map(boletin)

    parts = [
        f"# {boletin.theme_title}",
        "",
        f"**Autor:** {author_name}  ",
        f"**Temática:** {boletin.theme_label}  ",
        f"**Periodo cubierto:** {inicio} – {fin}  ",
        f"**Generado:** {gen}  ",
        f"**Noticias seleccionadas:** {len(boletin.noticias)}",
        "",
        "---",
        "",
    ]
    if not panorama:
        parts.extend(["## Noticias del periodo", ""])

    idx = 1
    for section, noticias in _section_groups(boletin):
        if section:
            parts.extend([f"## {section}", ""])
        for n in noticias:
            if panorama:
                parts.append(_format_noticia_panorama(n, idx))
            else:
                parts.append(_format_noticia_standard(n, idx))
            parts.append("")
            idx += 1
        if panorama and section:
            analysis = analyses.get(section.lower(), "")
            if analysis:
                parts.extend(
                    [
                        f"**Análisis de la sección {section}**",
                        "",
                        analysis,
                        "",
                    ]
                )

    parts.extend(
        [
            "---",
            "",
            f"## {boletin.conclusion_title}",
            "",
            boletin.sintesis.strip(),
            "",
            "---",
            "",
            f"_Preparado por {author_name} — uso interno. Verificar siempre las fuentes originales._",
            "",
        ]
    )
    return "\n".join(parts)


def to_html_email(boletin: BoletinSemanal, *, author_name: str = "Raimundo Ibieta") -> str:
    inicio = boletin.periodo_inicio.strftime("%d/%m/%Y")
    fin = boletin.periodo_fin.strftime("%d/%m/%Y")
    panorama = boletin.is_panorama
    analyses = _section_analysis_map(boletin)

    items = []
    idx = 1
    for section, noticias in _section_groups(boletin):
        if section:
            items.append(
                f'<h2 style="margin:30px 0 16px;padding-bottom:8px;border-bottom:2px solid #0f766e;'
                f'font-size:21px;color:#0f172a;">{escape(section)}</h2>'
            )
        for n in noticias:
            tema = _tema_label(n.tema)
            if panorama:
                items.append(
                    f"""
            <div style="margin:0 0 22px 0;padding:0 0 16px 0;border-bottom:1px solid #e2e8f0;">
              <h3 style="margin:0 0 10px;font-size:17px;line-height:1.35;color:#0f172a;">{idx}. {escape(n.titular)}</h3>
              <p style="margin:0 0 8px;font-size:13px;color:#64748b;"><strong>{escape(n.fuente)}</strong> — {escape(n.fecha)}</p>
              <p style="margin:0 0 12px;font-size:13px;"><a href="{escape(safe_http_url(n.link), quote=True)}" style="color:#0f766e;">Leer noticia</a></p>
              <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;"><strong>Resumen:</strong> {escape(n.resumen)}</p>
            </div>
            """
                )
            else:
                items.append(
                    f"""
            <div style="margin:0 0 28px 0;padding:0 0 20px 0;border-bottom:1px solid #e2e8f0;">
              <p style="margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#0f766e;">{escape(tema)}</p>
              <h2 style="margin:0 0 10px;font-size:18px;line-height:1.35;color:#0f172a;">{idx}. {escape(n.titular)}</h2>
              <p style="margin:0 0 8px;font-size:13px;color:#64748b;"><strong>{escape(n.fuente)}</strong> — {escape(n.fecha)}</p>
              <p style="margin:0 0 12px;font-size:13px;"><a href="{escape(safe_http_url(n.link), quote=True)}" style="color:#0f766e;">Leer noticia</a></p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Resumen:</strong> {escape(n.resumen)}</p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Comentario:</strong> {escape(n.comentario)}</p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Riesgos:</strong> {escape(n.riesgos)}</p>
              <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;"><strong>Oportunidades:</strong> {escape(n.oportunidades)}</p>
            </div>
            """
                )
            idx += 1
        if panorama and section:
            analysis = analyses.get(section.lower(), "")
            if analysis:
                items.append(
                    f"""
            <div style="margin:0 0 28px 0;padding:14px 16px;background:#f8fafc;border-left:3px solid #0f766e;">
              <p style="margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#0f766e;">Análisis de la sección</p>
              <p style="margin:0;font-size:14px;line-height:1.6;color:#334155;">{escape(analysis)}</p>
            </div>
            """
                )

    sintesis_html = escape(boletin.sintesis).replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Georgia,'Times New Roman',serif;">
  <div style="max-width:680px;margin:24px auto;background:#ffffff;padding:32px 28px;border-top:4px solid #0f766e;">
    <p style="margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#0f766e;">Boletín de análisis</p>
    <h1 style="margin:0 0 4px;font-size:26px;color:#0f172a;">{escape(boletin.theme_title)}</h1>
    <p style="margin:0 0 4px;font-size:14px;color:#0f766e;"><strong>{escape(author_name)}</strong> · {escape(boletin.theme_label)}</p>
    <p style="margin:0 0 24px;font-size:14px;color:#64748b;">Periodo: {inicio} – {fin} · {len(boletin.noticias)} noticias</p>
    {''.join(items)}
    <div style="margin-top:8px;padding:18px;background:#f0fdfa;border-left:3px solid #0f766e;">
      <h2 style="margin:0 0 10px;font-size:16px;color:#0f172a;">{escape(boletin.conclusion_title)}</h2>
      <p style="margin:0;font-size:14px;line-height:1.6;color:#334155;">{sintesis_html}</p>
    </div>
    <p style="margin:24px 0 0;font-size:11px;color:#94a3b8;">Preparado por {escape(author_name)}. Adjunto: PDF del boletín.</p>
  </div>
</body>
</html>
"""
