import glob
import os
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, sync_playwright


def _launch(pw) -> Browser | None:
    try:
        return pw.chromium.launch()
    except Exception:
        found = sorted(
            glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
        )
        return pw.chromium.launch(executable_path=found[-1]) if found else None


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as pw:
        b = _launch(pw)
        if b is None:
            pytest.skip("Chromium indisponible")
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    p = browser.new_page(viewport={"width": 1000, "height": 700})
    yield p
    p.close()
