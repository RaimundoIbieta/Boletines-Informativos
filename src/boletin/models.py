from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RawArticle(BaseModel):
    title: str
    url: str
    source: str = ""
    published: date | None = None
    snippet: str = ""
    full_text: str = ""
    query_topic: str = ""


class NoticiaAnalizada(BaseModel):
    titular: str
    fuente: str
    fecha: str
    link: str
    resumen: str = Field(description="Resumen breve de 3-4 líneas")
    comentario: str = Field(description="Comentario analítico / técnico-político")
    riesgos: str = Field(description="Riesgos relevantes para la audiencia")
    oportunidades: str = Field(description="Oportunidades relevantes para la audiencia")
    tema: str = "GENERAL"
    relevancia: int = Field(ge=1, le=10, default=5)

    @model_validator(mode="before")
    @classmethod
    def _compat_comentario(cls, data: Any) -> Any:
        if isinstance(data, dict) and "comentario" not in data and "comentario_pae" in data:
            data = {**data, "comentario": data["comentario_pae"]}
        return data


class BoletinSemanal(BaseModel):
    periodo_inicio: date
    periodo_fin: date
    generado_el: date
    noticias: list[NoticiaAnalizada]
    sintesis: str
    theme_id: str = "pae"
    theme_title: str = "Boletín semanal"
    theme_label: str = "Boletín"
