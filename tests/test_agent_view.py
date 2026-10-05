from jev_harness.agent_view import _element_options, rank_elements
from jev_harness.observe import Element, Observation


def _el(i: int, tag: str, name: str, type_: str = "", value: str = "", y: int = 100, disabled: bool = False) -> Element:
    return Element(i, tag, type_, "", name, value, False, disabled, False, 10, y, 50, 20, [], -1)


def _obs(items: list[Element]) -> Observation:
    return Observation(items, "t", "u", 0, 500)


def test_element_kind_and_label() -> None:
    assert _el(1, "input", "", "password").kind == "password"
    assert _el(2, "input", "", "checkbox").kind == "toggle"
    assert _el(3, "select", "").kind == "select"
    assert _el(4, "button", "").label == "button sans nom"


def test_rank_prefers_matching_label_and_skips_disabled() -> None:
    items = [
        _el(1, "button", "Annuler"),
        _el(2, "button", "Envoyer", disabled=True),
        _el(3, "button", "Envoyer le message"),
    ]
    ranked = rank_elements(_obs(items), "Envoyer")
    assert [e.id for e in ranked][0] == 3 and all(e.id != 2 for e in ranked)


def test_rank_wants_empty_field_for_typing() -> None:
    items = [_el(1, "button", "Valider"), _el(2, "input", "Nom", "text")]
    assert rank_elements(_obs(items), "nom", "type")[0].id == 2


def test_options_skip_filled_fields() -> None:
    opts = _element_options([_el(1, "input", "Nom", "text", "deja"), _el(2, "button", "Ok")])
    assert list(opts) == ["click #2 Ok"]


def test_scroll_flags() -> None:
    obs = Observation([], "t", "u", 0, 500)
    assert obs.can_down and not obs.can_up
