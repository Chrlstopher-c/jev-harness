#!/usr/bin/env bash
# Lance la session navigateur interactif (normalement pilotée par le lab; ce script sert au lancement manuel).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs run
[ -f run/session.pid ] && kill -0 "$(cat run/session.pid)" 2>/dev/null && { echo "déjà lancée"; exit 0; }
[ -d .venv ] || { uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt; }
set -a; [ -f .env.local ] && . ./.env.local; set +a
: > logs/session.log
nohup .venv/bin/python -m jev_harness.session >> logs/session.log 2>&1 &
echo $! > run/session.pid
echo "session lancée (pid $(cat run/session.pid)), port ${SESSION_PORT:-?}"
