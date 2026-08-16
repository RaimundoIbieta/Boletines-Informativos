from __future__ import annotations

from media_analyzer.models import SourceDocument
from media_analyzer.relevance import (
    filter_relevant,
    is_relevant,
    normalize,
    significant_terms,
)


def _doc(title: str, text: str = "") -> SourceDocument:
    return SourceDocument(
        id=f"d{abs(hash(title)) % 10**8}",
        source_type="reddit",
        title=title,
        url="https://example.com/x",
        publisher="Reddit",
        text=text or title,
        excerpt=(text or title)[:200],
    )


class TestNormalize:
    def test_strips_accents_and_case(self):
        assert normalize("Reforma de Pensión") == "reforma de pension"

    def test_handles_empty(self):
        assert normalize("") == ""


class TestSignificantTerms:
    def test_drops_stopwords_and_short_words(self):
        assert significant_terms("reforma de pensiones en Chile") == [
            "reforma",
            "pensiones",
        ]

    def test_single_word_topic(self):
        assert significant_terms("Codelco") == ["codelco"]


class TestIsRelevant:
    def test_exact_phrase_matches(self):
        assert is_relevant("Avanza la reforma de pensiones", "reforma de pensiones")

    def test_accent_insensitive(self):
        assert is_relevant("La REFORMA DE PENSIÓN avanza", "reforma de pension")

    def test_two_key_terms_scattered(self):
        assert is_relevant(
            "La reforma que discute el Congreso sobre pensiones", "reforma de pensiones"
        )

    def test_single_term_is_not_enough_for_multiword_topic(self):
        """«reforma tributaria» no es «reforma de pensiones»."""
        assert not is_relevant("Avanza la reforma tributaria", "reforma de pensiones")

    def test_unrelated_post_is_rejected(self):
        assert not is_relevant("Busco amistad, o hablar un rato", "reforma de pensiones")
        assert not is_relevant("Dep. Limache 1 - 3 Universidad de Chile", "reforma de pensiones")

    def test_actor_mention_makes_it_relevant(self):
        assert is_relevant(
            "Kast respondió en el debate de anoche",
            "elecciones presidenciales",
            actors=["Kast"],
        )

    def test_single_word_topic_requires_that_word(self):
        assert is_relevant("Codelco reporta pérdidas", "Codelco")
        assert not is_relevant("Enap reporta pérdidas", "Codelco")

    def test_empty_text_is_not_relevant(self):
        assert not is_relevant("", "reforma de pensiones")

    def test_topic_of_only_stopwords_keeps_everything(self):
        """Sin términos útiles no se puede filtrar; mejor no descartar nada."""
        assert is_relevant("cualquier cosa", "de la")


class TestFilterRelevant:
    def test_splits_and_marks_dropped(self):
        docs = [
            _doc("Avanza la reforma de pensiones en el Senado"),
            _doc("Busco amistad, o hablar un rato"),
            _doc("El debate sobre pensiones y la reforma sigue"),
        ]
        kept, dropped = filter_relevant(docs, "reforma de pensiones")
        assert len(kept) == 2
        assert len(dropped) == 1
        assert dropped[0].included is False
        assert dropped[0].exclusion_reason == "off_topic"

    def test_keeps_everything_when_all_match(self):
        docs = [_doc("reforma de pensiones hoy"), _doc("pensiones: la reforma avanza")]
        kept, dropped = filter_relevant(docs, "reforma de pensiones")
        assert len(kept) == 2
        assert dropped == []

    def test_uses_body_when_title_is_generic(self):
        docs = [_doc("Nota del día", "El texto discute la reforma de pensiones en detalle")]
        kept, _ = filter_relevant(docs, "reforma de pensiones")
        assert len(kept) == 1
