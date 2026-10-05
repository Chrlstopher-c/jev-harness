# STATE
- Recherche : planificateur LLM (rotation Groq/Cerebras), Jev choisit les résultats, réponse ancrée dans le passage.
- Session interactive : Chromium persistant + flux CDP, HUD dans le lab, commandes en langage naturel (`commands.py`).
- Actions réelles (`agent.py`) : 1 appel LLM par tâche, Jev seulement si élément ambigu, confirmations HUD.
- Échecs (05/10) : `play_game` branché ; testé headless avec Jev simulé, pas encore avec le vrai Jev ni via le HUD.
- Jev et le modèle local ne tiennent pas ensemble en VRAM ; ne jamais paralléliser Jev contre lui-même.
- Bureau virtuel V1 (05/10) : sway headless isolé (écran 1600x900), vue noVNC dans le lab, prise de main, lancement d'applis,
  clic/touches/saisie, liste des fenêtres, journal des actions. Serveur MCP `bureau-virtuel` (stdio) enregistré au niveau utilisateur ; pas encore d'agent local `act` dessus.
- Banc d'échecs (05/10, 58 positions, SF prof. 10) : perte moyenne Jev 144 cp [IC95 97–199], heuristique 106 [60–158], hasard 161 [119–206] :
  Jev indistinguable du hasard et pas meilleur que l'heuristique seule ; échantillon à étendre (300+).
- Banc JevK5 vs decider-2b-vision (05/10, `bench/`) : Jev = raisonnement (nettement devant), decider = vision (4,3 Go, 54 ms) ; pas de modèle unique.
  `jev.yes_no` passé en choix yes/no (le type noul natif est défaillant : 35,6 % vs 100 %).
- Cohabitation Jev+decider (05/10) : bf16+bf16 = OOM ; **Jev Q8_0 GGUF (llama-server, 4,6 Go) + decider (4,3 Go) = 10,3 Go sur 12,3, sans perte mesurable** (bench/README.md).
  Reste à brancher : shim /v1/systemone sur llama-server pour le lab/harnais, service « yeux » decider.
- Piège : `/usr/bin/sway` a `cap_sys_nice` → temps réel → SIGKILL en rendu logiciel ; on lance une copie sans capability.
- Piège : Hyprland ne démarre pas en headless pur ici (`CBackend::create() failed`) ; imbriqué il s'ouvre en fenêtre sur le bureau réel.
