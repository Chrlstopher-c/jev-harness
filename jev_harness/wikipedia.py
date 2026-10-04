"""Recherche Wikipédia par l'API (quelques dizaines de ms, sans navigateur)."""
import re
from urllib.parse import quote

import httpx
from loguru import logger

from .browser import Hit
from .events import timed


def search(query: str, lang: str = "fr") -> list[Hit]:
    params = {"action": "query", "list": "search", "srsearch": query, "srlimit": 8, "format": "json"}
    try:
        with timed("browser", "chercher sur Wikipédia (API)"):
            r = httpx.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, timeout=10,
                          headers={"User-Agent": "jev-harness/0.1"})
            r.raise_for_status()
            rows = r.json()["query"]["search"]
    except (httpx.HTTPError, KeyError, ValueError) as err:
        logger.error("Wikipédia en échec: {}", err)
        return []
    return [Hit(x["title"], re.sub(r"<[^>]+>", "", x.get("snippet", "")),
                f"https://{lang}.wikipedia.org/wiki/{quote(x['title'].replace(' ', '_'))}") for x in rows]
