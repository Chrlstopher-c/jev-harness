"""Tâches texte à vérité terrain: lecture (EN/FR), raisonnement numérique et à deux sauts, oui/non ancré."""

import random

from .common import Task

SYLLABLES = [
    "bre",
    "kos",
    "val",
    "mor",
    "tin",
    "dar",
    "el",
    "quo",
    "san",
    "vi",
    "lo",
    "nex",
    "ar",
    "tul",
    "ha",
    "ro",
    "ze",
    "mi",
]
ATTRS = {
    "tower": {
        "unit": "m",
        "range": (30, 480),
        "en": "{e} is {v} tall.",
        "fr": "{e} mesure {v} de haut.",
        "q_en": "How tall is {e}?",
        "q_fr": "Quelle est la hauteur de {e} ?",
        "noun": "tower",
    },
    "town": {
        "unit": "",
        "range": (800, 90000),
        "en": "{e} has {v} inhabitants.",
        "fr": "{e} compte {v} habitants.",
        "q_en": "How many inhabitants does {e} have?",
        "q_fr": "Combien d'habitants compte {e} ?",
        "noun": "town",
    },
    "item": {
        "unit": "euros",
        "range": (5, 900),
        "en": "{e} costs {v}.",
        "fr": "{e} coûte {v}.",
        "q_en": "How much does {e} cost?",
        "q_fr": "Combien coûte {e} ?",
        "noun": "item",
    },
    "company": {
        "unit": "",
        "range": (1850, 2019),
        "en": "{e} was founded in {v}.",
        "fr": "{e} a été fondée en {v}.",
        "q_en": "When was {e} founded?",
        "q_fr": "En quelle année {e} a-t-elle été fondée ?",
        "noun": "company",
    },
}
SUPERLATIVES = [
    ("tower", "the tallest", max),
    ("tower", "the shortest", min),
    ("item", "the cheapest", min),
    ("item", "the most expensive", max),
    ("company", "the oldest", min),
    ("company", "the most recent", max),
    ("town", "the most populated", max),
    ("town", "the least populated", min),
]


def fake_name(rng: random.Random, used: set[str]) -> str:
    while True:
        name = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3))).capitalize()
        if name not in used:
            used.add(name)
            return name


def _values(rng: random.Random, attr: str, count: int) -> list[int]:
    lo, hi = ATTRS[attr]["range"]
    return rng.sample(range(lo, hi), count)


def _fmt(attr: str, value: int) -> str:
    if attr == "company":
        return str(value)
    unit = ATTRS[attr]["unit"]
    return f"{value:,}".replace(",", " ") + (f" {unit}" if unit else "")


def lookup_task(rng: random.Random, idx: int, lang: str) -> Task:
    attr = rng.choice(list(ATTRS))
    used: set[str] = set()
    names = [fake_name(rng, used) for _ in range(rng.randint(5, 8))]
    vals = _values(rng, attr, len(names))
    spec = ATTRS[attr]
    state = " ".join(spec[lang].format(e=n, v=_fmt(attr, v)) for n, v in zip(names, vals))
    target = rng.randrange(len(names))
    options = [_fmt(attr, v) for v in rng.sample(vals, min(4, len(vals)))]
    gold = _fmt(attr, vals[target])
    if gold not in options:
        options[0] = gold
    rng.shuffle(options)
    return Task(
        f"lookup_{lang}_{idx}",
        f"lecture_{lang}",
        "choice",
        state,
        spec[f"q_{lang}"].format(e=names[target]),
        options,
        options.index(gold),
        meta={"attr": attr},
    )


def superlative_task(rng: random.Random, idx: int) -> Task:
    attr, label, fn = rng.choice(SUPERLATIVES)
    used: set[str] = set()
    names = [fake_name(rng, used) for _ in range(rng.randint(4, 6))]
    vals = _values(rng, attr, len(names))
    state = " ".join(ATTRS[attr]["en"].format(e=n, v=_fmt(attr, v)) for n, v in zip(names, vals))
    best = vals.index(fn(vals))
    options = names[:4] if best < 4 else names[:3] + [names[best]]
    rng.shuffle(options)
    return Task(
        f"superlative_{idx}",
        "raisonnement_comparaison",
        "choice",
        state,
        f"Which {ATTRS[attr]['noun']} is {label}?",
        options,
        options.index(names[best]),
        meta={"attr": attr},
    )


def sum_task(rng: random.Random, idx: int) -> Task:
    used: set[str] = set()
    names = [fake_name(rng, used) for _ in range(4)]
    vals = rng.sample(range(10, 400), 4)
    state = " ".join(ATTRS["item"]["en"].format(e=n, v=_fmt("item", v)) for n, v in zip(names, vals))
    a, b = rng.sample(range(4), 2)
    total = vals[a] + vals[b]
    others = {vals[i] + vals[j] for i in range(4) for j in range(i + 1, 4)} - {total}
    options = [f"{total} euros"] + [f"{v} euros" for v in rng.sample(sorted(others), 3)]
    rng.shuffle(options)
    return Task(
        f"sum_{idx}",
        "raisonnement_calcul",
        "choice",
        state,
        f"How much do {names[a]} and {names[b]} cost together?",
        options,
        options.index(f"{total} euros"),
    )


def two_hop_task(rng: random.Random, idx: int) -> Task:
    used: set[str] = set()
    people = [fake_name(rng, used) for _ in range(4)]
    firms = [fake_name(rng, used) for _ in range(4)]
    cities = [fake_name(rng, used) for _ in range(4)]
    facts = [f"{p} works at {f}." for p, f in zip(people, firms)] + [
        f"{f} is based in {c}." for f, c in zip(firms, cities)
    ]
    rng.shuffle(facts)
    t = rng.randrange(4)
    options = cities[:]
    rng.shuffle(options)
    return Task(
        f"twohop_{idx}",
        "raisonnement_deux_sauts",
        "choice",
        " ".join(facts),
        f"In which city does {people[t]} work?",
        options,
        options.index(cities[t]),
    )


def yesno_task(rng: random.Random, idx: int) -> Task:
    attr = rng.choice(list(ATTRS))
    used: set[str] = set()
    names = [fake_name(rng, used) for _ in range(rng.randint(4, 6))]
    vals = _values(rng, attr, len(names))
    spec = ATTRS[attr]
    state = " ".join(spec["en"].format(e=n, v=_fmt(attr, v)) for n, v in zip(names, vals))
    i, mode = rng.randrange(len(names)), rng.choice(["entailed", "contradicted", "absent"])
    if mode == "entailed":
        claim, gold = spec["en"].format(e=names[i], v=_fmt(attr, vals[i])), 0
    elif mode == "contradicted":
        wrong = rng.choice([v for v in range(*spec["range"]) if v != vals[i]])
        claim, gold = spec["en"].format(e=names[i], v=_fmt(attr, wrong)), 1
    else:
        claim, gold = spec["en"].format(e=fake_name(rng, used), v=_fmt(attr, rng.choice(vals))), 1
    return Task(
        f"yesno_{idx}",
        "oui_non_ancre",
        "yesno",
        state,
        f'Does the text state this? "{claim}"',
        ["yes", "no"],
        gold,
        meta={"mode": mode},
    )


def make_text_tasks(seed: int, counts: dict[str, int]) -> list[Task]:
    rng = random.Random(seed)
    makers = {
        "lecture_en": lambda i: lookup_task(rng, i, "en"),
        "lecture_fr": lambda i: lookup_task(rng, i, "fr"),
        "comparaison": lambda i: superlative_task(rng, i),
        "calcul": lambda i: sum_task(rng, i),
        "deux_sauts": lambda i: two_hop_task(rng, i),
        "oui_non": lambda i: yesno_task(rng, i),
    }
    return [makers[name](i) for name, n in counts.items() for i in range(n)]
