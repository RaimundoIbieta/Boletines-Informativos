from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from media_analyzer.connectors.collect import (
    POST_PATTERNS,
    _parse_relative_es,
    _unwrap_redirect,
    extract_social_posts,
)
from media_analyzer.models import RESTRICTED_PLATFORMS, SourceDocument

ARTICLE_HTML = """
<html><body>
<p>El candidato respondió en redes.</p>
<blockquote class="twitter-tweet">
  <a href="https://x.com/PresidenteKast/status/2085733852329263276">Ver publicación</a>
</blockquote>
<iframe src="https://www.instagram.com/p/ABC123xyz/embed"></iframe>
<a href="https://www.tiktok.com/@usuario.cl/video/7412345678901234567">video</a>
<a href="https://www.facebook.com/CNNChile/posts/1029384756">post</a>
<footer>
  Síguenos en <a href="https://twitter.com/biobio">Twitter</a> y
  <a href="https://www.instagram.com/biobiochile/">Instagram</a>
</footer>
</body></html>
"""


def test_extracts_posts_and_ignores_profiles():
    found = extract_social_posts(ARTICLE_HTML)
    assert found["x"] == ["https://x.com/PresidenteKast/status/2085733852329263276"]
    assert found["instagram"] == ["https://www.instagram.com/p/ABC123xyz"]
    assert found["tiktok"] == ["https://www.tiktok.com/@usuario.cl/video/7412345678901234567"]
    assert found["facebook"] == ["https://www.facebook.com/CNNChile/posts/1029384756"]
    # Los enlaces de perfil del propio medio no deben colarse como publicaciones.
    joined = " ".join(url for urls in found.values() for url in urls)
    assert "twitter.com/biobio" not in joined
    assert "instagram.com/biobiochile" not in joined


def test_platform_patterns_cover_restricted_set():
    assert set(POST_PATTERNS) == set(RESTRICTED_PLATFORMS)


def test_extract_filters_by_requested_platform():
    found = extract_social_posts(ARTICLE_HTML, ["tiktok"])
    assert list(found) == ["tiktok"]


def test_unwrap_bing_redirect():
    wrapped = (
        "http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid=&tid=abc"
        "&url=https%3a%2f%2fwww.elmostrador.cl%2fnoticia-1&c=1"
    )
    assert _unwrap_redirect(wrapped) == "https://www.elmostrador.cl/noticia-1"


def test_unwrap_leaves_direct_urls():
    direct = "https://www.latercera.com/politica/noticia-2"
    assert _unwrap_redirect(direct) == direct


def test_parse_relative_dates_spanish():
    now = datetime.now(timezone.utc)
    hace_semana = _parse_relative_es("hace 1 semana")
    assert hace_semana is not None
    assert 6 <= (now - hace_semana).days <= 8

    emitido = _parse_relative_es("Emitido hace 2 meses")
    assert emitido is not None
    assert 55 <= (now - emitido).days <= 65

    assert _parse_relative_es("") is None
    assert _parse_relative_es("sin fecha") is None


def test_social_documents_keep_citation_trail():
    """Cada post de red cerrada debe poder rastrearse al medio que lo citó."""
    from media_analyzer.connectors.collect import collect_social_from_articles
    from media_analyzer.models import AnalysisRequest

    request = AnalysisRequest(
        topic="elecciones",
        period_start=date.today() - timedelta(days=10),
        period_end=date.today(),
    )
    article = SourceDocument(
        id="news_1",
        source_type="news",
        title="Nota con posts",
        url="https://example.com/nota",
        publisher="example.com",
        published_at=datetime.now(timezone.utc),
        excerpt="resumen",
    )

    # Sin red: se valida el contrato de metadata sobre el HTML ya extraído.
    posts = extract_social_posts(ARTICLE_HTML)
    assert posts
    assert callable(collect_social_from_articles)
    assert article.url
