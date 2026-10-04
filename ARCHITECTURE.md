# ARCHITECTURE
Un seul package `jev_harness/`, découpé par capacité :
- Recherche : `research.py`, `planner.py`, `answer.py`, `site_report.py`, `wikipedia.py`, `runner.py`, `briefs.py`, `brief_gen.py`.
- Navigateur : `browser.py` (page headless/X11), `display.py` (Xvfb), `session.py` + `session_ws.py` + `hub.py` (session interactive et flux).
- Actions : `observe.py` (éléments numérotés), `actor.py` (gestes réels), `agent.py` + `agent_view.py` (boucle de tâche).
- Échecs : `chess_adapters.py` (lecture/gestes par site), `chess_view.py` (coups candidats annotés), `chess_agent.py` (partie).
- Commandes : `commands.py` (routeur LLM → outils).
- Clients : `jev.py` (JevK5, lecture de probabilités), `llm.py` (cloud), `echohub.py` + `echohub_load.py` (modèle local).
- Transverse : `events.py` (journal en arbre), `env.py`.
Définitions : « client » = appel d'un service externe sans logique métier ; « adaptateur » = lecture/gestes propres à un site.
Frontière : le lab pilote la session par HTTP/WebSocket uniquement ; Jev n'est jamais appelé en parallèle de lui-même.
