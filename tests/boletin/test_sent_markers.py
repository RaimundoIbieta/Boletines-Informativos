from __future__ import annotations

from datetime import date

import pytest

from boletin import sent_markers
from boletin.config import compute_period_bounds


@pytest.fixture(autouse=True)
def _isolated_output(tmp_path, monkeypatch):
    monkeypatch.setattr(sent_markers, "OUTPUT_DIR", tmp_path)


def test_marker_roundtrip():
    start, end = date(2026, 8, 1), date(2026, 8, 15)
    assert sent_markers.already_sent("b1", start, end) is False
    sent_markers.mark_sent("b1", start, end, note="11 noticias")
    assert sent_markers.already_sent("b1", start, end) is True


def test_semimonthly_sends_share_start_but_not_marker():
    """El envío del 15 (1→15) y el del cierre (1→fin) comparten inicio."""
    mid_month = compute_period_bounds("calendar_semimonthly", 7, date(2026, 8, 15))
    month_end = compute_period_bounds("calendar_semimonthly", 7, date(2026, 8, 31))

    assert mid_month == (date(2026, 8, 1), date(2026, 8, 15))
    assert month_end == (date(2026, 8, 1), date(2026, 8, 31))
    assert mid_month[0] == month_end[0]
    assert mid_month[1] != month_end[1]

    sent_markers.mark_sent("b1", *mid_month)
    assert sent_markers.already_sent("b1", *mid_month) is True
    assert sent_markers.already_sent("b1", *month_end) is False


def test_markers_are_per_bulletin():
    start, end = date(2026, 8, 1), date(2026, 8, 15)
    sent_markers.mark_sent("b1", start, end)
    assert sent_markers.already_sent("b2", start, end) is False
