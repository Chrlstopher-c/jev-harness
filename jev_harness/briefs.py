"""Magasin de briefs (JSON partagé avec le banc d'essai) et briefs de recherche."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

STORE = Path(os.environ.get("JEV_BRIEFS", "data/briefs.json"))
SEED = Path(__file__).with_name("seed_briefs.json")


@dataclass
class Brief:
    goal: str
    queries: list[str]
    answer_type: str = "text"
    intent: str = "encyclopedic"


def load() -> list[dict]:
    path = STORE if STORE.exists() else SEED
    return json.loads(path.read_text())


def get(brief_id: str) -> dict | None:
    return next((b for b in load() if b["id"] == brief_id), None)


def from_goal(goal: str) -> Brief:
    keywords = " ".join(w for w in re.findall(r"\w+", goal) if len(w) > 3)
    queries = [goal] + ([keywords] if keywords and keywords != goal else [])
    return Brief(goal, queries)
