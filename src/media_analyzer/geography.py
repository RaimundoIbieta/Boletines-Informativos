from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from media_analyzer.models import (
    AnalysisRequest,
    GeoObservation,
    GeoScopeClassification,
    SourceDocument,
)

DATA = Path(__file__).resolve().parent / "data" / "chile_places.json"

# Países más frecuentes en la conversación en español. Se buscan como palabras
# completas para evitar falsos positivos ("peru" dentro de otra palabra).
COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "Argentina": ("argentina", "argentino", "argentina"),
    "Bolivia": ("bolivia", "boliviano", "boliviana"),
    "Brasil": ("brasil", "brazil", "brasileno", "brasilena"),
    "Colombia": ("colombia", "colombiano", "colombiana"),
    "Ecuador": ("ecuador", "ecuatoriano", "ecuatoriana"),
    "México": ("mexico", "mexicano", "mexicana"),
    "Paraguay": ("paraguay", "paraguayo", "paraguaya"),
    "Perú": ("peru", "peruano", "peruana"),
    "Uruguay": ("uruguay", "uruguayo", "uruguaya"),
    "Venezuela": ("venezuela", "venezolano", "venezolana"),
    "Estados Unidos": (
        "estados unidos",
        "ee uu",
        "eeuu",
        "usa",
        "estadounidense",
        "norteamericano",
        "norteamericana",
    ),
    "Canadá": ("canada", "canadiense"),
    "España": ("espana", "espanol", "espanola"),
    "Francia": ("francia", "frances", "francesa"),
    "Alemania": ("alemania", "aleman", "alemana"),
    "Italia": ("italia", "italiano", "italiana"),
    "Reino Unido": ("reino unido", "britanico", "britanica"),
    "Rusia": ("rusia", "ruso", "rusa"),
    "Ucrania": ("ucrania", "ucraniano", "ucraniana"),
    "China": ("china", "chino", "china"),
    "Japón": ("japon", "japones", "japonesa"),
    "India": ("india", "indio", "india"),
    "Israel": ("israel", "israeli"),
    "Palestina": ("palestina", "palestino", "palestina"),
}

CHILE_ALIASES = ("chile", "chileno", "chilena", "chilenos", "chilenas")
COUNTRY_TLDS = {
    "cl": "Chile",
    "ar": "Argentina",
    "bo": "Bolivia",
    "br": "Brasil",
    "co": "Colombia",
    "ec": "Ecuador",
    "mx": "México",
    "py": "Paraguay",
    "pe": "Perú",
    "uy": "Uruguay",
    "ve": "Venezuela",
    "ca": "Canadá",
    "es": "España",
    "fr": "Francia",
    "de": "Alemania",
    "it": "Italia",
    "uk": "Reino Unido",
    "ru": "Rusia",
    "ua": "Ucrania",
    "jp": "Japón",
}


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


def _contains_alias(corpus: str, alias: str) -> bool:
    """Busca frases o palabras completas, no subcadenas accidentales."""
    folded = _fold(alias).strip()
    if not folded:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(folded)}(?!\w)", corpus))


def _document_corpus(doc: SourceDocument) -> str:
    return _fold(f"{doc.title}\n{doc.excerpt}\n{doc.text[:3000]}")


def _source_country(doc: SourceDocument) -> str:
    """Origen verificable por dominio territorial; .com queda indeterminado."""
    try:
        host = (urlparse(doc.url or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    suffix = host.rsplit(".", 1)[-1] if "." in host else ""
    return COUNTRY_TLDS.get(suffix, "")


def _target_aliases(request: AnalysisRequest) -> tuple[list[str], list[str]]:
    """Aliases del territorio objetivo y nombres del resto de Chile."""
    places = load_places()
    target: list[str] = [request.territory_label]
    national: list[str] = list(CHILE_ALIASES)

    if request.territory_level == "regional":
        for region in places.get("regions", []):
            if region.get("code") == request.region_code:
                target.extend([region["name"], *region.get("aliases", [])])
                break
    elif request.territory_level == "communal":
        for commune in places.get("communes", []):
            if commune.get("code") == request.commune_code:
                target.extend([commune["name"], *commune.get("aliases", [])])
                break

    # En nivel nacional el objetivo es Chile; en nivel subnacional, Chile sin
    # la región/comuna se registra como conversación del resto del país.
    if request.territory_level == "national":
        target.extend(CHILE_ALIASES)
        national = []
    return list(dict.fromkeys(target)), list(dict.fromkeys(national))


def classify_geographic_scope(
    documents: list[SourceDocument], request: AnalysisRequest
) -> list[GeoScopeClassification]:
    """Clasifica estrictamente la geografía sin eliminar piezas extranjeras.

    Una pieza extranjera que trata el tema se conserva como ``international``.
    Si menciona simultáneamente el territorio objetivo y otro país queda como
    ``cross_border``. La ausencia de evidencia se declara ``undetermined`` en
    vez de inferir una ubicación.
    """
    target_aliases, national_aliases = _target_aliases(request)
    results: list[GeoScopeClassification] = []

    for doc in documents:
        corpus = _document_corpus(doc)
        target_hits = [a for a in target_aliases if _contains_alias(corpus, a)]
        national_hits = [a for a in national_aliases if _contains_alias(corpus, a)]
        foreign: list[str] = []
        evidence: list[str] = []
        source_country = _source_country(doc)

        if source_country == "Chile":
            if request.territory_level == "national":
                target_hits.append("fuente .cl")
            else:
                national_hits.append("fuente .cl")
        elif source_country:
            foreign.append(source_country)
            evidence.append(f"fuente .{(urlparse(doc.url).hostname or '').rsplit('.', 1)[-1]}")

        for country, aliases in COUNTRY_ALIASES.items():
            hit = next((a for a in aliases if _contains_alias(corpus, a)), None)
            if hit:
                foreign.append(country)
                evidence.append(hit)

        if target_hits and foreign:
            scope = "cross_border"
            confidence = 0.9
        elif target_hits:
            scope = "target_territory"
            confidence = 0.9
        elif request.territory_level != "national" and national_hits and foreign:
            scope = "cross_border"
            confidence = 0.8
        elif request.territory_level != "national" and national_hits:
            scope = "rest_of_country"
            confidence = 0.8
        elif foreign:
            scope = "international"
            confidence = 0.85
        else:
            scope = "undetermined"
            confidence = 0.0

        classification = GeoScopeClassification(
            document_id=doc.id,
            scope=scope,
            source_country=source_country,
            target_places=list(dict.fromkeys(target_hits)),
            foreign_countries=list(dict.fromkeys(foreign)),
            evidence=list(dict.fromkeys([*target_hits, *national_hits, *evidence]))[:12],
            confidence=confidence,
        )
        doc.metadata = {
            **(doc.metadata or {}),
            "geographic_scope": scope,
            "target_places": classification.target_places,
            "foreign_countries": classification.foreign_countries,
            "source_country": source_country,
            "geographic_confidence": confidence,
        }
        results.append(classification)
    return results


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
