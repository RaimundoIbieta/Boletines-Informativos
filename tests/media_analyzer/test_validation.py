from __future__ import annotations

from datetime import date, timedelta

import pytest

from media_analyzer.validation import is_private_ip, month_windows, validate_public_http_url


def test_month_windows_single_month():
    start = date(2026, 7, 10)
    end = date(2026, 7, 20)
    wins = month_windows(start, end)
    assert wins == [(start, end)]


def test_month_windows_cross_months():
    start = date(2026, 6, 20)
    end = date(2026, 8, 5)
    wins = month_windows(start, end)
    assert len(wins) == 3
    assert wins[0] == (date(2026, 6, 20), date(2026, 6, 30))
    assert wins[1] == (date(2026, 7, 1), date(2026, 7, 31))
    assert wins[2] == (date(2026, 8, 1), date(2026, 8, 5))


def test_month_windows_inverted():
    assert month_windows(date(2026, 8, 1), date(2026, 7, 1)) == []


def test_private_ips():
    assert is_private_ip("127.0.0.1")
    assert is_private_ip("10.0.0.1")
    assert is_private_ip("192.168.1.1")
    assert not is_private_ip("8.8.8.8")


def test_ssrf_blocks_localhost():
    with pytest.raises(ValueError):
        validate_public_http_url("http://localhost/admin", resolve_dns=False)
    with pytest.raises(ValueError):
        validate_public_http_url("http://127.0.0.1/", resolve_dns=False)
    with pytest.raises(ValueError):
        validate_public_http_url("ftp://example.com/", resolve_dns=False)
    with pytest.raises(ValueError):
        validate_public_http_url("https://user:pass@example.com/", resolve_dns=False)


def test_ssrf_allows_public_without_dns():
    url = validate_public_http_url("https://example.com/path", resolve_dns=False)
    assert url.startswith("https://")


def test_period_max_two_years():
    from media_analyzer.models import AnalysisRequest

    start = date(2024, 1, 1)
    end = start + timedelta(days=731)
    with pytest.raises(ValueError):
        AnalysisRequest(topic="próximo presidente", period_start=start, period_end=end)
