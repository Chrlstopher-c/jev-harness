# STATE
- Recherche : planificateur LLM (rotation Groq/Cerebras), Jev choisit les résultats, réponse ancrée dans le passage.
- Session interactive : Chromium persistant + flux CDP, HUD dans le lab, commandes en langage naturel (`commands.py`).
- Actions réelles (`agent.py`) : 1 appel LLM par tâche, Jev seulement si élément ambigu, confirmations HUD.
- Échecs (05/10) : `play_game` branché ; testé headless avec Jev simulé, pas encore avec le vrai Jev ni via le HUD.
- Jev et le modèle local ne tiennent pas ensemble en VRAM ; ne jamais paralléliser Jev contre lui-même.
