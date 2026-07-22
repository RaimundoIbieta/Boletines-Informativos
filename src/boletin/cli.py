from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from boletin.config import (
    CONFIG_PATH,
    WEEKDAY_MAP,
    WEEKDAY_NAMES,
    get_runtime,
    load_app_config,
)
from boletin.pipeline import run_boletin, should_run_scheduled


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_run(args: argparse.Namespace) -> int:
    ctx = get_runtime()

    if args.theme:
        if args.theme not in ctx.app.themes:
            logging.error("Temática desconocida: %s", args.theme)
            return 1
        ctx.app.active_theme = args.theme

    if args.scheduled and not should_run_scheduled(ctx):
        now = datetime.now(ctx.timezone)
        logging.info(
            "Fuera de ventana (%s %02d:%02d). Ahora: %s",
            WEEKDAY_NAMES.get(ctx.schedule_weekday, "?"),
            ctx.schedule_hour,
            ctx.schedule_minute,
            now.isoformat(),
        )
        return 0

    reference = date.fromisoformat(args.date) if args.date else None
    send = not (args.no_email or args.dry_run)

    if send:
        ctx.secrets.validate_for_send(ctx.emails)
    elif not ctx.secrets.has_llm_key():
        logging.error("Falta API key de IA en .env")
        return 1

    boletin, md_path, pdf_path = run_boletin(
        ctx,
        send_email=send,
        reference_date=reference,
        dry_run=args.dry_run,
        skip_drive=args.no_drive,
        skip_pages=args.no_pages,
    )
    print(f"Temática: {boletin.theme_id}")
    print(f"Noticias: {len(boletin.noticias)}")
    print(f"Markdown: {md_path}")
    print(f"PDF:      {pdf_path}")
    if send:
        print(f"Enviado a: {', '.join(ctx.emails)}")
    return 0


def _cmd_config_show(_: argparse.Namespace) -> int:
    app = load_app_config()
    print(f"Archivo: {CONFIG_PATH}")
    print(f"Autor:   {app.author_name}")
    print(f"Emails:  {', '.join(app.emails)}")
    print(
        f"Agenda:  {app.schedule.weekday} {app.schedule.hour:02d}:{app.schedule.minute:02d} "
        f"({app.schedule.timezone})"
    )
    print(f"Tema:    {app.active_theme}")
    print(f"Temas:   {', '.join(app.themes)}")
    print(f"Drive:   {'on' if app.drive.enabled else 'off'} → {app.drive.folder_name}")
    print(f"Pages:   {'on' if app.github_pages.enabled else 'off'}")
    return 0


def _cmd_add_email(args: argparse.Namespace) -> int:
    app = load_app_config()
    email = args.email.strip().lower()
    if email in [e.lower() for e in app.emails]:
        print(f"Ya estaba: {email}")
        return 0
    app.emails.append(email)
    app.save()
    print(f"Agregado: {email}")
    print(f"Lista: {', '.join(app.emails)}")
    return 0


def _cmd_remove_email(args: argparse.Namespace) -> int:
    app = load_app_config()
    email = args.email.strip().lower()
    before = len(app.emails)
    app.emails = [e for e in app.emails if e.lower() != email]
    if len(app.emails) == before:
        print(f"No estaba: {email}")
        return 1
    app.save()
    print(f"Eliminado: {email}")
    print(f"Lista: {', '.join(app.emails) or '(vacía)'}")
    return 0


def _cmd_set_schedule(args: argparse.Namespace) -> int:
    app = load_app_config()
    day = args.day.strip().lower()
    if day not in WEEKDAY_MAP:
        print(f"Día inválido. Usa: {', '.join(WEEKDAY_MAP)}")
        return 1
    app.schedule.weekday = day
    app.schedule.hour = args.hour
    app.schedule.minute = args.minute
    app.save()
    print(
        f"Agenda: {app.schedule.weekday} "
        f"{app.schedule.hour:02d}:{app.schedule.minute:02d}"
    )
    print("Ejecuta: python -m boletin sync-schedule   # para actualizar el LaunchAgent")
    return 0


def _cmd_set_theme(args: argparse.Namespace) -> int:
    app = load_app_config()
    if args.theme not in app.themes:
        print(f"Temática desconocida. Disponibles: {', '.join(app.themes)}")
        return 1
    app.active_theme = args.theme
    app.save()
    print(f"Temática activa: {app.active_theme} ({app.theme().title})")
    return 0


def _cmd_drive_auth(_: argparse.Namespace) -> int:
    from boletin.drive import authenticate_drive

    authenticate_drive()
    print("Drive autenticado correctamente.")
    return 0


def _cmd_sync_schedule(_: argparse.Namespace) -> int:
    from boletin.schedule_sync import sync_launch_agent

    path = sync_launch_agent()
    print(f"LaunchAgent actualizado: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Boletines semanales configurables → correo + PDF + Drive + GitHub Pages",
    )
    sub = parser.add_subparsers(dest="command")

    # Default run (también sin subcomando, por compatibilidad)
    run_p = sub.add_parser("run", help="Generar y enviar el boletín")
    run_p.add_argument("--no-email", action="store_true")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--no-drive", action="store_true")
    run_p.add_argument("--no-pages", action="store_true")
    run_p.add_argument("--scheduled", action="store_true")
    run_p.add_argument("--date", type=str, default=None)
    run_p.add_argument("--theme", type=str, default=None, help="Override de temática")
    run_p.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("config", help="Mostrar configuración").set_defaults(
        func=_cmd_config_show
    )

    add_e = sub.add_parser("add-email", help="Agregar destinatario")
    add_e.add_argument("email")
    add_e.set_defaults(func=_cmd_add_email)

    rm_e = sub.add_parser("remove-email", help="Quitar destinatario")
    rm_e.add_argument("email")
    rm_e.set_defaults(func=_cmd_remove_email)

    sch = sub.add_parser("set-schedule", help="Cambiar día/hora")
    sch.add_argument("--day", required=True, help="monday…sunday")
    sch.add_argument("--hour", type=int, required=True)
    sch.add_argument("--minute", type=int, default=0)
    sch.set_defaults(func=_cmd_set_schedule)

    th = sub.add_parser("set-theme", help="Cambiar temática activa")
    th.add_argument("theme", help="pae | economia | …")
    th.set_defaults(func=_cmd_set_theme)

    sub.add_parser("drive-auth", help="Autenticar Google Drive").set_defaults(
        func=_cmd_drive_auth
    )
    sub.add_parser("sync-schedule", help="Actualizar LaunchAgent macOS").set_defaults(
        func=_cmd_sync_schedule
    )

    # Compatibilidad: `python -m boletin --no-email` sin subcomando
    if argv is None:
        argv = sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] in {
        "run",
        "config",
        "add-email",
        "remove-email",
        "set-schedule",
        "set-theme",
        "drive-auth",
        "sync-schedule",
    }:
        args = parser.parse_args(argv)
        if args.command != "run":
            return args.func(args)
        _configure_logging(args.verbose)
        return _cmd_run(args)

    # Flags antiguos a nivel raíz
    root = argparse.ArgumentParser(parents=[run_p], add_help=True)
    args = root.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))
    return _cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
