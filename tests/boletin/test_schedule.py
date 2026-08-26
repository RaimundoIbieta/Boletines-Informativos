from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from boletin.config import AppConfig, RuntimeContext, ScheduleConfig, Settings, compute_period_bounds
from boletin.pipeline import is_semimonthly_send_day, should_run_scheduled
from boletin.supabase_store import RemoteBulletin, runtime_for_bulletin

SANTIAGO = ZoneInfo("America/Santiago")


def _base_context(env_hour: int | None = 7, env_minute: int | None = 30) -> RuntimeContext:
    """Motor local: el .env fija una hora propia para el agendador de la Mac."""
    return RuntimeContext(
        app=AppConfig(schedule=ScheduleConfig(hour=env_hour or 7, minute=env_minute or 30)),
        secrets=Settings(schedule_hour=env_hour, schedule_minute=env_minute),
    )


def _remote(hour: int = 18, minute: int = 30, frequency: str = "semimonthly") -> RemoteBulletin:
    return RemoteBulletin(
        id="3b0040a6",
        user_id="u1",
        title="Panorama Quincenal de Chile y el Mundo",
        short_label="Chile y Mundo · 15/fin",
        audience="",
        focus="",
        queries=[("chile", "GENERAL")],
        analysis_axes=[],
        sections=["Economía", "Social", "Política", "Nacional", "Internacional"],
        schedule_frequency=frequency,
        schedule_weekday="monday",
        schedule_hour=hour,
        schedule_minute=minute,
        emails=["lector@example.com"],
        period_mode="calendar_semimonthly",
        output_format="panorama_sectional",
    )


def test_bulletin_hour_wins_over_env_override():
    ctx = runtime_for_bulletin(_base_context(env_hour=7, env_minute=30), _remote(18, 30))
    assert (ctx.schedule_hour, ctx.schedule_minute) == (18, 30)


def test_env_override_still_applies_without_web_bulletin():
    ctx = _base_context(env_hour=7, env_minute=30)
    assert (ctx.schedule_hour, ctx.schedule_minute) == (7, 30)


def test_semimonthly_waits_for_its_own_hour():
    """El 15 a las 07:52 no toca un boletín de las 18:30, aunque el .env diga 07:30."""
    ctx = runtime_for_bulletin(_base_context(), _remote(18, 30))
    morning = datetime(2026, 8, 15, 7, 52, tzinfo=SANTIAGO)
    assert should_run_scheduled(ctx, morning) is False


def test_semimonthly_runs_after_its_hour():
    ctx = runtime_for_bulletin(_base_context(), _remote(18, 30))
    evening = datetime(2026, 8, 15, 18, 31, tzinfo=SANTIAGO)
    assert should_run_scheduled(ctx, evening) is True


def test_semimonthly_skips_day_one_and_runs_month_end():
    ctx = runtime_for_bulletin(_base_context(), _remote(18, 30))
    assert should_run_scheduled(ctx, datetime(2026, 8, 14, 23, 0, tzinfo=SANTIAGO)) is False
    assert should_run_scheduled(ctx, datetime(2026, 8, 1, 19, 0, tzinfo=SANTIAGO)) is False
    assert should_run_scheduled(ctx, datetime(2026, 8, 31, 18, 30, tzinfo=SANTIAGO)) is True


def test_semimonthly_month_lengths():
    assert is_semimonthly_send_day(date(2026, 2, 15))
    assert is_semimonthly_send_day(date(2026, 2, 28))
    assert not is_semimonthly_send_day(date(2026, 2, 27))
    assert is_semimonthly_send_day(date(2028, 2, 29))
    assert is_semimonthly_send_day(date(2026, 4, 30))
    assert not is_semimonthly_send_day(date(2026, 4, 29))
    assert is_semimonthly_send_day(date(2026, 8, 31))
    assert not is_semimonthly_send_day(date(2026, 8, 30))


def test_weekly_bulletin_uses_its_own_hour():
    remote = _remote(hour=18, minute=30, frequency="weekly")
    remote.schedule_weekday = "friday"
    ctx = runtime_for_bulletin(_base_context(), remote)
    friday_morning = datetime(2026, 8, 14, 8, 0, tzinfo=SANTIAGO)
    friday_evening = datetime(2026, 8, 14, 18, 30, tzinfo=SANTIAGO)
    assert should_run_scheduled(ctx, friday_morning) is False
    assert should_run_scheduled(ctx, friday_evening) is True


def test_calendar_semimonthly_period_bounds():
    assert compute_period_bounds("calendar_semimonthly", 7, date(2026, 8, 15)) == (
        date(2026, 8, 1),
        date(2026, 8, 15),
    )
    assert compute_period_bounds("calendar_semimonthly", 7, date(2026, 8, 31)) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    assert compute_period_bounds("calendar_semimonthly", 7, date(2026, 2, 28)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )
    assert compute_period_bounds("calendar_semimonthly", 7, date(2028, 2, 29)) == (
        date(2028, 2, 1),
        date(2028, 2, 29),
    )
    # Preview antes del 15: no inventa días futuros
    assert compute_period_bounds("calendar_semimonthly", 7, date(2026, 8, 10)) == (
        date(2026, 8, 1),
        date(2026, 8, 10),
    )
