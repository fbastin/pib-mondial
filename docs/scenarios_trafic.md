# Scénarios de PIB et de population pour la prévision du trafic aérien

Export destiné au projet de prévision de long terme pour Aéroports de Montréal (méthode de Kenza). Il réunit ce que ce dépôt sait des projections du FMI et de leurs erreurs passées, prolongé jusqu'en 2050 par les scénarios de l'OCDE et de l'ONU.

Produit par `python produire_rapports.py`, ou seul par `python -m pib.scenarios --data-dir data`, dans `data/processed/` :

| Fichier | Contenu |
|---|---|
| `scenarios_pib_population.csv` | Une ligne par pays, année (de 2000 à 2050) et scénario |
| `scenarios_pib_population_pays.csv` | Par pays : zone de croissance de long terme, scénarios de l'OCDE retenus, bornes et probabilités de recul d'ici 2031 |
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

**Jusqu'en 2031**, autour de la trajectoire du FMI, d'après ses erreurs de niveau passées au même horizon, parmi les projections comparables (même classe de croissance projetée, même groupe de revenu) :

- `central_fmi` : la trajectoire du FMI ;
- `central_corrige` : divisée par (1 + erreur médiane passée), soit 2,7 % plus bas en 2031 pour le Canada et les États-Unis ;
- `bas`, `haut` : bornes de l'intervalle à 80 % (−11,9 % et +6,9 % en 2031 pour le Canada), calibrées en temps réel (79 % de couverture, voir le README) ;
- `crise_mondiale` : divisée par (1 + erreur médiane des périodes passées qui contenaient une récession mondiale).

**De 2032 à 2050**, chaque scénario suit la croissance du PIB potentiel par habitant des scénarios de long terme de l'OCDE (*Perspectives économiques* n° 117) :
- celle du pays s'il est couvert (49 pays, dont le Canada et les États-Unis), sinon celle de sa région (135 pays) ;
- le scénario de référence de l'OCDE (`BAU1`) pour les scénarios centraux et de crise ;
- le moins et le plus favorable pour `bas` et `haut`.

Le niveau atteint en 2031 est conservé : après une crise, pas de rattrapage, comme après 2008.

**Probabilités de récession** (`scenarios_pib_population_pays.csv`) : au moins une année de recul entre 2027 et 2031, 65 % pour le Canada. Si une récession mondiale survient, 98 % ; sinon, 42 %. Une période de cinq ans contient une récession mondiale dans 41 % des cas depuis 1961.

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

- **Les fourchettes ne sont calibrées que jusqu'à 5 ans.** Au-delà, l'écart entre scénarios est celui de 2031, plus celui des scénarios de l'OCDE. Ceux-ci ne diffèrent que par la transition énergétique et les dommages climatiques, pas par l'incertitude macroéconomique : l'écart ne s'élargit donc guère après 2031, alors que l'incertitude réelle, elle, continue de croître. Piste : extrapoler l'écart-type de l'erreur avec l'horizon, comme le propose la note d'Aéroports de Paris sur la prévision probabilisée de PIB (Sallier, 2010 ; voir `docs/revue_litterature.md`, § 3.3).
- **La croissance de long terme de l'OCDE** porte sur le PIB potentiel en parité de pouvoir d'achat ; seule sa croissance est utilisée, appliquée au niveau en dollars de 2015.
- **Rien ne mesure encore l'optimisme éventuel des scénarios de l'OCDE**, comme ce dépôt l'a fait pour le FMI.
