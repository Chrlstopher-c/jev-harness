# jev-harness
Harnais navigateur piloté par JevK5 : recherche web, actions réelles sur une page, parties d'échecs.
Stack : Python 3.12 (venv uv), Playwright/Chromium, python-chess, httpx, loguru.
Lancement manuel : `./start.sh` (session interactive, variables dans `.env.local`, voir `.env.example`), `./stop.sh`, `./restart.sh`.
En usage normal le lab `jevk5-lab` démarre et arrête la session.
CLI : `.venv/bin/python run.py --brief <id>` ou `--ask "<question>"`. Tests : `.venv/bin/pytest`.
