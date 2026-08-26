from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RawArticle(BaseModel):
    title: str
    url: str
    source: str = ""
    published: date | None = None
    published_at: datetime | None = None
    snippet: str = ""
    full_text: str = ""
    query_topic: str = ""


class NoticiaAnalizada(BaseModel):
    titular: str
    fuente: str
    fecha: str
    link: str
    resumen: str = Field(description="Resumen breve de 3-4 líneas")
    comentario: str = Field(default="", description="Comentario analítico / técnico-político")
    riesgos: str = Field(default="", description="Riesgos relevantes para la audiencia")
    oportunidades: str = Field(default="", description="Oportunidades relevantes para la audiencia")
    tema: str = "GENERAL"
    relevancia: int = Field(ge=1, le=10, default=5)

    @model_validator(mode="before")
    @classmethod
    def _compat_comentario(cls, data: Any) -> Any:
        if isinstance(data, dict) and "comentario" not in data and "comentario_pae" in data:
            data = {**data, "comentario": data["comentario_pae"]}
        return data


class SeccionSintesis(BaseModel):
    seccion: str
    analisis: str


class BoletinSemanal(BaseModel):
    periodo_inicio: date
    periodo_fin: date
    generado_el: date
    noticias: list[NoticiaAnalizada]
    sintesis: str
    sintesis_secciones: list[SeccionSintesis] = Field(default_factory=list)
    theme_id: str = "pae"
    theme_title: str = "Boletín semanal"
    theme_label: str = "Boletín"
    sections: list[str] = Field(default_factory=list)
    cadence: str = "weekly"
    output_format: str = "standard"

    @property
    def is_panorama(self) -> bool:
        return (self.output_format or "standard").strip().lower() == "panorama_sectional"

    @property
    def conclusion_title(self) -> str:
        if not self.is_panorama:
            return "Síntesis del periodo"
        start, end = self.periodo_inicio, self.periodo_fin
        months = {
            1: "enero",
            2: "febrero",
            3: "marzo",
            4: "abril",
            5: "mayo",
            6: "junio",
            7: "julio",
            8: "agosto",
            9: "septiembre",
            10: "octubre",
            11: "noviembre",
            12: "diciembre",
        }
        if start.day == 1 and end.day == 15 and start.month == end.month:
            return "Conclusión de la primera quincena"
        if start.day == 1 and start.month == end.month:
            return f"Conclusión del mes de {months[start.month]} de {start.year}"
        return "Conclusión del periodo"
