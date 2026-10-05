"""Chargement des scripts JavaScript injectés dans les pages (dossier js/)."""

from functools import cache
from pathlib import Path

JS_DIR = Path(__file__).parent / "js"


@cache
def load_js(name: str) -> str:
    return (JS_DIR / f"{name}.js").read_text(encoding="utf-8")
