from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from media_analyzer.connectors.collect import (
    collect_bluesky,
    collect_mastodon,
    collect_news,
    collect_reddit,
    collect_reddit_comments,
    collect_social_from_articles,
    collect_x_timelines,
    collect_youtube,
    enrich_with_oembed,
    ingest_urls,
    normalize_handle,
)
from media_analyzer.deduplication import cluster_same_story, dedupe_documents
from media_analyzer.extractors.files import extract_text_file
from media_analyzer.geography import detect_geography
from media_analyzer.models import (
    RESTRICTED_PLATFORMS,
    AnalysisReport,
    AnalysisRequest,
    CoverageMetrics,
    OpinionAnalysis,
    SourceDocument,
    StoryCluster,
)
from media_analyzer.normalization import content_hash
from media_analyzer.opinion import build_opinion_analysis
from media_analyzer.sentiment import analyze_with_llm
from media_analyzer.validation import month_windows

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "news": "Medios digitales",
    "youtube": "YouTube",
    "reddit": "Reddit",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
    "x": "X (Twitter)",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "url": "Enlaces aportados",
    "file": "Archivos aportados",
}

PLATFORM_SEARCH_TERMS = {
    "x": "publicación en X",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "video TikTok",
}

PLATFORM_METHODS = {
    "news": ("public_search", "Búsqueda de noticias y RSS abiertos."),
    "youtube": ("public_search", "Resultados públicos de búsqueda de YouTube."),
    "reddit": ("public_api", "API pública de búsqueda de Reddit."),
    "bluesky": ("public_api", "API pública de Bluesky."),
    "mastodon": ("public_api", "API pública de Mastodon."),
    "x": (
        "public_timeline",
        "Timeline público de las cuentas indicadas (sin login), más publicaciones citadas "
        "por medios. X no permite buscar por tema sin sesión.",
    ),
    "instagram": (
        "media_citation",
        "Sin API abierta: solo publicaciones citadas por medios o aportadas por ti.",
    ),
    "facebook": (
        "media_citation",
        "Sin API abierta: solo publicaciones citadas por medios o aportadas por ti.",
    ),
    "tiktok": (
        "media_citation",
        "Sin API abierta: solo publicaciones citadas por medios o aportadas por ti.",
    ),
    "url": ("user_supplied", "Enlaces que entregaste en la solicitud."),
    "file": ("user_supplied", "Archivos que subiste."),
}


def _opinion_targets(request: AnalysisRequest) -> tuple[list[str], list[str]]:
    """Actores a evaluar y rivales con los que se los compara."""
    config = request.configuration or {}
    actors = [a.strip() for a in (request.actors or []) if a.strip()]
    if not actors:
        actors = [request.topic.strip()]
    raw_rivals = config.get("rivals") or config.get("compare_with") or []
    if isinstance(raw_rivals, str):
        raw_rivals = [r.strip() for r in raw_rivals.replace(",", "\n").split("\n")]
    rivals = [r.strip() for r in raw_rivals if isinstance(r, str) and r.strip()]
    # Sin rivales explícitos, los demás actores del pedido cumplen ese rol.
    if not rivals and len(actors) > 1:
        rivals = actors[1:]
    return actors[:3], rivals[:4]


def _opinion_analyses(
    request: AnalysisRequest,
    documents: list[SourceDocument],
    *,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.0-flash",
) -> list[OpinionAnalysis]:
    actors, rivals = _opinion_targets(request)
    analyses: list[OpinionAnalysis] = []
    for actor in actors:
        others = [r for r in rivals if r.lower() != actor.lower()]
        try:
            analysis = build_opinion_analysis(
                documents,
                actor,
                rivals=others,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model,
            )
        except Exception as exc:
            logger.warning("Análisis de opinión falló para %s: %s", actor, exc)
            continue
        if analysis.documents_analyzed:
            analyses.append(analysis)
    return analyses


def _opinion_findings(analyses: list[OpinionAnalysis]) -> list[str]:
    findings: list[str] = []
    for analysis in analyses[:2]:
        audience = analysis.audience
        if not analysis.reliable:
            findings.append(
                f"Sobre {analysis.actor} no hay base suficiente para medir opinión: "
                f"{analysis.combined.opinionated} menciones con postura explícita en "
                f"{analysis.documents_analyzed} analizadas."
            )
        elif audience.opinionated:
            findings.append(
                f"En la conversación de audiencia sobre {analysis.actor}, "
                f"{audience.favorable_share:.0f}% de las menciones con postura son favorables "
                f"y {audience.critical_share:.0f}% críticas "
                f"({audience.opinionated} menciones con opinión de {audience.total} analizadas)."
            )
        for duel in analysis.duels[:2]:
            if not duel.conclusive:
                findings.append(
                    f"Entre {duel.actor} y {duel.rival} solo se hallaron {duel.total} "
                    f"comparaciones explícitas ({duel.actor_votes} a {duel.rival_votes}): "
                    "insuficiente para declarar una preferencia."
                )
            elif duel.winner == "empate":
                findings.append(
                    f"En las comparaciones explícitas {duel.actor} vs {duel.rival} hay empate "
                    f"({duel.actor_votes} a {duel.rival_votes} de {duel.total})."
                )
            else:
                findings.append(
                    f"En las comparaciones explícitas entre {duel.actor} y {duel.rival}, "
                    f"gana {duel.winner} con {duel.actor_share:.0f}% de las menciones a favor "
                    f"de {duel.actor} sobre {duel.total} comparaciones encontradas."
                )
    return findings


def _x_handles(request: AnalysisRequest, documents: list[SourceDocument]) -> list[str]:
    """Cuentas de X a leer: las que pidió el usuario y las que aparecen citadas."""
    raw: list[str] = []
    config = request.configuration or {}
    for key in ("x_accounts", "accounts", "social_accounts"):
        value = config.get(key)
        if isinstance(value, list):
            raw.extend(str(v) for v in value)
        elif isinstance(value, dict):
            raw.extend(str(v) for v in (value.get("x") or []))
        elif isinstance(value, str):
            raw.extend(value.replace(",", "\n").split())
    for doc in documents:
        if doc.source_type == "x" and doc.author:
            raw.append(doc.author)
    handles: list[str] = []
    for item in raw:
        handle = normalize_handle(item)
        if handle and handle.lower() not in {h.lower() for h in handles}:
            handles.append(handle)
    return handles


def _platform_coverage(
    by_source: Counter,
    enabled: set[str],
    request: AnalysisRequest,
    errors: dict[str, str],
) -> list:
    from media_analyzer.models import PlatformCoverage

    rows = []
    for key in PLATFORM_LABELS:
        count = int(by_source.get(key, 0))
        requested = (
            key in enabled
            or (key == "url" and request.urls)
            or (key == "file" and request.file_paths)
        )
        if not requested and count == 0:
            continue
        method, note = PLATFORM_METHODS.get(key, ("unavailable", ""))
        failure = errors.get(key) or (
            errors.get("redes_cerradas") if key in RESTRICTED_PLATFORMS else None
        )
        if key == "x" and not failure:
            failure = errors.get("x_timelines")
        if failure and count == 0:
            method = "unavailable"
            note = f"La fuente no respondió en esta corrida: {failure[:160]}"
        elif count == 0 and method in {"public_api", "public_search", "public_timeline"}:
            if key == "x":
                note = (
                    "Sin publicaciones: indica cuentas públicas de X para leerlas, "
                    "o aporta enlaces. X no permite buscar por tema sin sesión."
                )
            else:
                note = f"{note} Sin resultados en este periodo."
        rows.append(
            PlatformCoverage(
                platform=key,
                label=PLATFORM_LABELS[key],
                documents=count,
                method=method,
                note=note,
            )
        )
    return rows


def run_analysis(
    request: AnalysisRequest,
    *,
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.0-flash",
    output_dir: Path | None = None,
    progress_cb=None,
) -> AnalysisReport:
    def progress(pct: int, stage: str) -> None:
        if progress_cb:
            progress_cb(pct, stage)
        logger.info("[%s%%] %s", pct, stage)

    progress(5, "validating")
    windows = month_windows(request.period_start, request.period_end)
    if len(windows) > 1:
        logger.info("Periodo largo: %s ventanas mensuales", len(windows))

    progress(15, "collecting")
    documents: list[SourceDocument] = []
    errors: dict[str, str] = {}
    enabled = set(request.enabled_sources or [])
    # Sin fuentes explícitas: abrir el set por defecto (salvo que solo haya URLs/archivos).
    if not enabled and not request.urls and not request.file_paths:
        enabled = {
            "news",
            "youtube",
            "reddit",
            "bluesky",
            "mastodon",
            *RESTRICTED_PLATFORMS,
        }
    # "indexed" era el nombre antiguo del bloque de redes cerradas.
    if "indexed" in enabled:
        enabled.update(RESTRICTED_PLATFORMS)

    collectors = []
    if "news" in enabled:
        collectors.append(("news", collect_news))
    if "reddit" in enabled:
        collectors.append(("reddit", collect_reddit))
    if "youtube" in enabled:
        collectors.append(("youtube", collect_youtube))
    if "bluesky" in enabled:
        collectors.append(("bluesky", collect_bluesky))
    if "mastodon" in enabled:
        collectors.append(("mastodon", collect_mastodon))

    news_docs: list[SourceDocument] = []
    for name, fn in collectors:
        try:
            docs = fn(request)
            documents.extend(docs)
            if name == "news":
                news_docs = docs
            logger.info("Conector %s → %s docs", name, len(docs))
        except Exception as exc:
            errors[name] = str(exc)[:300]
            logger.warning("Conector %s error: %s", name, exc)

    # Redes cerradas: publicaciones citadas/incrustadas por los medios del periodo.
    restricted = [p for p in RESTRICTED_PLATFORMS if p in enabled]
    if restricted:
        try:
            base_articles = news_docs or collect_news(request)
            social_docs = collect_social_from_articles(
                request, base_articles, platforms=restricted
            )
            found = {d.source_type for d in social_docs}
            missing = [p for p in restricted if p in PLATFORM_SEARCH_TERMS and p not in found]
            if missing:
                # Segunda pasada: notas que hablan explícitamente de esa red.
                extra_queries = [
                    f"{request.topic} {PLATFORM_SEARCH_TERMS[p]}" for p in missing
                ]
                try:
                    targeted = collect_news(request, queries=extra_queries, max_per_query=8)
                    social_docs.extend(
                        collect_social_from_articles(request, targeted, platforms=missing)
                    )
                except Exception as exc:
                    logger.warning("Búsqueda dirigida de redes falló: %s", exc)
            documents.extend(social_docs)
            logger.info(
                "Redes cerradas (%s) → %s posts citados por medios",
                ", ".join(restricted),
                len(social_docs),
            )
        except Exception as exc:
            errors["redes_cerradas"] = str(exc)[:300]
            logger.warning("Redes cerradas error: %s", exc)

    # Timelines públicos de X: cuentas indicadas por el usuario + las que citan los medios.
    if "x" in enabled:
        handles = _x_handles(request, documents)
        if handles:
            try:
                x_docs = collect_x_timelines(request, handles)
                documents.extend(x_docs)
                logger.info(
                    "X timelines públicos (%s cuentas) → %s publicaciones",
                    len(handles),
                    len(x_docs),
                )
            except Exception as exc:
                errors["x_timelines"] = str(exc)[:300]
                logger.warning("X timelines error: %s", exc)
        else:
            logger.info("X: sin cuentas indicadas; solo posts citados por medios.")

    # Comentarios de Reddit: la opinión de personas, no de cuentas de medios.
    if "reddit" in enabled and documents:
        try:
            comment_docs = collect_reddit_comments(request, documents)
            documents.extend(comment_docs)
            logger.info("Comentarios de Reddit → %s opiniones de audiencia", len(comment_docs))
        except Exception as exc:
            errors["reddit_comentarios"] = str(exc)[:300]
            logger.warning("Comentarios de Reddit error: %s", exc)

    if any(d.source_type == "tiktok" for d in documents):
        try:
            enriched = enrich_with_oembed(documents)
            logger.info("TikTok enriquecidos con oEmbed: %s", enriched)
        except Exception as exc:
            logger.warning("oEmbed falló: %s", exc)

    progress(35, "ingesting_inputs")
    if request.urls:
        try:
            documents.extend(ingest_urls(request.urls))
        except Exception as exc:
            errors["urls"] = str(exc)[:300]
    for path in request.file_paths:
        try:
            title, text = extract_text_file(path)
            documents.append(
                SourceDocument(
                    id=f"file_{content_hash(path)[:12]}",
                    source_type="file",
                    title=title,
                    url="",
                    publisher="archivo",
                    excerpt=text[:400],
                    text=text,
                    content_hash=content_hash(text),
                )
            )
        except Exception as exc:
            errors[f"file:{path}"] = str(exc)[:300]

    # Filtro exclude_terms
    if request.exclude_terms:
        excl = [t.lower() for t in request.exclude_terms if t]
        filtered = []
        for d in documents:
            blob = f"{d.title} {d.excerpt} {d.text[:500]}".lower()
            if any(t in blob for t in excl):
                d.included = False
                d.exclusion_reason = "exclude_term"
            else:
                filtered.append(d)
        documents = filtered

    progress(50, "deduplicating")
    discovered = len(documents)
    documents = dedupe_documents(documents)

    progress(60, "geography")
    geo = detect_geography(documents)

    progress(70, "analyzing")
    report = analyze_with_llm(
        request,
        documents,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )

    clusters = []
    for i, group in enumerate(cluster_same_story(documents), start=1):
        clusters.append(
            StoryCluster(
                id=f"story_{i}",
                title=group[0].title,
                document_ids=[d.id for d in group],
                primary_document_id=group[0].id,
                source_diversity=len({d.publisher for d in group}),
                summary=group[0].excerpt[:240],
            )
        )
    report.clusters = clusters
    report.opinion = _opinion_analyses(
        request,
        documents,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    if report.opinion:
        report.findings = [*_opinion_findings(report.opinion), *report.findings]
        for analysis in report.opinion:
            if analysis.bias_note:
                report.warnings.append(f"{analysis.actor}: {analysis.bias_note}")
    report.geography = {
        "mentions": [
            {
                "place": g.place,
                "region_code": g.region_code,
                "commune_code": g.commune_code,
                "document_id": g.document_id,
                "relation": g.relation,
            }
            for g in geo[:200]
        ],
        "top_places": dict(Counter(g.place for g in geo).most_common(15)),
    }
    by_source = Counter(d.source_type for d in documents)
    report.coverage = CoverageMetrics(
        documents_discovered=discovered,
        documents_included=len(documents),
        by_source=dict(by_source),
        connector_errors=errors,
        platforms=_platform_coverage(by_source, enabled, request, errors),
        period_start=request.period_start,
        period_end=request.period_end,
        territory=request.territory_label,
    )
    empty_restricted = [
        p
        for p in RESTRICTED_PLATFORMS
        if p in enabled and by_source.get(p, 0) == 0 and "redes_cerradas" not in errors
    ]
    if empty_restricted:
        labels = ", ".join(PLATFORM_LABELS[p] for p in empty_restricted)
        report.warnings.append(
            f"Sin publicaciones de {labels} en esta muestra: no tienen API abierta, así que "
            "solo aparecen cuando un medio las cita o cuando aportas enlaces y archivos."
        )
    if errors:
        report.warnings.append(
            "Algunos conectores fallaron o devolvieron cobertura parcial: "
            + ", ".join(errors.keys())
        )

    progress(85, "rendering")
    if output_dir:
        from media_analyzer.renderers.exports import write_all_exports

        write_all_exports(report, output_dir)

    progress(100, "completed")
    return report
