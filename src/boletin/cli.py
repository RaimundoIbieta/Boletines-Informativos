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

    reference = date.fromisoformat(args.date) if args.date else None
    send = not (args.no_email or args.dry_run)

    from boletin.supabase_store import (
        already_sent_remote,
        fetch_active_bulletins,
        fetch_bulletin_by_id,
        fetch_pending_send_requests,
        record_run,
        supabase_configured,
        update_send_request,
    )
    from boletin.sent_markers import already_sent, mark_sent

    # Primero: pruebas pedidas desde la web (botón Probar)
    if (
        supabase_configured(ctx.secrets)
        and not args.theme
        and not getattr(args, "local", False)
        and (bool(args.scheduled) or bool(getattr(args, "from_web", False)) or bool(getattr(args, "process_tests", False)))
    ):
        try:
            n_tests = _process_test_requests(
                ctx,
                send=send,
                reference=reference,
                dry_run=args.dry_run,
                skip_drive=args.no_drive,
                skip_pages=args.no_pages,
                record_run=record_run,
                fetch_pending_send_requests=fetch_pending_send_requests,
                fetch_bulletin_by_id=fetch_bulletin_by_id,
                update_send_request=update_send_request,
            )
            if getattr(args, "process_tests", False) and not args.scheduled and not getattr(args, "from_web", False):
                if n_tests:
                    logging.info("Pruebas web procesadas: %s", n_tests)
                else:
                    logging.info("No había pruebas pendientes en send_requests.")
                return 0
        except Exception as exc:
            logging.error("Error procesando pruebas web: %s", exc)
            if getattr(args, "process_tests", False) and not args.scheduled:
                return 1

    # Preferir boletines de la web (Supabase) en modo agenda o con --from-web
    use_web = (
        supabase_configured(ctx.secrets)
        and not args.theme
        and not getattr(args, "local", False)
        and (bool(args.scheduled) or bool(getattr(args, "from_web", False)))
    )
    if use_web:
        try:
            remotes = fetch_active_bulletins(ctx.secrets)
        except Exception as exc:
            logging.error("No se pudieron leer boletines de Supabase: %s", exc)
            return 1

        if remotes:
            return _run_web_bulletins(
                ctx,
                remotes,
                scheduled=bool(args.scheduled),
                send=send,
                reference=reference,
                dry_run=args.dry_run,
                skip_drive=args.no_drive,
                skip_pages=args.no_pages,
                already_sent=already_sent,
                already_sent_remote=already_sent_remote,
                mark_sent=mark_sent,
                record_run=record_run,
            )
        logging.info("Supabase sin boletines activos con correos; uso config.yaml local.")

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


def _process_test_requests(
    base_ctx,
    *,
    send: bool,
    reference: date | None,
    dry_run: bool,
    skip_drive: bool,
    skip_pages: bool,
    record_run,
    fetch_pending_send_requests,
    fetch_bulletin_by_id,
    update_send_request,
) -> int:
    from datetime import timedelta

    from boletin.supabase_store import runtime_for_bulletin

    pending = fetch_pending_send_requests(base_ctx.secrets)
    if not pending:
        return 0

    # Prueba: desde el lunes de la semana pasada hasta hoy (no solo la semana cerrada)
    today = reference or date.today()
    this_monday = today - timedelta(days=today.weekday())
    test_start = this_monday - timedelta(days=7)
    test_end = today

    done = 0
    for req in pending:
        req_id = req["id"]
        bulletin_id = req["bulletin_id"]
        update_send_request(base_ctx.secrets, req_id, status="running")
        try:
            remote = fetch_bulletin_by_id(base_ctx.secrets, bulletin_id)
            if not remote:
                raise RuntimeError("Boletín no encontrado, sin correos o sin búsquedas.")
            ctx = runtime_for_bulletin(base_ctx, remote)
            if send:
                ctx.secrets.validate_for_send(ctx.emails)
            logging.info(
                "Prueba web «%s» → %s | periodo %s→%s",
                remote.title,
                ", ".join(remote.emails),
                test_start.isoformat(),
                test_end.isoformat(),
            )
            boletin, md_path, pdf_path = run_boletin(
                ctx,
                send_email=send,
                reference_date=today,
                period_start=test_start,
                period_end=test_end,
                dry_run=dry_run,
                skip_drive=skip_drive,
                skip_pages=skip_pages,
            )
            print(f"— PRUEBA {remote.short_label}")
            print(f"  Noticias: {len(boletin.noticias)}")
            print(f"  Markdown: {md_path}")
            print(f"  PDF:      {pdf_path}")
            if send:
                print(f"  Enviado a: {', '.join(ctx.emails)}")
                record_run(
                    ctx.secrets,
                    bulletin_id=remote.id,
                    user_id=remote.user_id,
                    periodo_inicio=test_start.isoformat(),
                    periodo_fin=test_end.isoformat(),
                    noticias=len(boletin.noticias),
                    status="test",
                )
            update_send_request(base_ctx.secrets, req_id, status="done")
            done += 1
        except Exception as exc:
            logging.exception("Fallo prueba %s", req_id)
            update_send_request(base_ctx.secrets, req_id, status="error", error=str(exc)[:500])
    return done


def _run_web_bulletins(
    base_ctx,
    remotes,
    *,
    scheduled: bool,
    send: bool,
    reference: date | None,
    dry_run: bool,
    skip_drive: bool,
    skip_pages: bool,
    already_sent,
    already_sent_remote,
    mark_sent,
    record_run,
) -> int:
    from boletin.supabase_store import runtime_for_bulletin

    ran = 0
    for remote in remotes:
        ctx = runtime_for_bulletin(base_ctx, remote)
        if scheduled and not should_run_scheduled(ctx):
            logging.info(
                "Omitido %s (fuera de ventana %s %02d:%02d)",
                remote.short_label,
                remote.schedule_weekday,
                remote.schedule_hour,
                remote.schedule_minute,
            )
            continue

        start, end = ctx.period_bounds(reference)
        if scheduled and (
            already_sent(remote.id, start)
            or already_sent_remote(ctx.secrets, remote.id, start.isoformat())
        ):
            logging.info(
                "Omitido %s (ya enviado para periodo %s)",
                remote.short_label,
                start.isoformat(),
            )
            continue

        if send:
            try:
                ctx.secrets.validate_for_send(ctx.emails)
            except ValueError as exc:
                logging.error("%s: %s", remote.short_label, exc)
                continue
        elif not ctx.secrets.has_llm_key():
            logging.error("Falta API key de IA en .env")
            return 1

        logging.info(
            "Generando «%s» → %s",
            remote.title,
            ", ".join(remote.emails),
        )
        boletin, md_path, pdf_path = run_boletin(
            ctx,
            send_email=send,
            reference_date=reference,
            dry_run=dry_run,
            skip_drive=skip_drive,
            skip_pages=skip_pages,
        )
        print(f"— {remote.short_label}")
        print(f"  Noticias: {len(boletin.noticias)}")
        print(f"  Markdown: {md_path}")
        print(f"  PDF:      {pdf_path}")
        if send:
            print(f"  Enviado a: {', '.join(ctx.emails)}")
            mark_sent(remote.id, start, note=f"{len(boletin.noticias)} noticias")
            record_run(
                ctx.secrets,
                bulletin_id=remote.id,
                user_id=remote.user_id,
                periodo_inicio=start.isoformat(),
                periodo_fin=end.isoformat(),
                noticias=len(boletin.noticias),
                pdf_url="",
                drive_url="",
                status="published",
            )
        ran += 1

    if scheduled and ran == 0:
        logging.info("Ningún boletín web due en esta ventana.")
    elif ran == 0:
        logging.warning("No se ejecutó ningún boletín.")
        return 1
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


def _cmd_admin(args: argparse.Namespace) -> int:
    from boletin.admin_app import run_admin

    run_admin(port=args.port, open_browser=not args.no_browser)
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
    run_p.add_argument(
        "--from-web",
        action="store_true",
        help="Usar boletines/correos/frecuencia de Supabase (todos los activos)",
    )
    run_p.add_argument(
        "--process-tests",
        action="store_true",
        help="Procesar solicitudes de prueba pendientes (botón Probar en la web)",
    )
    run_p.add_argument(
        "--local",
        action="store_true",
        help="Forzar config.yaml (ignorar boletines de Supabase)",
    )
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

    adm = sub.add_parser("admin", help="Abrir panel web local de configuración")
    adm.add_argument("--port", type=int, default=5055)
    adm.add_argument("--no-browser", action="store_true")
    adm.set_defaults(func=_cmd_admin)

    commands = {
        "run",
        "config",
        "add-email",
        "remove-email",
        "set-schedule",
        "set-theme",
        "drive-auth",
        "sync-schedule",
        "admin",
    }

    # Compatibilidad: `python -m boletin --no-email` sin subcomando
    if argv is None:
        argv = sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] in commands:
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
