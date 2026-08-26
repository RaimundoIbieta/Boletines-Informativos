from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from media_analyzer.models import (
    ActorInsight,
    AnalysisReport,
    AnalysisRequest,
    NarrativeInsight,
    SentimentObservation,
    SourceDocument,
)

logger = logging.getLogger(__name__)


def _heuristic_sentiment(text: str, target: str) -> SentimentObservation:
    t = (text or "").lower()
    target_l = target.lower()
    pos = ["apoya", "apoyo", "mejor", "lidera", "favorito", "ganaría", "positivo", "confianza"]
    neg = ["rechazo", "crítica", "critica", "escándalo", "fraude", "corrupción", "peor", "renuncia", "polémica"]
    score = 0
    for w in pos:
        if w in t:
            score += 1
    for w in neg:
        if w in t:
            score -= 1
    if score >= 2:
        label, s = "positivo", 0.5
    elif score <= -2:
        label, s = "negativo", -0.5
    elif score > 0:
        label, s = "positivo", 0.25
    elif score < 0:
        label, s = "negativo", -0.25
    else:
        label, s = "neutral", 0.0
    # Extraer una frase cercana al target si aparece
    evidence = text[:180]
    idx = t.find(target_l)
    if idx >= 0:
        evidence = text[max(0, idx - 40) : idx + 140]
    return SentimentObservation(
        document_id="",
        target=target,
        label=label,  # type: ignore[arg-type]
        score=s,
        confidence=0.4,
        evidence=evidence.strip(),
    )


def analyze_with_llm(
    request: AnalysisRequest,
    documents: list[SourceDocument],
    *,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-3.6-flash",
) -> AnalysisReport:
    actors = list(dict.fromkeys([*(request.actors or []), * _guess_actors(documents, request.topic)]))
    if not actors:
        actors = [request.topic]

    observations: list[SentimentObservation] = []
    if gemini_api_key and documents:
        try:
            observations = _call_gemini_sentiment(
                request, documents[:40], actors, gemini_api_key, gemini_model
            )
        except Exception as exc:
            logger.warning("Gemini sentimiento falló, uso heurística: %s", exc)

    if not observations:
        for doc in documents[:60]:
            for actor in actors[:8]:
                obs = _heuristic_sentiment(f"{doc.title}\n{doc.excerpt}\n{doc.text[:800]}", actor)
                obs.document_id = doc.id
                observations.append(obs)

    actor_insights = _aggregate_actors(actors, observations, documents)
    narratives = _extract_narratives(documents, observations)
    trends = _volume_trends(documents)
    sentiment_summary = _sentiment_summary(observations)
    warnings = []
    if len(documents) < 5:
        warnings.append("Muestra pequeña: los resultados son exploratorios, no representativos.")
    warnings.append(
        "Las redes restringidas (X/Instagram/Facebook/TikTok) tienen cobertura parcial gratuita."
    )
    if (request.period_end - request.period_start).days > 30:
        warnings.append(
            "Periodo largo: la cobertura histórica de redes abiertas puede ser incompleta."
        )

    findings = []
    if actor_insights:
        top = actor_insights[0]
        findings.append(
            f"El actor con más menciones es {top.name} ({top.mentions}), "
            f"con tono promedio {top.average_score:+.2f}."
        )
    # El pico y la tendencia los reporta el módulo de proyección, que agrupa por
    # día, semana o mes según el periodo; duplicarlo aquí daba cifras discordantes.
    findings.append(
        f"Se analizaron {len(documents)} documentos sobre «{request.topic}» "
        f"en {request.territory_label}."
    )

    summary = (
        f"Radiografía mediática de «{request.topic}» ({request.territory_label}) "
        f"entre {request.period_start.isoformat()} y {request.period_end.isoformat()}. "
        f"Se procesaron {len(documents)} piezas de fuentes abiertas y aportes del usuario. "
        "El sentimiento se calcula por actor con evidencia textual; "
        "no equivale a una encuesta representativa."
    )

    return AnalysisReport(
        request_id=request.id or "",
        topic=request.topic,
        territory_label=request.territory_label,
        period_start=request.period_start,
        period_end=request.period_end,
        generated_at=datetime.now(timezone.utc),
        executive_summary=summary,
        findings=findings,
        actors=actor_insights,
        narratives=narratives,
        trends=trends,
        sentiment=sentiment_summary,
        geography={},
        documents=documents,
        methodology={
            "prompt_version": "media-v1",
            "sentiment": "dirigido por actor con evidencia",
            "sources": request.enabled_sources,
            "limitations": warnings,
        },
        warnings=warnings,
        model_provider="gemini" if gemini_api_key else "heuristic",
        model_name=gemini_model if gemini_api_key else "heuristic-v1",
    )


def _guess_actors(documents: list[SourceDocument], topic: str) -> list[str]:
    # Extrae nombres propios simples (2 palabras capitalizadas)
    pat = re.compile(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)+)\b")
    counts: Counter[str] = Counter()
    for doc in documents[:80]:
        for m in pat.findall(f"{doc.title} {doc.excerpt}"):
            if len(m) > 5 and "Chile" not in m:
                counts[m] += 1
    return [name for name, _ in counts.most_common(8)]


def _aggregate_actors(
    actors: list[str],
    observations: list[SentimentObservation],
    documents: list[SourceDocument],
) -> list[ActorInsight]:
    by_actor: dict[str, list[SentimentObservation]] = defaultdict(list)
    for obs in observations:
        by_actor[obs.target].append(obs)
    insights = []
    for actor in actors:
        rows = by_actor.get(actor) or []
        if not rows:
            # menciones por texto
            mentions = sum(
                1
                for d in documents
                if actor.lower() in f"{d.title} {d.excerpt} {d.text[:500]}".lower()
            )
            insights.append(ActorInsight(name=actor, mentions=mentions))
            continue
        labels = Counter(r.label for r in rows)
        avg = sum(r.score for r in rows) / max(1, len(rows))
        quotes = [r.evidence for r in rows if r.evidence][:3]
        insights.append(
            ActorInsight(
                name=actor,
                mentions=len(rows),
                sentiment=dict(labels),
                average_score=round(avg, 3),
                sample_quotes=quotes,
            )
        )
    insights.sort(key=lambda a: a.mentions, reverse=True)
    return insights


def _extract_narratives(
    documents: list[SourceDocument],
    observations: list[SentimentObservation],
) -> list[NarrativeInsight]:
    # Narrativas simples por polaridad dominante
    pos = [o for o in observations if o.label in {"positivo", "muy_positivo"}]
    neg = [o for o in observations if o.label in {"negativo", "muy_negativo"}]
    out = []
    if pos:
        out.append(
            NarrativeInsight(
                title="Expectativa / apoyo",
                description="Fragmentos con tono favorable hacia actores del tema.",
                polarity="positivo",
                document_ids=[o.document_id for o in pos[:8]],
                evidence=[o.evidence for o in pos[:3] if o.evidence],
            )
        )
    if neg:
        out.append(
            NarrativeInsight(
                title="Crítica / rechazo",
                description="Fragmentos con tono crítico o de riesgo reputacional.",
                polarity="negativo",
                document_ids=[o.document_id for o in neg[:8]],
                evidence=[o.evidence for o in neg[:3] if o.evidence],
            )
        )
    if documents:
        out.append(
            NarrativeInsight(
                title="Cobertura informativa",
                description="Piezas de medios y redes que describen el tema sin polaridad clara.",
                polarity="neutral",
                document_ids=[d.id for d in documents[:8]],
                evidence=[d.title for d in documents[:3]],
            )
        )
    return out


def _volume_trends(documents: list[SourceDocument]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for d in documents:
        if d.published_at:
            counts[d.published_at.date().isoformat()] += 1
    return [{"date": d, "count": c} for d, c in sorted(counts.items())]


def _sentiment_summary(observations: list[SentimentObservation]) -> dict[str, Any]:
    labels = Counter(o.label for o in observations)
    avg = sum(o.score for o in observations) / max(1, len(observations))
    return {
        "labels": dict(labels),
        "average_score": round(avg, 3),
        "observations": len(observations),
    }


def _call_gemini_sentiment(
    request: AnalysisRequest,
    documents: list[SourceDocument],
    actors: list[str],
    api_key: str,
    model: str,
) -> list[SentimentObservation]:
    import httpx

    payload_docs = [
        {
            "id": d.id,
            "title": d.title,
            "source": d.publisher,
            "text": (d.text or d.excerpt)[:900],
        }
        for d in documents
    ]
    prompt = f"""Analiza sentimiento DIRIGIDO a actores sobre el tema "{request.topic}" en Chile.
Actores: {actors}
Devuelve SOLO JSON:
{{"observations":[{{"document_id":"...","target":"actor","label":"muy_negativo|negativo|neutral|mixto|positivo|muy_positivo","score":-1.0,"confidence":0.0,"evidence":"cita corta"}}]}}
Reglas:
- score entre -1 y 1
- evidence debe ser cita literal corta del texto
- no inventes document_id
Documentos:
{json.dumps(payload_docs, ensure_ascii=False)}
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(text)
    out: list[SentimentObservation] = []
    valid_ids = {d.id for d in documents}
    for item in data.get("observations") or []:
        doc_id = str(item.get("document_id") or "")
        if doc_id not in valid_ids:
            continue
        out.append(
            SentimentObservation(
                document_id=doc_id,
                target=str(item.get("target") or request.topic),
                label=str(item.get("label") or "neutral"),  # type: ignore[arg-type]
                score=float(item.get("score") or 0),
                confidence=float(item.get("confidence") or 0.5),
                evidence=str(item.get("evidence") or "")[:300],
            )
        )
    return out
