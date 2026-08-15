from __future__ import annotations

import argparse
import logging
import socket
import sys
from datetime import date, timedelta
from pathlib import Path

from media_analyzer.models import AnalysisRequest
from media_analyzer.pipeline import run_analysis


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_run(args: argparse.Namespace) -> int:
    today = date.today()
    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=29)
    end = date.fromisoformat(args.end) if args.end else today
    actors = [x.strip() for x in (args.actor or []) if x.strip()]
    include = [x.strip() for x in (args.include or []) if x.strip()]
    exclude = [x.strip() for x in (args.exclude or []) if x.strip()]
    urls = []
    if args.url:
        urls.extend(args.url)
    if args.urls_file:
        urls.extend(
            line.strip()
            for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
    sources = [x.strip() for x in (args.source or []) if x.strip()] or [
        "news",
        "youtube",
        "reddit",
        "bluesky",
        "mastodon",
        "indexed",
    ]
    req = AnalysisRequest(
        topic=args.topic,
        actors=actors,
        include_terms=include,
        exclude_terms=exclude,
        territory_level=args.territory_level,
        region_code=args.region,
        commune_code=args.commune,
        territory_label=args.territory_label or "Chile",
        period_start=start,
        period_end=end,
        enabled_sources=sources,
        urls=urls,
        file_paths=list(args.file or []),
    )
    gemini_key = ""
    gemini_model = "gemini-2.0-flash"
    try:
        from boletin.config import Settings

        s = Settings()
        gemini_key = args.gemini_key or s.gemini_api_key
        gemini_model = s.gemini_model or gemini_model
    except Exception:
        gemini_key = args.gemini_key or ""

    out = Path(args.output)
    report = run_analysis(
        req,
        gemini_api_key=gemini_key,
        gemini_model=gemini_model,
        output_dir=out,
    )
    print(f"Tema: {report.topic}")
    print(f"Docs: {report.coverage.documents_included}")
    print(f"Actores: {len(report.actors)}")
    print(f"Salida: {out}")
    return 0


def _cmd_process_queue(args: argparse.Namespace) -> int:
    from boletin.config import Settings
    from media_analyzer.store import (
        claim_request,
        fetch_inputs,
        save_documents,
        save_result,
        update_request,
        upload_export_files,
    )

    secrets = Settings()
    worker_id = args.worker_id or f"{socket.gethostname()}-{date.today().isoformat()}"
    request_id = (args.request_id or "").strip() or None
    claimed = claim_request(secrets, worker_id, request_id=request_id)
    if not claimed:
        logging.info("No hay solicitudes pendientes.")
        return 0

    rid = claimed["id"]
    user_id = claimed["user_id"]
    logging.info("Procesando análisis %s · %s", rid, claimed.get("topic"))
    try:
        inputs = fetch_inputs(secrets, rid)
        urls = [i["original_url"] for i in inputs if i.get("kind") == "url" and i.get("original_url")]
        file_paths = []
        # Archivos locales opcionales vía configuration
        conf = claimed.get("configuration") or {}

        def progress(pct: int, stage: str) -> None:
            update_request(
                secrets,
                rid,
                status="running",
                progress=pct,
                current_stage=stage,
            )

        req = AnalysisRequest(
            id=rid,
            user_id=user_id,
            topic=claimed["topic"],
            actors=list(claimed.get("actors") or []),
            include_terms=list(claimed.get("include_terms") or []),
            exclude_terms=list(claimed.get("exclude_terms") or []),
            territory_level=claimed.get("territory_level") or "national",
            region_code=claimed.get("region_code"),
            commune_code=claimed.get("commune_code"),
            territory_label=claimed.get("territory_label") or "Chile",
            period_start=date.fromisoformat(str(claimed["period_start"])[:10]),
            period_end=date.fromisoformat(str(claimed["period_end"])[:10]),
            enabled_sources=list(claimed.get("enabled_sources") or []),
            urls=urls,
            file_paths=file_paths,
            configuration=conf if isinstance(conf, dict) else {},
        )
        out = Path(args.output) / rid
        report = run_analysis(
            req,
            gemini_api_key=secrets.gemini_api_key,
            gemini_model=secrets.gemini_model or "gemini-2.0-flash",
            output_dir=out,
            progress_cb=progress,
        )
        save_documents(
            secrets,
            rid,
            [d.model_dump(mode="json") for d in report.documents],
        )
        save_result(secrets, rid, user_id, report.model_dump(mode="json"))
        try:
            uploaded = upload_export_files(secrets, rid, user_id, out)
            logging.info("Artefactos subidos: %s", len(uploaded))
        except Exception as up_exc:
            logging.warning("No se pudieron subir artefactos: %s", up_exc)
        status = "partial" if report.coverage.connector_errors else "completed"
        update_request(secrets, rid, status=status, progress=100, current_stage="done")
        print(f"OK {rid} → {out} ({report.coverage.documents_included} docs)")
        return 0
    except Exception as exc:
        logging.exception("Falló análisis %s", rid)
        update_request(
            secrets,
            rid,
            status="failed",
            progress=100,
            current_stage="error",
            error=str(exc),
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analizador-medios")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Ejecutar un análisis local")
    run_p.add_argument("--topic", required=True)
    run_p.add_argument("--start")
    run_p.add_argument("--end")
    run_p.add_argument("--territory-level", default="national", choices=["national", "regional", "communal"])
    run_p.add_argument("--region")
    run_p.add_argument("--commune")
    run_p.add_argument("--territory-label", default="Chile")
    run_p.add_argument("--actor", action="append", default=[])
    run_p.add_argument("--include", action="append", default=[])
    run_p.add_argument("--exclude", action="append", default=[])
    run_p.add_argument("--source", action="append", default=[])
    run_p.add_argument("--url", action="append", default=[])
    run_p.add_argument("--urls-file")
    run_p.add_argument("--file", action="append", default=[])
    run_p.add_argument("--output", default="output/media_analysis/local")
    run_p.add_argument("--gemini-key", default="")
    run_p.set_defaults(func=_cmd_run)

    q = sub.add_parser("process-queue", help="Procesar una solicitud pendiente de Supabase")
    q.add_argument("--output", default="output/media_analysis")
    q.add_argument("--worker-id")
    q.add_argument("--request-id", default="", help="Reclamar una solicitud concreta")
    q.set_defaults(func=_cmd_process_queue)

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
