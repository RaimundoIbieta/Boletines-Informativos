from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from media_analyzer.connectors.collect import (
    collect_bluesky,
    collect_indexed_social,
    collect_mastodon,
    collect_news,
    collect_reddit,
    collect_youtube,
    ingest_urls,
)
from media_analyzer.deduplication import cluster_same_story, dedupe_documents
from media_analyzer.extractors.files import extract_text_file
from media_analyzer.geography import detect_geography
from media_analyzer.models import (
    AnalysisReport,
    AnalysisRequest,
    CoverageMetrics,
    SourceDocument,
    StoryCluster,
)
from media_analyzer.normalization import content_hash
from media_analyzer.sentiment import analyze_with_llm
from media_analyzer.validation import month_windows

logger = logging.getLogger(__name__)


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
        enabled = {"news", "youtube", "reddit", "bluesky", "mastodon", "indexed"}

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
    if "indexed" in enabled:
        collectors.append(("indexed", collect_indexed_social))

    for name, fn in collectors:
        try:
            docs = fn(request)
            documents.extend(docs)
            logger.info("Conector %s → %s docs", name, len(docs))
        except Exception as exc:
            errors[name] = str(exc)[:300]
            logger.warning("Conector %s error: %s", name, exc)

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
        period_start=request.period_start,
        period_end=request.period_end,
        territory=request.territory_label,
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
