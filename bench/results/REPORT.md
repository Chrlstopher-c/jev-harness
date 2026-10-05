# JevK5 vs decider-2b-vision

Exactitude top-1 (IC95 de Wilson), moyenne des deux ordres d'options. Écart = JevK5 − decider avec IC95 bootstrap, p exact de McNemar (paires discordantes JevK5 seul / decider seul).

| Catégorie | JevK5 | decider-2b-vision | Écart apparié |
|---|---|---|---|
| lecture_en | 100.0% [94.0% ; 100.0%] · n=60 · ECE 0.01 | 100.0% [94.0% ; 100.0%] · n=60 · ECE 0.00 | +0.0% [+0.0% ; +0.0%] · p=1.000 (0/0) |
| lecture_fr | 100.0% [91.2% ; 100.0%] · n=40 · ECE 0.01 | 100.0% [91.2% ; 100.0%] · n=40 · ECE 0.00 | +0.0% [+0.0% ; +0.0%] · p=1.000 (0/0) |
| oui_non_ancre | 35.6% [26.4% ; 45.9%] · n=90 · ECE 0.14 | 98.9% [94.0% ; 99.8%] · n=90 · ECE 0.05 | -63.3% [-73.3% ; -53.3%] · p=0.000 (0/57) |
| oui_non_ancre (Jev posé en choix yes/no) | 100.0% [95.9% ; 100.0%] · n=90 · ECE 0.08 | 98.9% [94.0% ; 99.8%] · n=90 · ECE 0.05 | +1.1% [+0.0% ; +3.3%] · p=1.000 (1/0) |
| raisonnement_calcul | 92.0% [81.2% ; 96.8%] · n=50 · ECE 0.31 | 50.0% [36.6% ; 63.4%] · n=50 · ECE 0.06 | +42.0% [+26.0% ; +58.0%] · p=0.000 (23/2) |
| raisonnement_comparaison | 98.0% [89.5% ; 99.6%] · n=50 · ECE 0.06 | 80.0% [67.0% ; 88.8%] · n=50 · ECE 0.09 | +18.0% [+8.0% ; +30.0%] · p=0.004 (9/0) |
| raisonnement_deux_sauts | 100.0% [92.9% ; 100.0%] · n=50 · ECE 0.09 | 82.0% [69.2% ; 90.2%] · n=50 · ECE 0.11 | +18.0% [+8.0% ; +30.0%] · p=0.004 (9/0) |
| vision_bureau | n/a | 100.0% [80.6% ; 100.0%] · n=16 · ECE 0.07 | — |
| vision_comptage | n/a | 73.3% [48.0% ; 89.1%] · n=15 · ECE 0.19 | — |
| vision_couleur | n/a | 100.0% [79.6% ; 100.0%] · n=15 · ECE 0.00 | — |
| vision_lecture_mot | n/a | 100.0% [79.6% ; 100.0%] · n=15 · ECE 0.00 | — |
| vision_position | n/a | 100.0% [79.6% ; 100.0%] · n=15 · ECE 0.00 | — |

### Échecs (perte en centipions vs meilleur coup Stockfish, plus bas = meilleur)

| Choix | Perte moyenne [IC95] | Gaffes ≥200 cp | Meilleur coup |
|---|---|---|---|
| heuristique (1er candidat) | 85 [54 ; 120] | 14% | 36% |
| hasard (moyenne) | 189 [149 ; 230] | 30% | 12% |
| jevk5 | 119 [77 ; 167] | 22% | 32% |
| decider-2b-vision | 218 [161 ; 282] | 35% | 17% |

Écart apparié de perte (JevK5 − decider) : -99 cp [-165 ; -39] (négatif = JevK5 meilleur).

### Latence et mémoire

| Modèle | p50 (ms/requête) | p95 (ms) | VRAM crête |
|---|---|---|---|
| jevk5 | 117 | 234 | 8 154 Mo (nvidia-smi sur jevk5-serve, 05/10) |
| decider-2b-vision | 54 | 99 | 4299 |
