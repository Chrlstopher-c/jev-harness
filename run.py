"""CLI: python run.py --brief <id> | python run.py --ask "<demande en langage naturel>" """
import sys

from loguru import logger

from jev_harness import briefs, events
from jev_harness.runner import execute


def resolve(argv: list[str]) -> tuple[str, list[str], str, str]:
    """(demande, requêtes fixes éventuelles, type de réponse) depuis `--brief ID` ou `--ask TEXTE`."""
    if argv[1] == "--brief":
        rec = briefs.get(argv[2])
        if rec is None:
            raise SystemExit(f"brief inconnu: {argv[2]}")
        return rec["request"], list(rec.get("queries", [])), rec.get("answer_type", "text"), rec.get("intent", "encyclopedic")
    return argv[2], [], "text", "encyclopedic"


if __name__ == "__main__":
    logger.add("logs/run.log", mode="w")
    events.reset()
    request, fixed, answer_type, intent = resolve(sys.argv)
    result = execute(request, fixed, answer_type, intent=intent)
    events.archive()
    sys.exit(1 if result is False else 0)
