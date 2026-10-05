# STATE
- Recherche : planificateur LLM (rotation Groq/Cerebras), Jev choisit les résultats, réponse ancrée dans le passage.
- Session interactive : Chromium persistant + flux CDP, HUD dans le lab, commandes en langage naturel (`commands.py`).
- Actions réelles (`agent.py`) : 1 appel LLM par tâche, Jev seulement si élément ambigu, confirmations HUD.
- Échecs (05/10) : `play_game` branché ; testé headless avec Jev simulé, pas encore avec le vrai Jev ni via le HUD.
- Jev et le modèle local ne tiennent pas ensemble en VRAM ; ne jamais paralléliser Jev contre lui-même.
- Bureau virtuel V1 (05/10) : sway headless isolé (écran 1600x900), vue noVNC dans le lab, prise de main, lancement d'applis,
  clic/touches/saisie, liste des fenêtres, journal des actions. Serveur MCP `bureau-virtuel` (stdio) enregistré au niveau utilisateur ; pas encore d'agent local `act` dessus.
- Piège : `/usr/bin/sway` a `cap_sys_nice` → temps réel → SIGKILL en rendu logiciel ; on lance une copie sans capability.
- Piège : Hyprland ne démarre pas en headless pur ici (`CBackend::create() failed`) ; imbriqué il s'ouvre en fenêtre sur le bureau réel.
