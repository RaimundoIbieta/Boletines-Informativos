from __future__ import annotations

import re
import subprocess
import webbrowser
from threading import Timer

from flask import Flask, flash, redirect, render_template_string, request, url_for

from boletin.config import WEEKDAY_MAP, ThemeConfig, load_app_config
from boletin.schedule_sync import sync_launch_agent

app = Flask(__name__)
app.secret_key = "boletin-local-admin"


def _slug(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9áéíóúñü]+", "-", s, flags=re.I)
    s = re.sub(r"-+", "-", s).strip("-")
    s = (
        s.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace("ü", "u")
    )
    return s or "tema"


PAGE = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Panel · Boletines</title>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --ink:#1a2332; --muted:#5a6978; --teal:#0b4f4a; --soft:#e8f5f3;
      --line:#dce4ea; --bg:#f7faf9; --danger:#992f2a;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:"Source Sans 3",system-ui,sans-serif;background:radial-gradient(900px 420px at 8% -10%,#d8efe9,transparent 55%),var(--bg);color:var(--ink)}
    .wrap{max-width:980px;margin:0 auto;padding:40px 20px 80px}
    h1{font-family:Fraunces,Georgia,serif;font-size:2.2rem;margin:0 0 6px}
    .sub{color:var(--muted);margin:0 0 24px}
    .flash{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:10px 12px;border-radius:10px;margin-bottom:14px}
    .grid{display:grid;gap:16px}
    @media(min-width:860px){.grid-2{grid-template-columns:1fr 1fr}}
    .card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px}
    .card h2{margin:0 0 12px;font-size:1.15rem;font-family:Fraunces,Georgia,serif}
    label{display:block;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin:10px 0 6px}
    input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font:inherit}
    textarea{min-height:90px;resize:vertical}
    .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    .chip{display:inline-flex;gap:8px;align-items:center;background:var(--soft);color:var(--teal);padding:6px 10px;border-radius:999px;font-weight:600;font-size:.92rem}
    button,.btn{border:0;background:var(--teal);color:#fff;font-weight:700;padding:10px 14px;border-radius:10px;cursor:pointer;text-decoration:none;display:inline-block}
    button.secondary,.btn.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}
    button.danger{background:var(--danger)}
    .hint{font-size:.9rem;color:var(--muted);margin-top:8px}
    .queries{font-family:ui-monospace,Menlo,monospace;font-size:.85rem;background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:10px;white-space:pre-wrap}
    .theme{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}
    .active{outline:2px solid var(--teal)}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Panel de configuración</h1>
    <p class="sub">Aquí controlas correos, frecuencia y temáticas. El sitio de GitHub solo muestra el archivo de PDFs.</p>

    {% for m in messages %}
      <div class="flash">{{ m }}</div>
    {% endfor %}

    <div class="grid grid-2">
      <section class="card">
        <h2>Destinatarios</h2>
        <div class="row" style="margin-bottom:12px">
          {% for e in app.emails %}
            <span class="chip">{{ e }}
              <form method="post" action="{{ url_for('remove_email') }}" style="display:inline">
                <input type="hidden" name="email" value="{{ e }}" />
                <button class="danger" style="padding:2px 8px;border-radius:8px;font-size:.75rem">x</button>
              </form>
            </span>
          {% else %}
            <span class="hint">Sin correos</span>
          {% endfor %}
        </div>
        <form method="post" action="{{ url_for('add_email') }}">
          <label>Agregar correo</label>
          <div class="row">
            <input type="email" name="email" placeholder="colegas@empresa.cl" required style="flex:1" />
            <button type="submit">Agregar</button>
          </div>
        </form>
      </section>

      <section class="card">
        <h2>Frecuencia / horario</h2>
        <form method="post" action="{{ url_for('set_schedule') }}">
          <label>Día</label>
          <select name="weekday">
            {% for key, label in days %}
              <option value="{{ key }}" {% if app.schedule.weekday==key %}selected{% endif %}>{{ label }}</option>
            {% endfor %}
          </select>
          <div class="row">
            <div style="flex:1">
              <label>Hora</label>
              <input type="number" name="hour" min="0" max="23" value="{{ app.schedule.hour }}" required />
            </div>
            <div style="flex:1">
              <label>Minuto</label>
              <input type="number" name="minute" min="0" max="59" value="{{ app.schedule.minute }}" required />
            </div>
          </div>
          <p class="hint">Zona: {{ app.schedule.timezone }}. Tras guardar se actualiza el envío automático del Mac.</p>
          <button type="submit" style="margin-top:12px">Guardar horario</button>
        </form>
      </section>
    </div>

    <section class="card" style="margin-top:16px">
      <h2>Temática activa</h2>
      <form method="post" action="{{ url_for('set_theme') }}" class="row">
        <select name="theme" style="flex:1">
          {% for tid, t in app.themes.items() %}
            <option value="{{ tid }}" {% if app.active_theme==tid %}selected{% endif %}>{{ tid }} — {{ t.title }}</option>
          {% endfor %}
        </select>
        <button type="submit">Usar esta temática</button>
      </form>
      <p class="hint">La temática activa define qué se busca en la web y cómo se analiza el boletín.</p>
    </section>

    <section class="card" style="margin-top:16px">
      <h2>Crear temática personalizada</h2>
      <form method="post" action="{{ url_for('create_theme') }}">
        <label>ID (opcional, sin espacios)</label>
        <input name="theme_id" placeholder="mineria" />
        <label>Título del boletín</label>
        <input name="title" placeholder="Boletín semanal minería Chile" required />
        <label>Etiqueta corta</label>
        <input name="short_label" placeholder="Minería Chile" required />
        <label>Audiencia</label>
        <input name="audience" placeholder="gerentes y analistas del sector" />
        <label>Enfoque (qué debe cubrir)</label>
        <textarea name="focus" placeholder="Noticias de minería, cobre, litio, Codelco, regulaciones ambientales..." required></textarea>
        <label>Búsquedas web (una por línea). Formato: consulta | TEMA</label>
        <textarea name="queries" placeholder="cobre Chile OR Codelco | MINERIA
litio Chile OR SQM | LITIO
permisos ambientales minería Chile | REGULACION" required></textarea>
        <label>Ejes de análisis (uno por línea)</label>
        <textarea name="axes" placeholder="impacto regulatorio
riesgos operativos
oportunidades de inversión"></textarea>
        <div class="row" style="margin-top:12px">
          <button type="submit">Crear temática</button>
          <label style="display:flex;gap:8px;align-items:center;text-transform:none;letter-spacing:0;font-size:.95rem;font-weight:600;color:var(--ink)">
            <input type="checkbox" name="activate" value="1" checked /> Activar al crear
          </label>
        </div>
      </form>
    </section>

    <section class="card" style="margin-top:16px">
      <h2>Temáticas existentes</h2>
      {% for tid, t in app.themes.items() %}
        <div class="theme {% if app.active_theme==tid %}active{% endif %}">
          <strong>{{ t.title }}</strong> <span class="hint">({{ tid }})</span>
          <p class="hint">{{ t.focus[:220] }}{% if t.focus|length > 220 %}…{% endif %}</p>
          <div class="queries">{% for q, topic in t.queries %}{{ q }} | {{ topic }}
{% endfor %}</div>
        </div>
      {% endfor %}
    </section>

    <p class="hint" style="margin-top:18px">
      Archivo online (solo lectura):
      <a href="https://raimundoibieta.github.io/Boletines-Informativos/" target="_blank" rel="noopener">GitHub Pages</a>
    </p>
  </div>
</body>
</html>
"""


DAYS = [
    ("monday", "Lunes"),
    ("tuesday", "Martes"),
    ("wednesday", "Miércoles"),
    ("thursday", "Jueves"),
    ("friday", "Viernes"),
    ("saturday", "Sábado"),
    ("sunday", "Domingo"),
]


@app.get("/")
def home():
    cfg = load_app_config()
    return render_template_string(PAGE, app=cfg, days=DAYS)


@app.post("/emails/add")
def add_email():
    cfg = load_app_config()
    email = (request.form.get("email") or "").strip().lower()
    if email and email not in [e.lower() for e in cfg.emails]:
        cfg.emails.append(email)
        cfg.save()
        flash(f"Correo agregado: {email}")
    return redirect(url_for("home"))


@app.post("/emails/remove")
def remove_email():
    cfg = load_app_config()
    email = (request.form.get("email") or "").strip().lower()
    cfg.emails = [e for e in cfg.emails if e.lower() != email]
    cfg.save()
    flash(f"Correo eliminado: {email}")
    return redirect(url_for("home"))


@app.post("/schedule")
def set_schedule():
    cfg = load_app_config()
    day = (request.form.get("weekday") or "monday").lower()
    if day not in WEEKDAY_MAP:
        flash("Día inválido")
        return redirect(url_for("home"))
    cfg.schedule.weekday = day
    cfg.schedule.hour = int(request.form.get("hour") or 7)
    cfg.schedule.minute = int(request.form.get("minute") or 30)
    cfg.save()
    try:
        sync_launch_agent()
        flash(
            f"Horario guardado: {day} {cfg.schedule.hour:02d}:{cfg.schedule.minute:02d} (LaunchAgent actualizado)"
        )
    except Exception as exc:
        flash(f"Horario guardado, pero no se pudo sync LaunchAgent: {exc}")
    return redirect(url_for("home"))


@app.post("/theme")
def set_theme():
    cfg = load_app_config()
    theme = (request.form.get("theme") or "").strip()
    if theme not in cfg.themes:
        flash("Temática no encontrada")
        return redirect(url_for("home"))
    cfg.active_theme = theme
    cfg.save()
    flash(f"Temática activa: {theme}")
    return redirect(url_for("home"))


@app.post("/themes/create")
def create_theme():
    cfg = load_app_config()
    title = (request.form.get("title") or "").strip()
    short_label = (request.form.get("short_label") or "").strip()
    audience = (request.form.get("audience") or "").strip()
    focus = (request.form.get("focus") or "").strip()
    theme_id = (request.form.get("theme_id") or "").strip() or _slug(short_label or title)
    theme_id = _slug(theme_id)

    queries_raw = request.form.get("queries") or ""
    queries: list[tuple[str, str]] = []
    for line in queries_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            q, topic = [p.strip() for p in line.split("|", 1)]
        else:
            q, topic = line, "GENERAL"
        if q:
            queries.append((q, topic or "GENERAL"))

    axes = [
        a.strip()
        for a in (request.form.get("axes") or "").splitlines()
        if a.strip()
    ]

    if not title or not short_label or not focus or not queries:
        flash("Faltan título, etiqueta, enfoque o búsquedas")
        return redirect(url_for("home"))

    cfg.themes[theme_id] = ThemeConfig(
        id=theme_id,
        title=title,
        short_label=short_label,
        audience=audience,
        focus=focus,
        queries=queries,
        analysis_axes=axes,
    )
    if request.form.get("activate"):
        cfg.active_theme = theme_id
    cfg.save()
    flash(f"Temática creada: {theme_id}")
    return redirect(url_for("home"))


# Fix flash rendering (Flask flashes need get_flashed_messages)
@app.context_processor
def inject_flashes():
    from flask import get_flashed_messages

    return {"messages": get_flashed_messages()}


def run_admin(host: str = "127.0.0.1", port: int = 5055, open_browser: bool = True) -> None:
    url = f"http://{host}:{port}/"
    if open_browser:
        Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Panel de configuración: {url}")
    app.run(host=host, port=port, debug=False)
