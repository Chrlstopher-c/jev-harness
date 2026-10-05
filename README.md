# jev-harness
Harnais navigateur piloté par JevK5 : recherche web, actions réelles sur une page, parties d'échecs.
Stack : Python 3.12 (venv uv), Playwright/Chromium, python-chess, httpx, loguru.
Lancement manuel : `./start.sh` (session interactive, variables dans `.env.local`, voir `.env.example`), `./stop.sh`, `./restart.sh`.
En usage normal le lab `jevk5-lab` démarre et arrête la session.
CLI : `.venv/bin/python run.py --brief <id>` ou `--ask "<question>"`. Tests : `.venv/bin/pytest`.

## Serveur MCP du bureau virtuel
`jev_harness/desktop_mcp.py` (venv dédié `.venv-mcp`, `requirements-mcp.txt`) : outils `desktop_state`, `desktop_start`, `desktop_stop`,
`desktop_screenshot`, `desktop_do` (plusieurs gestes en un appel). Il passe par le labo (`LAB_URL`, à fournir en variable d'environnement
lors de l'enregistrement : `claude mcp add -s user bureau-virtuel -e LAB_URL=http://<hôte>:<port> -e PYTHONPATH=<projet> -- <projet>/.venv-mcp/bin/python -m jev_harness.desktop_mcp`).

## Bureau virtuel
Un bureau Wayland complet et isolé (sway headless + wayvnc + websockify, D-Bus privé), piloté par `jev_harness/desktop_server.py`
(démarré par le lab). Prérequis : `sway`, `wayvnc`, `grim`, `wtype`, `waybar`, `foot`. Variables : `DESKTOP_PORT`, `DESKTOP_VNC_PORT`,
`DESKTOP_WS_PORT` (voir `.env.example`). Les navigateurs y utilisent un profil dédié (`~/.local/share/jev-desktop/profiles`).
