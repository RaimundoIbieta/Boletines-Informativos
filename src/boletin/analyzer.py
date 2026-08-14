from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, datetime

from boletin.config import Settings, ThemeConfig
from boletin.collector import is_blocked_title, is_google_news_url, unwrap_google_news_url
from boletin.models import BoletinSemanal, NoticiaAnalizada, RawArticle

logger = logging.getLogger(__name__)

DEFAULT_MIN = 8
DEFAULT_MAX = 10

_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "o", "en", "un", "una", "unos", "unas",
    "por", "para", "con", "sin", "al", "a", "se", "su", "sus", "que", "como", "más",
    "tras", "ante", "sobre", "entre", "desde", "hasta", "este", "esta", "estos", "estas",
    "chile", "chileno", "chilena", "gobierno", "tras", "segun", "según",
}


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


def _title_tokens(title: str) -> set[str]:
    t = _fold(title)
    # Unifica variantes frecuentes del mismo hecho
    t = (
        t.replace("megarreforma", "mega reforma")
        .replace("mega-reforma", "mega reforma")
        .replace("mega reforma", "mega reforma")
    )
    words = re.findall(r"[a-z0-9]{4,}", t)
    return {w for w in words if w not in _STOPWORDS}


def _token_soft_overlap(ta: set[str], tb: set[str]) -> set[str]:
    """Tokens compartidos permitiendo prefijos/compuestos (mega⊂megarreforma)."""
    shared: set[str] = set(ta & tb)
    for a in ta:
        for b in tb:
            if a == b:
                continue
            if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                shared.add(a if len(a) <= len(b) else b)
    return shared


def _titles_are_same_story(a: str, b: str) -> bool:
    """True si dos titulares describen el mismo hecho (cobertura multi-medio)."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return False
    inter = _token_soft_overlap(ta, tb)
    if len(inter) >= 3:
        return True
    jacc = len(inter) / max(1, len(ta | tb))
    if jacc >= 0.4 and len(inter) >= 2:
        return True
    # Nombre propio + otro ancla (p. ej. Kast + reforma/congreso)
    rare = {w for w in inter if len(w) >= 5}
    if rare and len(inter) >= 2:
        return True
    if len(inter) >= 2 and (inter == ta or inter == tb):
        return True
    return False


def _dedupe_same_story(noticias: list[NoticiaAnalizada]) -> list[NoticiaAnalizada]:
    """Deja una sola noticia por hecho; conserva la de mayor relevancia."""
    kept: list[NoticiaAnalizada] = []
    for n in sorted(noticias, key=lambda x: x.relevancia, reverse=True):
        dup = next((k for k in kept if _titles_are_same_story(n.titular, k.titular)), None)
        if dup:
            logger.info(
                "Duplicado del mismo hecho omitido (%s) — ya está: %s",
                n.titular[:70],
                dup.titular[:70],
            )
            continue
        kept.append(n)
    return kept


def _build_system_prompt(theme: ThemeConfig, min_n: int, max_n: int) -> str:
    axes = "\n".join(f"- {a}" for a in theme.analysis_axes) or "- impacto estratégico"
    theme_text = f"{theme.title} {theme.short_label}".lower()
    politics_priority = ""
    if "polític" in theme_text or "politic" in theme_text:
        politics_priority = """
Jerarquía editorial para POLÍTICA CHILENA (OBLIGATORIA):
- El foco principal es la política como ejercicio del poder y actuación de los políticos.
- Prioriza: Presidencia y gabinete; nombramientos y renuncias de ministros/subsecretarios;
  decisiones del Gobierno; oposición; partidos y coaliciones; Congreso, negociaciones y
  votaciones; conflictos, responsabilidades políticas, elecciones y encuestas.
- Un cambio de gabinete, renuncia o nombramiento ministerial relevante NO puede omitirse
  si aparece entre las candidatas del periodo.
- Las políticas públicas sectoriales (por ejemplo, Política Nacional de la Lectura) son
  secundarias: inclúyelas si provocan una decisión o controversia política nacional, o si
  no hay suficiente actualidad sobre actores políticos.
- Si hay suficientes candidatas de política institucional/partidaria, la MAYORÍA de las
  noticias seleccionadas debe pertenecer a esa categoría.
"""
    sections_priority = ""
    if theme.sections:
        section_names = ", ".join(theme.sections)
        sections_priority = f"""
Secciones editoriales fijas (OBLIGATORIAS y en este orden):
{section_names}
- Clasifica cada noticia en EXACTAMENTE una de estas secciones; usa el nombre exacto.
- Incluye al menos una noticia relevante por sección cuando existan candidatas.
- Busca equilibrio: idealmente 2 o 3 noticias por sección, sin rellenar con notas irrelevantes.
- Desambiguación: POLÍTICA trata actores, partidos, Gobierno y Congreso; NACIONAL trata
  hechos internos relevantes que no correspondan principalmente a Economía, Social o Política;
  INTERNACIONAL trata hechos externos con impacto o interés para Chile.
"""
    return f"""Eres un analista experto. Temática del boletín: {theme.title}.

Audiencia: {theme.audience or "tomadores de decisión"}.

Enfoque:
{theme.focus.strip()}

Ancla siempre el análisis en:
{axes}
{politics_priority}
{sections_priority}

Reglas de fecha (OBLIGATORIAS):
- El boletín cubre SOLO el periodo indicado, incluidos el primer y el ÚLTIMO día.
- Lo ocurrido el último día del periodo (hoy) es lo más relevante: NO lo omitas.
- NO incluyas noticias de meses o semanas anteriores aunque aparezcan en las candidatas.
- Si una nota es recirculada/antigua y el RSS la muestra “reciente”, DESCÁRTALA.
- El campo "fecha" de cada noticia DEBE caer dentro del periodo (YYYY-MM-DD).

Otras reglas:
- Selecciona entre {min_n} y {max_n} noticias REALES de las candidatas.
- No inventes noticias, URLs, fechas ni fuentes.
- El campo "link" DEBE ser la URL exacta de la candidata (sitio del medio). NUNCA uses news.google.com.
- DIVERSIDAD (OBLIGATORIA): cada HECHO o acontecimiento aparece UNA sola vez.
  Si varios medios cubren lo mismo (misma reforma, mismo anuncio, misma votación),
  elige SOLO la mejor fuente (oficial o más completa) y DESCARTA el resto.
  Prioriza variedad de subtemas: no sirve un boletín con 7 versiones del mismo titular.
- Resumen: 3-4 líneas.
- comentario, riesgos y oportunidades: concretos y accionables para ESTA audiencia y temática.
- Al final, síntesis semanal de 6-8 líneas (sobre esta temática, no sobre otras).
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


def _section_candidates(
    articles: list[RawArticle],
    sections: list[str],
    *,
    per_section: int = 15,
) -> list[RawArticle]:
    """Acota periodos largos sin perder representación de ninguna sección."""
    if not sections:
        return articles
    selected: list[RawArticle] = []
    selected_urls: set[str] = set()
    for section in sections:
        rows = [a for a in articles if _fold(a.query_topic) == _fold(section)]
        rows.sort(key=lambda a: a.published or date.min, reverse=True)
        for article in rows[:per_section]:
            if article.url not in selected_urls:
                selected.append(article)
                selected_urls.add(article.url)
    return selected


def _user_prompt(
    articles: list[RawArticle],
    start: date,
    end: date,
    min_n: int,
    max_n: int,
    theme: ThemeConfig,
) -> str:
    section_rule = (
        f" El campo tema debe ser uno de: {', '.join(theme.sections)}."
        if theme.sections
        else ""
    )
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
                "tema": (
                    f"una sección exacta: {', '.join(theme.sections)}"
                    if theme.sections
                    else "etiqueta corta del subtema"
                ),
                "relevancia": "1-10",
            }
        ],
        "sintesis": "6-8 líneas",
    }
    return f"""Periodo del boletín: {start.isoformat()} a {end.isoformat()} inclusive (SOLO noticias de esas fechas).
Temática: {theme.title}

Prioriza lo más reciente: los hechos de {end.isoformat()} deben aparecer si son relevantes.{section_rule}
Selecciona entre {min_n} y {max_n} noticias más relevantes y DIVERSAS.
Si varios medios repiten el mismo hecho, quédate con una sola.
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
        # Solo links directos del medio (como en generación local)
        if is_google_news_url(n.link):
            fixed = unwrap_google_news_url(n.link)
            if fixed and not is_google_news_url(fixed):
                n.link = fixed
            else:
                logger.warning("Link Google News sin URL directa, omitido: %s", n.titular[:80])
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
        if theme.sections:
            folded = _fold(n.tema).strip()
            section = next((s for s in theme.sections if _fold(s).strip() == folded), None)
            if not section:
                logger.warning("Sección no válida (%s); se asigna a %s", n.tema, theme.sections[0])
                section = theme.sections[0]
            n.tema = section.upper()
        noticias.append(n)

    noticias = _dedupe_same_story(noticias)
    if theme.sections:
        order = {_fold(section): i for i, section in enumerate(theme.sections)}
        noticias.sort(key=lambda n: (order.get(_fold(n.tema), len(order)), -n.relevancia))
    else:
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
        sections=theme.sections,
        cadence=theme.cadence,
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
    if theme.sections:
        min_noticias = max(min_noticias, len(theme.sections))
        max_noticias = max(max_noticias, len(theme.sections) * 3)
        articles = _section_candidates(articles, theme.sections)
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
