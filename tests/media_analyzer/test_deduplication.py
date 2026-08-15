from __future__ import annotations

from media_analyzer.deduplication import cluster_same_story, dedupe_documents
from media_analyzer.models import SourceDocument


def _doc(id_: str, title: str, text: str, url: str = "") -> SourceDocument:
    return SourceDocument(
        id=id_,
        title=title,
        url=url,
        canonical_url=url,
        text=text,
        excerpt=text[:80],
        content_hash="",
        publisher="test",
    )


def test_dedupe_exact_hash():
    a = _doc("1", "Titulo A", "mismo texto exacto")
    b = _doc("2", "Titulo B", "mismo texto exacto")
    kept = dedupe_documents([a, b])
    assert len(kept) == 1


def test_dedupe_same_url():
    a = _doc("1", "Uno", "texto uno", url="https://example.com/a")
    b = _doc("2", "Dos", "texto dos distinto", url="https://example.com/a")
    kept = dedupe_documents([a, b])
    assert len(kept) == 1


def test_cluster_same_story():
    docs = [
        _doc("1", "Kast lidera encuesta nacional Chile", "a"),
        _doc("2", "Kast lidera nueva encuesta nacional", "b"),
        _doc("3", "Clima extremo en Magallanes", "c"),
    ]
    clusters = cluster_same_story(docs)
    assert len(clusters) == 2
    assert max(len(c) for c in clusters) == 2
