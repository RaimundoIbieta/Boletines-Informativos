from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from media_analyzer.forecast import (
    _linear_fit,
    _r_squared,
    bucket_start,
    build_trend_analysis,
    choose_bucket,
)
from media_analyzer.models import AnalysisRequest, SourceDocument


def _request(days: int, topic: str = "reforma de pensiones") -> AnalysisRequest:
    return AnalysisRequest(
        topic=topic,
        actors=[topic],
        period_start=date.today() - timedelta(days=days),
        period_end=date.today(),
    )


def _docs(per_day: dict[int, int], *, text: str = "reforma de pensiones avanza"):
    """Genera documentos fechados a N días atrás según el mapa {dias_atras: cantidad}."""
    out = []
    for days_ago, count in per_day.items():
        stamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
        for i in range(count):
            out.append(
                SourceDocument(
                    id=f"d{days_ago}_{i}",
                    source_type="news",
                    title=text,
                    url=f"https://example.com/{days_ago}/{i}",
                    publisher="Medio",
                    published_at=stamp,
                    text=text,
                    excerpt=text,
                )
            )
    return out


class TestBuckets:
    def test_short_period_uses_days(self):
        assert choose_bucket(7) == "day"

    def test_medium_period_uses_weeks(self):
        assert choose_bucket(60) == "week"

    def test_long_period_uses_months(self):
        assert choose_bucket(400) == "month"

    def test_week_bucket_starts_on_monday(self):
        assert bucket_start(date(2026, 8, 13), "week") == date(2026, 8, 10)

    def test_month_bucket_starts_on_first(self):
        assert bucket_start(date(2026, 8, 13), "month") == date(2026, 8, 1)


class TestLinearFit:
    def test_perfect_upward_line(self):
        slope, intercept = _linear_fit([1.0, 2.0, 3.0, 4.0])
        assert round(slope, 6) == 1.0
        assert round(intercept, 6) == 1.0

    def test_flat_series(self):
        slope, _ = _linear_fit([5.0, 5.0, 5.0])
        assert slope == 0.0

    def test_single_value(self):
        assert _linear_fit([7.0]) == (0.0, 7.0)

    def test_empty(self):
        assert _linear_fit([]) == (0.0, 0.0)

    def test_r_squared_perfect_fit(self):
        values = [1.0, 2.0, 3.0, 4.0]
        slope, intercept = _linear_fit(values)
        assert _r_squared(values, slope, intercept) == 1.0


class TestTrendAnalysis:
    def test_growing_volume_is_detected(self):
        docs = _docs({6: 1, 5: 2, 4: 3, 3: 5, 2: 7, 1: 9})
        trend = build_trend_analysis(docs, _request(7))
        assert trend.bucket == "day"
        assert trend.direction == "creciente"
        assert trend.slope > 0
        assert trend.momentum > 0

    def test_declining_volume_is_detected(self):
        docs = _docs({6: 9, 5: 7, 4: 5, 3: 3, 2: 2, 1: 1})
        trend = build_trend_analysis(docs, _request(7))
        assert trend.direction == "decreciente"
        assert trend.slope < 0

    def test_stable_volume_is_detected(self):
        docs = _docs({5: 4, 4: 4, 3: 4, 2: 4, 1: 4})
        trend = build_trend_analysis(docs, _request(7))
        assert trend.direction == "estable"

    def test_short_series_is_not_projected(self):
        docs = _docs({2: 3, 1: 4})
        trend = build_trend_analysis(docs, _request(7))
        assert not trend.projectable
        assert trend.projection == []
        assert "demasiado corta" in trend.note

    def test_projection_has_horizon_and_band(self):
        docs = _docs({6: 1, 5: 2, 4: 3, 3: 4, 2: 5, 1: 6})
        trend = build_trend_analysis(docs, _request(7), horizon=3)
        assert len(trend.projection) == 3
        for point in trend.projection:
            assert point.low <= point.expected <= point.high
            assert point.expected >= 0

    def test_projection_dates_follow_last_period(self):
        docs = _docs({6: 1, 5: 2, 4: 3, 3: 4, 2: 5, 1: 6})
        trend = build_trend_analysis(docs, _request(7))
        last_observed = trend.points[-1].period_start
        assert trend.projection[0].period_start == last_observed + timedelta(days=1)

    def test_peak_is_identified(self):
        docs = _docs({6: 1, 5: 2, 4: 20, 3: 3, 2: 2, 1: 1})
        trend = build_trend_analysis(docs, _request(7))
        assert trend.peak_documents == 20

    def test_erratic_series_is_flagged_unreliable(self):
        docs = _docs({6: 1, 5: 30, 4: 2, 3: 25, 2: 1, 1: 28})
        trend = build_trend_analysis(docs, _request(7))
        assert trend.fit < 0.3
        assert not trend.reliable
        assert "orientativa" in trend.note

    def test_documents_outside_period_are_ignored(self):
        docs = _docs({400: 50, 3: 2, 2: 2, 1: 2})
        trend = build_trend_analysis(docs, _request(7))
        assert sum(p.documents for p in trend.points) == 6

    def test_tone_trend_improving(self):
        docs = []
        for days_ago, (good, bad) in {6: (0, 3), 5: (1, 3), 4: (2, 2), 3: (3, 1), 2: (4, 0)}.items():
            stamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
            for i in range(good):
                docs.append(
                    SourceDocument(
                        id=f"g{days_ago}{i}", source_type="reddit",
                        title="la reforma es un acierto excelente",
                        text="la reforma es un acierto excelente",
                        url=f"https://e.com/g{days_ago}{i}", published_at=stamp,
                    )
                )
            for i in range(bad):
                docs.append(
                    SourceDocument(
                        id=f"b{days_ago}{i}", source_type="reddit",
                        title="la reforma es un desastre y un fracaso",
                        text="la reforma es un desastre y un fracaso",
                        url=f"https://e.com/b{days_ago}{i}", published_at=stamp,
                    )
                )
        trend = build_trend_analysis(docs, _request(7, "reforma"), actor="reforma")
        assert trend.tone_direction == "mejorando"

    def test_no_documents_returns_empty(self):
        trend = build_trend_analysis([], _request(7))
        assert trend.points == []
        assert not trend.projectable


class TestTrendFindings:
    def test_short_series_does_not_claim_a_trend(self):
        """Sin tramos suficientes no debe decir «es desconocida ... pico 0 el None»."""
        from media_analyzer.pipeline import _trend_findings

        docs = _docs({3: 2, 2: 5, 1: 2})
        trend = build_trend_analysis(docs, _request(7))
        findings = _trend_findings(trend)
        text = " ".join(findings)
        assert "desconocida" not in text
        assert "None" not in text
        assert "9 piezas" in text

    def test_clear_trend_is_reported_with_projection(self):
        from media_analyzer.pipeline import _trend_findings

        docs = _docs({6: 1, 5: 2, 4: 3, 3: 4, 2: 5, 1: 6})
        findings = _trend_findings(build_trend_analysis(docs, _request(7)))
        text = " ".join(findings)
        assert "creciente" in text
        assert "se esperan" in text

    def test_weekly_projection_uses_feminine_article(self):
        """«para el semana» era una concordancia rota."""
        from media_analyzer.pipeline import _trend_findings

        docs = _docs({d: 3 + d for d in (40, 33, 26, 19, 12, 5)})
        trend = build_trend_analysis(docs, _request(60))
        assert trend.bucket == "week"
        text = " ".join(_trend_findings(trend))
        assert "para el semana" not in text
        if "se esperan" in text:
            assert "para la semana" in text

    def test_no_points_returns_nothing(self):
        from media_analyzer.pipeline import _trend_findings

        assert _trend_findings(build_trend_analysis([], _request(7))) == []


def test_tone_balance_bounds():
    from media_analyzer.models import TrendPoint

    assert TrendPoint(period_start=date.today(), favorable=5).tone_balance == 100.0
    assert TrendPoint(period_start=date.today(), critical=5).tone_balance == -100.0
    assert TrendPoint(period_start=date.today(), favorable=2, critical=2).tone_balance == 0.0
    assert TrendPoint(period_start=date.today()).tone_balance == 0.0
