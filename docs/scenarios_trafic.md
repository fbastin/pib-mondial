# Scénarios de PIB et de population pour la prévision du trafic aérien

Export destiné au projet de prévision de long terme pour Aéroports de Montréal (méthode de Kenza). Il réunit ce que ce dépôt sait des projections du FMI et de leurs erreurs passées, prolongé jusqu'en 2050 par les scénarios de l'OCDE et de l'ONU.

Produit par `python produire_rapports.py`, ou seul par `python -m pib.scenarios --data-dir data`, dans `data/processed/` :

| Fichier | Contenu |
|---|---|
| `scenarios_pib_population.csv` | Une ligne par pays, année (de 2000 à 2050) et scénario |
| `scenarios_pib_population_pays.csv` | Par pays : zone de croissance de long terme, origine des bornes au-delà de 2031, bornes et probabilités de recul d'ici 2031 |
| `scenarios_pib_population_sources.json` | Sources et paramètres |
| `scenarios_pib_tirages.csv` | 60 trajectoires conjointes de tous les pays, de 2026 à 2050 (`python -m pib.tirages`) |
| `scenarios_pib_tirages_controle.csv` | Contrôle des tirages : part sous `bas` et au-dessus de `haut` par pays ; quantiles de quelques agrégats contre la somme des bornes |

**Le nom ne change pas avec l'horizon** : lire ces fichiers plutôt que `gdp_unified_<début>_<fin>.csv`, dont le nom suit les bornes du run.

## Pour la chaîne du projet trafic : de `gdp_unified_2000_2030.csv` au fichier stable

La chaîne du projet trafic lit le PIB par `julia/run/build_macro_series.jl --source …/GDP/data/processed/gdp_unified_2000_2030.csv`. Ce fichier ne suit plus les mises à jour : son nom portait les bornes du run, devenues 2000-2031.

**En attendant, rien à changer.** L'ancien fichier, figé au 29 septembre 2026, reste à sa place sur le Drive (`Transport Aerien/GDP/data/processed/gdp_unified_2000_2030.csv`). La commande du README du projet trafic fonctionne telle quelle. Il restera là jusqu'au passage au fichier stable, mais ne sera plus mis à jour. La procédure ci-dessous est aussi dans `Pour_Chama_PIB_projet_trafic.txt`, à côté du fichier.

**Le passage ne change aucun chiffre.** Sur toutes les années communes, `GDP_Per_Capita_USD` est identique dans l'ancien fichier, dans `gdp_unified_2000_2031.csv` et dans `scenarios_pib_population.csv` (scénario `central_fmi`, colonne `pib_par_habitant_usd_courants`), à l'arrondi près (0,00005 $). La seule différence : l'année 2031 s'ajoute aux projections.

**Procédure, une fois :**

1. Dans `julia/run/build_macro_series.jl`, fonction `macro_series`, juste après `table = CSV.read(path, DataFrame)`, ajouter :

   ```julia
   if "scenario" in names(table)        # fichier stable de pib-mondial : scenarios_pib_population.csv
       table = filter(r -> r.scenario == "central_fmi", table)
       table.GDP_Per_Capita_USD = table.pib_par_habitant_usd_courants
       table.is_forecast = table.periode .!= "observé"
   end
   ```

   La fonction lit alors les deux formats. Sur l'ancien fichier, sa sortie est inchangée (vérifié pour le Canada, les États-Unis, la France, le Royaume-Uni et la Chine, avec et sans `--with-forecast`).

2. Remplacer, dans les commandes et dans le README du projet trafic, `--source …/GDP/data/processed/gdp_unified_2000_2030.csv` par `--source …/GDP/data/processed/scenarios_pib_population.csv`.

3. Vérifier : `--country CAN --years 2005-2020` donne, comme avant, 16 années, de 36 384 à 52 670 $ par habitant.

**Ensuite, à chaque édition du WEO, plus rien à changer.** La chaîne de ce dépôt est relancée (`python produire_rapports.py`). Le Drive est mis à jour sous le même nom. Il suffit de relancer `build_macro_series.jl` : les projections, et les années récentes révisées, suivent la nouvelle édition.

**Pour aller plus loin, dans un second temps :**
- **Le PIB en volume par habitant** (`pib_reel_par_habitant_usd_2015`) plutôt qu'en dollars courants, comme le recommande la section « Pour la méthode de Kenza ». Remplacer `pib_par_habitant_usd_courants` dans l'adaptation ci-dessus ; les prix normalisés changent, le modèle est donc à recaler.
- **Les autres scénarios** (`bas`, `haut`, `crise_mondiale`…), jusqu'en 2050 : remplacer `"central_fmi"` par le scénario voulu, en volume. Les dollars courants ne sont donnés que jusqu'en 2031.
- **Plusieurs marchés à la fois :** les trajectoires conjointes (`scenarios_pib_tirages.csv`, plus bas).

## Colonnes de `scenarios_pib_population.csv`

| Colonne | Contenu |
|---|---|
| `country_code`, `country_name`, `income_group` | Pays (codes ISO3 de la Banque Mondiale) et groupe de revenu |
| `year`, `periode` | Année ; `observé`, `projection du FMI` (jusqu'en 2031) ou `long terme` |
| `scenario` | `central_fmi`, `central_corrige`, `bas`, `haut`, `crise_mondiale`, et pour comparaison `bas_groupe_seul`, `haut_groupe_seul`, `bas_elargi`, `haut_elargi` |
| `pib_reel_par_habitant_usd_2015` | PIB en volume par habitant, dollars constants de 2015 |
| `population_millions_centrale`, `…_basse`, `…_haute` | Population, millions : centrale, et bornes de l'intervalle à 80 % de l'ONU |
| `population_millions_basse_calibree`, `…_haute_calibree` | Bornes à 80 % calibrées sur les erreurs passées de l'ONU (ci-dessous), plus larges |
| `pib_reel_milliards_usd_2015` | PIB en volume, population centrale |
| `pib_par_habitant_usd_courants` | PIB par habitant en dollars courants, pour `central_fmi` jusqu'en 2031 seulement |

Les années observées sont identiques dans tous les scénarios : chacun est une série complète de 2000 à 2050.

## Les scénarios de PIB par habitant

**Jusqu'en 2031**, autour de la trajectoire du FMI, d'après ses erreurs de niveau passées au même horizon, parmi les projections comparables (même classe de croissance projetée, même groupe de revenu, celui-ci tel qu'il était connu à la date de chaque édition passée) :

- `central_fmi` : la trajectoire du FMI ;
- `central_corrige` : divisée par (1 + erreur médiane passée), soit 2,9 % plus bas en 2031 pour le Canada et les États-Unis ;
- `bas`, `haut` : bornes de l'intervalle à 80 % (−11,3 % et +5,1 % en 2031 pour le Canada), calibrées en temps réel (79 % de couverture, voir le README) ;
- `crise_mondiale` : divisée par (1 + erreur médiane des périodes passées qui contenaient une récession mondiale) ;
- `bas_groupe_seul`, `haut_groupe_seul` : les bornes à 80 % tirées du seul groupe de revenu, sans la classe de croissance projetée, élargies de même après 2031.
- `bas_elargi`, `haut_elargi` : pour les pays à revenu élevé, les bornes `bas` et `haut` élargies après 2031 (ci-dessous) ; pour les autres, les mêmes que `bas` et `haut`.

**Pourquoi deux jeux de bornes.** Éprouvées en temps réel, les deux méthodes se valent, sans pondération comme hors de la Chine et de l'Inde. Pondéré par le PIB sur les éditions 2000-2007, le groupe seul l'emporte : la croissance de ces deux pays dépassait alors les projections, et la méthode retenue penche vers le bas la fourchette des pays à forte croissance projetée. La méthode retenue est conservée ; la variante montre ce que coûterait l'autre choix.
- **Pour le Canada et les pays riches,** même borne haute ; borne basse un peu plus basse avec le groupe seul (−13,6 % en 2031, contre −11,3 %).
- **Pour les pays à forte croissance projetée,** l'écart est plus net : Inde 2031, de −19,6 à +8,4 % avec le groupe seul, contre −25,0 à +4,6 %.

**De 2032 à 2050, les scénarios centraux et de crise** suivent la croissance du PIB potentiel par habitant du scénario de référence de l'OCDE (`BAU1`, *Perspectives économiques* n° 117). C'est celle du pays s'il est couvert (49 pays, dont le Canada et les États-Unis), sinon celle de sa région (135 pays). Le niveau atteint en 2031 est conservé : après une crise, pas de rattrapage, comme après 2008.

**Les bornes `bas` et `haut` s'élargissent avec l'horizon,** comme se sont élargies les erreurs passées des trajectoires du FMI prolongées (`pib.long_terme`) :
- **La mesure :** chaque édition du WEO depuis 1999 est prolongée au-delà de 5 ans par la dérive (croissance moyenne des 10 dernières années connues à sa date), puis confrontée au réalisé jusqu'à la dernière année connue. Cela fait jusqu'à 25 ans d'horizon, 8 930 trajectoires.
- **Le lissage :** par groupe de revenu connu à la date de l'édition, les quantiles à 10 et 90 % de l'erreur de niveau sont lissés par une loi de l'horizon, log(1 + q) = α + β (h + 1)^b (`gdp_long_horizon_bands.csv`, paramètres dans `gdp_long_horizon_law.csv`).
- **Le raccord :** la fourchette propre au pays en 2031 est conservée, puis élargie de 2031 à l'année visée comme ces quantiles entre 5 ans et l'horizon correspondant.

Pour le Canada (revenu élevé), en % de `central_fmi` :

| | `bas` | `haut` |
|---|---|---|
| 2031 | 89 % | 105 % |
| 2040 | 72 % | 104 % |
| 2050 | 59 % | 101 % |

Soit, en 2050, de 37 852 $ à 65 010 $ autour de 64 344 $, contre 54 183 $ à 68 790 $ quand les bornes suivaient les scénarios extrêmes de l'OCDE.

**La variante élargie des pays riches** (`bas_elargi`, `haut_elargi`). La fourchette ci-dessus est à peu près symétrique autour de son propre milieu, en logarithme : 97 % du central en 2031, 77 % en 2050. Ce n'est donc pas sa largeur qui écrase le haut, c'est ce décalage, l'optimisme passé du FMI prolongé. Le biais lui-même est solide : chacune des 31 éditions de 1999 à 2014 a surestimé le niveau du Canada à 10 ans, de 2 à 18 %. Son extrapolation jusqu'en 2050 l'est moins, d'où deux ajustements, au-delà de 2031 :
- **Le milieu de la fourchette est figé** au-delà de 16 ans, dernier horizon où la loi de long terme est ajustée (2042). Le décalage venait des éditions 1999-2009, toutes traversées par la crise de 2008. Pour les pays riches, l'erreur médiane à 10 ans des éditions 2010-2014 est de +9 %, contre +12 à +15 % avant, et leur 10e centile de −6 % montre une vraie possibilité de hausse.
- **La largeur ne descend pas sous un plancher** tiré de Müller, Stock et Watson (2022). Leur intervalle à 67 % pour la croissance moyenne des États-Unis sur 50 ans, de 0,6 à 2,7 % par an, donne un écart-type du logarithme du niveau d'au moins 0,011 par année d'horizon. Le plancher suppose la croissance moyenne au moins aussi incertaine sur moins de 50 ans que sur 50, comme dans leur modèle entre 50 et 100 ans. Il joue dès 2040.

| Canada, % de `central_fmi` | `bas` | `haut` | `bas_elargi` | `haut_elargi` |
|---|---|---|---|---|
| 2031 | 89 % | 105 % | 89 % | 105 % |
| 2040 | 72 % | 104 % | 71 % | 105 % |
| 2050 | 59 % | 101 % | 60 % | 117 % |

Le bas bouge à peine ; le haut gagne 16 points en 2050. Pour un aéroport, le haut compte autant que le bas : il dimensionne la capacité. Au prix normalisé du Canada, la loi de Kenza amortit toutefois l'effet du PIB sur le trafic (élasticité au revenu d'environ 0,4). Le haut de la population calibrée (+23 % en 2050, ci-dessous) pèse alors davantage.

**La fourchette est très asymétrique.** Pour les pays déjà riches à la date de l'édition, le réalisé n'a presque jamais dépassé de beaucoup les trajectoires prolongées : le haut de la fourchette reste près de `central_fmi`. Le bas s'éloigne, lui, d'environ 1,5 point de `central_fmi` par an.

**Le groupe de revenu compte.** Classés selon leur groupe actuel, les cas passés auraient compté parmi les riches des pays devenus riches depuis, en dépassant les prévisions (Chili, Pologne, pays baltes). Cela donnait au Canada un haut de 128 % en 2050. Pour les pays à revenu intermédiaire, la marge à la hausse est plus large : Inde, 47 à 122 % de `central_fmi` en 2050.

**Les trajectoires qui prolongent un effondrement sont écartées des fourchettes.** Pour 5 % des trajectoires, la croissance des dix années passées était négative : la prolonger, c'est extrapoler un effondrement. Les éditions de 1999 à 2003 l'ont fait pour les économies issues de l'URSS, dont le réalisé a ensuite atteint jusqu'à 16 fois la trajectoire prolongée (Géorgie, Kazakhstan, Turkménistan, Ukraine). Les scénarios, eux, suivent après 2031 la croissance de l'OCDE, qui ne prolonge aucun effondrement : ces erreurs ne disent rien de leur incertitude. Elles gonflaient le haut des fourchettes des pays non riches, et d'autant plus que l'horizon est long, puisque seules les premières éditions y sont évaluables :
- **Inde 2050 :** 47 à 122 % du central, au lieu de 49 à 193 % ; Nigeria, 52 à 125 % au lieu de 55 à 197 % ; Éthiopie, 64 à 173 % au lieu de 66 à 253 %.
- **Pays riches :** à peine touchés (Canada 2050 : 59 à 101 %, au lieu de 59 à 103 %).
- **Le bas** bouge de 3 points au plus.

Même sans ces cas, la queue haute des pays non riches reste portée par les premières éditions : à 10 ans, le 90e centile du réalisé passe, pour le revenu intermédiaire inférieur, de 140 % du prévu pour les éditions 1999-2004 à 106 % pour celles de 2010-2014.

**Ce que dit l'évaluation des prolongements** (`gdp_long_horizon_errors.csv`) :
- **Prolonger la croissance de moyen terme du FMI** (médiane de ses horizons 3 à 5) surestime le niveau de 12 % en médiane à 10 ans, de 28 % à 20 ans. La trajectoire centrale suit donc l'OCDE après 2031, pas le FMI.
- **Le FMI jusqu'à 5 ans, puis la dérive,** fait mieux que la dérive seule dans 56 à 64 % des cas, de 5 à 20 ans.
- **80 % de ses erreurs de niveau** restent sous 30 % à 10 ans, sous 50 % à 20 ans.

Sans `gdp_long_horizon_bands.csv`, `bas` et `haut` suivent à défaut le scénario de l'OCDE le moins et le plus favorable pour la zone (colonne `bornes_long_terme` du fichier par pays).

**Probabilités de récession** (`scenarios_pib_population_pays.csv`) : au moins une année de recul entre 2027 et 2031, 64 % pour le Canada. Si une récession mondiale survient, 97 % ; sinon, 41 %. Une période de cinq ans contient une récession mondiale dans 41 % des cas depuis 1961.

## Agréger plusieurs marchés : les trajectoires conjointes

Les bornes `bas` et `haut` sont calculées **pays par pays**. Additionner la borne basse de chaque marché (Canada, États-Unis, Europe…) ne donne pas un « scénario bas à 80 % » de l'ensemble : cette combinaison n'a pas de probabilité connue. Les erreurs des pays sont liées, mais pas parfaitement.

`scenarios_pib_tirages.csv` donne **60 trajectoires conjointes** de tous les pays, de 2026 à 2050 :

| Colonne | Contenu |
|---|---|
| `tirage` | Édition du WEO rejouée (`S1990` à `F2019` : avril et octobre de 1990 à 2019) |
| `country_code`, `year` | Pays, année |
| `pib_reel_par_habitant_usd_2015` | PIB en volume par habitant, dollars constants de 2015 |

**Construction** (rééchantillonnage de Schaake, Clark et al., 2004) :
- **Jusqu'en 2031,** chaque tirage rejoue une édition passée. À chaque horizon, chaque pays y reçoit son rang parmi les 60 éditions de sa propre histoire, puis le quantile correspondant de **sa fourchette actuelle**. Exemple : l'édition où le Canada a le plus surestimé son niveau à 5 ans lui donne le plus bas des 60 niveaux de 2031. Chaque pays garde donc exactement sa fourchette, mais les crises communes restent communes.
- **Pays absent d'une édition :** il prend le rang médian des pays de son groupe de revenu dans cette édition.
- **Au-delà de 2031,** chaque tirage garde sa position relative dans la fourchette `bas`–`haut` de son pays.

**Ce que ça change** (en % de la somme des `central_fmi`, population centrale ; intervalle à 95 % par bootstrap des années d'édition) :

| Agrégat | Année | Tirages : 10e – 90e centile | Somme des `bas` – somme des `haut` |
|---|---|---|---|
| Tous les pays | 2031 | 90,2 (89,2 à 93,3) – 100,7 | 85,2 – 105,5 |
| Tous les pays | 2050 | 70,1 (66,9 à 78,4) – 105,8 | 55,6 – 116,7 |
| Canada, États-Unis, France, Royaume-Uni | 2031 | 87,7 (84,3 à 94,2) – 104,4 | 88,7 – 105,1 |
| Canada, États-Unis, France, Royaume-Uni | 2050 | 57,4 (50,6 à 71,3) – 99,3 | 58,8 – 101,0 |
| G7 | 2050 | 59,6 (56,5 à 74,6) – 94,1 | 58,8 – 101,0 |

- **Pour le monde entier,** sommer les bornes exagère nettement l'incertitude : les erreurs des pays se compensent en partie.
- **Pour quelques marchés riches,** la somme des bornes reste dans l'incertitude des tirages. Les États-Unis y pèsent environ 60 %, et les pires tirages rejouent pour tous les éditions de 2005 à 2008, prises de court par la crise financière.
- **La meilleure façon de s'en servir :** faire passer chacun des 60 tirages dans le modèle de trafic, puis lire les quantiles du trafic total. La dépendance entre marchés est alors celle qu'ont connue les éditions passées.

**Limites :**
- **60 tirages, dont des paires voisines.** Les éditions d'avril et d'octobre d'une même année sont très proches : cela fait une trentaine d'épisodes indépendants. Les quantiles d'un agrégat se lisent à quelques points près ; d'où les intervalles du fichier de contrôle.
- **Aucun choc nouveau après 2031 :** un tirage garde sa position relative dans la fourchette de chaque pays. L'élargissement des bornes après 2031 vient des erreurs passées des trajectoires prolongées (ci-dessus), qui ne disent rien de leur dépendance entre pays.
- **PIB seulement :** la population reste celle du scénario central.

## Population

- **Jusqu'en 2031 :** celle du pipeline (Banque Mondiale, puis FMI).
- **Ensuite :** prolongée par la croissance de la variante médiane de l'ONU (*World Population Prospects* 2024).
- **Variantes basse et haute :** le rapport des bornes à 80 % de l'ONU à sa médiane, appliqué à la centrale dès la première année projetée. Pour le Canada en 2050 : 42,1 à 51,5 millions, autour de 46,6.
- **Variantes calibrées, à préférer :** `population_millions_basse_calibree` et `…_haute_calibree`. Pour le Canada en 2050 : 42,1 à 57,2 millions.

**Pourquoi calibrer** (`pib.population`). Les révisions de l'ONU de 1998 à 2022, relues dans ses archives, ont été confrontées aux estimations de la révision 2024 :
- **Les bornes de l'ONU sont trop étroites.** Appliquées aux erreurs passées des mêmes pays au même horizon, celles de 2024 n'en contiennent que 19 % à 1 an, 39 % à 5 ans, 54 % à 20 ans, au lieu de 80 %. Elles ignorent notamment les révisions de la population de départ, de l'ordre de 2 % en médiane dès la première année.
- **Pour les grands pays, la population a dépassé les projections.** Pays de plus de 5 millions d'habitants : erreur médiane de −2,0 % à 10 ans, −4,6 % à 20 ans (projeté / estimé − 1). À 20 ans : Royaume-Uni −8 à −10 % selon la révision, Canada −3 à −8 %, France −4 à −6 % ; États-Unis entre −6 et +2,5 %.
- **La calibration.** Chaque réalisé passé est exprimé en demi-largeurs des bornes de l'ONU du pays, à l'horizon. Les 10e et 90e centiles, par classe de taille (plus ou moins de 5 millions) et lissés selon l'horizon, donnent le multiplicateur de chaque côté. Pour les grands pays : côté haut × 3,5 à 5 ans, × 2,5 à 10 ans, × 2 au-delà de 20 ans ; côté bas × 1,9 à 5 ans, × 1 au-delà de 20 ans. Les multiplicateurs ne descendent jamais sous 1 : les révisions évaluables couvrent une période d'immigration forte, qui ne dit rien du risque inverse.
- **Hors échantillon.** Estimées sur les révisions 1998 à 2008, les bornes calibrées contiennent 82 à 87 % des erreurs des révisions 2010 à 2022 ; celles de l'ONU, 25 à 57 %.

| Canada, millions | Centrale | ONU | Calibrées |
|---|---|---|---|
| 2031 | 42,8 | 41,8 – 44,0 | 41,3 – 46,4 |
| 2040 | 44,9 | 42,4 – 47,7 | 42,2 – 51,3 |
| 2050 | 46,6 | 42,1 – 51,5 | 42,1 – 57,2 |

À comparer au PIB par habitant : en 2050, de 59 à 101 % du central pour le Canada. L'incertitude de la population est plus faible, mais elle va dans l'autre sens : vers le haut.

**Limites :**
- **Les horizons de 20 à 25 ans** ne reposent que sur les révisions de 1998 à 2004, toutes prises de court par l'immigration des années 2000 et 2010.
- **Pas de dépendance avec le PIB.** Une population plus forte que prévu par l'immigration accroît aussi le PIB total ; les scénarios combinent les deux sans lien.
- **Deux classes de taille seulement,** sans groupe de revenu : les révisions de la population de départ, qui dominent les erreurs des petits pays, se distinguent mal par le revenu.

## Pour la méthode de Kenza

- **Utiliser le PIB en volume par habitant.** Le prix normalisé rapporte un prix au revenu ; en volume, il ne mêle pas l'inflation à la croissance du revenu. La variante indexée, qui remplace le prix par `PIB_ref / PIB_par_habitant(t)`, n'a besoin que d'un rapport, sans unité : le volume convient directement. Le dollar courant n'est fourni que jusqu'en 2031, pour la continuité.
- **Combiner les dimensions au besoin.** Les scénarios de PIB et les variantes de population sont indépendants : `bas` × population basse donne le cas le plus défavorable. Préférer les variantes de population calibrées, plus larges que celles de l'ONU.
- **Pour plusieurs marchés à la fois,** passer par les trajectoires conjointes (`scenarios_pib_tirages.csv`, ci-dessus) plutôt que d'additionner les bornes de chaque pays.
- **Pour une crise ponctuelle**, `crise_mondiale` donne le niveau ; la pire année médiane (−3,7 % pour le Canada) et le profil de 2008 (`docs/cas_crise_2008.md`) donnent la forme de la trajectoire.
- **La zone de chalandise n'est pas le pays.** Ces séries sont nationales ; le PIB métropolitain (Statistique Canada, tableau 36-10-0468-01) reste la piste identifiée par la feuille de route du projet trafic.

## Limites

- **Au-delà de 2031, les fourchettes sont tirées des erreurs passées, avec trois réserves :**
  - **Extrapolation au-delà de 16 ans.** Les lois sont ajustées jusqu'à 16 ans, dernier horizon qui compte au moins 10 années d'édition. Au-delà, donc de 2043 à 2050, elles sont extrapolées. Les quantiles observés à 20 ans, sur 6 années d'édition seulement, toutes traversées par 2009 et 2020, sont un peu plus étroits que la loi (90e centile de 60 % contre 66 % pour les pays à revenu élevé). Les bornes de ces années-là sont à lire comme indicatives.
  - **Groupe de revenu, pas pays.** Les quantiles sont ceux du groupe connu à la date de chaque édition : le Canada reçoit ceux des pays alors à revenu élevé, dont la Grèce de 2010 ou l'Irlande de 2015.
  - **Un échantillon dominé par 2008-2009.** Pour les pays riches, les éditions évaluables au-delà de 10 ans (1999 à 2009) n'avaient pas vu venir la perte de niveau de 2008-2009. Un haut de fourchette proche de la trajectoire centrale reflète cet épisode ; une période plus favorable l'aurait relevé. Le modèle de long terme de Müller, Stock et Watson (2022) va dans ce sens. Leur intervalle à 67 % pour la croissance moyenne des États-Unis sur 50 ans, de 0,6 à 2,7 % par an, correspond à un écart-type du logarithme du niveau de 0,54, contre 0,34 pour notre loi des pays riches prolongée jusque-là, sans hausse possible. À 25 ans, il correspond à au moins 0,27, contre 0,23 pour la nôtre. Le haut de la fourchette des pays riches est donc probablement trop bas : d'où la variante élargie.
  - **PIB total, appliqué au PIB par habitant.** Les erreurs portent sur le PIB en volume ; l'incertitude de la population est traitée à part, par les variantes de l'ONU.
- **La dérive tient lieu de croissance de long terme** dans la mesure des erreurs : les scénarios passés de l'OCDE ne sont pas archivés.
- **La croissance de long terme de l'OCDE** porte sur le PIB potentiel en parité de pouvoir d'achat ; seule sa croissance est utilisée, appliquée au niveau en dollars de 2015.
- **Rien ne mesure encore l'optimisme éventuel des scénarios de l'OCDE**, comme ce dépôt l'a fait pour le FMI.
