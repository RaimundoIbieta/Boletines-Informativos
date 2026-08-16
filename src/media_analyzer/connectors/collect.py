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


def opinion_queries(request: AnalysisRequest) -> list[str]:
    """Consultas orientadas a debate, no a titulares.

    Buscar solo el nombre trae notas de prensa; para saber qué opina la gente hay
    que buscar las formas en que se expresa una preferencia.
    """
    topic = (request.topic or "").strip()
    if not topic:
        return []
    config = request.configuration or {}
    raw_rivals = config.get("rivals") or config.get("compare_with") or []
    if isinstance(raw_rivals, str):
        raw_rivals = raw_rivals.replace(",", "\n").split("\n")
    rivals = [r.strip() for r in raw_rivals if isinstance(r, str) and r.strip()]

    exact = f'"{topic}"' if " " in topic else topic
    queries = [f"{exact} opinión", f"{exact} críticas"]
    for rival in rivals[:2]:
        queries.append(f"{exact} vs {rival}")
        queries.append(f"{exact} better than {rival}")
    return queries


def collect_reddit(
    request: AnalysisRequest, *, limit: int = 25, delay_seconds: float = 5.0
) -> list[SourceDocument]:
    """RSS primero: Reddit bloquea search.json y aplica rate limit agresivo."""
    import time

    # Las comillas fuerzan la frase exacta: sin ellas Reddit trae cualquier post
    # del subreddit que comparta una sola palabra con la consulta.
    topic = (request.topic or "").strip()
    exact = f'"{topic}"' if " " in topic else topic
    queries = [f"{exact} {request.territory_label}".strip(), *opinion_queries(request)]
    docs: list[SourceDocument] = []
    seen: set[str] = set()
    last_error: Exception | None = None
    for index, query in enumerate(queries[:5]):
        if index:
            time.sleep(delay_seconds)
        try:
            for doc in _reddit_from_rss(query, request):
                if doc.url not in seen:
                    seen.add(doc.url)
                    docs.append(doc)
        except Exception as exc:
            last_error = exc
            logger.info("Reddit RSS falló para «%s»: %s", query[:40], exc)
    if docs:
        return docs
    logger.info("Reddit RSS no disponible (%s); intento JSON.", last_error)
    query = f"{request.topic} {request.territory_label}".strip()

    q = quote_plus(query)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}&t=year"
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


# public.api.bsky.app responde 403 a agentes de navegador; api.bsky.app acepta un UA propio.
BSKY_HOSTS = ("api.bsky.app", "public.api.bsky.app")
API_UA = "BoletinesInformativos/1.0 (+https://github.com/RaimundoIbieta/Boletines-Informativos)"


def collect_bluesky(request: AnalysisRequest, *, limit: int = 25) -> list[SourceDocument]:
    """Busca en Bluesky por tema y por actor. Propaga el error si la API rechaza."""
    territory = (request.territory_label or "").strip()
    queries = [request.topic]
    # Sin el territorio, un tema como «reforma de pensiones» trae sobre todo
    # conversación de otros países.
    if territory and territory.lower() not in {"internacional", "global", "mundial"}:
        queries.append(f"{request.topic} {territory}")
    queries.extend(a for a in request.actors[:2] if a.strip())
    queries.extend(opinion_queries(request))
    posts: list[dict] = []
    last_error: Exception | None = None
    working_host: str | None = None
    with httpx.Client(
        headers={"User-Agent": API_UA, "Accept": "application/json"},
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        for query in queries:
            for host in (working_host,) if working_host else BSKY_HOSTS:
                url = (
                    f"https://{host}/xrpc/app.bsky.feed.searchPosts"
                    f"?q={quote_plus(query)}&limit={limit}&lang=es"
                )
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    posts.extend(resp.json().get("posts") or [])
                    working_host = host
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Bluesky %s falló (%s): %s", host, query[:30], exc)
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


def _strip_html(raw: str) -> str:
    import html as html_mod

    text = html_mod.unescape(html_mod.unescape(raw or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_reddit_comment_feed(xml: str) -> list[dict]:
    """Extrae autor, texto y enlace de cada comentario del RSS de un hilo."""
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
    out: list[dict] = []
    for entry in entries:
        author = re.search(r"<name>(.*?)</name>", entry)
        content = re.search(r'<content type="html">(.*?)</content>', entry, re.S)
        link = re.search(r'<link href="([^"]+)"', entry)
        updated = re.search(r"<updated>(.*?)</updated>", entry)
        text = _strip_html(content.group(1)) if content else ""
        if not text:
            continue
        out.append(
            {
                "author": (author.group(1) if author else "").strip(),
                "text": text,
                "url": (link.group(1) if link else "").strip(),
                "updated": (updated.group(1) if updated else "").strip(),
            }
        )
    return out


def collect_reddit_comments(
    request: AnalysisRequest,
    threads: list[SourceDocument],
    *,
    max_threads: int = 6,
    per_thread: int = 40,
    delay_seconds: float = 6.0,
) -> list[SourceDocument]:
    """Baja los comentarios de los hilos encontrados: es la opinión de la audiencia.

    Reddit limita fuerte por IP, así que se recorren pocos hilos con pausas y se
    prioriza los que tienen más discusión.
    """
    import time

    candidates = [
        d
        for d in threads
        if d.source_type == "reddit" and "/comments/" in (d.url or "")
        and (d.metadata or {}).get("kind") != "comment"
    ]
    candidates.sort(
        key=lambda d: (d.engagement or {}).get("num_comments") or 0, reverse=True
    )
    candidates = candidates[:max_threads]
    if not candidates:
        return []

    docs: list[SourceDocument] = []
    failures = 0
    with httpx.Client(
        headers={"User-Agent": BROWSER_UA},
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        for index, thread in enumerate(candidates):
            if index:
                time.sleep(delay_seconds)
            base = (thread.url or "").split("?")[0].rstrip("/")
            try:
                resp = client.get(f"{base}.rss?limit={per_thread}&sort=top")
                if resp.status_code == 429:
                    time.sleep(delay_seconds * 2)
                    resp = client.get(f"{base}.rss?limit={per_thread}&sort=top")
                resp.raise_for_status()
                comments = parse_reddit_comment_feed(resp.text)
            except Exception as exc:
                failures += 1
                logger.warning("Comentarios de Reddit fallaron (%s): %s", base[:60], exc)
                continue

            # El primer bloque del feed es el post original, que ya viene como documento.
            for comment in comments[1:]:
                text = comment["text"]
                if len(text) < 15:
                    continue
                author = comment["author"].lstrip("/").replace("u/", "")
                if author.lower() in {"automoderator", "[deleted]"}:
                    continue
                published = None
                if comment["updated"]:
                    try:
                        published = datetime.fromisoformat(
                            comment["updated"].replace("Z", "+00:00")
                        )
                    except Exception:
                        published = None
                url = comment["url"] or thread.url
                docs.append(
                    SourceDocument(
                        id=_doc_id("rdc", url or text[:80]),
                        source_type="reddit",
                        title=text[:120],
                        url=url,
                        canonical_url=canonical_url(url),
                        publisher=thread.publisher or "Reddit",
                        author=author,
                        published_at=published or thread.published_at,
                        excerpt=text[:400],
                        text=text,
                        content_hash=content_hash(text),
                        metadata={
                            "kind": "comment",
                            "voice": "audience",
                            "thread_title": thread.title,
                            "thread_url": thread.url,
                        },
                    )
                )
    if not docs and failures:
        raise RuntimeError(
            f"Reddit no entregó comentarios ({failures} hilos con error de límite de tasa)."
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


SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"


# Rutas de X y placeholders de plantillas de embed que no son cuentas reales.
RESERVED_HANDLES = {
    "user_id",
    "i",
    "intent",
    "home",
    "search",
    "hashtag",
    "share",
    "explore",
    "notifications",
    "messages",
    "settings",
    "compose",
    "login",
    "signup",
    "widgets",
}


def normalize_handle(raw: str) -> str:
    """Acepta @usuario, usuario o una URL de perfil y devuelve el handle limpio."""
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("http"):
        path = urlparse(value).path.strip("/")
        value = path.split("/")[0] if path else ""
    value = value.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", value or ""):
        return ""
    if value.lower() in RESERVED_HANDLES:
        return ""
    return value


def _parse_syndication_entries(html: str) -> list[dict]:
    import json

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S
    )
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except Exception:
        return []
    timeline = (data.get("props") or {}).get("pageProps", {}).get("timeline") or {}
    return timeline.get("entries") or []


def collect_x_timelines(
    request: AnalysisRequest,
    handles: list[str],
    *,
    delay_seconds: float = 2.0,
    max_accounts: int = 12,
) -> list[SourceDocument]:
    """Lee publicaciones públicas de cuentas de X sin login ni seguirlas.

    Usa el endpoint de sindicación de widgets, que sirve el timeline público.
    No permite buscar por tema: X cerró la búsqueda sin sesión, así que hay que
    indicar las cuentas que se quieren leer.
    """
    import time

    clean = []
    for raw in handles:
        handle = normalize_handle(raw)
        if handle and handle.lower() not in {h.lower() for h in clean}:
            clean.append(handle)
    clean = clean[:max_accounts]
    if not clean:
        return []

    docs: list[SourceDocument] = []
    failures: list[str] = []
    with httpx.Client(
        headers={
            "User-Agent": BROWSER_UA,
            "Referer": "https://platform.twitter.com/",
            "Accept-Language": "es-CL,es;q=0.9",
        },
        timeout=25.0,
        follow_redirects=True,
    ) as client:
        for index, handle in enumerate(clean):
            if index:
                time.sleep(delay_seconds)
            entries: list[dict] = []
            for attempt in range(3):
                try:
                    resp = client.get(SYNDICATION_URL.format(handle=handle))
                    if resp.status_code == 429:
                        time.sleep(delay_seconds * (attempt + 2))
                        continue
                    resp.raise_for_status()
                    entries = _parse_syndication_entries(resp.text)
                    break
                except Exception as exc:
                    if attempt == 2:
                        failures.append(f"@{handle}: {exc}")
                    else:
                        time.sleep(delay_seconds * (attempt + 1))
            if not entries:
                if f"@{handle}" not in " ".join(failures):
                    failures.append(f"@{handle}: sin publicaciones legibles")
                continue

            for entry in entries:
                tweet = (entry.get("content") or {}).get("tweet") or {}
                text = (tweet.get("full_text") or tweet.get("text") or "").strip()
                if not text:
                    continue
                published = None
                created = tweet.get("created_at")
                if created:
                    try:
                        published = parsedate_to_datetime(created)
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                    except Exception:
                        published = None
                if published:
                    day = published.date()
                    if day < request.period_start or day > request.period_end:
                        continue
                user = tweet.get("user") or {}
                screen_name = user.get("screen_name") or handle
                tweet_id = tweet.get("id_str") or tweet.get("conversation_id_str") or ""
                link = tweet.get("permalink") or ""
                if link and link.startswith("/"):
                    link = f"https://x.com{link}"
                if not link:
                    link = f"https://x.com/{screen_name}/status/{tweet_id}"
                docs.append(
                    SourceDocument(
                        id=_doc_id("x", link or text[:60]),
                        source_type="x",
                        title=text[:120],
                        url=link,
                        canonical_url=canonical_url(link),
                        publisher="X (Twitter)",
                        author=f"@{screen_name}",
                        published_at=published,
                        excerpt=text[:400],
                        text=text,
                        content_hash=content_hash(text),
                        engagement={
                            "likes": tweet.get("favorite_count"),
                            "reposts": tweet.get("retweet_count"),
                            "replies": tweet.get("reply_count"),
                        },
                        metadata={
                            "coverage": "public_timeline",
                            "account": f"@{screen_name}",
                            "followers": (user.get("followers_count") if user else None),
                        },
                    )
                )

    if not docs and failures:
        raise RuntimeError("X no entregó timelines públicos: " + "; ".join(failures[:3]))
    return docs


def fetch_tiktok_oembed(url: str) -> dict:
    """Metadata pública de un video de TikTok (sin login)."""
    api = f"https://www.tiktok.com/oembed?url={quote_plus(url)}"
    with httpx.Client(headers={"User-Agent": BROWSER_UA}, timeout=20.0) as client:
        resp = client.get(api)
        resp.raise_for_status()
        return resp.json()


def enrich_with_oembed(documents: list[SourceDocument]) -> int:
    """Completa título y autor de los videos de TikTok detectados."""
    enriched = 0
    for doc in documents:
        if doc.source_type != "tiktok" or not doc.url:
            continue
        try:
            data = fetch_tiktok_oembed(doc.url)
        except Exception as exc:
            logger.debug("oEmbed TikTok falló para %s: %s", doc.url, exc)
            continue
        title = (data.get("title") or "").strip()
        author = (data.get("author_name") or "").strip()
        if title:
            doc.title = title[:200]
            doc.excerpt = title[:400]
            doc.text = f"{title}\n{doc.text}".strip()
        if author:
            doc.author = author
        doc.metadata = {**(doc.metadata or {}), "oembed": True}
        enriched += 1
    return enriched


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
