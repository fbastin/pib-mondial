# La crise de 2008 dans les prévisions du FMI

La chute du PIB de 2009 avait-elle été prévue ? Et le rebond qui a suivi ? Cas d'étude
tiré des éditions d'époque du *World Economic Outlook* (classeur historique du FMI).

Reproduire : `python -m pib.cas_de_crise --annee 2009`. Les tableaux sont écrits dans
`data/processed/weo_cas_2009_*.csv` ; `--annee 2020` fait la même lecture pour la pandémie.

- **Croissance réalisée :** ré-estimation du FMI un an après, comme dans l'évaluation.
- **Niveaux réalisés :** estimation actuelle, tirée de l'édition d'avril 2026 archivée, qui intègre les révisions des comptes survenues depuis.
- **Éditions :** le classeur ne contient que les éditions d'avril (S) et d'octobre (F). Les mises à jour intermédiaires (novembre 2008, janvier 2009) n'y figurent pas : le FMI a révisé plus tôt que ne le montrent les tableaux, mais après le choc.

## 1. La chute de 2009 n'a été vue que dans l'année même

| Croissance 2009 (%) | Avril 2008 | Octobre 2008 | Avril 2009 | Réalisé |
|---|---|---|---|---|
| Monde | +3,8 | +3,0 | −1,3 | −0,6 |
| Économies avancées | +1,3 | +0,5 | −3,8 | −3,2 |
| Économies émergentes et en développement | +6,6 | +6,1 | +1,6 | +2,5 |
| États-Unis | +0,6 | +0,1 | −2,8 | −2,6 |
| Allemagne | +1,0 | 0,0 | −5,6 | −4,7 |
| Japon | +1,5 | +0,5 | −6,2 | −5,2 |
| Chine | +9,5 | +9,3 | +6,5 | +9,1 |

| Édition | Pays dont le recul 2009 était annoncé | Part du PIB mondial | Reculs survenus qui étaient annoncés |
|---|---|---|---|
| Avril 2008 | 1 sur 184 | 0 % | 0 % |
| Octobre 2008 | 7 sur 183 | 16 % | 8 % |
| Avril 2009 | 78 sur 183 | 82 % | 74 % |
| Octobre 2009 | 89 sur 185 | 80 % | 88 % |
| *Réalisé* | *89 pays* | *77 %* | |

- **L'édition d'octobre 2008**, parue trois semaines après la faillite de Lehman Brothers, annonçait encore +3,0 % pour le monde, et un recul pour sept pays seulement.
- **L'édition d'avril 2009 voit la chute, mais l'exagère** : −1,3 % pour le monde contre −0,6 %, +6,5 % pour la Chine contre +9,1 % (plan de relance).
- **L'erreur à un an sur 2009 est un record** : sur l'année 2009, l'erreur médiane de l'édition d'avril 2008 atteint +4,2 points, contre +0,4 point pour l'ensemble des années visées.

## 2. Le rebond de 2010 n'a pas été prévu non plus

| Croissance 2010 (%) | Avril 2008 | Avril 2009 | Octobre 2009 | Avril 2010 | Réalisé |
|---|---|---|---|---|---|
| Monde | +4,8 | +1,9 | +3,1 | +4,2 | +5,1 |
| Économies avancées | +2,7 | 0,0 | +1,3 | +2,3 | +3,1 |
| Économies émergentes et en développement | +7,1 | +4,0 | +5,1 | +6,3 | +7,3 |
| États-Unis | +2,9 | 0,0 | +1,5 | +3,1 | +3,0 |
| Allemagne | +1,7 | −1,0 | +0,3 | +1,2 | +3,6 |
| Japon | +1,7 | +0,5 | +1,7 | +1,9 | +4,0 |
| Brésil | +4,5 | +2,2 | +3,5 | +5,5 | +7,5 |

- **Après le choc, le FMI l'a prolongé.** L'édition d'avril 2009 sous-estime le rebond de 2010 pour 77 % des pays : −3,0 points pondéré par le PIB, −1,7 point en médiane. L'édition d'octobre 2009 le sous-estime encore de −1,8 point pondéré par le PIB ; il n'est rattrapé qu'en 2010.
- **Les prévisions d'avant la crise étaient plus justes pour 2010** : l'édition d'avril 2008 donnait +4,8 % pour le monde, contre +1,9 % dans celle d'avril 2009, pour un réalisé de +5,1 %.
- **Après une crise, l'erreur change de signe.** Le biais optimiste habituel, poussé à +4,2 points pour 2009, fait place pour 2010 à un pessimisme marqué (−1,7 point en médiane à un an).

## 3. En niveau : un rebond de la croissance, pas un retour sur la trajectoire

PIB en volume, base 100 en 2007 :

| | 2011 projeté oct. 2008 | 2011 projeté avr. 2009 | 2011 réalisé | 2013 projeté oct. 2008 | 2013 projeté avr. 2009 | 2013 réalisé |
|---|---|---|---|---|---|---|
| Monde | 116,9 | 108,2 | 112,4 | 128,3 | 119,0 | 120,1 |
| Économies avancées | 107,0 | 99,6 | 101,7 | 112,8 | 105,7 | 104,4 |
| Économies émergentes | 129,2 | 118,9 | 123,4 | 147,8 | 135,5 | 136,4 |
| États-Unis | 107,0 | 101,8 | 101,7 | 112,4 | 108,9 | 106,3 |
| Allemagne | 104,1 | 96,0 | 103,0 | 107,5 | 99,7 | 103,8 |
| Royaume-Uni | 106,6 | 98,2 | 98,4 | 113,5 | 104,0 | 101,6 |
| Japon | 105,0 | 95,7 | 96,6 | 109,4 | 101,5 | 100,2 |
| Italie | 100,8 | 94,9 | 95,8 | 103,2 | 97,7 | 91,1 |
| Espagne | 105,5 | 98,2 | 96,4 | 112,3 | 101,1 | 92,3 |
| Chine | 144,8 | 137,7 | 145,2 | 175,2 | 168,1 | 168,8 |

- **La perte de niveau est durable.** En 2013, le PIB réalisé reste sous la trajectoire projetée en octobre 2008 :
  - de 6,4 % pour le monde, 7,4 % pour les économies avancées et 7,7 % pour les émergentes ;
  - de 5,4 % pour les États-Unis, 8,5 % pour le Japon et 10,5 % pour le Royaume-Uni ;
  - de 11,7 % pour l'Italie et 17,8 % pour l'Espagne.

  Le rebond de 2010 a relevé la croissance, pas le niveau.
- **Le rebond sous-estimé en avril 2009 est surtout allemand et émergent.** En 2011, le niveau réalisé dépasse celui projeté alors de 7,2 % pour l'Allemagne, 7,5 % pour le Brésil et 5,5 % pour la Chine. Pour les États-Unis et le Royaume-Uni, il n'en diffère pas (0,0 % et +0,1 %).
- **Deux ans plus tard, beaucoup d'économies avancées finissent sous la projection d'après-choc.** En 2013, le niveau réalisé est inférieur à celui projeté en avril 2009 de 2,4 % pour les États-Unis, 2,3 % pour le Royaume-Uni, 6,7 % pour l'Italie et 8,7 % pour l'Espagne. La crise de la zone euro de 2011-2013 n'était pas prévue.
- **Pour le monde, la projection d'avril 2009 tombe juste en 2013 (119,0 contre 120,1), mais par compensation** : rebond émergent sous-estimé d'un côté, rechute européenne ignorée de l'autre.

## 4. Le test sur le trafic aérien

`python -m pib.cas_de_crise --annee 2009 --trafic`, tableaux `weo_cas_2009_trafic*.csv`.

**Question.** Le retard du trafic aérien sur sa tendance d'avant la crise s'explique-t-il par l'écart du PIB à la projection du FMI d'octobre 2008 ?

**Données.**
- **Europe :** trafic passagers d'Eurostat (`avia_paoc`), compté par aéroport, homogène depuis 2004, pour 30 pays.
- **États-Unis :** série de la Banque Mondiale (données de l'OACI).
- **Donnée écartée :** la série mondiale de la Banque Mondiale est rompue en 2010, par un changement de couverture des déclarations (+15 % pour l'Union européenne, +31 % pour l'Asie de l'Est en un an). Elle est aussi comptée par pays d'immatriculation des compagnies, ce qui déforme les grandes plateformes de correspondance.

**Au niveau agrégé, le PIB explique à peu près un tiers du retard.**

| | Europe (29 pays), 2013 | États-Unis, 2013 |
|---|---|---|
| Croissance du trafic depuis 2007 | +7,0 % | −0,2 % |
| Tendance d'avant la crise (2004-2007) | +7,0 %/an | +3,1 %/an |
| Retard sur la tendance | −35,0 % | −18,8 % |
| PIB réalisé / projeté en octobre 2008, depuis 2007 | +0,3 % / +10,9 % | +6,1 % / +11,7 % |
| Écart de PIB | −10,6 % | −5,6 % |
| Traduit en trafic (élasticité 1,0 à 1,5) | −10,6 % à −15,9 % | −5,6 % à −8,4 % |
| **Part du retard du trafic expliquée** | **30 à 45 %** | **30 à 45 %** |

Écarts en log × 100. En 2010, la part est de 22 à 32 % en Europe et de 28 à 41 % aux États-Unis. Le trafic américain de 2013 (743 millions de passagers) n'a toujours pas retrouvé celui de 2007 (744 millions).

**D'un pays européen à l'autre, en revanche, le PIB n'explique plus les écarts de trafic après la crise.** La relation, forte avant, disparaît :

| Période | Pente du trafic sur le PIB | IC 95 % | R² |
|---|---|---|---|
| 2004-2007 | 2,88 | 1,87 à 3,90 | 0,54 |
| 2007-2010 | 0,01 | −0,64 à 0,66 | 0,00 |
| 2007-2013 | 0,50 | −0,21 à 1,21 | 0,06 |

- La Grèce perd 31 % de PIB mais 4 % de trafic.
- La Lettonie et la Lituanie gagnent plus de 40 % de trafic avec un PIB 20 à 22 % sous sa projection.
- La Slovaquie et l'Irlande, avec des écarts de PIB comparables (−23 % et −17 %), en perdent 36 % et 19 %.

Compagnies à bas coûts, faillites (SkyEurope en 2009), fiscalité et intégration européenne pèsent plus, pays par pays, que la surprise sur le PIB.

**Réserves.**
- **La tendance de 2004-2007** inclut l'essor des compagnies à bas coûts et l'élargissement de l'Union : la prolonger surestime sans doute le trafic « attendu », et donc le retard.
- **L'élasticité est une hypothèse** (1,0 à 1,5, autour des 1,19 de Gallet et Doucouliagos, 2014). Plus faible pendant les reprises (Hanson et al., 2022), elle réduirait la part expliquée.
- **Les séries sont en passagers**, pas en passagers-kilomètres.
- **Pour 2020**, le module tourne aussi (`--annee 2020 --trafic`), mais les restrictions de voyage empêchent d'y lire le lien avec le revenu.

## Ce qu'on en retient

- **Le constat général sur les récessions** (voir le README) : un choc n'est vu que dans l'année même, et la prévision suivante devient trop pessimiste. Les années qui suivent une crise sont donc celles où le biais optimiste moyen décrit le plus mal l'erreur.
- **Une projection faite avant un choc surestime le niveau pour des années, même quand la croissance rebondit vite.** Une projection faite juste après le choc peut encore surestimer le niveau des économies avancées quelques années plus loin.
- **Le trafic aérien a pris un retard dont le PIB explique environ un tiers.** C'est vrai en Europe comme aux États-Unis, mais pas les différences entre pays. La note du dossier *Transport Aérien* sur Google Drive en tire les conséquences pour le projet trafic.
- **La comparaison avec la pandémie de 2020** est dans `docs/cas_crise_2020.md`.
