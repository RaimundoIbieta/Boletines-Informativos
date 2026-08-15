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
    "indexed",
    "url",
    "file",
    "rss",
]


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


class CoverageMetrics(BaseModel):
    documents_discovered: int = 0
    documents_included: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    connector_errors: dict[str, str] = Field(default_factory=dict)
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
    geography: dict[str, Any] = Field(default_factory=dict)
    clusters: list[StoryCluster] = Field(default_factory=list)
    documents: list[SourceDocument] = Field(default_factory=list)
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    methodology: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    prompt_version: str = "media-v1"
