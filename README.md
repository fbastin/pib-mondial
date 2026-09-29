# Traitement et Analyse des Données de PIB (GDP) - Historique & Prévisions

[![Tests](https://github.com/fbastin/pib-mondial/actions/workflows/tests.yml/badge.svg)](https://github.com/fbastin/pib-mondial/actions/workflows/tests.yml)

Ce projet permet de collecter, traiter, analyser et visualiser automatiquement les données historiques du PIB (GDP) par pays sur une période de **25 ans (2000–2024)** ainsi que les **prévisions de PIB jusqu'en 2030**.

## 📊 Sources de Données API

1. **Banque Mondiale (World Development Indicators - WDI)** :
   - Données historiques officielles de 1960 à 2024 (25 ans inclus par défaut : 2000-2024).
   - Indicateurs à prix courants : PIB Nominal (USD), Taux de croissance annuel (%), PIB par habitant, PIB PPA.
   - Indicateurs en volume : PIB à prix constants 2015 (`NY.GDP.MKTP.KD`), PIB PPA à prix constants 2021 (`NY.GDP.MKTP.PP.KD`).
   - Accès API libre et direct sans clé d'API.

2. **Fonds Monétaire International (FMI - World Economic Outlook)** :
   - Prévisions macroéconomiques et projections officielles jusqu'en 2030 (horizon 2025-2030).
   - Indicateurs : `NGDPD` (PIB nominal en Milliards USD), `NGDP_RPCH` (Croissance réelle %), `PPPGDP` (PIB PPA), `NGDPDPC` (PIB/habitant).
   - Accès API libre (IMF DataMapper API v1).

---

## 📁 Architecture du Projet

```
pib-mondial/
├── data/                               # Données brutes et transformées
│   ├── extraction_metadata.json        # Provenance du dernier run : date, bornes, millésimes, volumes
│   ├── raw/
│   │   ├── gdp_imf_weo_raw.json        # Données brutes FMI WEO JSON
│   │   ├── WEOhistorical.xlsx          # Prévisions d'époque, toutes éditions depuis 1990 (versionné)
│   │   └── LISEZ-MOI-WEOhistorical.md  # Provenance et structure de ce classeur
│   ├── processed/
│   │   ├── gdp_historical_2000_2024.csv # Données historiques Banque Mondiale
│   │   ├── gdp_forecast_2025_2030.csv   # Prévisions FMI 2025-2030
│   │   ├── gdp_unified_2000_2030.csv    # Série temporelle unifiée (2000-2030)
│   │   ├── gdp_country_summary.csv      # Synthèse par pays, CAGR & classements
│   │   ├── weo_forecast_evaluation_<indicateur>.csv # Une ligne par projection d'époque
│   │   └── weo_forecast_bias_<indicateur>.csv       # Biais et erreurs par horizon
│   └── plus_recent/                    # Rapport sur la dernière année publiée, s'il diffère
│       ├── extraction_metadata.json
│       └── processed/
├── outputs/                            # Livrables Excel & Visualisations
│   ├── gdp_master_dataset.xlsx         # Classeur Excel multi-onglets complet
│   ├── gdp_top10_trajectories_2000_2030.png # Graphique HD trajectoires Top 10
│   ├── gdp_cagr_comparison_top15.png   # Graphique HD comparaison CAGR
│   ├── gdp_nominal_vs_real_cagr_top15.png   # Écart croissance nominale / volume
│   ├── gdp_nominal_vs_real_trajectories.png # Trajectoires prix courants vs volume
│   ├── gdp_ranking_nominal_vs_ppp_2024.png  # Classement mondial : marché vs PPA
│   ├── gdp_source_discrepancy_2024.png # Écart entre sources et marche évitée
│   ├── gdp_forecast_accuracy.png       # Exactitude des prévisions FMI depuis 1990
│   ├── gdp_dashboard_interactive.html  # Tableau de bord interactif HTML (Plotly)
│   ├── resultats_gdp.html              # Page de résultats autonome
│   └── plus_recent/                    # Mêmes livrables pour le rapport le plus récent
├── produire_rapports.py                # Chaîne complète, pour chaque rapport
├── fetch_historical_gdp.py             # Collecte historique (Banque Mondiale)
├── fetch_forecast_gdp.py               # Collecte des prévisions (FMI)
├── http_utils.py                       # Requêtes HTTP communes : nouvelles tentatives, échec explicite
├── gdp_pipeline.py                     # Pipeline maître d'unification et d'analyse
├── evaluate_forecasts.py               # Évaluation des prévisions d'époque
├── visualize_gdp.py                    # Générateur de graphiques et dashboard
├── build_results_page.py               # Page de résultats pilotée par les données
├── gdp_analysis_notebook.ipynb         # Notebook Jupyter d'analyse (Python)
├── gdp_analysis_notebook_julia.ipynb   # Notebook Jupyter d'analyse (Julia)
├── create_notebook.py                  # Générateurs des deux notebooks
├── create_notebook_julia.py
├── Project.toml / Manifest.toml        # Environnement Julia (CSV, DataFrames, JSON, Plots, PlotlyBase)
├── test_gdp_pipeline.py                # Tests des invariants (pytest.ini, CI GitHub Actions)
├── documentation_gdp.tex / .pdf        # Documentation technique
├── HISTORIQUE.md                       # Journal des défauts corrigés et des choix de méthode
├── requirements.txt                    # Dépendances Python
└── README.md                           # Documentation complète
```

---

## 🚀 Guide d'Utilisation

### 1. Installation des Dépendances

```bash
python3 -m venv ~/.venvs/gdp
~/.venvs/gdp/bin/pip install -r requirements.txt
```

Les commandes ci-dessous supposent ce venv actif (`source ~/.venvs/gdp/bin/activate`). Il est délibérément créé **hors du dossier Nextcloud** pour ne pas synchroniser les dépendances.

### 2. Exécution du Pipeline Complet (Recommandé)

Une commande enchaîne la collecte, l'unification des séries, le classeur Excel, l'évaluation des prévisions, les graphiques et la page de résultats, pour chaque rapport produit (voir *Deux rapports*) :

```bash
python produire_rapports.py
```

Elle transmet ses bornes à `gdp_pipeline.py`, qui peut aussi être lancé seul (collecte, séries et Excel uniquement) :

```bash
python gdp_pipeline.py
```

Arguments personnalisables :
- `--start-year` : Année de début historique (par défaut: `2000`)
- `--end-year` : Dernière année observée (par défaut : choisie d'après les données, avec un second rapport sur la dernière année publiée si elle diffère ; imposée, elle donne un rapport unique)
- `--fcst-start` : Année de début prévision, avec `--end-year` seulement (obligatoirement `--end-year` + 1)
- `--fcst-end` : Année de fin prévision (par défaut: `2030`)
- `--data-dir` / `--output-dir` : Dossiers de sortie (par défaut: `data` et `outputs`)

*Exemple pour un historique de 30 ans (1995-2024) :*
```bash
python gdp_pipeline.py --start-year 1995
```

**Les bornes se propagent partout.** Le nom du fichier unifié (`gdp_unified_1995_2030.csv`), les colonnes de synthèse (`CAGR_Historique_1995_2024_Pct`), l'onglet Excel des séries, la frontière historique/prévision des graphiques et les titres suivent les années demandées. Les scripts en aval et les deux notebooks lisent la série du dernier run d'après `data/extraction_metadata.json` (voir *Provenance*) ; aucun n'a d'année codée en dur.

**Un échec interrompt tout.** Chaque requête est retentée trois fois. Si une source ou un indicateur reste injoignable, ou si les bornes sont incohérentes (prévision qui ne suit pas immédiatement l'historique), le script s'arrête avec un code de sortie non nul, sans rien écrire : `gdp_pipeline.py && visualize_gdp.py` n'enchaîne jamais sur des données partielles ou sur celles d'un run précédent.

### 3. Exécution Individuelle des Scripts

- **Récupérer uniquement l'historique** :
  ```bash
  python fetch_historical_gdp.py --start-year 2000 --end-year 2024
  ```

- **Récupérer uniquement les prévisions** :
  ```bash
  python fetch_forecast_gdp.py --forecast-start 2025 --forecast-end 2030
  ```

- **Générer les graphiques et le dashboard interactif** (pour le rapport le plus récent : `--data-dir data/plus_recent --output-dir outputs/plus_recent`) :
  ```bash
  python visualize_gdp.py [--data-dir data] [--output-dir outputs]
  ```

- **Construire la page de résultats** (`outputs/resultats_gdp.html`, autonome) :
  ```bash
  python build_results_page.py [--pays FRA]
  ```
  Tableaux lus dans `data/processed/`, graphiques inlinés depuis `outputs/`, faits saillants recalculés. Aucune valeur n'y est saisie à la main : la page suit les données au lieu d'en figer un instantané.

- **Recompiler la documentation LaTeX** (les fichiers auxiliaires restent dans `build/`) :
  ```bash
  mkdir -p build && pdflatex -output-directory=build documentation_gdp.tex
  cp build/documentation_gdp.pdf .
  ```

### 4. Notebooks d'Analyse

Deux notebooks couvrent les mêmes sept sections (chargement, Top 10, trajectoires interactives, comparaison des CAGR, carte de chaleur, interrogation par pays) et lisent les mêmes CSV produits par le pipeline.

- **Python** — `jupyter notebook gdp_analysis_notebook.ipynb` (pandas, matplotlib/seaborn, Plotly).
- **Julia** — `gdp_analysis_notebook_julia.ipynb` (CSV.jl, DataFrames.jl, Plots.jl avec bascule GR ↔ plotly). Préparation de l'environnement, décrit par `Project.toml` :

  ```julia
  using Pkg
  Pkg.activate(".")
  Pkg.instantiate()
  Pkg.add("IJulia")     # noyau Jupyter, si absent
  using IJulia; notebook(dir = ".")
  ```

  Le noyau IJulia démarre avec `--project=@.` : lancer Jupyter **depuis le dossier du projet** pour que `Project.toml` soit bien pris en compte.

La collecte des données reste côté Python : les notebooks n'appellent aucune API, ils exploitent `data/processed/`.

Les deux notebooks sont regénérables par leur script : `python create_notebook.py` et `python create_notebook_julia.py`.

---

## 🔗 Recouvrement des Sources et Raccord

Le WEO du FMI couvre **1980 à l'horizon de projection**, pas seulement les années à venir. Le pipeline conserve ses estimations des années observées : chaque année historique porte donc la valeur Banque Mondiale *et* la valeur FMI.

| Colonne | Contenu |
|---|---|
| `GDP_Nominal_FMI_Billions_USD` | Niveau FMI brut, sur toute la période qu'il couvre |
| `GDP_PPP_FMI_Billions_USD`, `GDP_Per_Capita_FMI_USD` | Idem pour la PPA courante et le PIB par habitant |
| `Ecart_Sources_Pct` | (FMI − Banque Mondiale) / Banque Mondiale sur le nominal, années observées seulement |
| `Facteur_Raccord` | Rapport appliqué aux niveaux nominaux projetés (constant par pays) |
| `Facteur_Raccord_PPA`, `Facteur_Raccord_Par_Habitant` | Rapports propres à la PPA courante et au PIB par habitant |

**La Banque Mondiale reste la référence sur les années observées** : les valeurs FMI servent de point de comparaison, jamais de substitution.

### Pourquoi un raccord

Les deux institutions concordent au centième de pourcent pour la plupart des pays (écart médian 0,03 % en 2024), mais divergent nettement pour une quinzaine. Juxtaposer l'observation de l'une et la projection de l'autre fabrique alors une croissance qui n'existe pas :

| | Sans raccord | Dynamique réelle du FMI |
|---|---|---|
| Burundi 2025 | +127,7 % | +43,0 % |
| Turkménistan 2025 | +74,9 % | +12,7 % |
| Soudan 2025 | **−20,0 %** | **+36,2 %** |

Le raccord conserve la dynamique du FMI et le niveau de la Banque Mondiale — `niveau[y] = observé[base] × FMI[y] / FMI[base]` — soit la même logique que le chaînage déjà appliqué aux volumes. Après raccord, la croissance livrée à la jonction reproduit exactement celle projetée par le FMI, pour les 189 pays comparables.

**Un facteur par série.** Les deux institutions ne divergent pas du même rapport sur chaque mesure : écart médian de 0,03 % sur le nominal, 0,3 % sur la PPA courante, 1,2 % sur le PIB par habitant. Chacune reçoit donc son propre facteur. Appliquer à la PPA celui du nominal recréait la marche que le raccord supprime (Burundi −46 % en 2025 au lieu des +6,9 % projetés par le FMI, Soudan +95 % au lieu de +6,2 %).

Visualisé par `gdp_source_discrepancy_2024.png`.

> **Ce que ce recouvrement ne fait pas.** L'API DataMapper ne sert que le millésime courant du WEO : sa valeur pour 2020 est l'estimation actuelle du FMI, pas ce qu'il projetait en 2018. La comparaison mesure donc un écart **entre institutions**, pas la qualité des prévisions. Pour cela, voir la section suivante.

---

## 🎯 Évaluer la Qualité des Prévisions

Mesurer si les prévisions étaient bonnes suppose les publications **d'époque**. Le FMI les consolide dans la *WEO Historical Forecasts Database* : 73 éditions depuis 1990, 201 entités, horizons −2 à +5. Le fichier se télécharge manuellement (le site refuse les scripts) et se dépose dans `data/raw/WEOhistorical.xlsx` — voir `data/raw/LISEZ-MOI-WEOhistorical.md`.

```bash
python evaluate_forecasts.py                        # croissance du PIB réel
python evaluate_forecasts.py --indicateur pcpi_pch  # inflation
```

L'horizon se déduit de l'écart entre l'année visée et l'édition qui la projette. Les valeurs d'horizon négatif sont des **ré-estimations du passé**, pas des prévisions, et sont écartées de l'évaluation.

### Le résultat, sur 69 345 projections et 196 pays

| Horizon | Biais moyen | Erreur absolue moyenne |
|---|---|---|
| 0 (année en cours) | +0,18 pt | 1,70 pt |
| 1 an | **+1,00 pt** | 2,74 pt |
| 3 ans | +1,01 pt | 2,95 pt |
| 5 ans | +0,93 pt | 3,04 pt |

Le FMI est quasiment sans biais sur l'année en cours, puis **surestime la croissance d'environ un point dès qu'il projette au-delà** — un biais stable quel que soit l'horizon, tandis que la dispersion, elle, continue de croître. La conclusion tient avec les deux références de comparaison (ré-estimation du FMI à un an, ou série Banque Mondiale), ce que le script calcule côte à côte plutôt que d'arbitrer.

Par année visée, les récessions ressortent nettement : erreur médiane de **+7,3 points pour 2020**, +3,9 pour 2009. Le rebond de 2021 est symétriquement sous-estimé. Visualisé par `gdp_forecast_accuracy.png`.

Les codes propres au classeur (`KOS` pour le Kosovo, `WBG` pour la Cisjordanie et Gaza) sont convertis vers ceux de la Banque Mondiale, faute de quoi ces territoires seraient écartés comme inconnus.

### Autres indicateurs : lire les médianes

La référence Banque Mondiale n'existe que pour la croissance du PIB : pour `pcpi_pch` et `bca_gdp_bp6`, seule la ré-estimation du FMI sert de référence.

Pour l'inflation, les moyennes ne décrivent pas l'erreur typique. Quelques projections d'hyperinflation (le Venezuela à 10 000 000 %) portent le biais moyen au-delà de 1 600 points à un an, quand la médiane reste à −0,1 point. La synthèse fournit donc aussi `mediane` et `erreur_absolue_mediane`, et le script avertit dès que l'erreur absolue moyenne dépasse dix fois la médiane.

---

## 💱 Nominal ou Volume : Corriger l'Effet Change

Le PIB nominal en USD courants mélange croissance réelle, inflation et mouvements de change. Les CAGR nominaux ne sont donc pas comparables d'un pays à l'autre en l'état.

Le pipeline produit en parallèle une lecture **en volume** (USD constants 2015), et l'écart entre les deux :

| Colonne | Contenu |
|---|---|
| `GDP_Real_Billions_USD` | PIB à prix constants 2015 (série continue 2000-2030) |
| `GDP_Real_PPP_Billions_Intl` | PIB PPA à prix constants 2021 |
| `CAGR_Reel_Historique_2000_2024_Pct` | Croissance annuelle en volume, observée |
| `CAGR_Reel_Prevision_2024_2030_Pct` | Croissance annuelle en volume, projetée |
| `Ecart_Nominal_Reel_2000_2024_Pts` | Nominal − réel : la part d'inflation et de change |

Le FMI ne publiant qu'un **taux** de croissance réelle (`NGDP_RPCH`) et non un niveau, les valeurs en volume 2025-2030 sont chaînées à partir du dernier point observé en 2024. Une année de croissance manquante interrompt le chaînage plutôt que d'extrapoler.

Quelques écarts sur 2000-2024 : Japon −0,77 % nominal contre +0,65 % en volume (yen déprécié), Russie 9,3 % contre 3,1 %, Chine 12,0 % contre 8,1 %.

### Comparer des niveaux : la parité de pouvoir d'achat

Corriger la **croissance** ne suffit pas pour comparer des **niveaux** : le PIB en volume reste converti au taux de change de l'année de base. Le classement par niveau s'appuie donc en parallèle sur `GDP_Real_PPP_Billions_Intl` ($ internationaux constants 2021) :

| Colonne | Contenu |
|---|---|
| `GDP_PPA_2024_Billion_Intl_2021` | Niveau à PPA, prix constants (idem 2000 et 2030) |
| `Rank_PPA_2024` / `Rank_PPA_2030` | Rang mondial sur cette base |
| `Ecart_Rang_Nominal_PPA_2024` | Rangs gagnés en passant du taux de marché à la PPA |

Le classement 2024 change sensiblement : la Chine passe 1ʳᵉ devant les États-Unis, l'Inde 3ᵉ (au lieu de 5ᵉ), la Russie 4ᵉ (au lieu de 10ᵉ), l'Indonésie 8ᵉ (au lieu de 16ᵉ) ; à l'inverse le Canada recule de 6 rangs et le Royaume-Uni de 4.

> **Portée du rang PPA projeté.** Les niveaux à parité de 2025-2030 étant chaînés depuis le dernier point observé, `Rank_PPA_2030` suppose les facteurs de conversion de 2021 inchangés sur tout l'horizon — alors qu'ils suivent les niveaux de prix relatifs. Ce classement projeté extrapole donc une structure de prix figée ; son incertitude dépasse celle des prévisions de croissance dont il dérive. Le rang PPA de l'année observée (`Rank_PPA_2024`) n'a pas cette limite.

---

## 📅 Deux rapports : référence et plus récent

La Banque Mondiale publie une nouvelle année pays par pays. En septembre 2026, 2025 est déjà disponible pour 186 pays, mais pas pour les Émirats arabes unis (27ᵉ économie), les Bahamas ou Aruba. Retenir 2025 comme dernière année observée les priverait de rang ; s'en tenir à 2024 ignorerait des données publiées. Le pipeline produit donc deux rapports :

| Rapport | Emplacement | Dernière année observée | Pays classés |
|---|---|---|---|
| Référence | `data/`, `outputs/` | 2024 | 183 |
| Plus récent | `data/plus_recent/`, `outputs/plus_recent/` | 2025 | 180 |

**Règle de la référence.** Parmi les cinq dernières années observées, la plus récente dont les pays privés de rang pèsent moins de 0,1 % du PIB des pays classables sur ces cinq ans. Un seuil en PIB plutôt qu'en nombre de pays : 2023 classe un pays de plus que 2024 (Saint-Marin, 0,002 % du PIB), ce qui ne justifie pas de perdre une année ; 2025 en perd trois qui pèsent 0,49 %, dont les Émirats.

**Le rapport le plus récent n'existe que s'il diffère.** Quand la dernière année publiée devient quasi complète, elle devient la référence et `plus_recent/` est supprimé : un rapport devenu sans objet ne reste pas en place, périmé.

Chaque rapport décrit ce choix dans le bloc `rapport` de son `extraction_metadata.json` (années candidates, pays classés et poids des absents pour chacune), et sa page de résultats situe le lecteur, avec un lien vers l'autre rapport. Les notebooks lisent le rapport de référence.

---

## ⚠️ Pays vs Agrégats

Les deux API diffusent les agrégats (`WLD` World, `OED` OECD members, `EUU` European Union, groupes de revenu…) dans le même flux que les pays, avec un code sur 3 lettres identique en apparence. Le pipeline les identifie via les endpoints de métadonnées (`/v2/country` côté Banque Mondiale, région `NA` ; `/api/v1/countries` côté FMI) et marque chaque ligne d'un drapeau **`is_aggregate`** :

- **conservés** dans `gdp_unified_2000_2030.csv` et l'onglet `Series_Temporelles` (le PIB mondial reste exploitable) ;
- **exclus** des classements, des rangs et de toutes les visualisations comparatives.

Sans ce filtre, le « Top 10 mondial » se compose d'agrégats et les États-Unis n'apparaissent qu'en 12ᵉ position.

La jointure historique/prévision se fait sur le **code ISO seul**, les deux sources nommant différemment un même pays (`Korea, Rep.` vs `Korea`). Les rares codes propres au FMI sont convertis au préalable (`UVK` → `XKX` pour le Kosovo, `WBG` → `PSE` pour la Cisjordanie et Gaza) : sans cela, le Kosovo formait deux entités classées séparément.

---

## 🏅 Classements : un même panel de pays

Tous les rangs (`Rank_2024`, `Rank_2030_Forecast`, `Rank_PPA_*`) portent sur les mêmes pays : ceux renseignés aux deux dates, au taux de marché comme à parité — 183 pays. Un écart de rang (`Rank_Change`, `Ecart_Rang_Nominal_PPA_2024`) traduit alors un mouvement, et non l'entrée ou la sortie d'un pays du classement.

Classer chaque colonne sur les pays qu'elle couvre faussait 140 écarts de rang sur 183 : Taïwan, absent de la Banque Mondiale, entrait 22ᵉ au classement 2030 ; le Pakistan, sans projection FMI au-delà de 2025, en sortait. La Belgique affichait −4 rangs au lieu de −3, l'Iran −16 au lieu de −15.

Les pays hors panel gardent leurs niveaux de PIB dans la synthèse, sans rang. Le pipeline en donne la liste à chaque run (Pakistan, Venezuela, Sri Lanka, Bolivie, Liban, Afghanistan…).

---

## ✅ Tests des Invariants

```bash
pytest test_gdp_pipeline.py -v
pytest test_gdp_pipeline.py -m "not donnees"   # sans les fichiers produits
```

91 tests, sans accès réseau. Ils portent sur les propriétés que les défauts rencontrés violaient **sans lever d'erreur** — le mode de défaillance de ce projet est la colonne vide ou le classement faux, pas l'exception :

| Invariant | Ce qu'il empêche |
|---|---|
| Les agrégats sont absents des classements | *World* et *OECD members* en tête du Top 30 |
| Un seul libellé et un seul code par pays | Un pays scindé en deux séries, PIB 2030 et rangs vides ; le Kosovo classé deux fois |
| Croissance implicite des volumes chaînés = taux FMI | Une dérive silencieuse du chaînage |
| Une année de croissance absente interrompt le chaînage | Des valeurs extrapolées passées pour des projections |
| Chaque série de niveau a son propre facteur de raccord | Une PPA du Burundi en chute de 46 % à la jonction |
| Tous les rangs portent sur un même panel | Des écarts de rang dus à l'entrée de Taïwan ou à la sortie du Pakistan |
| Les colonnes suivent les bornes du run ; des bornes incohérentes sont refusées | Une synthèse entièrement vide sur `--end-year 2023` |
| Les rangs sont cohérents avec leurs niveaux | Un classement PPA calculé sur le mauvais indicateur |
| Le CAGR vaut `NaN` s'il n'est pas calculable | Un taux inventé sur un PIB nul ou manquant |
| Une source injoignable interrompt la collecte | Une colonne vide, ou des agrégats classés comme pays |
| La série lue est celle du dernier run | Un graphique ou une évaluation bâtis sur un autre run |
| La référence Banque Mondiale ne sert qu'à la croissance | Une inflation projetée comparée à la croissance observée |
| Le rapport de référence reste quasi complet, le plus récent s'y ajoute sans le remplacer | Un classement privé des Émirats faute de donnée 2025, ou un rapport périmé laissé en place |

Chaque invariant est **validé par mutation** : le défaut correspondant, réintroduit dans une copie du code, fait bien échouer la suite. Les tests marqués `donnees` contrôlent les CSV réellement produits et se sautent tant que le pipeline n'a pas tourné.

---

## 🕓 Provenance des Données

Chaque exécution écrit `data/extraction_metadata.json` : date d'extraction, bornes du run, indicateurs interrogés, volumes obtenus et couverture par colonne.

Le champ `derniere_mise_a_jour` reprend le `lastupdated` déclaré par l'API de la Banque Mondiale — le millésime réel des séries historiques, qui sont révisées. L'API DataMapper du FMI n'expose pas le millésime de son WEO (publié en avril et octobre) : seule la date d'extraction permet de le situer.

Ce fichier désigne aussi la série du dernier run. Plusieurs `gdp_unified_<début>_<fin>.csv` peuvent coexister après des runs sur d'autres bornes : `visualize_gdp.py`, `evaluate_forecasts.py`, `build_results_page.py`, les notebooks et les tests lisent celle que désignent ses bornes — jamais la plus récemment modifiée, qu'une copie ou une synchronisation suffit à changer.

---

## 📈 Fichiers Produits et Métriques

1. **`outputs/gdp_master_dataset.xlsx`** :
   - `Top30_Economies` : Vue rapide des 30 premières puissances économiques mondiales.
   - `Synthese_Pays` : Indicateurs clés (PIB 2000, 2010, 2024, 2030), CAGR historique (2000-2024), CAGR prévisionnel (2024-2030), et évolution des rangs mondiaux (sur le panel décrit plus haut).
   - `Series_Temporelles_<début>_<fin>` : Données continues fusionnées pour tous les pays.
   - `Donnees_Historiques_Brutes` / `Previsions_FMI_Brutes` : Extractions directes des API.

2. **`outputs/gdp_dashboard_interactive.html`** :
   - Dashboard HTML interactif permettant de comparer les pays, de zoomer, de basculer entre les indicateurs et de suivre la frontière historique/prévision (2024/2025).

3. **`outputs/*.png`** :
   - Visualisations graphiques prêtes pour intégration dans des rapports ou présentations.
