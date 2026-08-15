from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from uuid import uuid4

import feedparser
import httpx

from media_analyzer.geography import territory_query_suffix
from media_analyzer.models import AnalysisRequest, SourceDocument
from media_analyzer.normalization import canonical_url, content_hash
from media_analyzer.validation import validate_public_http_url

logger = logging.getLogger(__name__)
USER_AGENT = "MediaAnalyzer/1.0 (+https://github.com/RaimundoIbieta/Boletines-Informativos)"
# Varias plataformas (Reddit, YouTube) rechazan agentes no-navegador.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _doc_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def _unwrap_redirect(link: str) -> str:
    """Convierte redirecciones de buscador (bing apiclick, google news) en la URL del medio."""
    if not link:
        return link
    try:
        parsed = urlparse(link)
    except Exception:
        return link
    host = (parsed.hostname or "").lower()
    if "bing.com" in host or "google.com" in host:
        from urllib.parse import parse_qs

        target = (parse_qs(parsed.query).get("url") or [""])[0]
        if target.startswith("http"):
            return target
    return link


def _parse_date(entry: dict) -> datetime | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None


def collect_news(
    request: AnalysisRequest,
    *,
    max_per_query: int = 12,
    queries: list[str] | None = None,
) -> list[SourceDocument]:
    suffix = territory_query_suffix(request.territory_level, request.territory_label)
    if queries is None:
        terms = [request.topic, *request.include_terms, *request.actors[:5]]
        queries = []
        for t in terms:
            t = (t or "").strip()
            if t:
                queries.append(f"{t} {suffix}")
    if not queries:
        queries = [f"{request.topic} Chile"]

    docs: list[SourceDocument] = []
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=25.0, follow_redirects=True) as client:
        for q in queries[:8]:
            url = (
                f"https://www.bing.com/news/search?q={quote_plus(q)}"
                f"&format=rss&setlang=es-CL&cc=CL"
            )
            try:
                resp = client.get(url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
            except Exception as exc:
                logger.warning("News feed falló (%s): %s", q[:40], exc)
                continue
            count = 0
            for entry in feed.entries:
                if count >= max_per_query:
                    break
                title = (entry.get("title") or "").strip()
                link = _unwrap_redirect((entry.get("link") or "").strip())
                if not title or not link:
                    continue
                try:
                    link = validate_public_http_url(link, resolve_dns=False)
                except ValueError:
                    continue
                published = _parse_date(entry)
                if published:
                    d = published.date()
                    if d < request.period_start or d > request.period_end:
                        continue
                snippet = re.sub(r"<[^>]+>", "", entry.get("summary") or "").strip()
                host = urlparse(link).netloc.replace("www.", "")
                docs.append(
                    SourceDocument(
                        id=_doc_id("news", link),
                        source_type="news",
                        title=title,
                        url=link,
                        canonical_url=canonical_url(link),
                        publisher=host,
                        published_at=published,
                        excerpt=snippet[:500],
                        text=snippet,
                        content_hash=content_hash(title + snippet),
                        metadata={"query": q},
                    )
                )
                count += 1
    return docs


def _reddit_from_rss(query: str, request: AnalysisRequest) -> list[SourceDocument]:
    """Reddit bloquea search.json desde varias IP; su RSS sigue abierto."""
    url = f"https://www.reddit.com/search.rss?q={quote_plus(query)}&sort=new&t=month"
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA},
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

    docs: list[SourceDocument] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = None
        for key in ("published", "updated"):
            raw = entry.get(key)
            if not raw:
                continue
            try:
                published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                break
            except Exception:
                continue
        if published:
            day = published.date()
            if day < request.period_start or day > request.period_end:
                continue
        text = re.sub(r"<[^>]+>", " ", entry.get("summary") or "").strip()
        author = (entry.get("author") or "").strip()
        docs.append(
            SourceDocument(
                id=_doc_id("reddit", link),
                source_type="reddit",
                title=title,
                url=link,
                canonical_url=canonical_url(link),
                publisher="Reddit",
                author=author,
                published_at=published,
                excerpt=(text or title)[:400],
                text=text or title,
                content_hash=content_hash(title + link),
            )
        )
    return docs


def collect_reddit(request: AnalysisRequest, *, limit: int = 25) -> list[SourceDocument]:
    """RSS primero: Reddit bloquea search.json y aplica rate limit agresivo."""
    query = f"{request.topic} Chile"
    try:
        return _reddit_from_rss(query, request)
    except Exception as rss_exc:
        logger.info("Reddit RSS no disponible (%s); intento JSON.", rss_exc)

    q = quote_plus(query)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}&t=year"
    docs: list[SourceDocument] = []
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA}, timeout=25.0, follow_redirects=True
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        children = (resp.json().get("data") or {}).get("children") or []

    for child in children:
        data = child.get("data") or {}
        title = (data.get("title") or "").strip()
        permalink = data.get("permalink") or ""
        link = f"https://www.reddit.com{permalink}" if permalink else (data.get("url") or "")
        if not title or not link:
            continue
        created = data.get("created_utc")
        published = None
        if created:
            published = datetime.fromtimestamp(float(created), tz=timezone.utc)
            d = published.date()
            if d < request.period_start or d > request.period_end:
                continue
        text = (data.get("selftext") or "")[:3000]
        docs.append(
            SourceDocument(
                id=_doc_id("reddit", link),
                source_type="reddit",
                title=title,
                url=link,
                canonical_url=canonical_url(link),
                publisher=f"r/{data.get('subreddit') or 'reddit'}",
                author=str(data.get("author") or ""),
                published_at=published,
                excerpt=text[:400] or title,
                text=text or title,
                content_hash=content_hash(title + text),
                engagement={
                    "score": data.get("score"),
                    "comments": data.get("num_comments"),
                },
            )
        )
    return docs


_RELATIVE_UNITS = {
    "minuto": 1 / 1440,
    "hora": 1 / 24,
    "día": 1,
    "dia": 1,
    "semana": 7,
    "mes": 30,
    "año": 365,
    "ano": 365,
}


def _parse_relative_es(text: str) -> datetime | None:
    """Convierte 'hace 3 semanas' / 'Emitido hace 5 meses' en fecha aproximada."""
    if not text:
        return None
    m = re.search(r"hace\s+(\d+)\s+([a-záéíóúñ]+)", text.lower())
    if not m:
        return None
    amount = int(m.group(1))
    raw_unit = m.group(2)
    # "meses" -> "mes", "semanas" -> "semana", "días" -> "día"
    candidates = [raw_unit]
    if raw_unit.endswith("es"):
        candidates.append(raw_unit[:-2])
    if raw_unit.endswith("s"):
        candidates.append(raw_unit[:-1])
    days = next((_RELATIVE_UNITS[c] for c in candidates if c in _RELATIVE_UNITS), None)
    if days is None:
        return None
    from datetime import timedelta

    return datetime.now(timezone.utc) - timedelta(days=amount * days)


def _yt_search_html(query: str) -> str:
    url = (
        "https://www.youtube.com/results?search_query="
        f"{quote_plus(query)}&hl=es&gl=CL&sp=CAI%253D"
    )
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA, "Accept-Language": "es-CL,es;q=0.9"},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _yt_extract_renderers(html: str) -> list[dict]:
    import json

    match = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", html, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except Exception:
        return []

    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if "videoRenderer" in node:
                found.append(node["videoRenderer"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found


def collect_youtube(request: AnalysisRequest, *, limit: int = 20) -> list[SourceDocument]:
    """Videos públicos de YouTube leyendo los resultados de búsqueda ordenados por fecha."""
    suffix = territory_query_suffix(request.territory_level, request.territory_label)
    queries = [f"{request.topic} {suffix}"]
    for actor in request.actors[:2]:
        if actor.strip():
            queries.append(f"{actor} {suffix}")

    docs: list[SourceDocument] = []
    seen: set[str] = set()
    for query in queries:
        try:
            html = _yt_search_html(query)
        except Exception as exc:
            logger.warning("YouTube búsqueda falló (%s): %s", query[:40], exc)
            continue
        renderers = _yt_extract_renderers(html)
        if not renderers:
            logger.warning("YouTube no devolvió resultados parseables para %s", query[:40])
        for video in renderers:
            video_id = video.get("videoId")
            if not video_id or video_id in seen:
                continue
            title = "".join(
                run.get("text", "") for run in (video.get("title", {}).get("runs") or [])
            ).strip()
            if not title:
                continue
            published = _parse_relative_es(
                (video.get("publishedTimeText") or {}).get("simpleText") or ""
            )
            if published:
                day = published.date()
                # Margen por la imprecisión de las fechas relativas de YouTube.
                from datetime import timedelta

                if day < request.period_start - timedelta(days=31) or day > request.period_end:
                    continue
            channel = ""
            owner_runs = (video.get("ownerText") or {}).get("runs") or []
            if owner_runs:
                channel = owner_runs[0].get("text") or ""
            description = "".join(
                run.get("text", "")
                for run in (video.get("detailedMetadataSnippets") or [{}])[0]
                .get("snippetText", {})
                .get("runs", [])
            )
            views = ((video.get("viewCountText") or {}).get("simpleText")) or ""
            link = f"https://www.youtube.com/watch?v={video_id}"
            seen.add(video_id)
            docs.append(
                SourceDocument(
                    id=_doc_id("yt", link),
                    source_type="youtube",
                    title=title,
                    url=link,
                    canonical_url=link,
                    publisher=channel or "YouTube",
                    author=channel,
                    published_at=published,
                    excerpt=(description or title)[:400],
                    text=f"{title}\n{description}".strip(),
                    content_hash=content_hash(title + video_id),
                    engagement={"views_text": views},
                    metadata={
                        "query": query,
                        "published_is_approximate": bool(published),
                    },
                )
            )
            if len(docs) >= limit:
                break
        if len(docs) >= limit:
            break
    return docs


# Solo URLs de publicaciones concretas; los enlaces a perfiles son ruido.
POST_PATTERNS: dict[str, re.Pattern[str]] = {
    "x": re.compile(
        r"https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]{1,20}/status/\d+",
        re.I,
    ),
    "instagram": re.compile(
        r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_\-]+",
        re.I,
    ),
    "tiktok": re.compile(
        r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.]+/video/\d+",
        re.I,
    ),
    "facebook": re.compile(
        r"https?://(?:www\.)?facebook\.com/(?:[A-Za-z0-9.\-]+/(?:posts|videos)/[A-Za-z0-9.\-]+"
        r"|permalink\.php\?story_fbid=\d+[^\s\"'<>]*"
        r"|share/[pvr]/[A-Za-z0-9_\-]+)",
        re.I,
    ),
}


def extract_social_posts(html: str, platforms: list[str] | None = None) -> dict[str, list[str]]:
    """Extrae URLs de publicaciones de redes cerradas incrustadas en un HTML."""
    wanted = platforms or list(POST_PATTERNS)
    out: dict[str, list[str]] = {}
    for platform in wanted:
        pattern = POST_PATTERNS.get(platform)
        if not pattern:
            continue
        urls: list[str] = []
        for raw in pattern.findall(html or ""):
            url = raw.rstrip(").,;\"'")
            if url not in urls:
                urls.append(url)
        if urls:
            out[platform] = urls
    return out


def collect_social_from_articles(
    request: AnalysisRequest,
    articles: list[SourceDocument],
    *,
    platforms: list[str] | None = None,
    max_articles: int = 25,
    limit_per_platform: int = 12,
) -> list[SourceDocument]:
    """Descubre publicaciones de X/Instagram/Facebook/TikTok citadas por los medios.

    Es cobertura indirecta y verificable: cada post queda ligado al artículo que lo citó.
    No sustituye a las APIs oficiales ni pretende ser una muestra completa.
    """
    wanted = [p for p in (platforms or list(POST_PATTERNS)) if p in POST_PATTERNS]
    if not wanted:
        return []

    docs: list[SourceDocument] = []
    counts: dict[str, int] = {p: 0 for p in wanted}
    seen: set[str] = set()
    candidates = [a for a in articles if a.url][:max_articles]

    with httpx.Client(
        headers={"User-Agent": BROWSER_UA, "Accept-Language": "es-CL,es;q=0.9"},
        timeout=20.0,
        follow_redirects=True,
    ) as client:
        for article in candidates:
            if all(counts[p] >= limit_per_platform for p in wanted):
                break
            try:
                resp = client.get(article.url)
                if resp.status_code >= 400:
                    continue
                if "text/html" not in resp.headers.get("content-type", ""):
                    continue
                html = resp.text[:600_000]
            except Exception as exc:
                logger.debug("No se pudo leer %s: %s", article.url, exc)
                continue

            for platform, urls in extract_social_posts(html, wanted).items():
                for url in urls:
                    if counts[platform] >= limit_per_platform:
                        break
                    key = url.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    counts[platform] += 1
                    handle = ""
                    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status", url, re.I)
                    if m:
                        handle = f"@{m.group(1)}"
                    m = re.search(r"tiktok\.com/(@[A-Za-z0-9_.]+)/video", url, re.I)
                    if m:
                        handle = m.group(1)
                    label = {
                        "x": "X (Twitter)",
                        "instagram": "Instagram",
                        "facebook": "Facebook",
                        "tiktok": "TikTok",
                    }[platform]
                    quote = (article.excerpt or article.title or "")[:400]
                    docs.append(
                        SourceDocument(
                            id=_doc_id(platform, url),
                            source_type=platform,  # type: ignore[arg-type]
                            title=f"Publicación en {label} citada por {article.publisher}",
                            url=url,
                            canonical_url=canonical_url(url),
                            publisher=label,
                            author=handle,
                            published_at=article.published_at,
                            excerpt=quote,
                            text=f"{article.title}\n{quote}".strip(),
                            content_hash=content_hash(url),
                            metadata={
                                "coverage": "indirect_media_citation",
                                "cited_by_url": article.url,
                                "cited_by": article.publisher,
                                "cited_by_document_id": article.id,
                            },
                        )
                    )
    return docs


def collect_bluesky(request: AnalysisRequest, *, limit: int = 25) -> list[SourceDocument]:
    """Busca en Bluesky por tema y por actor. Propaga el error si la API rechaza."""
    queries = [request.topic, *[a for a in request.actors[:3] if a.strip()]]
    posts: list[dict] = []
    last_error: Exception | None = None
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA, "Accept": "application/json"},
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        for query in queries:
            url = (
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
                f"?q={quote_plus(query)}&limit={limit}&lang=es"
            )
            try:
                resp = client.get(url)
                resp.raise_for_status()
                posts.extend(resp.json().get("posts") or [])
            except Exception as exc:
                last_error = exc
                logger.warning("Bluesky falló (%s): %s", query[:30], exc)
    if not posts and last_error is not None:
        # Sin esto el informe diría "sin resultados" cuando en realidad la API nos bloqueó.
        raise RuntimeError(f"Bluesky no respondió: {last_error}")

    docs: list[SourceDocument] = []
    for post in posts:
        record = post.get("record") or {}
        text = (record.get("text") or "").strip()
        author = ((post.get("author") or {}).get("handle")) or ""
        uri = post.get("uri") or ""
        if not text:
            continue
        created = record.get("createdAt")
        published = None
        if created:
            try:
                published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                d = published.date()
                if d < request.period_start or d > request.period_end:
                    continue
            except Exception:
                published = None
        link = f"https://bsky.app/profile/{author}/post/{uri.split('/')[-1]}" if uri else ""
        docs.append(
            SourceDocument(
                id=_doc_id("bsky", uri or text[:80]),
                source_type="bluesky",
                title=text[:120],
                url=link,
                canonical_url=canonical_url(link),
                publisher="Bluesky",
                author=author,
                published_at=published,
                excerpt=text[:400],
                text=text,
                content_hash=content_hash(text),
                engagement={"likeCount": (post.get("likeCount")), "repostCount": post.get("repostCount")},
            )
        )
    return docs


MASTODON_INSTANCES = ("mastodon.social", "mstdn.social", "masto.es")


def collect_mastodon(request: AnalysisRequest, *, limit: int = 20) -> list[SourceDocument]:
    """Busca en varias instancias públicas; masto.es aporta contenido en español."""
    q = quote_plus(request.topic)
    statuses: list[dict] = []
    last_error: Exception | None = None
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA, "Accept": "application/json"},
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        for host in MASTODON_INSTANCES:
            url = f"https://{host}/api/v2/search?q={q}&type=statuses&limit={limit}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                found = resp.json().get("statuses") or []
                statuses.extend(found)
                if found:
                    break
            except Exception as exc:
                last_error = exc
                logger.warning("Mastodon %s falló: %s", host, exc)
    if not statuses and last_error is not None:
        raise RuntimeError(f"Mastodon no respondió: {last_error}")

    docs: list[SourceDocument] = []
    for st in statuses:
        text = re.sub(r"<[^>]+>", "", st.get("content") or "").strip()
        link = st.get("url") or ""
        if not text:
            continue
        created = st.get("created_at")
        published = None
        if created:
            try:
                published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                d = published.date()
                if d < request.period_start or d > request.period_end:
                    continue
            except Exception:
                pass
        docs.append(
            SourceDocument(
                id=_doc_id("masto", link or text[:80]),
                source_type="mastodon",
                title=text[:120],
                url=link,
                canonical_url=canonical_url(link),
                publisher="Mastodon",
                author=((st.get("account") or {}).get("acct") or ""),
                published_at=published,
                excerpt=text[:400],
                text=text,
                content_hash=content_hash(text),
                engagement={"favourites": st.get("favourites_count"), "reblogs": st.get("reblogs_count")},
            )
        )
    return docs


def collect_indexed_social(
    request: AnalysisRequest,
    articles: list[SourceDocument] | None = None,
    *,
    platforms: list[str] | None = None,
) -> list[SourceDocument]:
    """Compatibilidad: descubre posts de redes cerradas citados por los medios.

    La versión anterior usaba `site:` contra Bing News, que no indexa publicaciones
    de redes sociales y por eso siempre devolvía cero documentos.
    """
    if articles is None:
        articles = collect_news(request)
    return collect_social_from_articles(request, articles, platforms=platforms)


def ingest_urls(urls: list[str]) -> list[SourceDocument]:
    from media_analyzer.extractors.html import fetch_url_text

    docs: list[SourceDocument] = []
    for raw in urls:
        try:
            url = validate_public_http_url(raw)
        except ValueError as exc:
            logger.warning("URL rechazada: %s (%s)", raw, exc)
            continue
        try:
            title, text = fetch_url_text(url)
        except Exception as exc:
            logger.warning("No se pudo ingerir %s: %s", url, exc)
            continue
        docs.append(
            SourceDocument(
                id=_doc_id("url", url),
                source_type="url",
                title=title or url,
                url=url,
                canonical_url=canonical_url(url),
                publisher=urlparse(url).netloc.replace("www.", ""),
                excerpt=(text or "")[:400],
                text=text[:8000],
                content_hash=content_hash(text or title or url),
            )
        )
    return docs
