from __future__ import annotations

from media_analyzer.models import SourceDocument
from media_analyzer.normalization import content_hash, title_key


def dedupe_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    """Elimina duplicados exactos (hash) y casi-duplicados por URL/título."""
    kept: list[SourceDocument] = []
    seen_hash: set[str] = set()
    seen_url: set[str] = set()
    seen_title: set[str] = set()

    for doc in documents:
        if not doc.included:
            continue
        h = doc.content_hash or content_hash(doc.text or doc.excerpt or doc.title)
        doc.content_hash = h
        url = (doc.canonical_url or doc.url or "").lower()
        tk = title_key(doc.title)
        if h and h in seen_hash:
            continue
        if url and url in seen_url:
            continue
        if tk and len(tk) > 20 and tk in seen_title:
            continue
        if h:
            seen_hash.add(h)
        if url:
            seen_url.add(url)
        if tk:
            seen_title.add(tk)
        kept.append(doc)
    return kept


def cluster_same_story(documents: list[SourceDocument]) -> list[list[SourceDocument]]:
    """Agrupación simple por solapamiento de tokens del título."""
    import re
    import unicodedata

    def fold(t: str) -> set[str]:
        x = unicodedata.normalize("NFD", t or "")
        x = "".join(c for c in x if unicodedata.category(c) != "Mn").lower()
        return {w for w in re.findall(r"[a-z0-9]{4,}", x)}

    clusters: list[list[SourceDocument]] = []
    for doc in documents:
        tokens = fold(doc.title)
        placed = False
        for cluster in clusters:
            base = fold(cluster[0].title)
            inter = tokens & base
            if len(inter) >= 3 or (len(inter) / max(1, len(tokens | base)) >= 0.4):
                cluster.append(doc)
                placed = True
                break
        if not placed:
            clusters.append([doc])
    return clusters
