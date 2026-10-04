"""Observation d'une page: éléments interactifs visibles et non masqués, numérotés, pour qu'un agent choisisse où agir."""
from dataclasses import dataclass

from playwright.sync_api import Page

from .events import timed

MAX_ITEMS = 60
SCRIPT = """() => {
  const SEL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],' +
    '[role=checkbox],[role=radio],[role=option],[role=combobox],[contenteditable=""],[contenteditable=true],[onclick]';
  const out = [], seen = new Set();
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width < 6 || r.height < 6 || s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) === 0) continue;
    if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) continue;
    const cx = Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2)), cy = Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2));
    const top = document.elementFromPoint(cx, cy);
    if (!top || !(el.contains(top) || top.contains(el))) continue;
    const key = Math.round(cx) + ',' + Math.round(cy);
    if (seen.has(key)) continue;
    seen.add(key);
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    const name = (el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText) || el.innerText || el.getAttribute('placeholder') || el.title || el.getAttribute('alt') ||
      (el.querySelector('img') && el.querySelector('img').alt) || (tag === 'select' ? '' : el.value) || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
    const isSel = tag === 'select';
    out.push({ tag, type, role: el.getAttribute('role') || '', name, value: isSel ? ((el.options[el.selectedIndex] || {}).text || '').trim().slice(0, 40) : type === 'password' ? (el.value ? '(rempli)' : '') : (el.value || '').toString().slice(0, 40),
      options: isSel ? Array.from(el.options).slice(0, 40).map(o => o.text.trim().slice(0, 40)) : [],
      selIndex: isSel ? Array.from(document.querySelectorAll('select')).indexOf(el) : -1,
      checked: !!el.checked, disabled: !!el.disabled, focused: document.activeElement === el,
      x: Math.round(cx), y: Math.round(cy), w: Math.round(r.width), h: Math.round(r.height) });
    if (out.length >= %d) break;
  }
  const max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
  return { items: out, title: document.title, url: location.href, scrollY: Math.round(scrollY), scrollMax: Math.round(max),
           w: innerWidth, h: innerHeight };
}""" % MAX_ITEMS


@dataclass
class Element:
    id: int
    tag: str
    type: str
    role: str
    name: str
    value: str
    checked: bool
    disabled: bool
    focused: bool
    x: int
    y: int
    w: int
    h: int
    options: list[str]
    sel_index: int
    frame: int = 0

    @property
    def kind(self) -> str:
        if self.tag == "textarea" or (self.tag == "input" and self.type in ("", "text", "search", "email", "url", "tel", "number", "password")):
            return "password" if self.type == "password" else "text"
        if self.tag == "input" and self.type in ("checkbox", "radio") or self.role in ("checkbox", "radio"):
            return "toggle"
        if self.tag == "select":
            return "select"
        return "click"

    @property
    def label(self) -> str:
        return self.name or self.value or f"{self.tag} sans nom"


@dataclass
class Observation:
    items: list[Element]
    title: str
    url: str
    scroll_y: int
    scroll_max: int

    @property
    def signature(self) -> str:
        return f"{self.url}|{self.scroll_y}|" + ";".join(f"{e.name}:{e.value}" for e in self.items[:25])

    @property
    def can_down(self) -> bool:
        return self.scroll_y < self.scroll_max - 4

    @property
    def can_up(self) -> bool:
        return self.scroll_y > 4


FRAME_LIMIT = 6
MIN_FRAME_W, MIN_FRAME_H = 80, 40
FIELDS = ("tag", "type", "role", "name", "value", "checked", "disabled", "focused", "x", "y", "w", "h", "options", "selIndex")


def _frame_items(page: Page, raw_main: dict) -> list[dict]:
    """Éléments de la page puis des cadres intégrés visibles, en coordonnées de la page principale."""
    out = [{**it, "frame": 0} for it in raw_main["items"]]
    vw, vh = raw_main["w"], raw_main["h"]
    for idx, fr in enumerate(page.frames[1:], start=1):
        if idx > FRAME_LIMIT:
            break
        try:
            box = fr.frame_element().bounding_box()
            if not box or box["width"] < MIN_FRAME_W or box["height"] < MIN_FRAME_H or box["y"] > vh or box["y"] + box["height"] < 0:
                continue
            for it in fr.evaluate(SCRIPT)["items"]:
                x, y = it["x"] + round(box["x"]), it["y"] + round(box["y"])
                if 0 <= x < vw and 0 <= y < vh:
                    out.append({**it, "x": x, "y": y, "frame": idx})
        except Exception:
            continue
    return out


def observe(page: Page) -> Observation:
    with timed("browser", "observer la page"):
        raw = page.evaluate(SCRIPT)
        items = _frame_items(page, raw)
    elements = [Element(i + 1, tag=it["tag"], type=it["type"], role=it["role"], name=it["name"], value=it["value"],
                        checked=it["checked"], disabled=it["disabled"], focused=it["focused"], x=it["x"], y=it["y"],
                        w=it["w"], h=it["h"], options=it["options"], sel_index=it["selIndex"], frame=it["frame"])
                for i, it in enumerate(items)]
    return Observation(elements, raw["title"], raw["url"], raw["scrollY"], raw["scrollMax"])
