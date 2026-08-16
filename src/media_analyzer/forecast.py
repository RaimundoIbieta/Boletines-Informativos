"""Tendencias y proyecciones sobre la conversación observada.

Responde a «hacia dónde va esto»: si el tema crece o se apaga, si el tono mejora
o empeora, y qué cabe esperar en el próximo tramo si la dinámica se mantiene.

Las proyecciones son extrapolaciones de la serie observada, no predicciones: un
hecho nuevo puede romperlas en un día. Por eso cada proyección viaja con su nivel
de confianza y se omite cuando la serie es demasiado corta o errática.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from statistics import fmean, pstdev

from media_analyzer.models import (
    MIN_TREND_POINTS,
    AnalysisRequest,
    ProjectionPoint,
    SourceDocument,
    TrendAnalysis,
    TrendPoint,
)
from media_analyzer.opinion import classify_stance, document_text, mentions_actor

logger = logging.getLogger(__name__)


def choose_bucket(period_days: int) -> str:
    """Agrupa por día, semana o mes según el largo del periodo."""
    if period_days <= 21:
        return "day"
    if period_days <= 120:
        return "week"
    return "month"


def bucket_start(day: date, bucket: str) -> date:
    if bucket == "day":
        return day
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _linear_fit(values: list[float]) -> tuple[float, float]:
    """Regresión lineal por mínimos cuadrados sobre índices 0..n-1.

    Devuelve (pendiente, intercepto). Con menos de dos puntos la pendiente es 0.
    """
    n = len(values)
    if n < 2:
        return 0.0, (values[0] if values else 0.0)
    mean_x = (n - 1) / 2
    mean_y = fmean(values)
    numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0, mean_y
    slope = numerator / denominator
    return slope, mean_y - slope * mean_x


def _r_squared(values: list[float], slope: float, intercept: float) -> float:
    """Qué parte de la variación explica la recta: mide si la tendencia es fiable."""
    if len(values) < 3:
        return 0.0
    mean_y = fmean(values)
    total = sum((v - mean_y) ** 2 for v in values)
    if total == 0:
        return 1.0
    residual = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(values))
    return max(0.0, min(1.0, 1 - residual / total))


def build_trend_analysis(
    documents: list[SourceDocument],
    request: AnalysisRequest,
    *,
    actor: str = "",
    horizon: int = 3,
) -> TrendAnalysis:
    """Serie temporal de volumen y tono, con su tendencia y proyección."""
    period_days = max(1, (request.period_end - request.period_start).days)
    bucket = choose_bucket(period_days)
    target = actor or request.topic

    volume: dict[date, int] = defaultdict(int)
    favorable: dict[date, int] = defaultdict(int)
    critical: dict[date, int] = defaultdict(int)

    for doc in documents:
        if not doc.published_at:
            continue
        day = doc.published_at.date()
        if day < request.period_start or day > request.period_end:
            continue
        key = bucket_start(day, bucket)
        volume[key] += 1
        text = document_text(doc)
        if target and mentions_actor(text, target):
            stance, _, _ = classify_stance(text, target)
            if stance == "favorable":
                favorable[key] += 1
            elif stance == "critica":
                critical[key] += 1

    points = [
        TrendPoint(
            period_start=key,
            documents=volume[key],
            favorable=favorable.get(key, 0),
            critical=critical.get(key, 0),
        )
        for key in sorted(volume)
    ]

    analysis = TrendAnalysis(bucket=bucket, points=points, horizon=horizon)
    if len(points) < MIN_TREND_POINTS:
        analysis.note = (
            f"Serie demasiado corta para proyectar: {len(points)} tramos observados "
            f"(mínimo {MIN_TREND_POINTS}). Amplía el periodo analizado."
        )
        return analysis

    counts = [float(p.documents) for p in points]
    slope, intercept = _linear_fit(counts)
    fit = _r_squared(counts, slope, intercept)
    average = fmean(counts)

    analysis.slope = round(slope, 3)
    analysis.fit = round(fit, 3)
    analysis.average = round(average, 2)
    # Un cambio menor al 10% del promedio por tramo es ruido, no tendencia.
    threshold = max(0.5, 0.1 * average)
    if slope > threshold:
        analysis.direction = "creciente"
    elif slope < -threshold:
        analysis.direction = "decreciente"
    else:
        analysis.direction = "estable"

    half = len(counts) // 2
    if half:
        first, second = fmean(counts[:half]), fmean(counts[half:])
        analysis.momentum = round(second - first, 2)

    peak = max(points, key=lambda p: p.documents)
    analysis.peak_period = peak.period_start
    analysis.peak_documents = peak.documents

    tone = [p.tone_balance for p in points if p.opinionated]
    if len(tone) >= MIN_TREND_POINTS:
        tone_slope, _ = _linear_fit(tone)
        analysis.tone_slope = round(tone_slope, 3)
        if tone_slope > 2:
            analysis.tone_direction = "mejorando"
        elif tone_slope < -2:
            analysis.tone_direction = "empeorando"
        else:
            analysis.tone_direction = "estable"

    # La banda de error usa la dispersión de los residuos, no un porcentaje fijo.
    residuals = [v - (slope * i + intercept) for i, v in enumerate(counts)]
    spread = pstdev(residuals) if len(residuals) > 1 else 0.0
    step = {"day": timedelta(days=1), "week": timedelta(weeks=1)}.get(bucket)

    last_index = len(counts) - 1
    last_start = points[-1].period_start
    for ahead in range(1, horizon + 1):
        index = last_index + ahead
        expected = max(0.0, slope * index + intercept)
        if step:
            next_start = last_start + step * ahead
        else:
            month = last_start.month + ahead
            year = last_start.year + (month - 1) // 12
            next_start = last_start.replace(year=year, month=(month - 1) % 12 + 1)
        analysis.projection.append(
            ProjectionPoint(
                period_start=next_start,
                expected=round(expected, 1),
                low=round(max(0.0, expected - 1.96 * spread), 1),
                high=round(expected + 1.96 * spread, 1),
            )
        )

    if fit < 0.3:
        analysis.note = (
            "La serie es irregular (la tendencia explica poco de la variación): "
            "la proyección es solo orientativa."
        )
    return analysis


def project_scenarios_with_gemini(
    request: AnalysisRequest,
    trend: TrendAnalysis,
    findings: list[str],
    api_key: str,
    model: str = "gemini-2.0-flash",
) -> list[dict]:
    """Escenarios a futuro redactados por el modelo a partir de la evidencia.

    Devuelve una lista de {nombre, probabilidad, descripción, señales}. Ante
    cualquier fallo devuelve lista vacía: el informe sigue sin escenarios.
    """
    import json

    import httpx

    series = [
        {"desde": p.period_start.isoformat(), "docs": p.documents, "tono": p.tone_balance}
        for p in trend.points[-12:]
    ]
    projection = [
        {"desde": p.period_start.isoformat(), "esperado": p.expected}
        for p in trend.projection
    ]
    prompt = f"""Eres analista de medios. Tema: «{request.topic}» ({request.territory_label}).
Periodo observado: {request.period_start} a {request.period_end}.
Serie por {trend.bucket}: {json.dumps(series, ensure_ascii=False)}
Tendencia: {trend.direction} (pendiente {trend.slope}, ajuste {trend.fit}).
Tono: {trend.tone_direction}.
Proyección estadística: {json.dumps(projection, ensure_ascii=False)}
Hallazgos: {json.dumps(findings[:8], ensure_ascii=False)}

Devuelve SOLO JSON:
{{"escenarios":[{{"nombre":"...","probabilidad":"alta|media|baja","descripcion":"2 frases","senales":["indicador observable"]}}]}}
Reglas:
- Entre 2 y 3 escenarios, mutuamente distintos.
- Fundaméntalos en los datos entregados; no inventes hechos ni cifras nuevas.
- "senales" son indicadores concretos que permitirían confirmar el escenario.
- Si la evidencia es débil, dilo en la descripción.
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    with httpx.Client(timeout=90.0) as client:
        resp = client.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            },
        )
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    out = []
    for item in (data.get("escenarios") or [])[:3]:
        name = str(item.get("nombre") or "").strip()
        if not name:
            continue
        probability = str(item.get("probabilidad") or "media").lower()
        if probability not in {"alta", "media", "baja"}:
            probability = "media"
        out.append(
            {
                "nombre": name[:120],
                "probabilidad": probability,
                "descripcion": str(item.get("descripcion") or "")[:400],
                "senales": [str(s)[:120] for s in (item.get("senales") or [])[:4]],
            }
        )
    return out
