# Scénarios de PIB et de population pour la prévision du trafic aérien

Export destiné au projet de prévision de long terme pour Aéroports de Montréal (méthode de Kenza). Il réunit ce que ce dépôt sait des projections du FMI et de leurs erreurs passées, prolongé jusqu'en 2050 par les scénarios de l'OCDE et de l'ONU.

Produit par `python produire_rapports.py`, ou seul par `python -m pib.scenarios --data-dir data`, dans `data/processed/` :

| Fichier | Contenu |
|---|---|
| `scenarios_pib_population.csv` | Une ligne par pays, année (de 2000 à 2050) et scénario |
| `scenarios_pib_population_pays.csv` | Par pays : zone de croissance de long terme, origine des bornes au-delà de 2031, bornes et probabilités de recul d'ici 2031 |
| `scenarios_pib_population_sources.json` | Sources et paramètres |

**Le nom ne change pas avec l'horizon** : lire ces fichiers plutôt que `gdp_unified_<début>_<fin>.csv`, dont le nom suit les bornes du run. La chaîne du projet trafic lisait `gdp_unified_2000_2030.csv`, remplacé depuis par `gdp_unified_2000_2031.csv`.

## Colonnes de `scenarios_pib_population.csv`

| Colonne | Contenu |
|---|---|
| `country_code`, `country_name`, `income_group` | Pays (codes ISO3 de la Banque Mondiale) et groupe de revenu |
| `year`, `periode` | Année ; `observé`, `projection du FMI` (jusqu'en 2031) ou `long terme` |
| `scenario` | `central_fmi`, `central_corrige`, `bas`, `haut`, `crise_mondiale` |
| `pib_reel_par_habitant_usd_2015` | PIB en volume par habitant, dollars constants de 2015 |
| `population_millions_centrale`, `…_basse`, `…_haute` | Population, millions : centrale, et bornes de l'intervalle à 80 % de l'ONU |
| `pib_reel_milliards_usd_2015` | PIB en volume, population centrale |
| `pib_par_habitant_usd_courants` | PIB par habitant en dollars courants, pour `central_fmi` jusqu'en 2031 seulement |

Les années observées sont identiques dans tous les scénarios : chacun est une série complète de 2000 à 2050.

## Les scénarios de PIB par habitant

**Jusqu'en 2031**, autour de la trajectoire du FMI, d'après ses erreurs de niveau passées au même horizon, parmi les projections comparables (même classe de croissance projetée, même groupe de revenu, celui-ci tel qu'il était connu à la date de chaque édition passée) :

- `central_fmi` : la trajectoire du FMI ;
- `central_corrige` : divisée par (1 + erreur médiane passée), soit 2,9 % plus bas en 2031 pour le Canada et les États-Unis ;
- `bas`, `haut` : bornes de l'intervalle à 80 % (−11,3 % et +5,1 % en 2031 pour le Canada), calibrées en temps réel (79 % de couverture, voir le README) ;
- `crise_mondiale` : divisée par (1 + erreur médiane des périodes passées qui contenaient une récession mondiale).

**De 2032 à 2050, les scénarios centraux et de crise** suivent la croissance du PIB potentiel par habitant du scénario de référence de l'OCDE (`BAU1`, *Perspectives économiques* n° 117). C'est celle du pays s'il est couvert (49 pays, dont le Canada et les États-Unis), sinon celle de sa région (135 pays). Le niveau atteint en 2031 est conservé : après une crise, pas de rattrapage, comme après 2008.

**Les bornes `bas` et `haut` s'élargissent avec l'horizon,** comme se sont élargies les erreurs passées des trajectoires du FMI prolongées (`pib.long_terme`) :
- **La mesure :** chaque édition du WEO depuis 1999 est prolongée au-delà de 5 ans par la dérive (croissance moyenne des 10 dernières années connues à sa date), puis confrontée au réalisé jusqu'à la dernière année connue. Cela fait jusqu'à 25 ans d'horizon, 8 930 trajectoires.
- **Le lissage :** par groupe de revenu connu à la date de l'édition, les quantiles à 10 et 90 % de l'erreur de niveau sont lissés par une loi de l'horizon, log(1 + q) = α + β (h + 1)^b (`gdp_long_horizon_bands.csv`, paramètres dans `gdp_long_horizon_law.csv`).
- **Le raccord :** la fourchette propre au pays en 2031 est conservée, puis élargie de 2031 à l'année visée comme ces quantiles entre 5 ans et l'horizon correspondant.

Pour le Canada (revenu élevé), en % de `central_fmi` :

| | `bas` | `haut` |
|---|---|---|
| 2031 | 89 % | 105 % |
| 2040 | 72 % | 105 % |
| 2050 | 59 % | 103 % |

Soit, en 2050, de 37 730 $ à 66 449 $ autour de 64 344 $, contre 54 183 $ à 68 790 $ quand les bornes suivaient les scénarios extrêmes de l'OCDE.

**La fourchette est très asymétrique.** Pour les pays déjà riches à la date de l'édition, le réalisé n'a presque jamais dépassé de beaucoup les trajectoires prolongées : le haut de la fourchette reste près de `central_fmi`. Le bas s'éloigne, lui, d'environ 1,5 point de `central_fmi` par an.

**Le groupe de revenu compte.** Classés selon leur groupe actuel, les cas passés auraient compté parmi les riches des pays devenus riches depuis, en dépassant les prévisions (Chili, Pologne, pays baltes). Cela donnait au Canada un haut de 128 % en 2050. Pour les pays à revenu intermédiaire, les rattrapages passés laissent au contraire une large marge à la hausse : Inde, 49 % à 193 % de `central_fmi` en 2050.

**Ce que dit l'évaluation des prolongements** (`gdp_long_horizon_errors.csv`) :
- **Prolonger la croissance de moyen terme du FMI** (médiane de ses horizons 3 à 5) surestime le niveau de 12 % en médiane à 10 ans, de 28 % à 20 ans. La trajectoire centrale suit donc l'OCDE après 2031, pas le FMI.
- **Le FMI jusqu'à 5 ans, puis la dérive,** fait mieux que la dérive seule dans 56 à 64 % des cas, de 5 à 20 ans.
- **80 % de ses erreurs de niveau** restent sous 30 % à 10 ans, sous 50 % à 20 ans.

Sans `gdp_long_horizon_bands.csv`, `bas` et `haut` suivent à défaut le scénario de l'OCDE le moins et le plus favorable pour la zone (colonne `bornes_long_terme` du fichier par pays).

**Probabilités de récession** (`scenarios_pib_population_pays.csv`) : au moins une année de recul entre 2027 et 2031, 64 % pour le Canada. Si une récession mondiale survient, 97 % ; sinon, 41 %. Une période de cinq ans contient une récession mondiale dans 41 % des cas depuis 1961.

## Population

- **Jusqu'en 2031 :** celle du pipeline (Banque Mondiale, puis FMI).
- **Ensuite :** prolongée par la croissance de la variante médiane de l'ONU (*World Population Prospects* 2024).
- **Variantes basse et haute :** le rapport des bornes à 80 % de l'ONU à sa médiane, appliqué à la centrale dès la première année projetée. Pour le Canada en 2050 : 42,1 à 51,5 millions, autour de 46,6.

## Pour la méthode de Kenza

- **Utiliser le PIB en volume par habitant.** Le prix normalisé rapporte un prix au revenu ; en volume, il ne mêle pas l'inflation à la croissance du revenu. La variante indexée, qui remplace le prix par `PIB_ref / PIB_par_habitant(t)`, n'a besoin que d'un rapport, sans unité : le volume convient directement. Le dollar courant n'est fourni que jusqu'en 2031, pour la continuité.
- **Combiner les dimensions au besoin.** Les scénarios de PIB et les variantes de population sont indépendants : `bas` × population basse donne le cas le plus défavorable.
- **Pour une crise ponctuelle**, `crise_mondiale` donne le niveau ; la pire année médiane (−3,7 % pour le Canada) et le profil de 2008 (`docs/cas_crise_2008.md`) donnent la forme de la trajectoire.
- **La zone de chalandise n'est pas le pays.** Ces séries sont nationales ; le PIB métropolitain (Statistique Canada, tableau 36-10-0468-01) reste la piste identifiée par la feuille de route du projet trafic.

## Limites

- **Au-delà de 2031, les fourchettes sont tirées des erreurs passées, avec trois réserves :**
  - **Extrapolation au-delà de 16 ans.** Les lois sont ajustées jusqu'à 16 ans, dernier horizon qui compte au moins 10 années d'édition. Au-delà, donc de 2043 à 2050, elles sont extrapolées. Les quantiles observés à 20 ans, sur 6 années d'édition seulement, toutes traversées par 2009 et 2020, sont un peu plus étroits que la loi (90e centile de 60 % contre 66 % pour les pays à revenu élevé). Les bornes de ces années-là sont à lire comme indicatives.
  - **Groupe de revenu, pas pays.** Les quantiles sont ceux du groupe connu à la date de chaque édition : le Canada reçoit ceux des pays alors à revenu élevé, dont la Grèce de 2010 ou l'Irlande de 2015.
  - **Un échantillon dominé par 2008-2009.** Pour les pays riches, les éditions évaluables au-delà de 10 ans (1999 à 2009) n'avaient pas vu venir la perte de niveau de 2008-2009. Un haut de fourchette proche de la trajectoire centrale reflète cet épisode ; une période plus favorable l'aurait relevé.
  - **PIB total, appliqué au PIB par habitant.** Les erreurs portent sur le PIB en volume ; l'incertitude de la population est traitée à part, par les variantes de l'ONU.
- **La dérive tient lieu de croissance de long terme** dans la mesure des erreurs : les scénarios passés de l'OCDE ne sont pas archivés.
- **La croissance de long terme de l'OCDE** porte sur le PIB potentiel en parité de pouvoir d'achat ; seule sa croissance est utilisée, appliquée au niveau en dollars de 2015.
- **Rien ne mesure encore l'optimisme éventuel des scénarios de l'OCDE**, comme ce dépôt l'a fait pour le FMI.
