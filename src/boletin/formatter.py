from __future__ import annotations

from boletin.models import BoletinSemanal, NoticiaAnalizada

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
    "GENERAL": "General",
}


def _tema_label(tema: str) -> str:
    return TEMA_LABEL.get(tema, tema.replace("_", " "))


def _format_noticia(n: NoticiaAnalizada, idx: int) -> str:
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


def to_markdown(boletin: BoletinSemanal, *, author_name: str = "Raimundo Ibieta") -> str:
    inicio = boletin.periodo_inicio.strftime("%d/%m/%Y")
    fin = boletin.periodo_fin.strftime("%d/%m/%Y")
    gen = boletin.generado_el.strftime("%d/%m/%Y")

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
        "## Noticias de la semana",
        "",
    ]
    for i, n in enumerate(boletin.noticias, start=1):
        parts.append(_format_noticia(n, i))
        parts.append("")

    parts.extend(
        [
            "---",
            "",
            "## Síntesis semanal",
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

    items = []
    for i, n in enumerate(boletin.noticias, start=1):
        tema = _tema_label(n.tema)
        items.append(
            f"""
            <div style="margin:0 0 28px 0;padding:0 0 20px 0;border-bottom:1px solid #e2e8f0;">
              <p style="margin:0 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#0f766e;">{tema}</p>
              <h2 style="margin:0 0 10px;font-size:18px;line-height:1.35;color:#0f172a;">{i}. {n.titular}</h2>
              <p style="margin:0 0 8px;font-size:13px;color:#64748b;"><strong>{n.fuente}</strong> — {n.fecha}</p>
              <p style="margin:0 0 12px;font-size:13px;"><a href="{n.link}" style="color:#0f766e;">Leer noticia</a></p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Resumen:</strong> {n.resumen}</p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Comentario:</strong> {n.comentario}</p>
              <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;"><strong>Riesgos:</strong> {n.riesgos}</p>
              <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;"><strong>Oportunidades:</strong> {n.oportunidades}</p>
            </div>
            """
        )

    sintesis_html = boletin.sintesis.replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Georgia,'Times New Roman',serif;">
  <div style="max-width:680px;margin:24px auto;background:#ffffff;padding:32px 28px;border-top:4px solid #0f766e;">
    <p style="margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#0f766e;">Boletín semanal</p>
    <h1 style="margin:0 0 4px;font-size:26px;color:#0f172a;">{boletin.theme_title}</h1>
    <p style="margin:0 0 4px;font-size:14px;color:#0f766e;"><strong>{author_name}</strong> · {boletin.theme_label}</p>
    <p style="margin:0 0 24px;font-size:14px;color:#64748b;">Periodo: {inicio} – {fin} · {len(boletin.noticias)} noticias</p>
    {''.join(items)}
    <div style="margin-top:8px;padding:18px;background:#f0fdfa;border-left:3px solid #0f766e;">
      <h2 style="margin:0 0 10px;font-size:16px;color:#0f172a;">Síntesis semanal</h2>
      <p style="margin:0;font-size:14px;line-height:1.6;color:#334155;">{sintesis_html}</p>
    </div>
    <p style="margin:24px 0 0;font-size:11px;color:#94a3b8;">Preparado por {author_name}. Adjunto: PDF del boletín.</p>
  </div>
</body>
</html>
"""
