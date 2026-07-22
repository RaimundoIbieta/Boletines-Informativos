from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import feedparser
import httpx
import trafilatura
from tenacity import retry, stop_after_attempt, wait_exponential

from boletin.models import RawArticle

logger = logging.getLogger(__name__)

USER_AGENT = (
    "BoletinPAE/1.0 (+https://github.com/local/boletines-informativos; "
    "weekly education newsletter Chile)"
)

SEARCH_QUERIES: list[tuple[str, str]] = [
    ("JUNAEB OR \"Programa de Alimentación Escolar\" OR PAE JUNAEB", "JUNAEB_PAE"),
    ("JUNAEB alimentación escolar Chile", "JUNAEB_PAE"),
    ("\"Programa de Alimentación Escolar\" Chile", "JUNAEB_PAE"),
    ("JUNJI alimentación OR colación OR comida", "JUNJI_INTEGRA"),
    ("\"Fundación Integra\" alimentación OR colación", "JUNJI_INTEGRA"),
    ("MINEDUC Chile educación OR subvención OR liceo", "MINEDUC"),
    ("Ministerio de Educación Chile alimentación escolar", "MINEDUC"),
]

# Titulares recirculados / engañosos que no deben entrar al boletín
TITLE_BLOCKLIST = [
    "adiós junaeb",
    "adios junaeb",
    "descontinuar el programa de alimentación escolar",
    "oficio del ministerio de hacienda que recomienda descontinuar",
    "oficio del ministerio de hacienda recomienda descontinuar",
    "descontinuar programas de salud mental",
    "descontinuar programas de salud mental y de reducción",
]


def is_blocked_title(title: str) -> bool:
    t = title.lower()
    return any(b in t for b in TITLE_BLOCKLIST)

# Fechas explícitas en texto chileno / ISO
_DATE_PATTERNS = [
    re.compile(
        r"\b(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(\d{4})\b",
        re.I,
    ),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
]

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _google_news_rss(query: str, start: date, end: date) -> str:
    """RSS con ventana after/before (before es exclusivo en Google News)."""
    before = end + timedelta(days=1)
    dated = f"{query} after:{start.isoformat()} before:{before.isoformat()}"
    q = quote_plus(dated)
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl=es-419&gl=CL&ceid=CL:es-419"
    )


def is_google_news_url(url: str) -> bool:
    try:
        return "news.google.com" in (urlparse(url).netloc or "").lower()
    except Exception:
        return "news.google.com" in (url or "").lower()


def unwrap_google_news_url(url: str) -> str:
    """Devuelve la URL directa del medio (nunca deja un link de Google News)."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if "news.google.com" not in parsed.netloc:
            return url
        qs = parse_qs(parsed.query)
        if "url" in qs:
            direct = unquote(qs["url"][0])
            if direct and not is_google_news_url(direct):
                return direct

        # Formato /rss/articles/CBMi… → URL del publisher
        if "/articles/" not in parsed.path:
            return ""

        clean = url.split("&hl=")[0].split("?oc=")[0]
        variants = [clean]
        if "/rss/articles/" in clean:
            variants.append(clean.replace("/rss/articles/", "/articles/", 1))
        else:
            variants.append(clean.replace("/articles/", "/rss/articles/", 1))

        try:
            from googlenewsdecoder import gnewsdecoder
        except ImportError:
            logger.warning("Falta googlenewsdecoder; no se puede obtener link directo")
            return ""

        import time

        for variant in variants:
            for attempt in range(3):
                try:
                    result = gnewsdecoder(variant, interval=1)
                    if isinstance(result, dict) and result.get("status"):
                        decoded = str(result.get("decoded_url") or "").strip()
                        if decoded and not is_google_news_url(decoded):
                            return decoded
                except Exception as exc:
                    logger.debug(
                        "Decode GNews intento %s falló: %s",
                        attempt + 1,
                        exc,
                    )
                if attempt < 2:
                    time.sleep(1.2 * (attempt + 1))
    except Exception as exc:
        logger.debug("unwrap GNews falló: %s", exc)
    return ""


def _parse_published(entry: dict) -> date | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.date()
        except (TypeError, ValueError, IndexError):
            pass
    if entry.get("published_parsed"):
        try:
            t = entry["published_parsed"]
            return date(t.tm_year, t.tm_mon, t.tm_mday)
        except Exception:
            pass
    return None


def _parse_spanish_date(day: str, month: str, year: str) -> date | None:
    try:
        return date(int(year), _MONTHS[month.lower()], int(day))
    except (KeyError, ValueError):
        return None


def extract_dates_from_text(text: str) -> list[date]:
    """Extrae fechas candidatas del titular/cuerpo (para validar antigüedad)."""
    if not text:
        return []
    found: list[date] = []
    sample = text[:2500]

    for m in _DATE_PATTERNS[0].finditer(sample):
        d = _parse_spanish_date(m.group(1), m.group(2), m.group(3))
        if d:
            found.append(d)

    for m in _DATE_PATTERNS[1].finditer(sample):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    for m in _DATE_PATTERNS[2].finditer(sample):
        try:
            # dd/mm/yyyy (Chile)
            found.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass

    return found


def resolve_article_date(
    rss_date: date | None,
    title: str,
    snippet: str,
    full_text: str,
    *,
    start: date,
    end: date,
) -> date | None:
    """
    Determina la fecha efectiva de la noticia.

    Regla: si el texto menciona claramente una fecha FUERA del periodo,
    se descarta (None) aunque el RSS diga lo contrario (Google News a menudo
    reindexa o recircula notas antiguas).
    """
    corpus = f"{title}\n{snippet}\n{full_text}"
    text_dates = extract_dates_from_text(corpus)

    out_of_range = [d for d in text_dates if d < start or d > end]
    in_range = [d for d in text_dates if start <= d <= end]

    # Señal fuerte de noticia antigua en el cuerpo
    if out_of_range and not in_range:
        oldest = min(out_of_range)
        logger.info(
            "Descartada por fecha en texto fuera de periodo (%s): %s",
            oldest.isoformat(),
            title[:80],
        )
        return None

    if rss_date and start <= rss_date <= end:
        # Si el texto solo muestra fechas fuera de rango, ya se filtró arriba
        return rss_date

    if in_range:
        return max(in_range)

    # Sin fecha verificable en el periodo → no incluir
    return None


def _source_from_entry(entry: dict) -> str:
    source = entry.get("source", {})
    if isinstance(source, dict) and source.get("title"):
        return str(source["title"]).strip()
    link = entry.get("link") or ""
    host = urlparse(unwrap_google_news_url(link) or link).netloc
    return host.replace("www.", "") if host else "Fuente desconocida"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _fetch_text(url: str, client: httpx.Client) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                favor_recall=True,
            )
            if text and len(text.strip()) > 120:
                return text.strip()
    except Exception as exc:
        logger.debug("trafilatura falló para %s: %s", url, exc)

    try:
        resp = client.get(url, follow_redirects=True, timeout=20.0)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, favor_recall=True)
        return (text or "").strip()
    except Exception as exc:
        logger.debug("httpx falló para %s: %s", url, exc)
        return ""


def _normalize_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title).strip().lower()
    t = re.sub(r"\s*-\s*[^-]+$", "", t)
    return t


def collect_articles(
    start: date,
    end: date,
    *,
    queries: list[tuple[str, str]] | None = None,
    max_per_query: int = 15,
    fetch_body: bool = True,
) -> list[RawArticle]:
    """Recolecta noticias estrictamente del rango [start, end] (lun–dom previo)."""
    search_queries = queries or SEARCH_QUERIES
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    articles: list[RawArticle] = []

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=25.0, follow_redirects=True) as client:
        for query, topic in search_queries:
            feed_url = _google_news_rss(query, start, end)
            logger.info(
                "Consultando feed (%s → %s): %s",
                start.isoformat(),
                end.isoformat(),
                query,
            )
            try:
                resp = None
                last_exc: Exception | None = None
                for attempt in range(3):
                    try:
                        resp = client.get(feed_url)
                        if resp.status_code == 503:
                            raise httpx.HTTPStatusError(
                                "503",
                                request=resp.request,
                                response=resp,
                            )
                        resp.raise_for_status()
                        break
                    except Exception as exc:
                        last_exc = exc
                        logger.warning(
                            "Feed intento %s/3 falló (%s): %s",
                            attempt + 1,
                            query[:40],
                            exc,
                        )
                        if attempt < 2:
                            import time

                            time.sleep(2 * (attempt + 1))
                else:
                    raise last_exc or RuntimeError("feed falló")
                feed = feedparser.parse(resp.text)
            except Exception as exc:
                logger.warning("No se pudo leer feed '%s': %s", query, exc)
                continue

            count = 0
            for entry in feed.entries:
                if count >= max_per_query:
                    break
                title = (entry.get("title") or "").strip()
                raw_link = (entry.get("link") or "").strip()
                link = unwrap_google_news_url(raw_link)
                if not title or not link or is_google_news_url(link):
                    if raw_link and is_google_news_url(raw_link):
                        logger.warning(
                            "Sin link directo del medio, omitido: %s",
                            title[:80] or raw_link[:60],
                        )
                    continue
                if is_blocked_title(title):
                    logger.info("Titular en lista negra, omitido: %s", title[:80])
                    continue

                rss_date = _parse_published(entry)
                if rss_date and (rss_date < start or rss_date > end):
                    continue

                key = _normalize_title(title)
                if key in seen_titles or link in seen_urls:
                    continue

                snippet = ""
                if entry.get("summary"):
                    snippet = re.sub(r"<[^>]+>", "", entry["summary"]).strip()

                full_text = ""
                if fetch_body:
                    full_text = _fetch_text(link, client)

                effective = resolve_article_date(
                    rss_date,
                    title,
                    snippet,
                    full_text,
                    start=start,
                    end=end,
                )
                if effective is None:
                    continue

                seen_titles.add(key)
                seen_urls.add(link)
                articles.append(
                    RawArticle(
                        title=title,
                        url=link,
                        source=_source_from_entry(entry),
                        published=effective,
                        snippet=snippet[:500],
                        full_text=full_text[:6000],
                        query_topic=topic,
                    )
                )
                count += 1

    articles.sort(key=lambda a: a.published or date.min, reverse=True)
    logger.info(
        "Artículos en periodo %s→%s: %s",
        start.isoformat(),
        end.isoformat(),
        len(articles),
    )
    return articles
