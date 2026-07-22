# Boletines semanales configurables

Genera un boletín, lo envía por correo (PDF adjunto), lo sube a **Google Drive** y lo publica en un **sitio GitHub Pages** para verlo online.

## Qué puedes configurar (`config.yaml`)

| Qué | Cómo |
|---|---|
| Destinatarios | `emails:` o `python -m boletin add-email alguien@correo.com` |
| Día / hora | `schedule:` o `python -m boletin set-schedule --day monday --hour 7 --minute 30` |
| Temática | `active_theme: pae` / `economia` o `python -m boletin set-theme economia` |
| Drive | `drive.enabled` + carpeta |
| Sitio web | `github_pages.enabled` |

Secretos (Gmail, Gemini, etc.) van en `.env`, no en `config.yaml`.

## Instalación

```bash
cd "Boletines Informativos"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completa GMAIL_APP_PASSWORD y GEMINI_API_KEY
```

## Comandos útiles

```bash
# Ver configuración
PYTHONPATH=src python -m boletin config

# Agregar / quitar correos
PYTHONPATH=src python -m boletin add-email colega@empresa.cl
PYTHONPATH=src python -m boletin remove-email colega@empresa.cl

# Cambiar día/hora y sincronizar el Mac
PYTHONPATH=src python -m boletin set-schedule --day monday --hour 7 --minute 30
PYTHONPATH=src python -m boletin sync-schedule

# Cambiar temática (PAE → economía)
PYTHONPATH=src python -m boletin set-theme economia

# Generar y enviar (Drive + Pages + correo)
PYTHONPATH=src python -m boletin run

# Solo archivos locales
PYTHONPATH=src python -m boletin run --no-email --no-drive --no-pages
```

## Google Drive (una sola vez)

1. En [Google Cloud Console](https://console.cloud.google.com/): crea un proyecto, habilita **Google Drive API**.
2. Credenciales → **OAuth client ID** → tipo **Aplicación de escritorio**.
3. Descarga el JSON como `credentials/credentials.json`.
4. Ejecuta:

```bash
PYTHONPATH=src python -m boletin drive-auth
```

Se abrirá el navegador para autorizar. El token queda en `credentials/drive_token.json` (no se sube a git).

## GitHub Pages (ver boletines online)

1. Crea un repo en GitHub y súbelo.
2. Settings → Pages → Source: **Deploy from a branch** → branch `main` → folder `/docs`.
3. La URL será: `https://<usuario>.github.io/<repo>/`

Cada corrida actualiza `docs/data/boletines.json` y copia el PDF a `docs/boletines/`. Si Drive está activo, también aparece el link a Drive.

Para publicar cambios del sitio:

```bash
git add docs config.yaml
git commit -m "Publicar boletín"
git push
```

## Periodo cubierto

Siempre la **semana calendario previa** (lunes→domingo anteriores al día de envío), con filtro estricto de fechas.

## Temáticas

Ya vienen dos en `config.yaml`:

- `pae` — JUNAEB / PAE / JUNJI / Integra / MINEDUC  
- `economia` — macro, Hacienda, Banco Central, mercados Chile  

Puedes agregar más bloques bajo `themes:` con tus propias búsquedas y ejes de análisis.
