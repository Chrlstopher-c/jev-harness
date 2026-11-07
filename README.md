# jev-harness
Harnais navigateur piloté par JevK5 : recherche web, actions réelles sur une page, parties d'échecs.
Stack : Python 3.12 (venv uv), Playwright/Chromium, python-chess, httpx, loguru.
Lancement manuel : `./start.sh` (session interactive, variables dans `.env.local`, voir `.env.example`), `./stop.sh`, `./restart.sh`.
En usage normal le lab `jevk5-lab` démarre et arrête la session.
CLI : `.venv/bin/python run.py --brief <id>` ou `--ask "<question>"`. Tests : `.venv/bin/pytest`.

## Banc JevK5 vs decider-2b-vision
Voir `bench/README.md` (méthode, commandes, conclusion).

## Banc d'échecs
`STOCKFISH_JS=<script wasm> .venv/bin/python bench_chess.py` : perte en centipions des coups de Jev, de l'heuristique et du hasard
(positions jouées par Stockfish, IC95 par bootstrap). `BENCH_POSITIONS`, `BENCH_DEPTH`, `BENCH_MODE=random|engine`.

## Bureau virtuel
Déplacé dans le projet autonome `bureau-virtuel` (entrées uinput, MCP `bureau-virtuel`). Le banc de vision
y capture ses images via `BV_URL` (`bench/capture_desktop.py`).

## Exploitation
Le labo démarre/arrête la session (onglet dédié). Journaux : `logs/`.
