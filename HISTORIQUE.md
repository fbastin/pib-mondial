# Historique du Projet PIB mondial

Journal des défauts corrigés et des choix de méthode, du plus récent au plus ancien.
L'usage courant est décrit dans le `README.md`, la méthode dans `documentation_gdp.pdf`.

---

## 📉 Risque de Récession ; Révisions d'une Édition à l'Autre (30 Septembre 2026)

**Les récessions que la trajectoire ne montre pas.** Le FMI n'annonce presque jamais de recul du PIB au-delà de l'année en cours : à un an, 2,4 % de ses projections sont négatives, contre 14,2 % des croissances réalisées ; il n'avait annoncé que 10 % de ces reculs. Sur les cinq années suivant une édition, un recul était annoncé dans 3 % des cas et en est survenu un dans 45 % (48 % pondéré par le PIB, 49 % pour les vingt premières économies ; 32 % hors des périodes contenant 2009 ou 2020), la pire année à −3,4 % en médiane. L'erreur de niveau porte désormais la pire année projetée et réalisée des horizons 1 à h (`pire_croissance_*`), d'où deux synthèses (`weo_recession_by_horizon_*`, `weo_recession_risk_*`) et une nouvelle section de la page de résultats.

**Une probabilité par pays.** Chaque fourchette reçoit la probabilité d'au moins une année de recul d'ici son horizon (`probabilite_recul_pct`, 2027-2031 aujourd'hui) et la profondeur typique (`pire_annee_mediane_pct`), tirées des mêmes projections comparables : classe de croissance projetée × groupe de revenu. États-Unis et grandes économies avancées : 65 % ; Chine : 46 % ; Inde : 23 %. Prédicteurs comparés sur les éditions 2008-2019, probabilités calculées sur 1990-2007 (score de Brier) : probabilité unique 0,279 ; groupe de revenu 0,274 ; classe de croissance 0,252 ; classe × groupe 0,250 ; fréquence passée des reculs du pays 0,283 et volatilité passée 0,283, moins bonnes qu'une probabilité unique. Le niveau dépend des crises de la période (38 % des cas avant 2008, 56 % après), l'ordre des classes non.

**Ce que corrige chaque édition.** Nouveau module `pib.revisions_weo`, lancé par `produire_rapports.py` après l'évaluation. Les éditions à deux ans et plus de l'année visée ne révisent presque pas (±0,03 point) ; l'édition d'avril de l'année visée retire 0,61 point en moyenne, celle d'octobre 0,32 : le biais optimiste se résorbe dans les dernières éditions (somme des révisions −1,09 point, biais à 5 ans +0,93). Test de Nordhaus : corrélation entre révisions successives de −0,09 à +0,18, légèrement positive près de l'année visée. Sortie `weo_forecast_revisions_*`.

**Ce que change la dernière édition.** Entre les deux dernières éditions archivées (octobre 2025, avril 2026), la croissance cumulée 2024-2030 — ce que retiennent les projections raccordées — change de plus de 2 % en volume pour 52 pays sur 189, de plus de 5 % en dollars pour 64. Les révisions de l'historique (changement d'année de base des prix constants : Inde, Royaume-Uni et 12 autres ; PIB en dollars révisé de plus de 5 % : 10 pays) sont signalées : le raccord les neutralise. Premier essai contrôlé sur l'année de raccord : pour le rapport le plus récent, 2025, encore estimée par l'édition d'octobre 2025, le test signalait 31 pays, prenant des révisions de l'inflation estimée pour des changements de base. Le contrôle porte désormais sur l'année de l'ancienne édition moins deux. Sortie `weo_edition_revisions.csv`.

**Correction.** La calibration des fourchettes rangeait les économies par année visée ; or avril et octobre visent la même année au même horizon, si bien que chaque pays y comptait deux fois et que les « vingt premières économies » n'en comptaient que dix. Le rang se prend désormais par édition. Couverture des vingt premières : 94,0 % au lieu de 93,8 %, conclusion inchangée.

145 tests ; douze mutations, toutes rattrapées.

---

## ↩️ Fourchettes Corrigées ; Efficience des Prévisions (29 Septembre 2026)

**Correction.** Les fourchettes livrées plus tôt dans la journée s'appuyaient sur l'historique propre de chaque pays (dès vingt années visées), au motif qu'il décrivait mieux une grande économie que son groupe de revenu. Le test rétrospectif le dément : calculées sur les éditions 1990-2007, elles ne contenaient que 67 % des erreurs des éditions 2008-2019, pour une cible de 80 %. Le biais d'un pays ne se reproduit pas d'une période à l'autre — corrélation de 0,01 ; la Chine passe de −1,9 à +1,0 point, l'Inde de −0,5 à +1,8 —, et la dispersion à peine (0,23). Le constat mis en avant alors (« Japon, France et Italie : fourchette entièrement sous la projection ») ne tenait pas davantage.

Les fourchettes reposent désormais sur les projections comparables : même classe de croissance cumulée projetée (cinq classes de même effectif) et même groupe de revenu, repli sur la classe seule sous cent cas. Couverture rétrospective : 83 % (94 % pour les vingt premières économies, prudentes ; 78 % pour les pays à faible revenu). Variantes écartées au même test : classe seule (83 %, mais 75 % pour les pays à faible revenu), classe × taille de l'économie (81 %). Le test est refait à chaque exécution (`gdp_projection_bands_calibration.csv`), la page de résultats le cite.

**Efficience.** Ce qui justifie le conditionnement : plus le FMI annonce de croissance, plus il surestime. Pente de Mincer-Zarnowitz (réalisé sur prévu, 1 % extrême retiré de chaque côté) : 0,93 sur l'année en cours, 0,74 à un an, 0,57 à 5 ans. À 5 ans, biais médian de −0,36 point pour le quintile des prévisions les plus modestes, +1,35 pour les plus fortes ; erreur de niveau médiane de +1,7 % à +6,8 % selon la croissance cumulée projetée.

129 tests ; six mutations de la nouvelle méthode, toutes rattrapées.

---

## 🗄️ Avril et Octobre, Prévision Naïve, Croissance Mondiale ; Archive des Éditions (29 Septembre 2026)

Les projections alimentent la prévision du trafic aérien, projet distinct. Côté PIB, trois lectures complètent l'évaluation et une archive prépare la suite.

- **Avril ou octobre.** L'horizon 0 mêlait deux éditions à six mois d'écart : sur l'année en cours, octobre est sans biais (+0,01 point, erreur absolue 1,40), avril penche de +0,35 (2,01). Synthèse `weo_forecast_bias_by_season_*`.
- **Face à une prévision naïve** — la croissance moyenne des années v−5 à v−2, déjà connues du FMI à l'édition v : le FMI est plus proche du réalisé dans 74 % des cas sur l'année en cours, 56 % seulement à 5 ans, où son erreur absolue ne vaut que 18 % de moins. Sortie `weo_forecast_vs_naive_*`.
- **Croissance mondiale** : l'agrégat du FMI, jusque-là écarté, est évalué contre sa seule ré-estimation (+0,56 point à un an, +0,83 à 5 ans). Premier essai contre la Banque Mondiale abandonné : elle agrège le monde aux taux de change, non à parité de pouvoir d'achat, et sa croissance mondiale est inférieure de 0,4 point en moyenne (23 années sur 25) — le biais en aurait été gonflé d'autant. Sortie `weo_world_bias_*`.
- **Archive des éditions** : l'API ne servant que l'édition courante et la précédente, `pib.update_weo_editions` archive désormais chaque édition servie en entier (tous pays, 145 indicateurs, PIB en dollars courants compris) dans `data/raw/weo_archive/`, une fois pour toutes. Premières éditions archivées : `F2025` et `S2026`. De quoi mesurer, édition après édition, les erreurs en dollars courants que la base historique ne permet pas.

121 tests ; sept mutations, toutes rattrapées.

---

## 🎯 PIB Prévu et PIB Réalisé ; Lectures du Biais (29 Septembre 2026)

Question posée : les analyses sont-elles bien fondées ? Pour l'essentiel, oui ; mais l'évaluation des prévisions surinterprétait son chiffre phare, et ne reliait pas ses résultats aux projections que les rapports présentent.

**Le biais de croissance, relu.** « Le FMI surestime la croissance d'environ un point » est une moyenne qui compte chaque pays pour un. À un an, pondéré par le PIB de l'année visée, le biais vaut +0,58 point ; la médiane, +0,34 ; sans 2009 ni 2020, +0,62. Les erreurs d'une même année n'étant pas indépendantes, l'intervalle de confiance est désormais calculé par grappes d'années visées : +0,38 à +1,62 point, soit une erreur type six fois celle qui les supposerait indépendantes. Le biais va de +0,7 point (revenu élevé) à +1,7 (faible revenu). La synthèse par horizon porte ces lectures (`biais_pondere_pib`, `ic95_*`, `biais_hors_recessions_mondiales`), une synthèse par groupe de revenu s'y ajoute, et le graphique d'exactitude montre le biais pondéré.

**PIB prévu et PIB réalisé.** L'analyse manquante : les croissances projetées par chaque édition, enchaînées, comparées aux croissances réalisées enchaînées de même. À 5 ans, le niveau prévu dépasse le réalisé de +4,6 % en médiane (+4,4 % pondéré par le PIB), de plus de 5 % dans 49 % des cas contre 15 % en sens inverse ; de +3,6 % (revenu élevé) à +6,0 % (faible revenu). Nouvelles sorties `weo_level_*` et graphique `gdp_forecast_level_errors.png`. Mesure en volume seulement : la base historique du FMI ne contient que des taux.

**Les projections à l'aune des erreurs passées.** Les projections 2031 (édition d'avril 2026, 5 ans d'horizon) reçoivent une fourchette empirique : 10ᵉ à 90ᵉ centile des erreurs de niveau passées au même horizon, celles du pays s'il en compte sur au moins vingt années visées (169 pays), sinon de son groupe de revenu. Premier essai avec les seuls groupes : les États-Unis recevaient la marge de toutes les économies à revenu élevé (−15 à +7 %), petites économies volatiles comprises, alors que leur propre historique donne −9,7 à +5,0 %. Pour le Japon, la France et l'Italie, la fourchette est entièrement sous la projection. Sorties `gdp_projection_bands.csv` et onglet `Fourchettes_2031` du classeur.

Le groupe de revenu de la Banque Mondiale (classification courante, appliquée à toute la période) est désormais collecté par le pipeline et suit chaque pays jusque dans la synthèse, pour que l'évaluation reste hors ligne. La page de résultats gagne deux sections, dont les commentaires se déduisent des chiffres.

115 tests ; dix mutations des nouvelles analyses, toutes rattrapées.

---

## 🗂️ Réorganisation du Dépôt (29 Septembre 2026)

Les quinze fichiers de code, de notebooks, de tests et de documentation s'entassaient à la racine. Ils sont désormais rangés par nature, historique git conservé (`git mv`) :

| Avant (racine) | Après |
|---|---|
| `http_utils.py`, `fetch_*.py`, `gdp_pipeline.py`, `update_weo_editions.py`, `evaluate_forecasts.py`, `visualize_gdp.py`, `build_results_page.py` | `pib/` — paquet Python, modules lancés par `python -m pib.<module>` |
| `gdp_analysis_notebook*.ipynb`, `create_notebook*.py` | `notebooks/` |
| `test_gdp_pipeline.py` | `tests/` (`pytest.ini` : `testpaths`, `pythonpath`) |
| `documentation_gdp.tex`, `.pdf` | `docs/` |

`produire_rapports.py` reste à la racine, seul point d'entrée ; il lance les étapes comme modules du paquet, qui reste importable quel que soit le répertoire courant. Les notebooks, que Jupyter exécute désormais dans `notebooks/`, retrouvent seuls la racine du dépôt : le notebook Python remonte jusqu'au dossier qui contient `pib/`, le notebook Julia part de l'environnement activé par son noyau (`Project.toml` de la racine). Les messages d'erreur renvoient à `python produire_rapports.py` plutôt qu'à des scripts qui n'existent plus à la racine.

Le README est réordonné — démarrage rapide, organisation du dépôt, utilisation, sources, méthode, livrables, provenance, tests — et corrigé au passage (sources Banque Mondiale « de 1960 à 2024 », venv « hors du dossier Nextcloud »). La documentation LaTeX gagne une section *Organisation du Dépôt*, les deux indicateurs en volume de la Banque Mondiale, qui manquaient à la liste des sources, et un guide couvrant les deux notebooks. Les entrées plus anciennes de ce journal gardent les chemins de leur époque.

---

## 📥 Éditions du WEO depuis l'API SDMX du FMI (29 Septembre 2026)

`WEOhistorical.xlsx` ne se télécharge qu'à la main (403 pour les scripts, y compris sur le lien d'un autre dépôt consulté, `thompalec/Forecasting-IMF-World-Economic-Outlook-using-nowcasts`, qui procède lui aussi manuellement). L'API SDMX du FMI (`api.imf.org`) accepte en revanche les scripts : elle sert l'édition courante (`WEO`) et des archives (`WEO_2025_OCT_VINTAGE`), identiques au classeur (écart nul sur `S2026`, ≤ 0,0005 sur `F2025`), mêmes codes pays.

`update_weo_editions.py` ajoute les éditions absentes du classeur à `data/raw/weo_editions_api.csv` (cumulatif, versionné, classeur prioritaire), sur les horizons −2 à +5 et pour les trois onglets (`NGDP_RPCH`, `PCPIPCH`, `BCA_NGDPD`). Le flux courant n'indique pas son édition : elle est déduite de la plus récente archive et vérifiée par l'horizon servi (édition + 5), faute de quoi le script s'arrête. `produire_rapports.py` le lance à chaque exécution (`--sans-editions-api` pour s'en passer).

Aujourd'hui, le classeur contient déjà les deux éditions servies : rien n'est ajouté. Vérifié en simulant le cas d'octobre — classeur privé de `S2026` : l'API la rétablit, et l'évaluation est identique à celle du classeur complet (78 490 projections, valeurs à 5·10⁻⁷ près, synthèse par horizon identique).

102 tests ; dix mutations de l'horizon et des éditions, toutes rattrapées.

---

## 🔭 Horizon de Prévision Automatique (29 Septembre 2026)

L'API DataMapper renvoie à chaque appel toutes les années de l'édition du WEO — jusqu'en 2031 pour celle d'avril 2026 —, mais le pipeline coupait à `--fcst-end 2030`. Sans cette option, l'horizon est désormais celui de l'édition : la dernière année dont le PIB projeté couvre plus de la moitié des pays. Il avancera d'un an à chaque édition de printemps. 2031 couvre les mêmes 188 pays que 2030 : aucun pays ne perd son rang (183 dans le rapport de référence, 180 dans le plus récent).

Les noms suivent : `gdp_unified_2000_2031.csv`, `CAGR_Prevision_2024_2031_Pct`, `Rank_2031_Forecast`… Les titres et libellés des deux notebooks, qui portaient encore 2030 ou 2024 en dur, suivent désormais les bornes du run ; au passage, `analyze_country` du notebook Python plantait sur un pays sans rang (`int(NaN)`) et affichait des milliards en « M$ ».

---

## 📅 Deux Rapports : Référence et Plus Récent (29 Septembre 2026)

La Banque Mondiale publie 2025 pour 186 pays, mais pas encore pour les Émirats arabes unis (27ᵉ économie), les Bahamas et Aruba. `--end-year 2025` les privait de rang ; `--end-year 2024`, défaut jusque-là, ignorait les données publiées.

Sans `--end-year`, le pipeline choisit désormais la dernière année observée d'après les données et produit jusqu'à deux rapports :

- **Référence** (`data/`, `outputs/`) : parmi les cinq dernières années observées, la plus récente dont les pays sans rang pèsent moins de 0,1 % du PIB des pays classables — 2024, 183 pays classés. Seuil en PIB et non en nombre de pays : un maximum strict aurait retenu 2023 pour le seul Saint-Marin (0,002 % du PIB).
- **Plus récent** (`plus_recent/`) : la dernière année publiée — 2025, 180 pays. N'existe que s'il diffère de la référence ; supprimé dès qu'il devient sans objet, pour ne pas laisser un rapport périmé en place.

Le choix est consigné dans le bloc `rapport` de chaque `extraction_metadata.json`, et chaque page de résultats renvoie vers l'autre rapport. `produire_rapports.py` enchaîne la chaîne complète pour chacun. Vérifié : le rapport de référence est identique, octet pour octet, à celui du code précédent avec `--end-year 2024`, évaluation comprise.

91 tests ; six mutations du mécanisme (seuil ignoré, règle en nombre de pays, rapport périmé conservé, valeurs précoces prises pour une année, frontière de prévision non déplacée, rapports intervertis), toutes rattrapées.

---

## 🔧 Correctifs du 29 Septembre 2026

Une revue du dépôt, menée en exécutant le pipeline sur les données réelles, a mis au jour trois défauts du même type que ceux du 12 août — des valeurs fausses, sans aucune erreur — et plusieurs fragilités.

1. **Écarts de rang calculés sur des ensembles différents.** Chaque rang était calculé sur les pays renseignés dans sa propre colonne. Taïwan, absent de la Banque Mondiale, entrait 22ᵉ au classement 2030 ; le Pakistan, sans projection FMI au-delà de 2025, en sortait. `Rank_Change` était faussé pour 140 pays sur 183 (Belgique −4 au lieu de −3, Iran −16 au lieu de −15), `Ecart_Rang_Nominal_PPA` pour 130 sur 195. Tous les rangs portent désormais sur un même panel : les 183 pays renseignés aux deux dates et sur les deux bases.

2. **Kosovo compté deux fois.** Le FMI code le Kosovo `UVK` (API) ou `KOS` (base historique), la Banque Mondiale `XKX` ; de même `WBG` / `PSE` pour la Cisjordanie et Gaza. La jointure sur le code produisait deux entités. Ces codes sont convertis à la lecture.

3. **Raccord incomplet.** Le facteur du nominal était appliqué à la PPA courante, et le PIB par habitant n'était pas raccordé. D'où des marches à la jonction : PPA du Burundi −46 % en 2025 (le FMI projette +6,9 %), PIB par habitant +121 %. Chaque série a désormais son propre facteur (`Facteur_Raccord_PPA`, `Facteur_Raccord_Par_Habitant`) et ses valeurs FMI en regard.

4. **Évaluation hors croissance du PIB.** La référence Banque Mondiale était toujours la croissance du PIB, y compris pour `--indicateur pcpi_pch` : l'inflation projetée était comparée à la croissance observée. Elle est réservée à `ngdp_rpch`. Pour l'inflation, les moyennes (biais de 900 à 1 900 points, à cause des projections d'hyperinflation du Venezuela) sont doublées de médianes, et le script avertit quand les moyennes sont dominées par des valeurs extrêmes.

5. **Échecs silencieux.** Un indicateur injoignable était signalé puis ignoré, une liste de pays manquante laissait les agrégats (Banque Mondiale : liste de repli incomplète ; FMI : aucun repli) entrer dans les classements, et les scripts sortaient avec le code 0 en cas d'échec. Les requêtes passent par `http_utils.get_json` (trois tentatives), un échec final interrompt le traitement avec un code non nul, et les réponses paginées de la Banque Mondiale sont lues en entier.

6. **Bornes et fichiers.** Une prévision ne commençant pas l'année suivant l'historique laissait le chaînage franchir une année absente : ces bornes sont refusées, et le chaînage s'interrompt sur tout trou. Les scripts en aval choisissaient la série unifiée la plus récemment modifiée (ou la dernière par ordre alphabétique pour les notebooks et les tests) : ils lisent désormais celle que désigne `extraction_metadata.json` (d'où `JSON` dans `Project.toml`). L'onglet Excel des séries et le titre du graphique d'exactitude suivent les données ; les conclusions de la page de résultats sont déduites des chiffres au lieu d'être rédigées d'avance.

7. **Ménage.** Le dossier `forecasts/` (ancien script d'extraction, redondant avec `evaluate_forecasts.py`) est supprimé ; ce journal remplace `SESSION_STATE.md`, dont les sections d'arborescence et de reprise, périmées, doublaient le README. Badge du README pointé vers `fbastin/pib-mondial`.

85 tests (76 unitaires, 9 sur les fichiers produits). Treize mutations, une par défaut corrigé, sont toutes rattrapées. Résultats de l'évaluation quasi inchangés (69 345 projections, 196 pays avec le Kosovo et la Cisjordanie et Gaza).

---

## 🔧 Correctifs du 12 Août 2026

Deux défauts faussaient l'ensemble des livrables analytiques ; les données et visuels ont été régénérés après correction.

1. **Agrégats comptés comme des pays.** `WB_AGGREGATES` était défini mais jamais appliqué, et le filtre `len(country_code) == 3` ne rejetait ni `WLD` ni `OED`. Le classement mondial plaçait *World*, *OECD members* et *IDA & IBRD total* devant les États-Unis (12ᵉ) et la Chine (16ᵉ) ; les graphiques « Top 10 » traçaient donc surtout des agrégats. Le drapeau `is_aggregate` est désormais construit depuis les endpoints de métadonnées des deux API (78 agrégats / 217 pays côté Banque Mondiale, 241 pays côté FMI).

2. **Pays scindés en deux séries.** Les payloads d'indicateurs FMI ne contiennent pas de bloc `countries` : `parse_imf_data` retombait sur le code brut (`USA` au lieu de `United States`). Le pivot sur `(code, nom)` produisait alors deux lignes par pays — l'une sans prévision, l'autre sans historique — d'où un **PIB 2030, un CAGR prévisionnel et un rang 2030 vides pour toutes les grandes économies**, et des séries dédoublées dans le dashboard. Les libellés proviennent maintenant de `/api/v1/countries` et la jointure se fait sur le seul code ISO.

3. **Fichiers intermédiaires absents.** `gdp_pipeline.py` n'écrivait ni le JSON brut FMI ni les CSV par source, pourtant documentés. Il les enregistre désormais.

**Environnement** : venv à `~/.venvs/gdp` (hors dossier Nextcloud). Le `python3` système du WSL n'a aucune des dépendances.

---

## 🎯 Évaluation des Prévisions d'Époque (12 Août 2026)

Source apportée par l'utilisateur : la **WEO Historical Forecasts Database** du FMI (`data/raw/WEOhistorical.xlsx`), qui consolide toutes les éditions depuis 1990 — bien meilleure que l'approche envisagée initialement (lire une centaine de fichiers d'éditions séparés). Le lecteur de millésimes individuels a donc été supprimé et remplacé.

- **Structure** : 73 éditions (S/F 1990-2026), 201 entités, années visées 1988-2031, horizons **−2 à +5**. L'horizon se déduit de l'écart entre l'année visée et l'édition ; les valeurs d'horizon négatif sont des ré-estimations du passé et non des prévisions.
- **Deux références de comparaison** calculées côte à côte plutôt qu'arbitrées : la ré-estimation du FMI un an après (référence retenue — juger une prévision sur des révisions ultérieures la pénaliserait pour une information hors de sa portée) et la série observée de la Banque Mondiale.
- **Résultat** sur 69 169 projections et 194 pays : biais de **+0,18 point sur l'année en cours**, puis **+1,0 point dès l'horizon 1**, stable jusqu'à 5 ans, tandis que l'erreur absolue moyenne passe de 1,70 à 3,04 points. Par année visée : +7,3 points d'erreur médiane pour 2020, +3,8 pour 2009, rebond 2021 sous-estimé. La conclusion tient avec les deux références.
- Le classeur contient aussi `pcpi_pch` (inflation) et `bca_gdp_bp6` (balance courante), accessibles par `--indicateur`.

Nouveau visuel `gdp_forecast_accuracy.png`, section dédiée dans la page de résultats, provenance dans `data/raw/LISEZ-MOI-WEOhistorical.md`. 61 tests, dont 12 sur cette base ; les cinq mutations correspondantes sont rattrapées — dont une qui ne l'était pas au premier essai (le choix de la référence à un an n'était pas distinguable faute de ré-estimation à deux ans dans l'échantillon ; la fixture a été complétée).

**Note** : `forecasts/` contient encore le script d'extraction d'origine, son CSV intermédiaire et un venv. Le classeur source en a été déplacé vers `data/raw/` ; le reste est superflu et peut être supprimé — je ne l'ai pas fait, le venv étant votre environnement de travail. *(Dossier supprimé le 29 septembre 2026.)*

---

## 🔗 Recouvrement des Sources, Raccord, Évaluation (12 Août 2026)

Les deux jeux couvraient des périodes disjointes par construction : `fetch_forecast_gdp.py` filtrait les données FMI sur le seul horizon de prévision, alors que le WEO couvre **1980-2031**. Quarante-cinq ans étaient téléchargés puis jetés à chaque exécution.

1. **Recouvrement** : les estimations FMI des années observées sont conservées (`GDP_Nominal_FMI_Billions_USD`, `Ecart_Sources_Pct`). La Banque Mondiale reste la référence sur ces années — les valeurs FMI comparent, ne substituent pas.

2. **Raccord** (`splice_forecast_levels`) : les deux sources concordent au centième de pourcent pour la plupart des pays (écart médian 0,03 % en 2024) mais divergent pour une quinzaine. Juxtaposer l'observation de l'une et la projection de l'autre fabriquait une croissance inexistante — **16 pays sautaient de plus de 5 points**, le Soudan changeant de signe (−20 % affiché au lieu de +36 % projeté), le Burundi affichant +128 % au lieu de +43 %. Les niveaux projetés sont rebasés sur le dernier niveau observé, ce qui conserve la dynamique du FMI. Après raccord, la croissance livrée à la jonction reproduit exactement celle du FMI pour les 188 pays comparables (écart maximal 0,000000 point).

3. **Évaluation des prévisions** (`evaluate_forecasts.py`) — *approche remplacée le jour même par la WEO Historical Forecasts Database (voir plus haut) ; `data/raw/vintages/` n'existe plus* : l'API ne servant que le millésime courant, la qualité des prévisions ne peut s'apprécier qu'avec les éditions d'époque. Le site du FMI répond 403 aux scripts ; les fichiers se déposent à la main dans `data/raw/vintages/` (voir le `LISEZ-MOI.md`). Le lecteur s'appuie sur `Estimates Start After`, seule colonne distinguant projection et estimation, et refuse tout fichier qui en manque.

Nouveau visuel : `gdp_source_discrepancy_2024.png` (écart de mesure et marche évitée). 57 tests désormais, dont 11 sur le recouvrement, le raccord et la lecture des millésimes ; les cinq mutations correspondantes sont toutes rattrapées.

**Limite assumée** : le lecteur de millésimes est validé contre un fichier synthétique reproduisant le format réel (tabulé sous `.xls`, UTF-16, milliers séparés, `n/a`, pied de page), pas contre un téléchargement authentique — inaccessible depuis cet environnement.

---

## 📄 Page de Résultats Pilotée par les Données (12 Août 2026)

`build_results_page.py` génère `outputs/resultats_gdp.html` : tableaux lus dans `data/processed/`, graphiques inlinés en base64 depuis `outputs/`, faits saillants du texte recalculés à chaque build.

Motif : la première version de cette page portait ses chiffres en dur, dans un script hors du projet. Elle aurait affiché d'anciennes valeurs dès le run suivant, sans le signaler — le défaut même que le pipeline s'attache à éliminer. Deux garde-fous ajoutés au passage : les intitulés de colonnes sont reconstruits depuis les bornes du run (erreur explicite s'ils ne correspondent pas aux données), et les pays cités dans les commentaires sont tirés des lignes réellement affichées, pour qu'aucun texte ne mentionne un pays absent du tableau qu'il accompagne.

Un graphique manquant produit un avertissement et l'omission de sa section, sans faire échouer la construction.

---

## 🔧 Paramétrage, Provenance, Ménage (12 Août 2026)

1. **Le paramétrage des années était en trompe-l'œil.** Le README documentait `--start-year 1995`, mais les années de référence étaient figées en aval : nom du fichier unifié, colonnes de synthèse (`GDP_2024_*`, `CAGR_..._2000_2024_Pct`), frontière historique/prévision et bornes d'axe des graphiques. Conséquence : `--end-year 2023` ou `--fcst-end 2028` vidait **toute** la synthèse — colonnes introuvables, donc PIB, CAGR et rangs `NaN`, sans erreur. Même mode de défaillance silencieuse que les bugs précédents.

   Corrigé de bout en bout : `reference_years()` dérive les années des bornes, les noms de colonnes les portent, `visualize_gdp.py` les redétecte via `detect_years()`, et les deux notebooks reconstruisent les noms de colonnes au chargement (`C_CAGR_H`, `C_RANK_PPA`…). Ajout de `--data-dir` / `--output-dir` aux deux CLI.

   Vérifié : un run `1995-2023 / 2024-2028` produit `gdp_unified_1995_2028.csv`, des colonnes remplies (204/217 pour le PIB 2023), des graphiques avec frontière 2023 et axe 1995-2028 ; le notebook Python s'exécute dessus sans erreur. Le run par défaut produit exactement les mêmes noms de colonnes et valeurs qu'avant.

2. **Provenance** : chaque exécution écrit `data/extraction_metadata.json` — date d'extraction, bornes, indicateurs, volumes, couverture par colonne, et surtout le `lastupdated` de l'API Banque Mondiale (millésime réel des séries, ici 2026-07-13). Le FMI n'expose pas le millésime de son WEO ; c'est signalé explicitement dans le fichier.

3. **Ménage** : `jupyter` et `nbconvert` ajoutés à `requirements.txt` (le README demandait d'ouvrir les notebooks sans les lister). Les auxiliaires LaTeX (`.aux`, `.log`, `.out`, `.toc`) sont sortis du dossier synchronisé — compilation vers `build/`, seul le PDF reste à la racine. `__pycache__` supprimé.

4. **Tests des invariants** (`test_gdp_pipeline.py`, 38 tests, sans réseau) : les propriétés que les défauts rencontrés violaient sans lever d'erreur — agrégats hors classement, un libellé par code ISO, chaînage dont la croissance implicite égale le taux FMI, interruption sur année manquante, colonnes suivant les bornes du run, rangs cohérents avec leurs niveaux, CAGR `NaN` si non calculable. Les tests marqués `donnees` contrôlent les CSV produits et se sautent en leur absence.

   **Validés par mutation** : chacun des six défauts a été réintroduit dans une copie du code pour vérifier que la suite échoue bien. Les six sont rattrapés — un test qui ne tombe jamais ne garde rien.

---

## 💱 Volet PIB en Volume (12 Août 2026)

Les CAGR du projet étaient calculés sur le PIB **nominal en USD courants**, qui mélange croissance réelle, inflation et change. Un volet en volume a été ajouté.

- **Collecte** : deux indicateurs Banque Mondiale supplémentaires — `NY.GDP.MKTP.KD` (prix constants 2015) et `NY.GDP.MKTP.PP.KD` (PPA constants 2021).
- **Prévisions** : le FMI ne publie qu'un taux (`NGDP_RPCH`), pas un niveau. `extend_real_series()` chaîne donc les niveaux 2025-2030 à partir du dernier point observé ; une année manquante interrompt le chaînage au lieu d'extrapoler. 2 219 valeurs reconstituées.
- **Synthèse** : colonnes `GDP_Reel_*`, `CAGR_Reel_*` et `Ecart_Nominal_Reel_2000_2024_Pts` (nominal − réel, en points).
- **Visuels** : `gdp_nominal_vs_real_cagr_top15.png` (segments reliant les deux mesures) et `gdp_nominal_vs_real_trajectories.png` (deux panneaux).
- **Notebooks** : nouvelle section 7 dans les deux versions, `analyze_country` affiche désormais les deux lectures.

Résultats saillants sur 2000-2024 : Japon −0,77 % nominal / +0,65 % en volume (le seul écart négatif du Top 15, dû au yen), Russie 9,3 % / 3,1 %, Chine 12,0 % / 8,1 %, États-Unis 4,5 % / 2,1 %. Couverture : 199 pays sur 216 en volume pour 2024, 183 pour 2030.

### Volet niveaux : parité de pouvoir d'achat

La correction du change sur la croissance ne rend pas les **niveaux** comparables — le volume reste converti au taux de l'année de base. Les niveaux et rangs s'appuient donc aussi sur `GDP_Real_PPP_Billions_Intl` ($ internationaux constants 2021) : colonnes `GDP_PPA_*`, `Rank_PPA_2024` / `Rank_PPA_2030`, `Ecart_Rang_Nominal_PPA_2024`.

Le classement 2024 se réordonne : Chine 1ʳᵉ (devant les États-Unis), Inde 3ᵉ (au lieu de 5ᵉ), Russie 4ᵉ (10ᵉ), Indonésie 8ᵉ (16ᵉ), Turquie 12ᵉ (17ᵉ) ; Canada −6 rangs, Royaume-Uni −4, Allemagne et Italie −3. Visualisé par `gdp_ranking_nominal_vs_ppp_2024.png`.

Aucune base n'est « la bonne » : le taux de marché mesure le poids financier international, la PPA le volume de production disponible localement.

---

## 🔷 Version Julia du Notebook (12 Août 2026)

`gdp_analysis_notebook_julia.ipynb` transpose le notebook Python à l'identique (mêmes 7 sections, mêmes données) :

| Étape | Python | Julia |
|---|---|---|
| Données | pandas | CSV.jl + DataFrames.jl |
| Graphiques statiques | matplotlib / seaborn | Plots.jl, backend GR |
| Graphique interactif | Plotly Express | Plots.jl, backend plotly (PlotlyBase.jl) |

- Environnement décrit par `Project.toml` (`Pkg.activate(".")` puis `Pkg.instantiate()`), noyau IJulia lancé avec `--project=@.` — d'où la nécessité de démarrer Jupyter depuis le dossier du projet.
- Générateur : `create_notebook_julia.py`, calqué sur `create_notebook.py`.
- La collecte reste côté Python : le notebook Julia lit `data/processed/`, il n'appelle aucune API.

**PlotlyKaleido.jl a également été écarté.** Ajouté un temps pour supprimer un avertissement de Plots et permettre l'export statique des figures plotly, il lance un sous-processus Chromium qui, lorsqu'il ne démarre pas (machine chargée), fait **échouer la cellule** au lieu de dégrader silencieusement. Mauvais compromis pour un avertissement cosmétique : l'avertissement est désormais assumé et documenté dans le notebook. Conséquence : la figure interactive ne produit plus de PNG, seulement le rendu HTML/JSON plotly.

**PlotlyJS.jl a été écarté après essai.** Son affichage transite par WebIO, dont les messages corrompent la signature HMAC du noyau IJulia : la cellule interactive interrompait la connexion (`ValueError: Invalid Signature`) et bloquait toute la suite du notebook. Le backend `plotly()` de Plots.jl, adossé à PlotlyBase.jl, donne le même graphique interactif sans WebIO ni Blink — le noyau reste stable de bout en bout. Le notebook bascule donc `plotly()` en section 4 puis revient à `gr()` pour les sections 5 et 6.

Autres points d'adaptation : les `missing` sont convertis en `NaN` (helper `tonum`) car Plots ne les accepte pas ; la heatmap est construite comme une matrice pays × années avec annotations posées une à une, `sns.heatmap` n'ayant pas d'équivalent direct.

**Piège Plots à connaître** : avec `orientation = :h`, Plots déduit les bornes de l'axe vertical des **valeurs** des barres, pas de leurs positions. Tant que les deux grandeurs ont le même ordre (CAGR 0–12 contre positions 1–15) le graphique paraît correct par coïncidence ; dès qu'elles divergent (PIB en milliers de milliards contre positions 1–12), l'axe s'écrase et toutes les barres se superposent sur une ligne — sans qu'aucune erreur ne soit levée. Les deux graphiques à barres horizontales fixent donc `ylims = (0.4, nrow + 0.6)` explicitement.
