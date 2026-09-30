# La pandémie de 2020 dans les prévisions du FMI, comparée à 2008

La chute du PIB de 2020 avait-elle été prévue ? Et le rebond de 2021 ? Même lecture que
pour la crise de 2008 (`docs/cas_crise_2008.md`), faite par le même module.

Reproduire : `python -m pib.cas_de_crise --annee 2020`. Les tableaux sont écrits dans
`data/processed/weo_cas_2020_*.csv`.

- **Croissance réalisée :** ré-estimation du FMI un an après.
- **Niveaux réalisés :** estimation actuelle, tirée de l'édition d'avril 2026 archivée ; base 100 en 2018.
- **Édition d'avril 2020 :** parue en plein confinement, elle ne projetait que 2020 et 2021. Ses niveaux au-delà restent vides.

## 1. La chute n'a pas été vue avant l'année, mais bien mesurée dès avril

| Croissance 2020 (%) | Avril 2019 | Octobre 2019 | Avril 2020 | Octobre 2020 | Réalisé |
|---|---|---|---|---|---|
| Monde | +3,6 | +3,4 | −3,0 | −4,4 | −3,1 |
| Économies avancées | +1,7 | +1,7 | −6,1 | −5,8 | −4,5 |
| Économies émergentes et en développement | +4,8 | +4,6 | −1,0 | −3,3 | −2,1 |
| États-Unis | +1,9 | +2,1 | −5,9 | −4,3 | −3,4 |
| Chine | +6,1 | +5,8 | +1,2 | +1,9 | +2,3 |
| Inde | +7,5 | +7,0 | +1,9 | −10,3 | −7,3 |
| Royaume-Uni | +1,4 | +1,4 | −6,5 | −9,8 | −9,8 |

| Édition | Pays dont le recul 2020 était annoncé | Part du PIB mondial | Reculs survenus qui étaient annoncés |
|---|---|---|---|
| Avril 2019 | 5 sur 193 | 0 % | 3 % |
| Octobre 2019 | 10 sur 193 | 1 % | 6 % |
| Avril 2020 | 154 sur 193 | 75 % | 90 % |
| Octobre 2020 | 167 sur 194 | 80 % | 96 % |
| *Réalisé* | *162 pays* | *79 %* | |

- **Comme en 2008, rien n'était annoncé avant l'année du choc.** L'édition d'octobre 2019 prévoyait +3,4 % pour le monde et un recul pour 10 pays pesant 1 % du PIB mondial ; 162 pays ont reculé, soit 79 % du PIB mondial.
- **Contrairement à 2008, l'édition d'avril de l'année du choc tombe juste pour le monde** (−3,0 % contre −3,1 %) et annonce 90 % des reculs. Le choc était déjà en cours lors de sa publication.
- **Les erreurs par pays restent fortes.** L'Inde est attendue à +1,9 % en avril 2020 et fait −7,3 % ; les États-Unis sont attendus à −5,9 % et font −3,4 %.

## 2. Le rebond de 2021 a été prévu, contrairement à celui de 2010

| Croissance 2021 (%) | Octobre 2019 | Avril 2020 | Octobre 2020 | Avril 2021 | Réalisé |
|---|---|---|---|---|---|
| Monde | +3,6 | +5,8 | +5,2 | +6,0 | +6,0 |
| Économies avancées | +1,6 | +4,5 | +3,9 | +5,1 | +5,2 |
| États-Unis | +1,7 | +4,7 | +3,1 | +6,4 | +5,7 |
| Chine | +5,9 | +9,2 | +8,2 | +8,4 | +8,1 |

- **L'édition d'avril 2020 attendait un rebond en V et l'a eu.** Son erreur sur 2021 est nulle en médiane (−0,4 point pondéré par le PIB). Le rebond est sous-estimé pour la moitié des pays seulement, contre 77 % en 2010.
- **L'édition d'octobre 2020, plus pessimiste, le sous-estime davantage** : −1,0 point pondéré par le PIB.

## 3. En niveau : retour sur la trajectoire pour les économies avancées, pas pour les émergentes

PIB en volume, base 100 en 2018 :

| 2024 | Projeté en oct. 2019 | Projeté en oct. 2020 | Réalisé | Écart à la trajectoire d'avant-crise |
|---|---|---|---|---|
| Monde | 122,6 | 115,9 | 118,5 | −3,4 % |
| Économies avancées | 110,0 | 106,6 | 110,8 | +0,7 % |
| Économies émergentes et en développement | 131,1 | 122,9 | 124,1 | −5,4 % |
| États-Unis | 111,4 | 108,1 | 115,7 | +3,8 % |
| Allemagne | 107,2 | 104,7 | 101,0 | −5,7 % |
| Royaume-Uni | 109,1 | 103,7 | 105,4 | −3,4 % |
| Japon | 103,4 | 101,4 | 100,6 | −2,7 % |
| Chine | 140,1 | 138,2 | 134,4 | −4,0 % |
| Inde | 151,2 | 127,0 | 132,6 | −12,3 % |

- **Les économies avancées retrouvent leur trajectoire d'avant la crise en 2024** (+0,7 %), les États-Unis la dépassent (+3,8 %). Après 2008, elles restaient 7,4 % en dessous cinq ans plus tard.
- **La projection d'après-choc d'octobre 2020 était trop pessimiste sur les niveaux** : +3,9 % pour les économies avancées et +7,0 % pour les États-Unis en 2024. C'est l'inverse de 2008, où les États-Unis finissaient sous la projection d'avril 2009.
- **Les émergentes restent sous leur trajectoire** (−5,4 %) : Inde −12,3 %, Chine −4,0 %. L'Allemagne reste aussi en dessous (−5,7 %).

## 2008 et 2020 comparées

| | 2008-2009 | 2020 |
|---|---|---|
| Recul annoncé avant l'année du choc | Non (octobre 2008 : 16 % du PIB mondial) | Non (octobre 2019 : 1 %) |
| Chute mesurée par l'édition d'avril de l'année du choc | Exagérée (monde −1,3 % contre −0,6 %) | Juste (−3,0 % contre −3,1 %) |
| Rebond de l'année suivante, édition d'avril de l'année du choc | Très sous-estimé (−3,0 points pondéré par le PIB) | Prévu (−0,4 point) |
| Économies avancées, niveau 4 à 5 ans après, face à la trajectoire d'avant-crise | −7,4 % (2013) | +0,7 % (2024) |

**Ce qu'on en retient.** Aucune des deux récessions n'était annoncée avant son année. La suite dépend de la nature du choc. Après la crise financière, le FMI a prolongé la chute puis ignoré la rechute européenne, et le niveau n'a pas rattrapé sa trajectoire. Après la pandémie, choc sanitaire et temporaire, il a prévu le rebond, et les économies avancées ont rattrapé leur trajectoire.

**Pour le trafic aérien, 2020 ne se compare pas à 2008.** Jusqu'en 2022, et 2023 pour la Chine, le trafic était limité par les restrictions de voyage et les fermetures de frontières, pas par le revenu. Son retard ne dit donc rien du lien entre PIB et demande. Le test ne devient possible qu'après la levée des restrictions, marché par marché, selon leur date de réouverture.

Un premier indice va dans ce sens : en 2023, le trafic intérieur, moins contraint, dépassait de 3,9 % son niveau de 2019, quand le trafic international n'en était qu'à 88,6 % et l'ensemble à 94,1 % ([IATA, 31 janvier 2024](https://www.iata.org/en/pressroom/2024-releases/2024-01-31-02/)). L'ensemble n'a dépassé son niveau de 2019 qu'en 2024, de 3,8 % ([IATA, 30 janvier 2025](https://www.iata.org/en/pressroom/2025-releases/2025-01-30-01/)). Voir la note du dossier *Transport Aérien* sur Google Drive.
