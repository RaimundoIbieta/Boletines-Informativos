from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from boletin.analyzer import analyze_articles
from boletin.archive import publish_to_pages
from boletin.collector import collect_articles
from boletin.config import OUTPUT_DIR, RuntimeContext
from boletin.emailer import send_boletin_email
from boletin.formatter import to_html_email, to_markdown
from boletin.models import BoletinSemanal
from boletin.pdf_generator import generate_pdf

logger = logging.getLogger(__name__)


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def is_semimonthly_send_day(day: date) -> bool:
    """Día 15 o último día calendario del mes (zona del boletín)."""
    return day.day == 15 or day.day == last_day_of_month(day.year, day.month)


def collection_cutoff(
    ctx: RuntimeContext,
    *,
    reference_date: date | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Corte horario del día de cierre para no incluir noticias posteriores.

    En envíos programados del día 15 / fin de mes, el límite es la hora del
    boletín (p. ej. 18:30 Chile). Si se regenera ese mismo día más tarde, se
    usa ese tope fijo para no mezclar hechos de la noche.
    """
    day = reference_date or ctx.today_local()
    frequency = (ctx.app.schedule.frequency or "weekly").strip().lower()
    if frequency != "semimonthly" or not is_semimonthly_send_day(day):
        return None
    tz = ctx.timezone if isinstance(ctx.timezone, ZoneInfo) else ZoneInfo(str(ctx.timezone))
    cutoff = datetime.combine(
        day,
        time(ctx.schedule_hour, ctx.schedule_minute),
        tzinfo=tz,
    )
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)
    # Si aún no llega la hora (prueba manual), no cortar por el futuro.
    return cutoff if current >= cutoff else current


def should_run_scheduled(ctx: RuntimeContext, now: datetime | None = None) -> bool:
    """True si hoy es el día programado y ya pasó la hora configurada.

    No usa una ventana corta: GitHub Actions a veces corre con retraso y
    perdía el envío. El anti-duplicado lo hacen los markers / bulletin_runs.
    """
    now = now or datetime.now(ctx.timezone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ctx.timezone)
    else:
        now = now.astimezone(ctx.timezone)

    frequency = (ctx.app.schedule.frequency or "weekly").strip().lower()
    if frequency == "semimonthly":
        if not is_semimonthly_send_day(now.date()):
            return False
    elif now.weekday() != ctx.schedule_weekday:
        return False
    target = ctx.schedule_hour * 60 + ctx.schedule_minute
    current = now.hour * 60 + now.minute
    return current >= target


def run_boletin(
    ctx: RuntimeContext,
    *,
    send_email: bool = True,
    reference_date: date | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    dry_run: bool = False,
    skip_drive: bool = False,
    skip_pages: bool = False,
) -> tuple[BoletinSemanal, Path, Path]:
    theme = ctx.theme
    if period_start is not None and period_end is not None:
        start, end = period_start, period_end
    else:
        start, end = ctx.period_bounds(reference_date)
    generated = reference_date or ctx.today_local()
    cutoff = collection_cutoff(ctx, reference_date=generated)
    logger.info(
        "Temática=%s | Periodo %s → %s%s",
        theme.id,
        start,
        end,
        f" | corte {cutoff.isoformat()}" if cutoff else "",
    )

    articles = collect_articles(
        start,
        end,
        queries=list(theme.queries),
        cutoff=cutoff,
    )
    boletin = analyze_articles(
        articles,
        ctx.secrets,
        start,
        end,
        theme,
        generated,
    )

    stamp = f"{start.isoformat()}_{end.isoformat()}"
    md_path = OUTPUT_DIR / f"boletin_{theme.id}_{stamp}.md"
    pdf_path = OUTPUT_DIR / f"boletin_{theme.id}_{stamp}.pdf"

    markdown = to_markdown(boletin, author_name=ctx.author_name)
    md_path.write_text(markdown, encoding="utf-8")
    generate_pdf(boletin, pdf_path, author_name=ctx.author_name)
    logger.info("Archivos: %s | %s", md_path.name, pdf_path.name)

    drive_view = ""
    drive_download = ""
    if ctx.app.drive.enabled and not dry_run and not skip_drive:
        try:
            from boletin.drive import upload_pdf

            uploaded = upload_pdf(
                pdf_path,
                folder_name=ctx.app.drive.folder_name,
            )
            drive_view = uploaded.get("web_view_link", "")
            drive_download = uploaded.get("web_content_link", "")
        except Exception as exc:
            logger.error("No se pudo subir a Drive: %s", exc)

    if ctx.app.github_pages.enabled and not dry_run and not skip_pages:
        publish_to_pages(
            boletin,
            pdf_path,
            drive_view_link=drive_view,
            drive_download_link=drive_download,
            copy_pdf=ctx.app.github_pages.publish_pdf,
            author_name=ctx.author_name,
        )

    if send_email and not dry_run:
        ctx.secrets.validate_for_send(ctx.emails)
        send_boletin_email(
            ctx.secrets,
            boletin,
            recipients=ctx.emails,
            html_body=to_html_email(boletin, author_name=ctx.author_name),
            text_body=markdown,
            pdf_path=pdf_path,
        )
    elif dry_run:
        logger.info("Dry-run: sin correo / Drive / Pages.")

    return boletin, md_path, pdf_path
