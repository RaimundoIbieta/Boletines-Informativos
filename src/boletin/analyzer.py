from __future__ import annotations

import json
import logging
from datetime import date, datetime

from boletin.config import Settings, ThemeConfig
from boletin.collector import is_blocked_title
from boletin.models import BoletinSemanal, NoticiaAnalizada, RawArticle

logger = logging.getLogger(__name__)

DEFAULT_MIN = 8
DEFAULT_MAX = 10


def _build_system_prompt(theme: ThemeConfig, min_n: int, max_n: int) -> str:
    axes = "\n".join(f"- {a}" for a in theme.analysis_axes) or "- impacto estratégico"
    return f"""Eres un analista experto. Temática del boletín: {theme.title}.

Audiencia: {theme.audience or "tomadores de decisión"}.

Enfoque:
{theme.focus.strip()}

Ancla siempre el análisis en:
{axes}

Reglas de fecha (OBLIGATORIAS):
- El boletín cubre SOLO el periodo indicado (semana previa completa).
- NO incluyas noticias de meses o semanas anteriores aunque aparezcan en las candidatas.
- Si una nota es recirculada/antigua y el RSS la muestra “reciente”, DESCÁRTALA.
- El campo "fecha" de cada noticia DEBE caer dentro del periodo (YYYY-MM-DD).

Otras reglas:
- Selecciona entre {min_n} y {max_n} noticias REALES de las candidatas.
- No inventes noticias, URLs, fechas ni fuentes.
- Resumen: 3-4 líneas.
- comentario, riesgos y oportunidades: concretos y accionables.
- Al final, síntesis semanal de 6-8 líneas.
- Responde SOLO con JSON válido.
"""


def _articles_payload(articles: list[RawArticle]) -> list[dict]:
    payload = []
    for i, a in enumerate(articles, start=1):
        payload.append(
            {
                "id": i,
                "titular": a.title,
                "fuente": a.source,
                "fecha": a.published.isoformat() if a.published else None,
                "link": a.url,
                "tema_sugerido": a.query_topic,
                "snippet": a.snippet,
                "texto": (a.full_text or a.snippet)[:3500],
            }
        )
    return payload


def _user_prompt(
    articles: list[RawArticle],
    start: date,
    end: date,
    min_n: int,
    max_n: int,
    theme: ThemeConfig,
) -> str:
    schema = {
        "noticias": [
            {
                "titular": "string",
                "fuente": "string",
                "fecha": "YYYY-MM-DD",
                "link": "url exacta de la candidata",
                "resumen": "3-4 líneas",
                "comentario": "análisis técnico-político / impacto",
                "riesgos": "riesgos para la audiencia",
                "oportunidades": "oportunidades para la audiencia",
                "tema": "etiqueta corta del subtema",
                "relevancia": "1-10",
            }
        ],
        "sintesis": "6-8 líneas",
    }
    return f"""Periodo del boletín: {start.isoformat()} a {end.isoformat()} (SOLO noticias de esas fechas).
Temática: {theme.title}

Selecciona entre {min_n} y {max_n} noticias más relevantes.
Si detectas una nota antigua o recirculada, exclúyela.
Devuelve JSON con esta forma exacta:
{json.dumps(schema, ensure_ascii=False, indent=2)}

Candidatas:
{json.dumps(_articles_payload(articles), ensure_ascii=False, indent=2)}
"""


def _parse_noticia_fecha(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_boletin(
    raw: str,
    start: date,
    end: date,
    generated: date,
    theme: ThemeConfig,
) -> BoletinSemanal:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    data = json.loads(text)
    noticias: list[NoticiaAnalizada] = []
    for item in data.get("noticias", []):
        n = NoticiaAnalizada.model_validate(item)
        if is_blocked_title(n.titular):
            logger.warning("Noticia en lista negra descartada: %s", n.titular[:80])
            continue
        f = _parse_noticia_fecha(n.fecha)
        if f is None:
            logger.warning("Noticia sin fecha parseable descartada: %s", n.titular[:80])
            continue
        if f < start or f > end:
            logger.warning(
                "Noticia fuera de periodo (%s) descartada: %s",
                f.isoformat(),
                n.titular[:80],
            )
            continue
        n.fecha = f.isoformat()
        noticias.append(n)

    noticias.sort(key=lambda n: n.relevancia, reverse=True)
    return BoletinSemanal(
        periodo_inicio=start,
        periodo_fin=end,
        generado_el=generated,
        noticias=noticias,
        sintesis=data.get("sintesis", "").strip(),
        theme_id=theme.id,
        theme_title=theme.title,
        theme_label=theme.short_label,
    )


def _call_openai(settings: Settings, system: str, user: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or "{}"


def _call_anthropic(settings: Settings, system: str, user: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8000,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": user + "\n\nResponde únicamente con JSON."}],
    )
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts)


def _call_gemini(settings: Settings, system: str, user: str) -> str:
    import httpx
    from tenacity import (
        retry,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential,
    )

    models = []
    for candidate in (
        settings.gemini_model,
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-flash-latest",
    ):
        if candidate and candidate not in models:
            models.append(candidate)

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user + "\n\nResponde únicamente con JSON válido."}],
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }
    headers = {"x-goog-api-key": settings.gemini_api_key}

    def _is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500, 503}
        return isinstance(exc, httpx.TransportError)

    last_error: Exception | None = None
    for model in models:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        logger.info("Intentando Gemini modelo %s…", model)

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=3, max=30),
            reraise=True,
        )
        def _request(request_url: str = url) -> str:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(request_url, headers=headers, json=payload)
                if response.status_code >= 400:
                    logger.warning(
                        "Gemini HTTP %s (%s): %s",
                        response.status_code,
                        model,
                        response.text[:400],
                    )
                response.raise_for_status()
                data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"Respuesta inesperada de Gemini: {data}") from exc

        try:
            return _request()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in {404, 429}:
                continue
            raise

    assert last_error is not None
    raise last_error


def analyze_articles(
    articles: list[RawArticle],
    settings: Settings,
    start: date,
    end: date,
    theme: ThemeConfig,
    generated: date | None = None,
    *,
    min_noticias: int = DEFAULT_MIN,
    max_noticias: int = DEFAULT_MAX,
) -> BoletinSemanal:
    if not articles:
        raise ValueError(
            "No se encontraron noticias en el periodo. "
            "Prueba ampliar búsquedas o ejecutar en otro momento."
        )

    generated = generated or date.today()
    system = _build_system_prompt(theme, min_noticias, max_noticias)
    user = _user_prompt(articles, start, end, min_noticias, max_noticias, theme)

    logger.info("Analizando %s artículos (%s)…", len(articles), theme.id)
    if settings.gemini_api_key:
        raw = _call_gemini(settings, system, user)
    elif settings.anthropic_api_key:
        raw = _call_anthropic(settings, system, user)
    elif settings.openai_api_key:
        raw = _call_openai(settings, system, user)
    else:
        raise ValueError(
            "Configura GEMINI_API_KEY, ANTHROPIC_API_KEY u OPENAI_API_KEY"
        )

    boletin = _parse_boletin(raw, start, end, generated, theme)
    if len(boletin.noticias) < min_noticias and len(articles) >= min_noticias:
        logger.warning(
            "El modelo devolvió solo %s noticias (mínimo %s).",
            len(boletin.noticias),
            min_noticias,
        )
    return boletin
