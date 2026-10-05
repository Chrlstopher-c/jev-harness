"""Charge `.env.local` du projet dans l'environnement (sans écraser les variables déjà définies)."""

import os
from pathlib import Path

from loguru import logger

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.local"


def load_env() -> None:
    try:
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        logger.warning("pas de {}", ENV_FILE.name)
