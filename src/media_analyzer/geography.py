from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from media_analyzer.models import GeoObservation, SourceDocument

DATA = Path(__file__).resolve().parent / "data" / "chile_places.json"


@lru_cache(maxsize=1)
def load_places() -> dict:
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    # Fallback mínimo embebido
    return {
        "regions": [
            {"code": "13", "name": "Metropolitana de Santiago", "aliases": ["rm", "santiago"]},
            {"code": "05", "name": "Valparaíso", "aliases": ["valparaiso"]},
            {"code": "08", "name": "Biobío", "aliases": ["biobio", "concepcion"]},
            {"code": "02", "name": "Antofagasta", "aliases": []},
            {"code": "09", "name": "La Araucanía", "aliases": ["araucania", "temuco"]},
        ],
        "communes": [
            {"code": "13101", "name": "Santiago", "region": "13", "aliases": []},
            {"code": "13114", "name": "Las Condes", "region": "13", "aliases": []},
            {"code": "13123", "name": "Providencia", "region": "13", "aliases": []},
            {"code": "5101", "name": "Valparaíso", "region": "05", "aliases": ["valparaiso"]},
            {"code": "8101", "name": "Concepción", "region": "08", "aliases": ["concepcion"]},
        ],
    }


def _fold(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


def detect_geography(documents: list[SourceDocument]) -> list[GeoObservation]:
    places = load_places()
    observations: list[GeoObservation] = []
    for doc in documents:
        corpus = _fold(f"{doc.title}\n{doc.excerpt}\n{doc.text[:2000]}")
        for commune in places.get("communes", []):
            names = [commune["name"], *commune.get("aliases", [])]
            if any(_fold(n) and _fold(n) in corpus for n in names):
                observations.append(
                    GeoObservation(
                        document_id=doc.id,
                        place=commune["name"],
                        region_code=commune.get("region"),
                        commune_code=commune.get("code"),
                        relation="mentioned_location",
                        confidence=0.7,
                        evidence=commune["name"],
                    )
                )
        for region in places.get("regions", []):
            names = [region["name"], *region.get("aliases", [])]
            if any(_fold(n) and _fold(n) in corpus for n in names):
                observations.append(
                    GeoObservation(
                        document_id=doc.id,
                        place=region["name"],
                        region_code=region.get("code"),
                        relation="mentioned_location",
                        confidence=0.6,
                        evidence=region["name"],
                    )
                )
        if "chile" in corpus:
            observations.append(
                GeoObservation(
                    document_id=doc.id,
                    place="Chile",
                    relation="mentioned_location",
                    confidence=0.5,
                    evidence="Chile",
                )
            )
    return observations


def territory_query_suffix(level: str, label: str) -> str:
    label = (label or "Chile").strip()
    if level == "national":
        return "Chile"
    return f"{label} Chile"
