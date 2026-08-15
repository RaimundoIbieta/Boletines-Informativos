"""Analiza lo que se dice *sobre* un actor: postura, comparaciones y preferencia.

La pregunta que responde este módulo no es qué publica el actor, sino qué opinan
terceros de él: si lo apoyan o lo critican, y cuando se lo compara con un rival,
quién sale favorecido. El resultado se expresa como un sondeo de la conversación
observada, que no es una encuesta representativa: mide lo que se publicó en las
fuentes accesibles, no a la población.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Iterable

from media_analyzer.models import (
    OpinionAnalysis,
    OpinionQuote,
    PreferenceDuel,
    SourceDocument,
    StanceBreakdown,
)

logger = logging.getLogger(__name__)

# Léxico bilingüe: Reddit y Bluesky mezclan inglés y español.
FAVORABLE = {
    "goat", "mejor", "leyenda", "legend", "ídolo", "idolo", "idol", "crack", "genio",
    "máquina", "maquina", "monstruo", "fenómeno", "fenomeno", "increíble", "increible",
    "incredible", "amazing", "brilliant", "clase", "class", "respeto", "respect",
    "admiro", "admirable", "grande", "greatest", "best", "king", "rey", "insuperable",
    "imparable", "espectacular", "impresionante", "love", "amo", "querido", "beloved",
    "ejemplo", "profesional", "trabajador", "dedicación", "dedicacion", "clutch",
    "histórico", "historico", "top", "élite", "elite", "gigante", "bestia",
}
CRITICAL = {
    "sobrevalorado", "overrated", "peor", "worst", "ego", "egoísta", "egoista",
    "egotistical", "arrogante", "arrogant", "odio", "hate", "detesto", "despise",
    "payaso", "clown", "ridículo", "ridiculo", "ridiculous", "llorón", "lloron",
    "crying", "tramposo", "cheat", "diver", "acabado", "washed", "finished",
    "decadencia", "fracaso", "failure", "penaldo", "pathetic", "patético", "patetico",
    "cringe", "annoying", "insufferable", "fraude", "fraud", "sobrestimado",
    "mediocre", "vergüenza", "verguenza", "embarrassing", "choke", "flop",
}
# Negadores que invierten el sentido de la frase.
NEGATORS = {"no", "not", "nunca", "never", "nadie", "nobody", "ni", "sin", "tampoco"}

# Palabras en handles/publishers que delatan una cuenta de medio y no de audiencia.
MEDIA_MARKERS = (
    "tv", "diario", "news", "noticia", "radio", "prensa", "press", "times", "post",
    "herald", "journal", "revista", "magazine", "sport", "deporte", "espn", "marca",
    "record", "latinus", "media", "cnn", "bbc", "afp", "reuters", "agencia", "canal",
    "informa", "reporte", "mundo", "nacion", "clarin", "abc", "elpais",
)

COMPARISON_PATTERNS = (
    r"(?P<a>[\w\s.'-]{2,28}?)\s+(?:es|is|era|was)?\s*(?:mucho\s+|much\s+|way\s+)?"
    r"(?:mejor|better|superior)\s+(?:que|than|a)\s+(?P<b>[\w\s.'-]{2,28})",
    r"(?P<a>[\w\s.'-]{2,28}?)\s*>\s*(?P<b>[\w\s.'-]{2,28})",
    r"(?:prefiero|prefer|elijo|choose)\s+(?:a\s+)?(?P<a>[\w\s.'-]{2,28}?)"
    r"\s+(?:antes\s+que|sobre|over|than|a)\s+(?P<b>[\w\s.'-]{2,28})",
)

AUDIENCE_SOURCES = {"reddit", "bluesky", "mastodon", "x", "instagram", "tiktok", "facebook"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü]+", (text or "").lower())


def document_text(doc: SourceDocument) -> str:
    """Texto para analizar, sin repetir el título cuando ya está en el cuerpo."""
    title = (doc.title or "").strip()
    body = (doc.text or doc.excerpt or "").strip()
    if not body:
        return title
    if title and title.rstrip(".…") in body:
        return body
    return f"{title}\n{body}".strip()


def is_media_voice(doc: SourceDocument) -> bool:
    """Distingue la voz de un medio de la de una persona.

    En Bluesky y Reddit circulan muchas cuentas de medios que solo replican
    titulares; contarlas como opinión ciudadana inflaría el resultado.
    """
    if doc.source_type in {"news", "youtube"}:
        return True
    if (doc.metadata or {}).get("coverage") == "indirect_media_citation":
        return True
    haystack = f"{doc.author or ''} {doc.publisher or ''}".lower()
    return any(marker in haystack for marker in MEDIA_MARKERS)


def name_keys(name: str) -> list[str]:
    """Formas en que puede aparecer un nombre: completo y cada parte significativa.

    La gente escribe «Cristiano», «Ronaldo» o «CR7», casi nunca el nombre completo.
    """
    value = (name or "").strip().lower()
    if not value:
        return []
    keys = [value]
    keys.extend(part for part in value.split() if len(part) > 3)
    return list(dict.fromkeys(keys))


def mentions_actor(text: str, actor: str, aliases: Iterable[str] = ()) -> bool:
    haystack = (text or "").lower()
    for name in (actor, *aliases):
        if any(key in haystack for key in name_keys(name)):
            return True
    return False


def classify_stance(text: str, actor: str) -> tuple[str, float, str]:
    """Devuelve postura, intensidad y la palabra que la explica.

    Se mira la ventana de texto alrededor del actor para no atribuirle
    valoraciones que en realidad apuntan a otra persona de la misma frase.
    """
    body = text or ""
    lower = body.lower()
    window = body
    idx = -1
    for candidate in name_keys(actor):
        idx = lower.find(candidate)
        if idx >= 0:
            break
    if idx >= 0:
        window = body[max(0, idx - 160) : idx + 220]

    words = _tokens(window)
    favor: list[str] = []
    against: list[str] = []
    for position, word in enumerate(words):
        previous = set(words[max(0, position - 3) : position])
        negated = bool(previous & NEGATORS)
        if word in FAVORABLE:
            (against if negated else favor).append(word)
        elif word in CRITICAL:
            (favor if negated else against).append(word)

    score = len(favor) - len(against)
    if score > 0:
        return "favorable", min(1.0, 0.3 + 0.2 * score), favor[0]
    if score < 0:
        return "critica", min(1.0, 0.3 + 0.2 * abs(score)), against[0]
    return "neutra", 0.0, ""


def _clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip(" .,:;!?\"'()[]"))
    return name


def detect_preference(text: str, actor: str, rival: str) -> str | None:
    """Ante una comparación explícita, indica quién queda arriba.

    Devuelve el nombre del favorecido, o None si no hay comparación clara.
    """
    body = (text or "").lower()
    actor_keys = name_keys(actor)
    rival_keys = name_keys(rival)
    if not any(k in body for k in actor_keys) or not any(k in body for k in rival_keys):
        return None

    def has(fragment: str, keys: list[str]) -> bool:
        return any(key in fragment for key in keys)

    for pattern in COMPARISON_PATTERNS:
        for match in re.finditer(pattern, body):
            left = _clean_name(match.group("a"))
            right = _clean_name(match.group("b"))
            if has(left, actor_keys) and has(right, rival_keys):
                return actor
            if has(left, rival_keys) and has(right, actor_keys):
                return rival
    return None


def classify_with_gemini(
    documents: list[SourceDocument],
    actor: str,
    rivals: list[str],
    api_key: str,
    model: str = "gemini-2.0-flash",
    *,
    limit: int = 60,
) -> dict[str, dict]:
    """Clasifica postura y preferencia con el modelo, que sí capta ironía.

    Devuelve {document_id: {"stance", "prefers", "reason"}}. Ante cualquier fallo
    se deja que el llamador use el léxico.
    """
    import json

    import httpx

    payload = [{"id": d.id, "text": document_text(d)[:700]} for d in documents[:limit]]
    if not payload:
        return {}
    prompt = f"""Analiza qué opinan estos textos SOBRE «{actor}».
Rivales para comparación: {rivals or "ninguno"}.
Devuelve SOLO JSON:
{{"items":[{{"id":"...","stance":"favorable|critica|neutra","prefers":"nombre o null","reason":"palabra clave"}}]}}
Reglas:
- stance es la actitud hacia {actor}, no el tono general del texto.
- Detecta ironía y sarcasmo: elogio burlón es "critica".
- Un titular informativo sin valoración es "neutra".
- "prefers" solo si el texto compara explícitamente a {actor} con un rival; indica quién queda mejor.
- No inventes ids.
Textos:
{json.dumps(payload, ensure_ascii=False)}
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    valid = {d.id for d in documents}
    out: dict[str, dict] = {}
    for item in data.get("items") or []:
        doc_id = str(item.get("id") or "")
        if doc_id not in valid:
            continue
        stance = str(item.get("stance") or "neutra").lower()
        if stance not in {"favorable", "critica", "neutra"}:
            stance = "neutra"
        prefers = item.get("prefers")
        out[doc_id] = {
            "stance": stance,
            "prefers": str(prefers) if prefers and str(prefers).lower() != "null" else "",
            "reason": str(item.get("reason") or "")[:40],
        }
    return out


def build_opinion_analysis(
    documents: list[SourceDocument],
    actor: str,
    *,
    rivals: list[str] | None = None,
    aliases: list[str] | None = None,
    max_quotes: int = 6,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.0-flash",
) -> OpinionAnalysis:
    """Resume qué se dice del actor y cómo se compara con sus rivales."""
    aliases = aliases or []
    rivals = [r for r in (rivals or []) if r.strip()]

    audience = StanceBreakdown()
    media = StanceBreakdown()
    quotes: list[OpinionQuote] = []
    duel_counts: dict[str, Counter] = {rival: Counter() for rival in rivals}
    reason_counter: Counter = Counter()
    analyzed = 0

    relevant = [doc for doc in documents if mentions_actor(document_text(doc), actor, aliases)]

    llm: dict[str, dict] = {}
    classifier = "lexicon"
    if gemini_api_key and relevant:
        try:
            llm = classify_with_gemini(relevant, actor, rivals, gemini_api_key, gemini_model)
            if llm:
                classifier = "gemini"
        except Exception as exc:
            logger.warning("Clasificación de opinión con Gemini falló, uso léxico: %s", exc)

    for doc in relevant:
        text = document_text(doc)
        analyzed += 1
        verdict = llm.get(doc.id)
        if verdict:
            stance = verdict["stance"]
            reason = verdict["reason"]
            intensity = 0.6 if stance != "neutra" else 0.0
        else:
            stance, intensity, reason = classify_stance(text, actor)
        bucket = media if is_media_voice(doc) else audience
        bucket.add(stance)
        if reason:
            reason_counter[reason] += 1

        if stance != "neutra" and len(quotes) < max_quotes * 3:
            snippet = re.sub(r"\s+", " ", text)[:260]
            quotes.append(
                OpinionQuote(
                    stance=stance,
                    intensity=intensity,
                    text=snippet,
                    author=doc.author or "",
                    source_type=doc.source_type,
                    url=doc.url or "",
                    voice="media" if is_media_voice(doc) else "audience",
                )
            )

        for rival in rivals:
            winner = detect_preference(text, actor, rival)
            if not winner and verdict and verdict["prefers"]:
                choice = verdict["prefers"].lower()
                if any(k in choice for k in name_keys(actor)):
                    winner = actor
                elif any(k in choice for k in name_keys(rival)):
                    winner = rival
            if winner:
                duel_counts[rival][winner] += 1

    duels: list[PreferenceDuel] = []
    for rival, counter in duel_counts.items():
        actor_votes = counter.get(actor, 0)
        rival_votes = counter.get(rival, 0)
        if not (actor_votes or rival_votes):
            continue
        duels.append(
            PreferenceDuel(
                actor=actor,
                rival=rival,
                actor_votes=actor_votes,
                rival_votes=rival_votes,
            )
        )
    duels.sort(key=lambda d: d.total, reverse=True)

    # Se prioriza la voz de la audiencia y se alternan posturas para no sesgar la muestra.
    quotes.sort(key=lambda q: (q.voice != "audience", -q.intensity))
    balanced: list[OpinionQuote] = []
    for stance in ("favorable", "critica"):
        balanced.extend([q for q in quotes if q.stance == stance][: max_quotes // 2])
    balanced.sort(key=lambda q: (q.voice != "audience", -q.intensity))

    return OpinionAnalysis(
        actor=actor,
        documents_analyzed=analyzed,
        audience=audience,
        media=media,
        duels=duels,
        quotes=balanced,
        top_reasons=[word for word, _ in reason_counter.most_common(8)],
        classifier=classifier,
    )
