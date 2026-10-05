# Banc JevK5 vs decider-2b-vision

Mêmes tâches, mêmes états, mêmes options pour les deux modèles ; chaque tâche est posée dans deux ordres d'options (biais de
position) et les probabilités sont moyennées. Vérité terrain : générée (lecture EN/FR, comparaison, calcul, deux sauts, oui/non),
Stockfish (échecs), rendu connu (images synthétiques), état réel du bureau virtuel (captures).

```
STOCKFISH_JS=<script wasm> python -m bench.make_tasks          # tâches (graine fixe) -> data/tasks.json
LAB_URL=http://<hôte>:<port> python -m bench.capture_desktop    # captures réelles (bureau virtuel démarré)
python -m bench.run_jev [--yesno-choice]                        # JevK5 chargé dans le labo
PYTHONPATH=. <venv doom-agent>/bin/python -m bench.run_decider  # decider-2b-vision, GPU libre
python -m bench.report                                          # -> results/REPORT.md
```
Jev bf16 (8,2 Go) et decider (4,3 Go) ne tiennent pas ensemble sur 12 Go (OOM constaté : Jev demande 7,8 Gio, 6,0 Gio libres
approche decider chargé). Avec JevK5 Q8_0 GGUF (llama-server, ≈4,6 Go) les deux tiennent : 10,3 Go sur 12,3 Go.
```
llama-server -m jevk5-4b-v0.3-Q8_0.gguf --host 127.0.0.1 --port <port> -c 4096 -ngl 99 -np 1
PYTHONPATH=. <venv doom-agent>/bin/python -m bench.run_jev_gguf http://127.0.0.1:<port>
```

## Conclusion (05/10/2026)
- **Raisonnement** : JevK5 nettement devant (comparaison 98 % vs 80 %, deux sauts 100 % vs 82 %, calcul 92 % vs 50 % ; tous écarts
  appariés significatifs). Échecs : perte moyenne 119 cp vs 218 cp (decider au niveau du hasard, 189).
- **Lecture, oui/non** : à égalité (≈100 %). Le type `noul` natif de Jev est défaillant (35,6 %) : poser le oui/non en choix
  yes/no (100 %). `jev.yes_no` du harnais l'applique désormais.
- **Vision** : decider seul ; 100 % sur couleur, mot, position, bureau réel ; comptage 73 % (n=15).
- **Coût** : decider 4,3 Go et 54 ms p50 ; Jev 8,2 Go et 117 ms p50.
- **Choix** : pas de modèle unique. JevK5 = cerveau de décision/raisonnement ; decider-2b-vision = yeux. Le « combo gagnant » à un
  seul modèle est réfuté au niveau 2B (écart de raisonnement trop grand).
- **Cohabitation (testée)** : JevK5 Q8_0 + decider-2b-vision résidents ensemble = 10,3 Go / 12,3 Go. Q8 vs bf16 : aucune perte mesurable
  (calcul 90 % vs 92 %, échecs 117 vs 119 cp, le reste identique), latence p50 127 ms vs 117 ms. **Configuration retenue : Jev Q8 + decider.**
- **Limites** : tâches synthétiques, vision n=15 par catégorie, une seule graine, pas de chaîne de pensée, decider-4b non testé.
