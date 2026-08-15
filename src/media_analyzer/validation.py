from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata",
}


def is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_http_url(url: str, *, resolve_dns: bool = True) -> str:
    """Valida URL pública HTTP(S) y bloquea SSRF a redes privadas."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL vacía")
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError("Solo se permiten URLs http/https")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL sin host")
    if host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Host no permitido")
    if parsed.username or parsed.password:
        raise ValueError("URL con credenciales no permitida")
    port = parsed.port
    if port is not None and port not in (80, 443, 8080, 8443):
        raise ValueError("Puerto no permitido")
    if is_private_ip(host):
        raise ValueError("IP privada/local no permitida")
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError(f"No se pudo resolver el host: {host}") from exc
        for info in infos:
            addr = info[4][0]
            if is_private_ip(addr):
                raise ValueError("El host resuelve a una red privada")
    return raw


def month_windows(start, end) -> list[tuple]:
    """Divide un rango largo en ventanas mensuales [start, end] inclusive."""
    from datetime import date
    from calendar import monthrange

    if end < start:
        return []
    windows = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = monthrange(cur.year, cur.month)[1]
        w_start = max(start, cur)
        w_end = min(end, date(cur.year, cur.month, last_day))
        windows.append((w_start, w_end))
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return windows
