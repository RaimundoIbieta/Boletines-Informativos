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


def _doc_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha1(key.encode()).hexdigest()[:12]}"


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


def collect_news(request: AnalysisRequest, *, max_per_query: int = 12) -> list[SourceDocument]:
    suffix = territory_query_suffix(request.territory_level, request.territory_label)
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
                link = (entry.get("link") or "").strip()
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


def collect_reddit(request: AnalysisRequest, *, limit: int = 25) -> list[SourceDocument]:
    q = quote_plus(f"{request.topic} Chile")
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}&t=year"
    headers = {"User-Agent": USER_AGENT}
    docs: list[SourceDocument] = []
    try:
        with httpx.Client(headers=headers, timeout=25.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            children = (resp.json().get("data") or {}).get("children") or []
    except Exception as exc:
        logger.warning("Reddit falló: %s", exc)
        return docs

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


def collect_youtube(request: AnalysisRequest, *, limit: int = 15) -> list[SourceDocument]:
    """Descubrimiento liviano vía Bing News/Web no disponible; usa RSS de búsqueda DDG-like.
    Fallback: feed de YouTube search via invidious-like no garantizado.
    Usamos Bing RSS con site:youtube.com.
    """
    suffix = territory_query_suffix(request.territory_level, request.territory_label)
    q = quote_plus(f"site:youtube.com {request.topic} {suffix}")
    url = f"https://www.bing.com/news/search?q={q}&format=rss&setlang=es-CL&cc=CL"
    headers = {"User-Agent": USER_AGENT}
    docs: list[SourceDocument] = []
    try:
        with httpx.Client(headers=headers, timeout=25.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
    except Exception as exc:
        logger.warning("YouTube discovery falló: %s", exc)
        return docs
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        if "youtube.com" not in link and "youtu.be" not in link:
            continue
        published = _parse_date(entry)
        if published:
            d = published.date()
            if d < request.period_start or d > request.period_end:
                continue
        docs.append(
            SourceDocument(
                id=_doc_id("yt", link),
                source_type="youtube",
                title=title,
                url=link,
                canonical_url=canonical_url(link),
                publisher="YouTube",
                published_at=published,
                excerpt=title,
                text=title,
                content_hash=content_hash(title + link),
            )
        )
    return docs


def collect_bluesky(request: AnalysisRequest, *, limit: int = 20) -> list[SourceDocument]:
    q = quote_plus(request.topic)
    url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={q}&limit={limit}"
    docs: list[SourceDocument] = []
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            posts = resp.json().get("posts") or []
    except Exception as exc:
        logger.warning("Bluesky falló: %s", exc)
        return docs
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


def collect_mastodon(request: AnalysisRequest, *, limit: int = 20) -> list[SourceDocument]:
    # Instancia pública chilena / general
    q = quote_plus(request.topic)
    url = f"https://mastodon.social/api/v2/search?q={q}&type=statuses&limit={limit}"
    docs: list[SourceDocument] = []
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            statuses = resp.json().get("statuses") or []
    except Exception as exc:
        logger.warning("Mastodon falló: %s", exc)
        return docs
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


def collect_indexed_social(request: AnalysisRequest, *, limit: int = 15) -> list[SourceDocument]:
    """Publicaciones públicas indexadas (cobertura parcial) vía Bing News/RSS site:."""
    sites = [
        ("x.com OR twitter.com", "indexed"),
        ("instagram.com", "indexed"),
        ("facebook.com", "indexed"),
        ("tiktok.com", "indexed"),
    ]
    docs: list[SourceDocument] = []
    headers = {"User-Agent": USER_AGENT}
    suffix = territory_query_suffix(request.territory_level, request.territory_label)
    with httpx.Client(headers=headers, timeout=25.0, follow_redirects=True) as client:
        for site, stype in sites:
            q = quote_plus(f"{request.topic} {suffix} ({site})")
            url = f"https://www.bing.com/news/search?q={q}&format=rss&setlang=es-CL&cc=CL"
            try:
                resp = client.get(url)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
            except Exception as exc:
                logger.warning("Indexed %s falló: %s", site, exc)
                continue
            for entry in feed.entries[: max(1, limit // len(sites))]:
                title = (entry.get("title") or "").strip()
                link = (entry.get("link") or "").strip()
                if not title or not link:
                    continue
                published = _parse_date(entry)
                if published:
                    d = published.date()
                    if d < request.period_start or d > request.period_end:
                        continue
                docs.append(
                    SourceDocument(
                        id=_doc_id("idx", link),
                        source_type="indexed",  # type: ignore[arg-type]
                        title=title,
                        url=link,
                        canonical_url=canonical_url(link),
                        publisher=urlparse(link).netloc.replace("www.", ""),
                        published_at=published,
                        excerpt=title,
                        text=title,
                        content_hash=content_hash(title + link),
                        metadata={"indexed_query": site, "coverage": "partial"},
                    )
                )
    return docs


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
