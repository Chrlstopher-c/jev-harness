import pytest

from jev_harness import answer, jev, research


def test_values_keep_units_and_order() -> None:
    assert answer._values("de 112 000 € à 389 900 €, soit 2,221 € le litre") == ["112 000 €", "389 900 €", "2,221 €"]


def test_values_dedupe() -> None:
    assert answer._values("42 puis 42") == ["42"]


def test_rank_prefers_goal_terms_and_numbers() -> None:
    passages = ["Une histoire sans rapport.", "La hauteur de la tour est de 330 m.", "La tour est belle."]
    assert research.rank("quelle est la hauteur de la tour", passages)[0].startswith("La hauteur")


def test_formulate_without_sentences_returns_passage() -> None:
    out = answer.formulate("question", "")
    assert out.value is None


def test_formulate_uses_jev_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_choose(state: str, instructions: str, options: list[str]) -> jev.Decision:
        calls.append(options)
        return jev.Decision(options[0], 0.9, {o: 1 / len(options) for o in options}, 0.0)

    monkeypatch.setattr(jev, "choose", fake_choose)
    out = answer.formulate("quelle est la hauteur de la tour", "La tour mesure 330 m de hauteur. Elle est à Paris.")
    assert out.value == "330 m" and calls
