"""Decide si un documento habla realmente del tema pedido.

Los buscadores devuelven cualquier pieza que comparta una palabra con la consulta:
al pedir «reforma de pensiones Chile», Reddit entrega posts de r/chile sobre
fútbol o avisos personales. Sin este filtro el análisis mide ruido y las
tendencias reflejan la actividad del subreddit, no la del tema.
"""

from __future__ import annotations

import re
import unicodedata

from media_analyzer.models import SourceDocument

# Palabras vacías que no aportan a la identificación del tema.
STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "un", "una", "y", "o", "en", "por",
    "para", "con", "sin", "sobre", "the", "of", "and", "in", "on", "for", "to",
    "que", "al", "se", "su", "sus", "es", "chile", "chileno", "chilena",
}


def normalize(text: str) -> str:
    """Minúsculas sin tildes, para comparar «pensión» con «pension»."""
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def significant_terms(phrase: str) -> list[str]:
    """Palabras con carga semántica de una frase, sin artículos ni preposiciones."""
    words = re.findall(r"[a-z0-9]+", normalize(phrase))
    return [w for w in words if len(w) > 3 and w not in STOPWORDS]


def is_relevant(text: str, topic: str, actors: list[str] | None = None) -> bool:
    """Un texto es relevante si contiene el tema, sus términos clave o un actor.

    Para temas de varias palabras se exige al menos dos términos significativos:
    «reforma» sola no basta para un análisis sobre «reforma de pensiones».
    """
    haystack = normalize(text)
    if not haystack.strip():
        return False

    topic_normalized = normalize(topic).strip()
    if topic_normalized and topic_normalized in haystack:
        return True

    for actor in actors or []:
        actor_normalized = normalize(actor).strip()
        if actor_normalized and actor_normalized in haystack:
            return True
        # Apellido o nombre suelto de un actor identificable.
        actor_terms = significant_terms(actor)
        if len(actor_terms) == 1 and actor_terms[0] in haystack:
            return True
        if len(actor_terms) > 1 and sum(t in haystack for t in actor_terms) >= 2:
            return True

    terms = significant_terms(topic)
    if not terms:
        return True
    if len(terms) == 1:
        return terms[0] in haystack
    return sum(term in haystack for term in terms) >= 2


def filter_relevant(
    documents: list[SourceDocument], topic: str, actors: list[str] | None = None
) -> tuple[list[SourceDocument], list[SourceDocument]]:
    """Separa los documentos del tema de los que llegaron por ruido del buscador."""
    kept: list[SourceDocument] = []
    dropped: list[SourceDocument] = []
    for doc in documents:
        blob = f"{doc.title or ''} {doc.excerpt or ''} {(doc.text or '')[:1200]}"
        if is_relevant(blob, topic, actors):
            kept.append(doc)
        else:
            doc.included = False
            doc.exclusion_reason = "off_topic"
            dropped.append(doc)
    return kept, dropped
