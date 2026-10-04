#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f run/session.pid ] || exit 0
pid=$(cat run/session.pid)
kill -TERM "$pid" 2>/dev/null && for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
kill -0 "$pid" 2>/dev/null && kill -KILL "$pid"
rm -f run/session.pid
