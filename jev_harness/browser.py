"""Outils navigateur (Playwright headless): recherche, lecture de page. Aucune décision ici."""
import base64
import glob
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, urlparse

from loguru import logger

from .display import SIZE, VirtualScreen
from playwright.sync_api import Page, sync_playwright

from .events import LIVE_DIR, timed

STABLE_MAX_S = 2.0
STABLE_STEP_MS = 150
MIN_TEXT_LEN = 200


def _unwrap_bing(href: str) -> str:
    u = parse_qs(urlparse(href).query).get("u", [""])[0]
    if not u.startswith("a1"):
        return href
    raw = u[2:] + "=" * (-len(u[2:]) % 4)
    return base64.urlsafe_b64decode(raw).decode("utf-8", "replace")


@dataclass
class Hit:
    title: str
    snippet: str
    url: str


def _chrome_paths() -> tuple[str | None, str | None]:
    full = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    shell = sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")))
    return (full[-1] if full else None), (shell[-1] if shell else None)


def _x11_env(display: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "XDG_SESSION_TYPE")}
    env["DISPLAY"] = display
    return env


class Browser:
    def __init__(self, grab: bool = True, profile: str | None = None) -> None:
        self._grab = grab
        self._profile = profile

    def __enter__(self) -> "Browser":
        with timed("startup", "démarrer le navigateur"):
            self._start()
        return self

    def _start(self) -> None:
        self.screen = VirtualScreen()
        virtual = self.screen.start(self._grab)
        full, shell = _chrome_paths()
        self._pw = sync_playwright().start()
        if virtual and full:
            self._launch_window(full)
        else:
            self.screen.stop()
            virtual = False
            self._launch_headless(os.environ.get("CHROMIUM_PATH") or shell)
        self.virtual = virtual

    def _launch_window(self, exe: str) -> None:
        env = _x11_env(self.screen.display or "")
        args = ["--ozone-platform=x11", f"--window-size={SIZE[0]},{SIZE[1]}", "--window-position=0,0"]
        if self._profile:
            ctx = self._pw.chromium.launch_persistent_context(
                self._profile, headless=False, executable_path=exe, env=env, viewport=None, locale="fr-FR",
                args=args + ["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"])
            self._b = ctx
            self.page: Page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            self._b = self._pw.chromium.launch(headless=False, executable_path=exe, env=env, args=args)
            ctx = self._b.new_context(viewport=None, locale="fr-FR")
            self.page = ctx.new_page()
        self._fit_window(ctx)

    def _launch_headless(self, exe: str | None) -> None:
        if self._profile:
            self._b = self._pw.chromium.launch_persistent_context(self._profile, headless=True, executable_path=exe,
                                                                  locale="fr-FR")
            self.page = self._b.pages[0] if self._b.pages else self._b.new_page()
        else:
            self._b = self._pw.chromium.launch(headless=True, executable_path=exe)
            self.page = self._b.new_page(locale="fr-FR")

    def _fit_window(self, ctx: object) -> None:
        try:
            cdp = ctx.new_cdp_session(self.page)  # type: ignore[attr-defined]
            wid = cdp.send("Browser.getWindowForTarget")["windowId"]
            cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                "left": 0, "top": 0, "width": SIZE[0], "height": SIZE[1], "windowState": "normal"}})
        except Exception as err:
            logger.warning("ajustement de la fenêtre impossible: {}", err)

    def __exit__(self, *_: object) -> None:
        with timed("startup", "arrêter le navigateur"):
            self.screen.stop_grab()
            self._b.close()
            self._pw.stop()
            self.screen.stop()

    def open(self, url: str, wait: str = "domcontentloaded") -> None:
        logger.info("open {}", url)
        with timed("browser", f"ouvrir {urlparse(url).netloc}"):
            try:
                self.page.goto(url, wait_until=wait, timeout=30000)
                if not self.virtual:
                    self.page.screenshot(path=str(LIVE_DIR / "frame.jpg"), type="jpeg", quality=60)
            except Exception as err:
                logger.error("navigation échouée {}: {}", url, err)
                raise

    def bing_search(self, query: str) -> list[Hit]:
        self.open(f"https://www.bing.com/search?q={quote_plus(query)}&setlang=fr", wait="commit")
        try:
            with timed("browser", "attendre les résultats Bing"):
                self.page.wait_for_selector("li.b_algo", timeout=6000)
        except Exception:
            logger.warning("Bing: aucun résultat affiché")
            return []
        hits: list[Hit] = []
        with timed("browser", "lire les résultats Bing"):
            for el in self.page.query_selector_all("li.b_algo")[:8]:
                a = el.query_selector("h2 a")
                sn = el.query_selector(".b_caption p")
                if a:
                    hits.append(Hit((a.text_content() or "").strip(), (sn.text_content() if sn else "") or "",
                                    _unwrap_bing(a.get_attribute("href") or "")))
        return hits

    def links(self) -> list[tuple[str, str]]:
        with timed("browser", "lister les liens de la page"):
            raw = self.page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => "
                "[(a.innerText || a.getAttribute('aria-label') || a.title || '').trim().slice(0, 80), a.href])")
        return [(t, h) for t, h in raw if h.startswith("http")]

    def _wait_stable(self) -> None:
        deadline = time.perf_counter() + STABLE_MAX_S
        prev, same = -1, 0
        while time.perf_counter() < deadline:
            try:
                n = self.page.evaluate("document.body ? document.body.innerText.length : 0")
            except Exception:
                n = -1
            same = same + 1 if n == prev and n > MIN_TEXT_LEN else 0
            if same >= 2:
                return
            prev = n
            self.page.wait_for_timeout(STABLE_STEP_MS)

    def text(self) -> str:
        with timed("browser", "lire la page"):
            self._wait_stable()
            try:
                return self.page.inner_text("body")
            except Exception as err:
                logger.error("lecture de la page échouée: {}", err)
                return ""

    def passages(self, size: int = 600) -> list[str]:
        lines = [x.strip() for x in self.text().splitlines() if x.strip()]
        out: list[str] = []
        cur: list[str] = []
        for line in lines:
            if cur and sum(len(x) + 1 for x in cur) + len(line) > size:
                out.append("\n".join(cur))
                cur = cur[-1:]
            cur.append(line[:size])
        return out + (["\n".join(cur)] if cur else [])
