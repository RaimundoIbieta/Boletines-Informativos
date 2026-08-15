from __future__ import annotations

from media_analyzer.connectors.collect import parse_reddit_comment_feed
from media_analyzer.models import SourceDocument
from media_analyzer.opinion import (
    build_opinion_analysis,
    classify_stance,
    detect_preference,
    is_media_voice,
    mentions_actor,
)


def _doc(text: str, *, source_type="reddit", author="usuario", publisher="Reddit", **kw):
    return SourceDocument(
        id=f"d{abs(hash(text)) % 10**8}",
        source_type=source_type,
        title=text[:80],
        url="https://example.com/1",
        publisher=publisher,
        author=author,
        text=text,
        excerpt=text[:200],
        **kw,
    )


class TestStance:
    def test_favorable(self):
        stance, intensity, _ = classify_stance(
            "Cristiano Ronaldo es una leyenda, el mejor de la historia", "Cristiano Ronaldo"
        )
        assert stance == "favorable"
        assert intensity > 0

    def test_critical(self):
        stance, _, reason = classify_stance(
            "Cristiano Ronaldo está sobrevalorado y es un egoísta", "Cristiano Ronaldo"
        )
        assert stance == "critica"
        assert reason in {"sobrevalorado", "egoísta", "egoista"}

    def test_neutral(self):
        stance, _, _ = classify_stance(
            "Cristiano Ronaldo jugará el próximo partido en Riad", "Cristiano Ronaldo"
        )
        assert stance == "neutra"

    def test_negation_inverts(self):
        """«no es el mejor» no puede contarse como apoyo."""
        stance, _, _ = classify_stance(
            "Ronaldo no es el mejor, nunca lo fue", "Ronaldo"
        )
        assert stance == "critica"

    def test_english_lexicon(self):
        stance, _, _ = classify_stance("Ronaldo is the GOAT, absolute legend", "Ronaldo")
        assert stance == "favorable"
        stance, _, _ = classify_stance("Ronaldo is overrated, what a clown", "Ronaldo")
        assert stance == "critica"


class TestPreference:
    def test_actor_wins_spanish(self):
        assert (
            detect_preference("Cristiano es mejor que Messi", "Cristiano Ronaldo", "Messi")
            == "Cristiano Ronaldo"
        )

    def test_rival_wins_spanish(self):
        assert (
            detect_preference("Messi es mejor que Cristiano", "Cristiano Ronaldo", "Messi")
            == "Messi"
        )

    def test_english_better_than(self):
        assert (
            detect_preference("Ronaldo is way better than Messi", "Ronaldo", "Messi")
            == "Ronaldo"
        )

    def test_greater_sign(self):
        assert detect_preference("messi > ronaldo", "Ronaldo", "Messi") == "Messi"

    def test_prefer_pattern(self):
        assert (
            detect_preference("prefiero a Ronaldo antes que Messi", "Ronaldo", "Messi")
            == "Ronaldo"
        )

    def test_no_comparison_returns_none(self):
        assert detect_preference("Ronaldo marcó dos goles", "Ronaldo", "Messi") is None

    def test_requires_both_names(self):
        assert detect_preference("Ronaldo es mejor que nadie", "Ronaldo", "Messi") is None


class TestMediaVoice:
    def test_news_is_media(self):
        assert is_media_voice(_doc("titular", source_type="news", publisher="La Tercera"))

    def test_media_account_on_social(self):
        assert is_media_voice(
            _doc("nota", source_type="bluesky", author="cuatrotv.bsky.social")
        )

    def test_person_is_audience(self):
        assert not is_media_voice(_doc("opino que...", author="carlitos88"))


def test_document_text_does_not_duplicate_title():
    from media_analyzer.opinion import document_text

    doc = _doc("Ronaldo es una leyenda absoluta")
    assert document_text(doc).count("leyenda") == 1


def test_mentions_actor_by_surname():
    assert mentions_actor("Ronaldo fue clave hoy", "Cristiano Ronaldo")
    assert not mentions_actor("Messi fue clave hoy", "Cristiano Ronaldo")


class TestOpinionAnalysis:
    def test_separates_audience_from_media(self):
        docs = [
            _doc("Cristiano Ronaldo es una leyenda y un crack", author="fan1"),
            _doc("Cristiano Ronaldo está sobrevalorado", author="critico1"),
            _doc(
                "Cristiano Ronaldo envía mensaje a Messi",
                source_type="news",
                publisher="ESPN",
            ),
        ]
        analysis = build_opinion_analysis(docs, "Cristiano Ronaldo", rivals=["Messi"])
        assert analysis.documents_analyzed == 3
        assert analysis.audience.favorable == 1
        assert analysis.audience.critica == 1
        assert analysis.media.total == 1

    def test_duel_counts_and_winner(self):
        docs = [
            _doc(f"Cristiano es mejor que Messi, razón {i}", author=f"fan{i}")
            for i in range(4)
        ] + [_doc("Messi es mejor que Cristiano", author="c")]
        analysis = build_opinion_analysis(docs, "Cristiano Ronaldo", rivals=["Messi"])
        duel = analysis.duels[0]
        assert duel.actor_votes == 4
        assert duel.rival_votes == 1
        assert duel.conclusive
        assert duel.winner == "Cristiano Ronaldo"
        assert duel.actor_share == 80.0

    def test_duel_below_threshold_is_inconclusive(self):
        """Con una sola comparación no se puede declarar un ganador."""
        docs = [_doc("Messi es mejor que Cristiano", author="c")]
        analysis = build_opinion_analysis(docs, "Cristiano Ronaldo", rivals=["Messi"])
        duel = analysis.duels[0]
        assert duel.total == 1
        assert not duel.conclusive
        assert duel.winner == "sin evidencia suficiente"

    def test_small_sample_is_flagged_unreliable(self):
        docs = [_doc("Ronaldo es un crack", author="a")]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert not analysis.reliable
        assert "Muestra insuficiente" in analysis.sample_note

    def test_unanimous_lexicon_result_is_flagged(self):
        """100% a favor por conteo de palabras merece una advertencia."""
        docs = [_doc(f"Ronaldo es un crack absoluto {i}", author=f"a{i}") for i in range(12)]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert analysis.classifier == "lexicon"
        assert "ironía" in analysis.bias_note

    def test_balanced_result_has_no_bias_note(self):
        docs = [_doc(f"Ronaldo es un crack {i}", author=f"a{i}") for i in range(6)] + [
            _doc(f"Ronaldo está sobrevalorado {i}", author=f"b{i}") for i in range(6)
        ]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert analysis.bias_note == ""

    def test_large_sample_is_reliable(self):
        docs = [_doc(f"Ronaldo es un crack número {i}", author=f"a{i}") for i in range(12)]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert analysis.reliable
        assert analysis.sample_note == ""

    def test_shares_use_only_opinionated(self):
        docs = [
            _doc("Ronaldo es un crack", author="a"),
            _doc("Ronaldo jugará mañana en Riad", author="b"),
        ]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert analysis.audience.favorable_share == 100.0
        assert analysis.audience.total == 2
        assert analysis.audience.opinionated == 1

    def test_ignores_documents_without_actor(self):
        docs = [_doc("Messi ganó el premio", author="a")]
        analysis = build_opinion_analysis(docs, "Cristiano Ronaldo")
        assert analysis.documents_analyzed == 0

    def test_quotes_have_evidence(self):
        docs = [_doc("Ronaldo es una leyenda absoluta", author="fan")]
        analysis = build_opinion_analysis(docs, "Ronaldo")
        assert analysis.quotes
        quote = analysis.quotes[0]
        assert quote.stance == "favorable"
        assert "leyenda" in quote.text
        assert quote.voice == "audience"


def test_parse_reddit_comment_feed():
    xml = """<feed>
      <entry><name>/u/AutoModerator</name>
        <content type="html">&lt;p&gt;bot&lt;/p&gt;</content>
        <link href="https://reddit.com/a"/><updated>2026-08-01T10:00:00+00:00</updated></entry>
      <entry><name>/u/fan99</name>
        <content type="html">&lt;p&gt;Ronaldo is the &lt;b&gt;GOAT&lt;/b&gt;&lt;/p&gt;</content>
        <link href="https://reddit.com/b"/><updated>2026-08-02T10:00:00+00:00</updated></entry>
    </feed>"""
    comments = parse_reddit_comment_feed(xml)
    assert len(comments) == 2
    assert comments[1]["author"] == "/u/fan99"
    assert comments[1]["text"] == "Ronaldo is the GOAT"
    assert "<" not in comments[1]["text"]
