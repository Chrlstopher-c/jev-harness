from playwright.sync_api import Page

from jev_harness.actor import Actor
from jev_harness.chess_adapters import LocalBoard, detect
from jev_harness.observe import observe

FORM = """<title>Form</title><label for=n>Nom</label><input id=n>
<select id=s><option>un</option><option>deux</option></select>
<button onclick="document.title='clique'">Envoyer</button><input type=password id=p value=secret>
<button style="display:none">Cache</button>"""
BOARD = """<div id=board data-fen="8/8/8/8/8/8/8/K6k w - - 0 1" data-turn=w data-human=w data-status=playing
data-eval="35"><div data-square=e2 style="width:40px;height:40px"></div></div>"""


def test_observe_lists_visible_elements_and_masks_password(page: Page) -> None:
    page.set_content(FORM)
    obs = observe(page)
    names = [e.label for e in obs.items]
    assert "Nom" in names or any(e.kind == "text" for e in obs.items)
    assert "Cache" not in names
    pwd = next(e for e in obs.items if e.kind == "password")
    assert pwd.value == "(rempli)"
    assert next(e for e in obs.items if e.kind == "select").options == ["un", "deux"]


def test_actor_click_reaches_button(page: Page) -> None:
    page.set_content(FORM)
    el = next(e for e in observe(page).items if e.label == "Envoyer")
    Actor(page).click(el.x, el.y, el.w, el.h)
    assert page.title() == "clique"


def test_local_board_adapter_reads_position(page: Page) -> None:
    page.set_content(BOARD)
    adapter = detect(page)
    assert isinstance(adapter, LocalBoard)
    pos = adapter.read()
    assert pos.turn == "w" and pos.mine == "w" and pos.eval_cp == 35
    assert adapter.square_xy("e2") is not None and adapter.square_xy("a9") is None


def test_detect_returns_none_on_ordinary_page(page: Page) -> None:
    page.set_content(FORM)
    assert detect(page) is None
