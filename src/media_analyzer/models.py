from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


SentimentLabel = Literal[
    "muy_negativo",
    "negativo",
    "neutral",
    "mixto",
    "positivo",
    "muy_positivo",
]

TerritoryLevel = Literal["national", "regional", "communal"]
SourceType = Literal[
    "news",
    "youtube",
    "reddit",
    "bluesky",
    "mastodon",
    "x",
    "instagram",
    "facebook",
    "tiktok",
    "indexed",
    "url",
    "file",
    "rss",
]

# Plataformas sin API abierta: se cubren por citas en medios y aportes del usuario.
RESTRICTED_PLATFORMS = ("x", "instagram", "facebook", "tiktok")


class AnalysisRequest(BaseModel):
    id: str | None = None
    user_id: str | None = None
    topic: str
    actors: list[str] = Field(default_factory=list)
    include_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    territory_level: TerritoryLevel = "national"
    region_code: str | None = None
    commune_code: str | None = None
    territory_label: str = "Chile"
    period_start: date
    period_end: date
    enabled_sources: list[str] = Field(
        default_factory=lambda: [
            "news",
            "youtube",
            "reddit",
            "bluesky",
            "mastodon",
            "indexed",
        ]
    )
    urls: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def _topic_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 3:
            raise ValueError("El tema debe tener al menos 3 caracteres.")
        return v

    @field_validator("period_end")
    @classmethod
    def _period_ok(cls, v: date, info) -> date:
        start = info.data.get("period_start")
        if start and v < start:
            raise ValueError("period_end debe ser >= period_start")
        if start and (v - start).days > 730:
            raise ValueError("Periodo máximo: 2 años")
        return v


class EvidenceSpan(BaseModel):
    document_id: str
    quote: str
    url: str = ""
    start: int | None = None
    end: int | None = None


class SourceDocument(BaseModel):
    id: str
    source_type: SourceType = "news"
    title: str = ""
    url: str = ""
    canonical_url: str = ""
    publisher: str = ""
    author: str = ""
    published_at: datetime | None = None
    language: str = "es"
    text: str = ""
    excerpt: str = ""
    content_hash: str = ""
    engagement: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    included: bool = True
    exclusion_reason: str = ""


class SentimentObservation(BaseModel):
    document_id: str
    target: str
    label: SentimentLabel = "neutral"
    score: float = 0.0
    confidence: float = 0.5
    evidence: str = ""
    emotion: str = ""
    irony_likely: bool = False


class GeoObservation(BaseModel):
    document_id: str
    place: str
    region_code: str | None = None
    commune_code: str | None = None
    relation: Literal[
        "event_location", "mentioned_location", "author_location", "outlet_location"
    ] = "mentioned_location"
    confidence: float = 0.5
    evidence: str = ""


class StoryCluster(BaseModel):
    id: str
    title: str
    document_ids: list[str] = Field(default_factory=list)
    primary_document_id: str = ""
    source_diversity: int = 0
    summary: str = ""


class ActorInsight(BaseModel):
    name: str
    mentions: int = 0
    sentiment: dict[str, int] = Field(default_factory=dict)
    average_score: float = 0.0
    sample_quotes: list[str] = Field(default_factory=list)


class NarrativeInsight(BaseModel):
    title: str
    description: str
    polarity: SentimentLabel | str = "neutral"
    document_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class PlatformCoverage(BaseModel):
    """Cómo se obtuvo cada plataforma y con qué límites."""

    platform: str
    label: str
    documents: int = 0
    method: Literal[
        "public_api",
        "public_search",
        "public_timeline",
        "media_citation",
        "user_supplied",
        "unavailable",
    ] = "unavailable"
    note: str = ""


class StanceBreakdown(BaseModel):
    """Conteo de posturas hacia un actor."""

    favorable: int = 0
    critica: int = 0
    neutra: int = 0

    def add(self, stance: str) -> None:
        if stance == "favorable":
            self.favorable += 1
        elif stance == "critica":
            self.critica += 1
        else:
            self.neutra += 1

    @property
    def total(self) -> int:
        return self.favorable + self.critica + self.neutra

    @property
    def opinionated(self) -> int:
        return self.favorable + self.critica

    @property
    def favorable_share(self) -> float:
        """Porcentaje de apoyo entre quienes sí opinan."""
        return round(100 * self.favorable / self.opinionated, 1) if self.opinionated else 0.0

    @property
    def critical_share(self) -> float:
        return round(100 * self.critica / self.opinionated, 1) if self.opinionated else 0.0


class OpinionQuote(BaseModel):
    """Cita textual que respalda una postura."""

    stance: Literal["favorable", "critica", "neutra"]
    intensity: float = 0.0
    text: str
    author: str = ""
    source_type: str = ""
    url: str = ""
    voice: Literal["audience", "media"] = "audience"


# Bajo estos mínimos el resultado es anecdótico y no se presenta como conclusión.
MIN_DUEL_COMPARISONS = 5
MIN_OPINIONATED_MENTIONS = 10


class PreferenceDuel(BaseModel):
    """Resultado de las comparaciones explícitas entre el actor y un rival."""

    actor: str
    rival: str
    actor_votes: int = 0
    rival_votes: int = 0

    @property
    def total(self) -> int:
        return self.actor_votes + self.rival_votes

    @property
    def actor_share(self) -> float:
        return round(100 * self.actor_votes / self.total, 1) if self.total else 0.0

    @property
    def conclusive(self) -> bool:
        """Con pocas comparaciones no se puede declarar un ganador."""
        return self.total >= MIN_DUEL_COMPARISONS

    @property
    def winner(self) -> str:
        if not self.conclusive:
            return "sin evidencia suficiente"
        if self.actor_votes > self.rival_votes:
            return self.actor
        if self.rival_votes > self.actor_votes:
            return self.rival
        return "empate"


class OpinionAnalysis(BaseModel):
    """Qué se dice del actor, separando audiencia de medios."""

    actor: str
    documents_analyzed: int = 0
    audience: StanceBreakdown = Field(default_factory=StanceBreakdown)
    media: StanceBreakdown = Field(default_factory=StanceBreakdown)
    duels: list[PreferenceDuel] = Field(default_factory=list)
    quotes: list[OpinionQuote] = Field(default_factory=list)
    top_reasons: list[str] = Field(default_factory=list)
    classifier: str = "lexicon"

    @property
    def reliable(self) -> bool:
        """Si hay pocas posturas explícitas, los porcentajes no significan nada."""
        return self.combined.opinionated >= MIN_OPINIONATED_MENTIONS

    @property
    def sample_note(self) -> str:
        if self.reliable:
            return ""
        return (
            f"Muestra insuficiente: solo {self.combined.opinionated} menciones con postura "
            f"explícita (mínimo {MIN_OPINIONATED_MENTIONS} para interpretar porcentajes). "
            "Amplía el periodo o agrega fuentes."
        )

    @property
    def bias_note(self) -> str:
        """Advierte cuando el conteo por palabras produce un resultado sospechoso.

        El léxico reconoce los elogios directos mucho mejor que las críticas
        irónicas, así que un resultado unánime suele ser un artefacto del método.
        """
        if self.classifier != "lexicon" or not self.reliable:
            return ""
        combined = self.combined
        if combined.favorable_share >= 90 or combined.critical_share >= 90:
            return (
                "Resultado casi unánime obtenido por conteo de palabras, que no detecta "
                "ironía ni sarcasmo: revisa las citas antes de darlo por bueno."
            )
        return ""

    @property
    def combined(self) -> StanceBreakdown:
        return StanceBreakdown(
            favorable=self.audience.favorable + self.media.favorable,
            critica=self.audience.critica + self.media.critica,
            neutra=self.audience.neutra + self.media.neutra,
        )


class CoverageMetrics(BaseModel):
    documents_discovered: int = 0
    documents_included: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    connector_errors: dict[str, str] = Field(default_factory=dict)
    platforms: list[PlatformCoverage] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    territory: str = "Chile"


class AnalysisReport(BaseModel):
    request_id: str = ""
    topic: str
    territory_label: str = "Chile"
    period_start: date
    period_end: date
    generated_at: datetime
    executive_summary: str = ""
    findings: list[str] = Field(default_factory=list)
    actors: list[ActorInsight] = Field(default_factory=list)
    narratives: list[NarrativeInsight] = Field(default_factory=list)
    trends: list[dict[str, Any]] = Field(default_factory=list)
    sentiment: dict[str, Any] = Field(default_factory=dict)
    opinion: list[OpinionAnalysis] = Field(default_factory=list)
    geography: dict[str, Any] = Field(default_factory=dict)
    clusters: list[StoryCluster] = Field(default_factory=list)
    documents: list[SourceDocument] = Field(default_factory=list)
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    methodology: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    prompt_version: str = "media-v1"
