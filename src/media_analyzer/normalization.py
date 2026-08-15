from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


_UTM = re.compile(r"^utm_|^fbclid$|^gclid$|^mc_", re.I)


def normalize_text(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    return t


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlparse(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_items = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _UTM.match(k)
    ]
    query = urlencode(sorted(query_items))
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    return urlunparse((scheme, netloc, path, "", query, ""))


def title_key(title: str) -> str:
    t = normalize_text(title)
    t = re.sub(r"[^a-z0-9áéíóúñü\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()
