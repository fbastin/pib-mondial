# PIB mondial : historique, prévisions et qualité des prévisions

[![Tests](https://github.com/fbastin/pib-mondial/actions/workflows/tests.yml/badge.svg)](https://github.com/fbastin/pib-mondial/actions/workflows/tests.yml)

Ce projet collecte le PIB par pays auprès de la **Banque Mondiale** (de 2000 à la dernière année publiée) et les prévisions du **FMI** (*World Economic Outlook*, jusqu'à l'horizon de l'édition en cours : 2031 pour avril 2026). Il les unifie en une série continue, en tire croissances, volumes, parités de pouvoir d'achat et classements, évalue la qualité des prévisions du FMI depuis 1990, et produit un classeur Excel, des graphiques, un tableau de bord et une page de résultats.

---

## 🚀 Démarrage rapide

```bash
python3 -m venv ~/.venvs/gdp
~/.venvs/gdp/bin/pip install -r requirements.txt
source ~/.venvs/gdp/bin/activate

python produire_rapports.py        # depuis la racine du dépôt
```

La commande enchaîne collecte, calcul, évaluation des prévisions, graphiques et page de résultats. À ouvrir ensuite : `outputs/resultats_gdp.html` (synthèse commentée) et `outputs/gdp_master_dataset.xlsx` (toutes les données). Si la dernière année publiée est encore incomplète, un second rapport est produit dans `outputs/plus_recent/` (voir *Deux rapports*).

Le venv est créé hors du dépôt : les dépendances ne sont ni versionnées ni synchronisées.

---

## 📁 Organisation du dépôt

```
pib-mondial/
├── produire_rapports.py          # Point d'entrée : la chaîne complète, pour chaque rapport
├── miroir.py                     # Copie du dépôt et de ses sorties vers un dossier partagé
├── pib/                          # Code : paquet Python
│   ├── http_utils.py             #   Requêtes HTTP communes : nouvelles tentatives, échec explicite
│   ├── fetch_historical_gdp.py   #   Collecte : historique Banque Mondiale (API WDI)
│   ├── fetch_forecast_gdp.py     #   Collecte : prévisions FMI (API DataMapper)
│   ├── gdp_pipeline.py           #   Calcul : unification, raccord, volumes, synthèse, rapports
│   ├── update_weo_editions.py    #   Évaluation : éditions récentes du WEO (API SDMX du FMI)
│   ├── evaluate_forecasts.py     #   Évaluation : prévisions d'époque confrontées au réalisé, récessions
│   ├── revisions_weo.py          #   Évaluation : révisions d'une édition du WEO à la suivante
│   ├── calibration.py            #   Évaluation : fourchettes et probabilités éprouvées en temps réel
│   ├── groupes_revenu.py         #   Groupe de revenu connu à la date de chaque édition (fourchettes)
│   ├── long_terme.py             #   Évaluation : fourchettes au-delà de l'horizon du FMI (trajectoires prolongées)
│   ├── population.py             #   Évaluation : erreurs passées des projections de population de l'ONU, bornes calibrées
│   ├── scenarios.py              #   Export : scénarios de PIB et de population jusqu'en 2050, pour le trafic
│   ├── tirages.py                #   Export : trajectoires conjointes de tous les pays, pour agréger des marchés
│   ├── chiffres_cles.py          #   Documentation : chiffres cités qui ont changé après une relance, et où
│   ├── cas_de_crise.py           #   Évaluation : une récession mondiale (2009, 2020) dans les prévisions
│   ├── millesimes_bm.py          #   Évaluation : éditions archivées des WDI, révisions du réalisé
│   ├── visualize_gdp.py          #   Livrables : graphiques et tableau de bord
│   └── build_results_page.py     #   Livrables : page de résultats HTML
├── notebooks/                    # Analyse interactive (Python et Julia) et générateurs
├── tests/                        # Tests des invariants (pytest)
├── docs/                         # Documentation technique (LaTeX et PDF), cas d'étude
├── data/
│   ├── raw/                      # Sources : classeur WEO historique, complément API, LISEZ-MOI
│   │   ├── weo_archive/          # Éditions complètes du WEO et métadonnées des pays, archivées à leur parution
│   │   ├── wdi_archive/          # Éditions archivées des WDI (non versionné, re-téléchargeable)
│   │   └── scenarios_long_terme/ # Scénarios de l'OCDE et population de l'ONU (non versionné)
│   ├── processed/                # Rapport de référence : séries, synthèse, évaluation
│   ├── plus_recent/              # Rapport le plus récent, s'il diffère
│   └── extraction_metadata.json  # Provenance du rapport de référence
├── outputs/                      # Livrables du rapport de référence
│   └── plus_recent/              # Livrables du rapport le plus récent
├── HISTORIQUE.md                 # Journal des défauts corrigés et des choix de méthode
├── requirements.txt              # Dépendances Python
├── Project.toml, Manifest.toml   # Environnement Julia des notebooks
├── pytest.ini                    # Configuration des tests
└── .github/workflows/tests.yml   # Tests à chaque push
```

**Versionné ou régénéré.** Le dépôt ne versionne que le code, la documentation et les sources qui ne se re-téléchargent pas par script : `data/raw/WEOhistorical.xlsx` (le site du FMI refuse les scripts), son complément `data/raw/weo_editions_api.csv`, et l'archive des éditions complètes du WEO et de leurs métadonnées, `data/raw/weo_archive/`, que l'API ne sert plus une fois l'édition suivante parue. Tout le reste — `data/processed/`, `data/plus_recent/`, `data/extraction_metadata.json`, `data/raw/gdp_imf_weo_raw.json`, `outputs/` — se régénère par `python produire_rapports.py` et n'est pas versionné.

---

## 🛠️ Utilisation

Toutes les commandes se lancent **depuis la racine du dépôt** : les chemins `data/` et `outputs/` en partent, et le paquet `pib` s'importe depuis là.

### La chaîne complète

```bash
python produire_rapports.py [--start-year 2000] [--end-year AAAA] [--fcst-end AAAA] [--sans-editions-api] [--sans-millesimes-bm]
```

- `--start-year` : première année de l'historique (par défaut : `2000`) ;
- `--end-year` : dernière année observée. Par défaut, choisie d'après les données, avec un second rapport sur la dernière année publiée si elle diffère ; imposée, elle donne un rapport unique ;
- `--fcst-end` : dernière année de prévision (par défaut : horizon de l'édition du WEO servie par l'API, 2031 aujourd'hui ; il avance d'un an à chaque édition de printemps) ;
- `--sans-editions-api` : ne pas interroger l'API du FMI pour les éditions récentes du WEO ;
- `--sans-millesimes-bm` : ne pas collecter les éditions archivées des WDI de la Banque Mondiale (la première collecte prend une vingtaine de minutes, les suivantes n'ajoutent que les éditions nouvelles) ;
- `--data-dir` / `--output-dir` : dossiers de sortie (par défaut : `data` et `outputs`).

*Exemple — historique de 30 ans :* `python produire_rapports.py --start-year 1995`

**Les bornes se propagent partout.** Le nom du fichier unifié (`gdp_unified_1995_2031.csv`), les colonnes de synthèse (`CAGR_Historique_1995_2024_Pct`), l'onglet Excel des séries, la frontière historique/prévision des graphiques et les titres suivent les années du run. Les étapes en aval et les deux notebooks lisent la série du dernier run d'après `extraction_metadata.json` (voir *Provenance*) ; aucune n'a d'année codée en dur.

**Après une nouvelle édition du WEO** (avril et octobre), dans l'ordre :

1. `python produire_rapports.py` : la chaîne entière, sur la nouvelle édition. Sa dernière étape liste les chiffres cités dans la documentation qui ont changé, avec les fichiers et lignes où l'ancienne valeur apparaît (`pib.chiffres_cles`).
2. Corriger ces passages (README, `docs/scenarios_trafic.md`, `docs/documentation_gdp.tex`, à recompiler), puis publier les nouvelles valeurs : `python -m pib.chiffres_cles --enregistrer`.
3. `pytest` : le contrôle `test_documentation_a_jour` échoue tant qu'un chiffre suivi manque à la documentation.
4. Ajouter une entrée à `HISTORIQUE.md`, valider, puis copier vers le dossier partagé : `python miroir.py --destination DOSSIER`.

Les chiffres suivis (`docs/chiffres_cles.json`) ne couvrent pas tout : les autres chiffres des sections touchées sont à relire.

**Un échec interrompt tout.** Chaque requête est retentée trois fois. Si une source ou un indicateur reste injoignable, ou si les bornes sont incohérentes (prévision qui ne suit pas immédiatement l'historique), l'étape s'arrête avec un code de sortie non nul, sans rien écrire, et la chaîne s'interrompt : elle n'enchaîne jamais sur des données partielles ou sur celles d'un run précédent.

### Étape par étape

| Étape | Commande |
|---|---|
| Collecte, séries unifiées, synthèse et Excel | `python -m pib.gdp_pipeline [--start-year …] [--end-year …] [--fcst-start …] [--fcst-end …]` |
| Éditions récentes du WEO, depuis l'API, et archivage des éditions complètes et de leurs métadonnées | `python -m pib.update_weo_editions [--sans-archive]` |
| Évaluation des prévisions | `python -m pib.evaluate_forecasts [--indicateur pcpi_pch]` |
| Révisions d'une édition à la suivante | `python -m pib.revisions_weo` |
| Fourchettes et probabilités de récession éprouvées en temps réel | `python -m pib.calibration [--horizon 5]` |
| Fourchettes au-delà de l'horizon du FMI (erreurs des trajectoires prolongées) | `python -m pib.long_terme` |
| Erreurs passées des projections de population de l'ONU, bornes calibrées | `python -m pib.population` |
| Scénarios de PIB et de population jusqu'en 2050, pour le projet trafic | `python -m pib.scenarios [--annee-fin 2050]` |
| Trajectoires conjointes de tous les pays, pour agréger des marchés | `python -m pib.tirages` |
| Cas d'étude d'une récession mondiale (hors chaîne) | `python -m pib.cas_de_crise --annee 2009 [--trafic]` |
| Éditions archivées des WDI : collecte, puis révisions du réalisé | `python -m pib.millesimes_bm --collecter` ; `python -m pib.millesimes_bm --data-dir data` |
| Graphiques et tableau de bord | `python -m pib.visualize_gdp` |
| Page de résultats | `python -m pib.build_results_page [--pays FRA]` |
| Chiffres cités dans la documentation qui ont changé, et où les corriger ; puis publication des nouvelles valeurs | `python -m pib.chiffres_cles [--enregistrer]` |
| Copie du dépôt et de ses sorties vers un dossier partagé (seulement ce qui a changé, sans rien supprimer) | `python miroir.py --destination DOSSIER [--simulation]` |
| Collecte seule, historique | `python -m pib.fetch_historical_gdp --start-year 2000 --end-year 2025` |
| Collecte seule, prévisions | `python -m pib.fetch_forecast_gdp --forecast-start 2025` |

Pour le rapport le plus récent, les quatre dernières étapes prennent `--data-dir data/plus_recent` (et `--output-dir outputs/plus_recent`). La page de résultats lit ses tableaux dans `data/processed/` et inline les graphiques de `outputs/` ; aucune valeur n'y est saisie à la main, ses commentaires se déduisent des chiffres.

### Notebooks

Deux notebooks, dans `notebooks/`, couvrent les mêmes sept sections (chargement, Top 10, trajectoires interactives, comparaison des CAGR, carte de chaleur, nominal ou volume, interrogation par pays) et lisent le rapport de référence produit par le pipeline. Ils retrouvent seuls la racine du dépôt : ils n'appellent aucune API et n'écrivent rien.

- **Python** — `jupyter notebook notebooks/gdp_analysis_notebook.ipynb` (pandas, matplotlib/seaborn, Plotly).
- **Julia** — `notebooks/gdp_analysis_notebook_julia.ipynb` (CSV.jl, DataFrames.jl, JSON.jl, Plots.jl avec bascule GR ↔ plotly). Environnement décrit par `Project.toml`, à préparer depuis la racine :

  ```julia
  using Pkg
  Pkg.activate(".")
  Pkg.instantiate()
  Pkg.add("IJulia")     # noyau Jupyter, si absent
  using IJulia; notebook(dir = ".")
  ```

  Le noyau IJulia démarre avec `--project=@.` : depuis `notebooks/`, il remonte jusqu'au `Project.toml` de la racine, où le notebook trouve aussi les données.

Les notebooks se régénèrent par leur script (`python notebooks/create_notebook.py`, `python notebooks/create_notebook_julia.py`). L'export HTML du notebook Julia, dans `outputs/`, s'obtient par :

```bash
jupyter nbconvert --to html --execute --ExecutePreprocessor.kernel_name=julia-1.12 \
    notebooks/gdp_analysis_notebook_julia.ipynb --output-dir outputs
```

### Tests

```bash
pytest                      # 222 tests, sans accès réseau
pytest -m "not donnees"     # sans les contrôles sur les fichiers produits
```

### Documentation technique

`docs/documentation_gdp.pdf` détaille la méthode. `docs/revue_litterature.md` situe les résultats dans la littérature (évaluation des prévisions du FMI, fourchettes tirées des erreurs passées, PIB et trafic aérien), avec sa bibliographie `docs/references.bib`. Pour la recompiler (les fichiers auxiliaires restent dans `build/`, non versionné) :

```bash
mkdir -p build && pdflatex -output-directory=build docs/documentation_gdp.tex \
    && pdflatex -output-directory=build docs/documentation_gdp.tex && cp build/documentation_gdp.pdf docs/
```

---

## 📊 Sources de données

1. **Banque Mondiale — World Development Indicators** (API libre, sans clé) :
   - séries annuelles depuis 1960, collectées par défaut depuis 2000 ;
   - prix courants : PIB nominal (USD), croissance annuelle (%), PIB par habitant, PIB à PPA ;
   - volume : PIB à prix constants 2015 (`NY.GDP.MKTP.KD`), PIB à PPA constante 2021 (`NY.GDP.MKTP.PP.KD`) ;
   - population (`SP.POP.TOTL`).
   - métadonnées des pays : distinction pays / agrégats, groupe de revenu (classification courante) ;
   - éditions archivées des WDI (source « WDI Database Archives », 142 éditions depuis 1989, le PIB à partir de 1994) : croissance réelle et PIB en dollars courants tels que publiés à chaque édition.

2. **FMI — World Economic Outlook, API DataMapper** (libre) :
   - estimations et projections de l'édition en cours, de 1980 à son horizon (cinq ans après l'année de l'édition) ;
   - `NGDPD` (PIB nominal, milliards USD), `NGDP_RPCH` (croissance réelle, %), `PPPGDP` (PIB à PPA), `NGDPDPC` (PIB par habitant), `LP` (population, millions).

3. **FMI — prévisions d'époque**, pour l'évaluation :
   - *WEO Historical Forecasts Database* (`data/raw/WEOhistorical.xlsx`), téléchargée à la main : toutes les éditions depuis 1990 ;
   - API SDMX (`api.imf.org`) : éditions plus récentes que le classeur, ajoutées automatiquement (voir *Évaluer la qualité des prévisions*).

---

## 📐 Méthode

### Deux rapports : référence et plus récent

La Banque Mondiale publie une nouvelle année pays par pays. En septembre 2026, 2025 est déjà disponible pour 186 pays, mais pas pour les Émirats arabes unis (27ᵉ économie), les Bahamas ou Aruba. Retenir 2025 comme dernière année observée les priverait de rang ; s'en tenir à 2024 ignorerait des données publiées. Le pipeline produit donc deux rapports :

| Rapport | Emplacement | Dernière année observée | Pays classés |
|---|---|---|---|
| Référence | `data/`, `outputs/` | 2024 | 183 |
| Plus récent | `data/plus_recent/`, `outputs/plus_recent/` | 2025 | 180 |

**Règle de la référence.** Parmi les cinq dernières années observées, la plus récente dont les pays privés de rang pèsent moins de 0,1 % du PIB des pays classables sur ces cinq ans. Un seuil en PIB plutôt qu'en nombre de pays : 2023 classe un pays de plus que 2024 (Saint-Marin, 0,002 % du PIB), ce qui ne justifie pas de perdre une année ; 2025 en perd trois qui pèsent 0,49 %, dont les Émirats.

**Le rapport le plus récent n'existe que s'il diffère.** Quand la dernière année publiée devient quasi complète, elle devient la référence et `plus_recent/` est supprimé : un rapport devenu sans objet ne reste pas en place, périmé.

Chaque rapport décrit ce choix dans le bloc `rapport` de son `extraction_metadata.json` (années candidates, pays classés et poids des absents pour chacune), et sa page de résultats situe le lecteur, avec un lien vers l'autre rapport. Les notebooks lisent le rapport de référence.

### Recouvrement des sources et raccord

Le WEO du FMI couvre **1980 à l'horizon de projection**, pas seulement les années à venir. Le pipeline conserve ses estimations des années observées : chaque année historique porte donc la valeur Banque Mondiale *et* la valeur FMI.

| Colonne | Contenu |
|---|---|
| `GDP_Nominal_FMI_Billions_USD` | Niveau FMI brut, sur toute la période qu'il couvre |
| `GDP_PPP_FMI_Billions_USD`, `GDP_Per_Capita_FMI_USD` | Idem pour la PPA courante et le PIB par habitant |
| `Ecart_Sources_Pct` | (FMI − Banque Mondiale) / Banque Mondiale sur le nominal, années observées seulement |
| `Facteur_Raccord` | Rapport appliqué aux niveaux nominaux projetés (constant par pays) |
| `Facteur_Raccord_PPA`, `Facteur_Raccord_Par_Habitant` | Rapports propres à la PPA courante et au PIB par habitant |
| `Population_FMI_Millions`, `Facteur_Raccord_Population` | Population du FMI en regard, et rapport appliqué à sa projection |

**La Banque Mondiale reste la référence sur les années observées** : les valeurs FMI servent de point de comparaison, jamais de substitution.

Les deux institutions concordent au centième de pourcent pour la plupart des pays (écart médian 0,03 % en 2024), mais divergent nettement pour une quinzaine. Juxtaposer l'observation de l'une et la projection de l'autre fabrique alors une croissance qui n'existe pas :

| | Sans raccord | Dynamique réelle du FMI |
|---|---|---|
| Burundi 2025 | +127,7 % | +43,0 % |
| Turkménistan 2025 | +74,9 % | +12,7 % |
| Soudan 2025 | **−20,0 %** | **+36,2 %** |

Le raccord conserve la dynamique du FMI et le niveau de la Banque Mondiale — `niveau[y] = observé[base] × FMI[y] / FMI[base]` — soit la même logique que le chaînage appliqué aux volumes. Après raccord, la croissance livrée à la jonction reproduit exactement celle projetée par le FMI, pour les 189 pays comparables.

**Un facteur par série.** Les deux institutions ne divergent pas du même rapport sur chaque mesure : écart médian de 0,03 % sur le nominal, 0,3 % sur la PPA courante, 1,2 % sur le PIB par habitant. Chacune reçoit donc son propre facteur. Appliquer à la PPA celui du nominal recréait la marche que le raccord supprime (Burundi −46 % en 2025 au lieu des +6,9 % projetés par le FMI, Soudan +95 % au lieu de +6,2 %). Visualisé par `gdp_source_discrepancy_2024.png`.

> **Ce que ce recouvrement ne fait pas.** L'API DataMapper ne sert que le millésime courant du WEO : sa valeur pour 2020 est l'estimation actuelle du FMI, pas ce qu'il projetait en 2018. La comparaison mesure donc un écart **entre institutions**, pas la qualité des prévisions — pour cela, voir *Évaluer la qualité des prévisions*.

### Nominal ou volume : corriger l'effet change

Le PIB nominal en USD courants mélange croissance réelle, inflation et mouvements de change : les CAGR nominaux ne sont pas comparables d'un pays à l'autre en l'état. Le pipeline produit en parallèle une lecture **en volume** (USD constants 2015), et l'écart entre les deux :

| Colonne | Contenu |
|---|---|
| `GDP_Real_Billions_USD` | PIB à prix constants 2015 (série continue jusqu'à l'horizon) |
| `GDP_Real_PPP_Billions_Intl` | PIB PPA à prix constants 2021 |
| `CAGR_Reel_Historique_2000_2024_Pct` | Croissance annuelle en volume, observée |
| `CAGR_Reel_Prevision_2024_2031_Pct` | Croissance annuelle en volume, projetée |
| `Ecart_Nominal_Reel_2000_2024_Pts` | Nominal − réel : la part d'inflation et de change |

Le FMI ne publiant qu'un **taux** de croissance réelle (`NGDP_RPCH`) et non un niveau, les valeurs en volume de l'horizon de prévision sont chaînées à partir du dernier point observé. Une année de croissance manquante interrompt le chaînage plutôt que d'extrapoler.

Quelques écarts sur 2000-2024 : Japon −0,77 % nominal contre +0,65 % en volume (yen déprécié), Russie 9,3 % contre 3,1 %, Chine 12,0 % contre 8,1 %.

**Population et PIB en volume par habitant.** Les modèles de trafic aérien raisonnent par habitant. La population observée vient de la Banque Mondiale ; la population projetée, du FMI (`LP`), raccordée à son dernier niveau comme les autres séries. Les deux sources divergent plus qu'on ne l'attendrait : écart médian de 0,7 % en 2024, plus de 5 % pour 42 pays (Éthiopie −18 %, Chypre −29 %, Yémen −55 % au FMI), d'où le raccord. Le PIB en volume par habitant se calcule sur toute la série, projections comprises : volume chaîné divisé par population raccordée.

| Colonne | Contenu |
|---|---|
| `Population_Millions` | Population, millions (série unifiée) |
| `GDP_Real_Per_Capita_USD_2015` | PIB en volume par habitant, USD constants 2015 |
| `GDP_Real_PPP_Per_Capita_Intl_2021` | PIB en volume à PPA par habitant, $ internationaux constants 2021 |
| `Population_2024_Millions`, `CAGR_Population_Prevision_2024_2031_Pct`… | Population aux années de référence et sa croissance (synthèse) |
| `GDP_Reel_Par_Habitant_2024_USD_2015`, `CAGR_Reel_Par_Habitant_Prevision_2024_2031_Pct`… | PIB en volume par habitant et sa croissance (synthèse) |

La croissance par habitant peut être bien plus faible que celle du PIB : de 2024 à 2031, 2,0 % par an pour le Nigeria contre 4,2 %, 6,6 % pour l'Éthiopie contre 8,4 % ; en Chine, où la population baisse, elle la dépasse (4,2 % contre 4,0 %).

**Comparer des niveaux : la parité de pouvoir d'achat.** Corriger la *croissance* ne suffit pas pour comparer des *niveaux* : le PIB en volume reste converti au taux de change de l'année de base. Le classement par niveau s'appuie donc en parallèle sur `GDP_Real_PPP_Billions_Intl` ($ internationaux constants 2021) :

| Colonne | Contenu |
|---|---|
| `GDP_PPA_2024_Billion_Intl_2021` | Niveau à PPA, prix constants (idem 2000 et 2031) |
| `Rank_PPA_2024` / `Rank_PPA_2031` | Rang mondial sur cette base |
| `Ecart_Rang_Nominal_PPA_2024` | Rangs gagnés en passant du taux de marché à la PPA |

Le classement 2024 change sensiblement : la Chine passe 1ʳᵉ devant les États-Unis, l'Inde 3ᵉ (au lieu de 5ᵉ), la Russie 4ᵉ (au lieu de 10ᵉ), l'Indonésie 8ᵉ (au lieu de 16ᵉ) ; à l'inverse le Canada recule de 6 rangs et le Royaume-Uni de 4.

> **Portée du rang PPA projeté.** Les niveaux à parité de l'horizon de prévision étant chaînés depuis le dernier point observé, `Rank_PPA_2031` suppose les facteurs de conversion de 2021 inchangés sur tout l'horizon — alors qu'ils suivent les niveaux de prix relatifs. Ce classement projeté extrapole une structure de prix figée ; son incertitude dépasse celle des prévisions de croissance dont il dérive. Le rang PPA de l'année observée (`Rank_PPA_2024`) n'a pas cette limite.

### Pays et agrégats

Les deux API diffusent les agrégats (`WLD` World, `OED` OECD members, `EUU` European Union, groupes de revenu…) dans le même flux que les pays, avec un code sur 3 lettres identique en apparence. Le pipeline les identifie via les endpoints de métadonnées (`/v2/country` côté Banque Mondiale, région `NA` ; `/api/v1/countries` côté FMI) et marque chaque ligne d'un drapeau **`is_aggregate`** :

- **conservés** dans la série unifiée et l'onglet `Series_Temporelles` (le PIB mondial reste exploitable) ;
- **exclus** des classements, des rangs et de toutes les visualisations comparatives.

Sans ce filtre, le « Top 10 mondial » se compose d'agrégats et les États-Unis n'apparaissent qu'en 12ᵉ position.

La jointure historique/prévision se fait sur le **code ISO seul**, les deux sources nommant différemment un même pays (`Korea, Rep.` vs `Korea`). Les rares codes propres au FMI sont convertis au préalable (`UVK` → `XKX` pour le Kosovo, `WBG` → `PSE` pour la Cisjordanie et Gaza) : sans cela, le Kosovo formait deux entités classées séparément.

### Classements : un même panel de pays

Tous les rangs (`Rank_2024`, `Rank_2031_Forecast`, `Rank_PPA_*`) portent sur les mêmes pays : ceux renseignés aux deux dates, au taux de marché comme à parité — 183 pays. Un écart de rang (`Rank_Change`, `Ecart_Rang_Nominal_PPA_2024`) traduit alors un mouvement, et non l'entrée ou la sortie d'un pays du classement.

Classer chaque colonne sur les pays qu'elle couvre faussait 140 écarts de rang sur 183 : Taïwan, absent de la Banque Mondiale, entrait 22ᵉ au classement projeté ; le Pakistan, sans projection FMI au-delà de 2025, en sortait. Les pays hors panel gardent leurs niveaux de PIB dans la synthèse, sans rang ; le pipeline en donne la liste à chaque run (Pakistan, Venezuela, Sri Lanka, Bolivie, Liban, Afghanistan…).

### Évaluer la qualité des prévisions

Mesurer si les prévisions étaient bonnes suppose les publications **d'époque**. Le FMI les consolide dans la *WEO Historical Forecasts Database* : 73 éditions depuis 1990, 201 entités, horizons −2 à +5. Le fichier se télécharge manuellement (le site refuse les scripts) et se dépose dans `data/raw/WEOhistorical.xlsx` — voir `data/raw/LISEZ-MOI-WEOhistorical.md`.

**Les éditions plus récentes que le classeur arrivent seules.** L'API SDMX du FMI (`api.imf.org`), qui accepte les scripts, sert l'édition courante du WEO et quelques éditions archivées, aux mêmes valeurs que le classeur. `pib.update_weo_editions` ajoute celles qui manquent au classeur dans `data/raw/weo_editions_api.csv`, versionné, que l'évaluation lit en complément ; `produire_rapports.py` le lance à chaque exécution. Après l'édition d'octobre 2026, `F2026` sera donc ajoutée sans téléchargement. Retélécharger le classeur reste possible : pour une édition présente des deux côtés, le classeur fait foi. L'API ne dit pas quelle édition porte son flux courant : elle est déduite de la plus récente archive (après `F2025`, c'est `S2026`) et vérifiée par la dernière année servie (année de l'édition + 5) ; sinon le script s'arrête plutôt que de deviner.

L'horizon se déduit de l'écart entre l'année visée et l'édition qui la projette. Les valeurs d'horizon négatif sont des **ré-estimations du passé**, pas des prévisions, et sont écartées de l'évaluation. Les codes propres au classeur (`KOS` pour le Kosovo, `WBG` pour la Cisjordanie et Gaza) sont convertis vers ceux de la Banque Mondiale.

**Le résultat, sur 69 345 projections et 196 pays** (erreur de croissance, en points) :

| Horizon | Biais moyen | Pondéré par le PIB | Médiane | IC 95 % du biais moyen | Erreur absolue moyenne |
|---|---|---|---|---|---|
| 0 (année en cours) | +0,18 | −0,07 | 0,00 | −0,03 à +0,39 | 1,70 |
| 1 an | **+1,00** | **+0,58** | +0,34 | +0,38 à +1,62 | 2,74 |
| 3 ans | +1,01 | +0,80 | +0,60 | +0,34 à +1,68 | 2,95 |
| 5 ans | +0,93 | +0,81 | +0,62 | +0,24 à +1,62 | 3,04 |

Le FMI est quasiment sans biais sur l'année en cours, puis **surestime la croissance dès qu'il projette au-delà**. L'ampleur dépend de la lecture :

- **Le biais moyen compte chaque pays pour un.** Pondéré par le PIB de l'année visée — ce que l'erreur représente pour l'économie mondiale —, il tombe de +1,0 à +0,6 point à un an ; la médiane, à +0,3. Quelques fortes surestimations tirent la moyenne.
- **Les récessions mondiales en expliquent une part** : sans 2009 ni 2020, le biais moyen à un an serait de +0,62 point. Par année visée, l'erreur médiane atteint **+7,3 points pour 2020** et +3,9 pour 2009 ; le rebond de 2021 est symétriquement sous-estimé (`gdp_forecast_accuracy.png`).
- **L'incertitude se mesure par année visée.** Les pays d'une même année subissent les mêmes chocs : leurs erreurs ne sont pas indépendantes. Calculée par grappes d'années, l'erreur type du biais moyen à un an est six fois celle qui les supposerait indépendantes ; l'intervalle de confiance, de +0,4 à +1,6 point, exclut zéro sans être étroit.
- **Le biais est plus fort pour les pays pauvres** : à un an, +0,7 point pour les pays à revenu élevé, +1,0 pour les revenus intermédiaires, +1,7 pour les pays à faible revenu (classification courante de la Banque Mondiale, appliquée à toute la période).

La conclusion tient avec les deux références de comparaison (ré-estimation du FMI à un an, ou série Banque Mondiale), calculées côte à côte plutôt qu'arbitrées. Le biais pondéré ne porte que sur les années visées que couvre la série du pipeline (depuis 2000).

**Avril ou octobre.** Pour une même année visée, l'édition d'octobre dispose de six mois d'information de plus. Sur l'année en cours, elle est sans biais (+0,01 point, erreur absolue 1,40) quand celle d'avril penche de +0,35 point (erreur absolue 2,01) ; le « quasiment sans biais » de l'horizon 0 fait la moyenne des deux. L'écart se réduit à un an (erreur absolue 2,82 contre 2,65) et disparaît au-delà (`weo_forecast_bias_by_season_*.csv`).

**Face à une prévision naïve.** Se tromper n'empêche pas d'être utile, à condition de faire mieux qu'une règle simple. La prévision naïve retenue est la croissance moyenne des quatre années que le FMI connaissait déjà (v−5 à v−2 pour une édition de l'année v : la ré-estimation de v−1 ne paraît qu'à l'automne de v).

| Horizon | Erreur absolue FMI | Erreur absolue naïve | FMI plus proche du réalisé |
|---|---|---|---|
| 0 | 1,59 | 3,25 | 74 % des cas |
| 1 an | 2,62 | 3,36 | 61 % |
| 5 ans | 3,04 | 3,70 | 56 % |

Le FMI apporte beaucoup sur l'année en cours ; à 5 ans — l'horizon des projections 2031 —, il ne fait que 18 % mieux que la règle naïve, et n'est plus proche du réalisé qu'un peu plus d'une fois sur deux (`weo_forecast_vs_naive_*.csv`).

**La croissance mondiale.** L'agrégat « World » du FMI, écarté de l'évaluation par pays, est évalué à part : biais de −0,10 point sur l'année en cours, +0,56 à un an, +0,83 à 5 ans (intervalle de confiance +0,20 à +1,46). Contre sa seule ré-estimation : la Banque Mondiale agrège le monde aux taux de change de marché et non à parité de pouvoir d'achat, et sa croissance mondiale, inférieure de 0,4 point en moyenne (23 années sur 25), gonflerait le biais de ce seul écart de pondération (`weo_world_bias_*.csv`).

**PIB prévu et PIB réalisé.** Une erreur de croissance répétée d'année en année se cumule sur le niveau. En enchaînant les croissances projetées par chaque édition, puis les croissances réalisées, on compare le niveau prévu au niveau atteint — en volume, l'année précédant l'édition servant de base commune :

| Horizon | Médiane | Pondérée par le PIB | 80 % des cas | Prévu trop haut de plus de 5 % | Trop bas de plus de 5 % |
|---|---|---|---|---|---|
| 1 an | +0,4 % | +0,6 % | −3,9 à +6,9 % | 15 % | 7 % |
| 3 ans | +2,4 % | +2,4 % | −6,2 à +14,9 % | 36 % | 13 % |
| 5 ans | **+4,6 %** | **+4,4 %** | −7,9 à +22,7 % | **49 %** | 15 % |

À 5 ans, le niveau prévu dépasse le réalisé de 4 à 5 % en médiane, et les erreurs ne se compensent pas : trop haut de plus de 5 % dans près d'un cas sur deux, trop bas de plus de 5 % dans un sur sept. L'erreur médiane à 5 ans va de +3,6 % (revenu élevé) à +6,0 % (faible revenu) ; contre la série Banque Mondiale, elle est de +3,6 %. Visualisé par `gdp_forecast_level_errors.png`. La base historique du FMI ne contenant que des taux, l'erreur sur le PIB en dollars courants — qui ajoute change et inflation — n'est pas mesurable ainsi.

**Plus le FMI annonce de croissance, plus il surestime.** Si les prévisions étaient bien calibrées, le réalisé suivrait un à un les écarts de croissance annoncés d'un pays à l'autre : la droite du réalisé sur le prévu (test d'efficience de Mincer et Zarnowitz, sans le 1 % de valeurs extrêmes de chaque côté) aurait une pente de 1. Elle vaut 0,93 sur l'année en cours, 0,74 à un an, **0,57 à 5 ans**. À 5 ans, le biais médian va de −0,36 point pour le cinquième des prévisions les plus modestes à +1,35 pour le cinquième des plus fortes ; sur le niveau, l'erreur médiane va de +1,7 % pour les croissances cumulées projetées les plus faibles (11 % en médiane) à +6,8 % pour les plus fortes (46 %) (`weo_forecast_efficiency_*.csv`, `weo_level_bias_by_projected_growth_ngdp_rpch.csv`). Pour la prévision du trafic aérien, c'est une mise en garde : les marchés à forte croissance projetée sont ceux dont les projections sont les plus optimistes.

**Les projections à l'aune des erreurs passées.** Les projections 2031 des rapports viennent de l'édition d'avril 2026, à 5 ans d'horizon. Appliquer à chacune les erreurs de niveau commises par le passé au même horizon, sur des projections comparables — même classe de croissance cumulée projetée (cinq classes de même effectif) et même groupe de revenu —, donne une fourchette empirique : celle où seraient tombés 80 % des cas (10ᵉ à 90ᵉ centile). Une cellule de moins de 100 cas se replie sur la classe de croissance seule.

| PIB en volume 2031 | Croissance projetée 2026-2031 | Écart à la projection (80 % des cas passés) | Au moins une année de recul 2027-2031 |
|---|---|---|---|
| États-Unis | +12,5 % | −11,3 à +5,1 % | 64 % |
| Chine | +25,0 % | −18,2 à +5,0 % | 52 % |
| Allemagne, Japon, France, Royaume-Uni | +4 à +9 % | −11,3 à +5,1 % | 64 % |
| Inde | +46,0 % | **−25,0 à +4,6 %** | 32 % |
| Indonésie | +35,1 % | −21,6 à +2,5 % | 50 % |

Plus la croissance projetée est forte, plus la fourchette penche vers le bas. **Ces fourchettes sont éprouvées sur le passé** : calculées sur les éditions 1990-2007, elles ont contenu 80 % des erreurs des éditions 2008-2019, pour une cible de 80 % (`gdp_projection_bands_calibration.csv`, refait à chaque exécution). Elles sont prudentes pour les vingt premières économies (91 %) et pour les pays à faible revenu (86 %). La dernière colonne vient des mêmes projections comparables : la part où il est survenu au moins une année de recul dans les cinq années suivant l'édition (voir ci-dessous).

**Éprouvées en temps réel** (`pib.calibration`). Le test précédent coupe une fois, en 2007. Plus exigeant : chaque édition de 2000 à 2019 reçoit des fourchettes tirées des seules erreurs connues à sa date. À 5 ans, l'erreur d'une édition m n'est connue qu'après la ré-estimation d'octobre m + 6 : l'édition v n'utilise donc que les éditions jusqu'à v − 7. Les méthodes sont comparées sur les mêmes 6 874 projections, avec des scores propres (Gneiting et Raftery, 2007 : plus petits, meilleurs) et des intervalles de confiance par bootstrap en blocs d'années visées :

| Méthode | Couverture (cible 80 %) | Score d'intervalle | Pondéré par le PIB | CRPS |
|---|---|---|---|---|
| Classe de croissance × groupe de revenu (retenue) | 78,7 % (76 à 81) | 55,6 | 31,9 | 7,70 |
| Classe de croissance seule | 81,8 % | 55,5 | 36,9 | 7,69 |
| Groupe de revenu seul | 80,2 % | 56,0 | **29,6** | 7,77 |
| Fourchette unique pour tous les pays | 82,8 % | 55,8 | 36,0 | 7,69 |
| Historique du pays | 58,5 % | 73,5 | 38,1 | 9,89 |

- **Les fourchettes poolées sont calibrées en temps réel en moyenne**, mais leur couverture dépend des chocs que traverse chaque fenêtre de cinq ans : de 65 % (édition 2003, qui sous-estimait l'essor d'avant 2008) à 86 % (éditions 2000 et 2010), 70 % pour l'édition 2015, dont la fenêtre inclut 2020.
- **Le choix des projections comparables compte par le groupe de revenu, et pondéré par le PIB.** Le score de la méthode retenue est alors meilleur que celui d'une fourchette unique (écart de 4,1, intervalle de 1,9 à 6,0) et de la classe seule (5,0), mais moins bon que celui du groupe seul (2,3, intervalle de 0,7 à 4,1). Sans pondération, les méthodes poolées se valent. Seul l'historique du pays est nettement moins bon.
- **L'avantage du groupe seul ne tient qu'à la Chine et à l'Inde d'avant 2008** (`gdp_bands_realtime_subsamples.csv`). Sans elles, l'écart pondéré tombe à 1,0 (intervalle de −0,7 à 3,0) ; sur les éditions 2008-2019, il est nul (0,1) ; il atteint 7,2 sur 2000-2007, quand leur croissance dépassait les projections. La méthode retenue est donc conservée. Les bornes du seul groupe de revenu sont publiées à côté (`borne_basse_pct_groupe_seul`, `borne_haute_pct_groupe_seul`), et en scénarios (`bas_groupe_seul`, `haut_groupe_seul`) : elles diffèrent de 4,5 points en moyenne, surtout pour les pays à forte croissance projetée (Inde 2031 : −19,6 à +8,4 % au lieu de −25,0 à +4,6 %).
- **Groupe de revenu connu à la date de l'édition** (`pib.groupes_revenu`, classement historique de la Banque Mondiale) pour les cas passés. Le groupe actuel rangerait parmi les pays riches ceux qui le sont devenus en dépassant les prévisions : un biais de sélection, faible à 5 ans (couverture de 79,0 % avec le groupe actuel), fort au-delà (voir ci-dessous).
- **Probabilités de récession.** Apprises sur les seules fréquences passées, elles faisaient mieux qu'une probabilité unique (score de Brier inférieur de 7,3 %, grâce surtout à la classe de croissance), mais leur niveau dépendait des crises que contenait la période d'apprentissage : 38 % en moyenne sur 2000-2019, pour 49 % de périodes avec recul. **Les crises mondiales sont désormais traitées à part** :
  - les récessions mondiales sont les reculs du PIB mondial par habitant depuis 1961 (1975, 1982, 1991, 2009, 2020 ; série de la Banque Mondiale, `world_gdp_per_capita_growth.csv`) ;
  - une période de 5 ans en contient une dans 41 % des cas ;
  - la probabilité de recul d'un pays mêle sa fréquence dans les périodes passées en crise et hors crise, dans sa cellule, pondérées par cette probabilité.

  En temps réel, la compétence passe de 7,3 à 11,3 % (intervalle de 5,6 à 17,1 %), un gain significatif ; la moyenne remonte à 41 %. La trajectoire du FMI, qui n'annonce presque jamais de recul, ferait bien pire (Brier supérieur de 79 %). En production, les probabilités bougent peu, mais `gdp_projection_bands.csv` donne aussi leurs versions conditionnelles, utiles aux scénarios : États-Unis 97 % de recul si une récession mondiale survient d'ici 2031, 41 % sinon ; Chine 78 % et 33 % ; Inde 39 % et 27 %.

Une première version tirait la fourchette de l'historique propre de chaque pays : elle n'aurait contenu que 67 % des erreurs de la période suivante. Le biais d'un pays ne se reproduit pas d'une période à l'autre — corrélation de 0,01 entre 1990-2007 et 2008-2020 ; la Chine passe de −1,9 à +1,0 point, l'Inde de −0,5 à +1,8.

Ce n'est pas une prévision corrigée, mais la marge d'erreur qu'a connue le FMI ; elle porte sur le volume, et serait plus large en dollars courants. Détail pour tous les pays : `data/processed/gdp_projection_bands.csv` et onglet `Fourchettes_2031` du classeur Excel.

**Les récessions que la trajectoire ne montre pas.** Une trajectoire peut atteindre le niveau prévu en passant par un creux. Or le FMI n'annonce presque jamais de recul du PIB au-delà de l'année en cours : à un an, 2,4 % de ses projections sont négatives, quand 14,2 % des croissances réalisées l'ont été ; il n'avait annoncé que 10 % de ces reculs un an à l'avance (59 % dans l'année même). Sur les années suivant une édition :

| Période | Recul annoncé | Recul survenu | Pondéré par le PIB | 20 premières économies | Hors 2009 et 2020 | Pire année médiane |
|---|---|---|---|---|---|---|
| 1 an | 2 % | 14 % | 12 % | 13 % | 11 % | −2,8 % |
| 3 ans | 3 % | 32 % | 32 % | 33 % | 23 % | −3,1 % |
| 5 ans | 3 % | **45 %** | 48 % | 49 % | 32 % | −3,4 % |

Recul : croissance annuelle en volume négative, selon la ré-estimation du FMI à un an ; « hors 2009 et 2020 » : périodes qui ne contiennent aucune des deux récessions mondiales. Celles-ci n'expliquent pas l'essentiel. Le risque dépend surtout de la croissance projetée : sur cinq ans, un recul est survenu dans 64 % des cas pour les croissances cumulées projetées les plus faibles (11 % en médiane), dans 27 % pour les plus fortes (46 %). Cet ordre tient avant et après 2007 ; le niveau, lui, dépend des crises de la période (38 % des cas pour les éditions jusqu'à 2007, 56 % ensuite). La fréquence par classe de croissance et groupe de revenu donne à chaque pays sa probabilité, dans `gdp_projection_bands.csv` (`probabilite_recul_pct`, et `pire_annee_mediane_pct` pour la profondeur). L'historique propre du pays et sa volatilité passée ont été essayés : sur les éditions 2008-2019, ils ne prévoyaient pas mieux qu'une probabilité unique (score de Brier), quand la classe de croissance l'améliorait. Pour le trafic aérien, qui amplifie les chocs, c'est l'information que la trajectoire médiane ne donne pas.

**Ce que corrige chaque édition.** `pib.revisions_weo` compare chaque prévision à celle de l'édition précédente, pour le même pays et la même année visée. Les éditions à deux ans et plus de l'année visée ne révisent presque pas (au plus 0,03 point en moyenne) ; **la correction vient tard** : l'édition d'avril de l'année visée retire 0,61 point en moyenne (0,29 hors 2009 et 2020), celle d'octobre 0,32. Mises bout à bout, les révisions font −1,09 point : à peu de chose près le biais à 5 ans, qui se résorbe donc dans les dernières éditions. Une révision n'en annonce guère une autre (test de Nordhaus) : la corrélation entre deux révisions successives va de −0,09 à +0,18, légèrement positive à l'approche de l'année visée. Ce qui se prévoit, c'est le sens des révisions tardives, pas leur enchaînement (`weo_forecast_revisions_ngdp_rpch.csv`).

**Ce que change la dernière édition.** L'archive des éditions complètes permet de comparer les deux dernières sur les niveaux. Le rapport raccorde les projections du FMI au dernier niveau observé par la Banque Mondiale, `niveau[y] = observé[base] × FMI[y] / FMI[base]` : ce qui passe dans ses projections est la révision de la croissance cumulée projetée. Entre octobre 2025 et avril 2026, celle de 2024-2030 change de plus de 2 % en volume pour 52 pays sur 189 (médiane 1,0 %), de plus de 5 % en dollars courants pour 64 (médiane 3,2 %) — Russie −9,0 %, Japon −6,3 %, Inde −3,2 %, États-Unis +2,3 % en dollars. Les révisions du niveau de l'historique, elles, s'éliminent dans le raccord. Elles se lisent sur une année observée dans les deux éditions (l'année de l'ancienne édition moins deux, 2023 ici) : sur une année encore estimée, une révision de l'inflation passerait pour un changement de prix de référence. Le PIB en dollars de 11 pays a été révisé de plus de 5 %.

**Changements de norme et d'année de base.** Ils viennent des métadonnées que le FMI attache à chaque pays : norme des comptes nationaux, année de base, chaînage des volumes, notes. L'API ne les sert que pour les deux dernières éditions ; `pib.update_weo_editions` les archive à chaque édition, à côté des données. Entre octobre 2025 et avril 2026 :
- **16 pays ont changé d'année de base** : Japon (2015 → 2020), Inde (2011-12 → 2022-23), Royaume-Uni, Australie, Suisse, Norvège, Bolivie (1990 → 2017)…
- **3 pays ont changé de norme** : l'Azerbaïdjan, les Bahamas et la Guinée sont passés du SCN 1993 au SCN 2008. Pour la Guinée, seules les métadonnées changent : ses données restent celles d'octobre.
- **Le critère utilisé jusqu'ici n'en retrouvait que 12.** Une révision de plus de 5 % du déflateur de l'historique manque les pays à faible inflation, où changer d'année de base déplace à peine le déflateur (Japon −1,1 %, Suisse +1,7 %, Australie −2,5 %). Il signalait en revanche 4 pays sans changement annoncé (Liban, Nauru, Togo, Tonga). Il reste publié comme « forte révision du déflateur ».

Détail : `weo_edition_revisions.csv`, qui garde aussi les pays sans projection jusqu'à l'année cible (Bolivie, Liban).

**La crise de 2008, cas d'étude** (`docs/cas_crise_2008.md`, reproduit par `python -m pib.cas_de_crise --annee 2009`). La chute de 2009 n'a été vue que dans l'année même : l'édition d'octobre 2008, trois semaines après la faillite de Lehman Brothers, annonçait encore +3,0 % pour le monde et un recul pour sept pays, quand 89 pays (77 % du PIB mondial) ont reculé. Le rebond de 2010 ne l'a pas été davantage : l'édition d'avril 2009 le sous-estime pour 77 % des pays (−3,0 points pondéré par le PIB). En niveau, le rebond a relevé la croissance, pas la trajectoire : en 2013, le PIB mondial reste 6,4 % sous le niveau projeté en octobre 2008, celui des économies avancées 7,4 %, celui de l'Espagne 17,8 % ; celui des États-Unis, du Royaume-Uni, de l'Italie et de l'Espagne finit même sous la projection d'avril 2009, faute d'avoir prévu la crise de la zone euro. Aux États-Unis, le rebond de 2010 a été sous-estimé (0,0 % prévu en avril 2009, +3,0 % réalisé), puis la reprise surestimée : de 2010 à 2013, chaque édition de 2008 à 2010 projetait au moins +7,6 % de croissance cumulée, pour +6,1 % selon l'estimation actuelle.

**Le trafic aérien après 2008** (`--trafic`). Eurostat pour 30 pays européens (trafic par aéroport, homogène depuis 2004), Banque Mondiale pour les États-Unis ; la série mondiale de la Banque Mondiale, rompue en 2010, est écartée. En 2013, le trafic accuse un retard de 35 % sur sa tendance de 2004-2007 en Europe, de 19 % aux États-Unis. L'écart du PIB à la projection d'octobre 2008, multiplié par une élasticité de 1,0 à 1,5, en explique **30 à 45 %** des deux côtés. D'un pays européen à l'autre, en revanche, le PIB n'explique plus le trafic après la crise (R² de 0,06, contre 0,54 en 2004-2007) : compagnies à bas coûts, faillites et fiscalité l'emportent.

**La pandémie de 2020, par contraste** (`docs/cas_crise_2020.md`, `--annee 2020`). La chute n'était pas plus annoncée (octobre 2019 : +3,4 % pour le monde, recul pour 10 pays pesant 1 % du PIB mondial), mais l'édition d'avril 2020 la mesure juste (−3,0 % contre −3,1 %) et prévoit le rebond de 2021 (erreur de −0,4 point pondéré par le PIB, contre −3,0 pour 2010). En 2024, les économies avancées retrouvent leur trajectoire d'avant la crise (+0,7 %, États-Unis +3,8 %), les émergentes non (−5,4 %). Pour le trafic aérien, 2020 ne se compare pas à 2008 : jusqu'en 2022-2023, le trafic était limité par les restrictions de voyage, pas par le revenu, et l'épisode ne teste pas le lien entre PIB et demande.

**Le réalisé aussi se révise.** La Banque Mondiale archive chaque édition de ses indicateurs ; `pib.millesimes_bm` les collecte et mesure, pour les années 1993 et suivantes, les révisions depuis la première publication :

| Depuis la première publication | 1 an après | 5 ans après | Aujourd'hui |
|---|---|---|---|
| Croissance : révision absolue médiane | 0,13 pt | 0,46 pt | 0,57 pt |
| Croissance : révisée de plus d'un point | 15 % | 30 % | 35 % |
| Niveau en dollars : révision absolue médiane | 0,6 % | 2,8 % | 5,7 % |
| Niveau en dollars : révisé de plus de 10 % | 7 % | 21 % | 38 % |

Les révisions penchent à la hausse (croissance +0,26 point en moyenne, niveau +4,3 % en médiane à ce jour) : révisions de fond des comptes nationaux et changements d'année de base (Chine +20 % sur 2004, après le recensement économique de 2005), mais aussi, dans les années 1990, conversions en dollars en forte inflation. Le niveau sur lequel se raccordent les projections est donc lui-même incertain : un cinquième des pays le voit révisé de plus de 10 % dans les cinq ans.

**Le biais du FMI ne tient pas à sa propre référence.** Contre la croissance que publiait la Banque Mondiale à la fin de l'année suivante — une référence indépendante du FMI, connue en temps réel —, le biais à un an vaut +0,88 point, contre +0,86 face à la ré-estimation du FMI, sur les mêmes 7 381 projections ; +0,68 face à la série actuelle, révisée à la hausse depuis (`weo_forecast_bias_by_reference_ngdp_rpch.csv`). Une partie de l'optimisme mesuré contre les premières estimations s'efface donc avec les révisions ultérieures des données.

**Scénarios pour le projet trafic** (`pib.scenarios`, détail dans `docs/scenarios_trafic.md`). Export de PIB en volume par habitant et de population, par pays, de 2000 à 2050, sous un nom qui ne change pas avec l'horizon (`scenarios_pib_population.csv`) :
- **jusqu'en 2031**, cinq scénarios autour de la trajectoire du FMI, tirés des fourchettes calculées à chaque horizon : central du FMI, central corrigé de l'erreur médiane, bas et haut (bornes à 80 %), crise mondiale (erreur médiane des périodes passées en crise mondiale). S'y ajoutent, pour comparaison, les bornes du seul groupe de revenu (`bas_groupe_seul`, `haut_groupe_seul`) ;
- **ensuite**, pour les scénarios centraux et de crise, la croissance du PIB potentiel par habitant du scénario de référence de l'OCDE (pays, sinon région). Les bornes `bas` et `haut` s'élargissent comme les erreurs passées des trajectoires du FMI prolongées, par groupe de revenu (`pib.long_terme`, ci-dessous). Pour les pays à revenu élevé, une variante élargie (`bas_elargi`, `haut_elargi`) cesse d'extrapoler le décalage sous la trajectoire centrale au-delà de 16 ans et impose une largeur minimale tirée de Müller, Stock et Watson (2022) : Canada 2050, de 60 à 117 % du central au lieu de 59 à 101 %. Les fourchettes écartent les trajectoires qui prolongeaient un effondrement (croissance passée négative), étrangères aux scénarios : Inde 2050, 47 à 122 % au lieu de 49 à 193 % ;
- **population :** celle du pipeline jusqu'en 2031, puis la croissance médiane de l'ONU (*World Population Prospects* 2024), avec les bornes de son intervalle à 80 %.

Pour le Canada, le PIB par habitant de 2031 va de 43 340 $ (bas) à 51 379 $ (haut) autour de 48 883 $ ; en 2050, de 37 852 à 65 010 $ autour de 64 344 $.

**Population : les bornes de l'ONU sont trop étroites** (`pib.population`). Les révisions des projections de l'ONU de 1998 à 2022, relues dans ses archives, sont confrontées aux estimations de la révision 2024, jusqu'à 25 ans d'horizon :
- **Les bornes à 80 % de l'ONU** pour 2024, appliquées aux erreurs passées des mêmes pays au même horizon, n'en contiennent que 19 % à 1 an, 39 % à 5 ans, 54 % à 20 ans. Elles ignorent notamment les révisions de la population de départ.
- **Pour les pays de plus de 5 millions d'habitants, la population a dépassé les projections :** −2,0 % d'erreur médiane à 10 ans, −4,6 % à 20 ans (projeté / estimé − 1). Royaume-Uni à 20 ans : −8 à −10 % selon la révision ; Canada : −3 à −8 %.
- **Bornes calibrées :** multiplicateurs des bornes de l'ONU par côté, horizon, classe de taille et tiers de largeur de ces bornes (jamais inférieurs à 1). Pour les grands pays aux bornes étroites, comme le Canada, le côté haut est multiplié par 2 à 2,4 au-delà de 10 ans, le côté bas reste celui de l'ONU au-delà de 20 ans. Estimées sur les révisions 1998-2008, elles contiennent 81 à 86 % des erreurs des révisions 2010-2022, contre 25 à 57 % pour celles de l'ONU.
- **Canada en 2050 :** 42,1 à 57,0 millions, au lieu de 42,1 à 51,5, autour de 46,6. Dans les scénarios : `population_millions_basse_calibree`, `population_millions_haute_calibree`.

**Trajectoires conjointes pour agréger des marchés** (`pib.tirages`, `scenarios_pib_tirages.csv`). Les bornes `bas` et `haut` sont calculées pays par pays : leur somme sur plusieurs marchés n'a pas de probabilité connue. Les 60 tirages rejouent chacun une édition passée du WEO (avril 1990 à octobre 2019), par le rééchantillonnage de Schaake. Chaque pays garde exactement sa fourchette (10 % des tirages sous `bas`, 10 % au-dessus de `haut`), mais un tirage donne à chaque pays son rang dans cette édition : les crises communes restent communes.
- **Pour tous les pays ensemble,** la somme des bornes exagère nettement : en 2050, de 56 à 117 % de la trajectoire centrale, contre 70 à 106 % pour les tirages (2031 : 85 à 106 %, contre 90 à 101 %).
- **Pour quelques marchés riches dominés par les États-Unis,** elle reste dans l'incertitude des tirages : Canada, États-Unis, France et Royaume-Uni en 2031, borne basse de 88,7 % contre 87,7 % (intervalle de 84,3 à 94,2). Les pertes de 2008-2009 ont frappé ces pays ensemble.
- **La population se tire aussi,** de la même façon, sur les révisions passées de l'ONU : chaque pays garde sa fourchette calibrée. Indépendamment du PIB total, car les erreurs passées des deux ne sont pas liées (corrélation de rang de 0,00 à 0,04) ; le PIB par habitant d'un tirage est donc son PIB total divisé par sa population.
- **Leur usage :** faire passer chaque tirage dans le modèle de trafic, puis lire les quantiles du trafic, plutôt que d'agréger les bornes.

**Au-delà de l'horizon du FMI** (`pib.long_terme`). Chaque édition du WEO depuis 1999 est prolongée au-delà de 5 ans, puis confrontée au réalisé jusqu'à la dernière année connue (8 930 trajectoires, jusqu'à 25 ans d'horizon) :
- **Prolonger la croissance de moyen terme du FMI** (médiane de ses horizons 3 à 5) surestime le niveau de 12 % en médiane à 10 ans, de 28 % à 20 ans.
- **Prolonger par la dérive**, la croissance moyenne des 10 dernières années connues à la date de l'édition, fait mieux que la dérive seule dans 56 à 64 % des cas.
- **L'erreur croît presque linéairement avec l'horizon :** 80 % des erreurs de niveau restent sous 30 % à 10 ans, sous 50 % à 20 ans. Pour les pays à revenu élevé à la date de l'édition, à 10 ans, de −4 % à +35 % (niveau prévu / réalisé − 1) : le réalisé a rarement dépassé la trajectoire prolongée. Classés selon leur groupe actuel, ces pays auraient montré −11 % à +35 %, par biais de sélection.
- **Les quantiles par groupe de revenu connu à la date de l'édition,** lissés par une loi log(1 + q) = α + β (h + 1)^b (ajustée jusqu'à 16 ans, extrapolée au-delà), donnent les bornes des scénarios après 2031. Avant, l'écart entre variantes de l'OCDE, qui ne diffèrent que par le climat et la transition énergétique, sous-estimait l'incertitude.

**Autres indicateurs : lire les médianes.** La référence Banque Mondiale n'existe que pour la croissance du PIB : pour `pcpi_pch` (inflation) et `bca_gdp_bp6` (balance courante), seule la ré-estimation du FMI sert de référence. Pour l'inflation, les moyennes ne décrivent pas l'erreur typique : quelques projections d'hyperinflation (le Venezuela à 10 000 000 %) portent le biais moyen au-delà de 1 600 points à un an, quand la médiane reste à −0,1 point. La synthèse fournit donc aussi `mediane` et `erreur_absolue_mediane`, et le script avertit dès que l'erreur absolue moyenne dépasse dix fois la médiane.

---

## 📈 Livrables

Pour chaque rapport (`data/` et `outputs/` ; `plus_recent/` pour le plus récent) :

| Fichier | Contenu |
|---|---|
| `data/processed/gdp_historical_<début>_<fin>.csv` | Extraction Banque Mondiale |
| `data/processed/gdp_forecast_<début>_<fin>.csv` | Extraction FMI (estimations et prévisions) |
| `data/processed/gdp_unified_<début>_<horizon>.csv` | Série temporelle unifiée, pays et agrégats |
| `data/processed/gdp_country_summary.csv` | Synthèse par pays : niveaux, CAGR, rangs, population et PIB en volume par habitant |
| `data/processed/weo_forecast_evaluation_<indicateur>.csv` | Une ligne par projection d'époque |
| `data/processed/weo_forecast_bias_<indicateur>.csv` | Biais et erreurs par horizon : moyens, pondérés par le PIB, médians, IC 95 %, hors récessions |
| `data/processed/weo_forecast_bias_by_income_<indicateur>.csv` | Biais par horizon et groupe de revenu |
| `data/processed/weo_forecast_bias_by_season_<indicateur>.csv` | Biais par horizon et saison d'édition (avril, octobre) |
| `data/processed/weo_forecast_vs_naive_<indicateur>.csv` | Le FMI face à une prévision naïve, par horizon |
| `data/processed/weo_world_bias_<indicateur>.csv` | Biais de l'agrégat mondial du FMI, par horizon |
| `data/processed/weo_level_evaluation_ngdp_rpch.csv` | Erreur sur le niveau du PIB, par pays, édition et horizon ; pire année projetée et réalisée des horizons 1 à h |
| `data/processed/weo_level_bias_ngdp_rpch.csv`, `weo_level_bias_by_income_ngdp_rpch.csv` | Erreur de niveau par horizon (quantiles, parts), et par groupe de revenu |
| `data/processed/weo_forecast_efficiency_<indicateur>.csv` | Test d'efficience (pente du réalisé sur le prévu) et biais médian par quintile de prévision |
| `data/processed/weo_level_bias_by_projected_growth_ngdp_rpch.csv` | Erreur de niveau et fréquence des reculs par classe de croissance projetée |
| `data/processed/weo_recession_by_horizon_ngdp_rpch.csv` | Années de recul annoncées et survenues, par horizon |
| `data/processed/weo_recession_risk_ngdp_rpch.csv` | Au moins une année de recul sur les h années suivant l'édition, par groupe |
| `data/processed/weo_forecast_revisions_ngdp_rpch.csv` | Révisions d'une édition à la suivante : sens, enchaînement (test de Nordhaus) |
| `data/processed/weo_edition_revisions.csv` | Ce que change la dernière édition archivée, par pays : projections, historique, forte révision du déflateur ; norme et année de base selon les métadonnées du FMI, et leurs changements |
| `data/processed/wdi_growth_revisions.csv`, `wdi_level_revisions.csv` | Révisions de la croissance et du niveau de la Banque Mondiale depuis leur première publication, par délai et groupe de revenu |
| `data/processed/wdi_largest_level_revisions.csv` | Plus fortes révisions du niveau parmi les 50 premières économies |
| `data/processed/weo_forecast_bias_by_reference_ngdp_rpch.csv` | Biais du FMI contre sa ré-estimation, la Banque Mondiale en temps réel et sa série actuelle |
| `data/processed/gdp_projection_bands.csv` | Fourchette empirique autour du PIB projeté, et probabilité d'une année de recul, par pays : globale, et selon qu'une récession mondiale survient ou non |
| `data/processed/world_gdp_per_capita_growth.csv` | Croissance du PIB mondial par habitant depuis 1961 (Banque Mondiale) : les récessions mondiales |
| `data/processed/gdp_projection_bands_by_horizon.csv` | Fourchettes et probabilités à chaque horizon, de l'année de l'édition à 2031 |
| `data/processed/scenarios_pib_population.csv`, `…_pays.csv`, `…_sources.json` | Scénarios de PIB par habitant et de population jusqu'en 2050, pour le projet trafic |
| `data/processed/population_projection_errors.csv`, `population_bounds_calibration.csv`, `population_calibrated_bounds.csv` | Erreurs passées des projections de population de l'ONU par groupe, taille et horizon ; multiplicateurs de ses bornes ; bornes calibrées par pays |
| `data/processed/scenarios_pib_tirages.csv`, `…_controle.csv` | 60 trajectoires conjointes de tous les pays jusqu'en 2050, PIB par habitant et population ; contrôle : part sous les bornes et au-dessus par pays, quantiles des agrégats contre la somme des bornes |
| `data/processed/weo_cas_<année>_*.csv` | Cas d'étude d'une récession mondiale, sur demande (`pib.cas_de_crise`) : croissance de l'année du choc aux quatre suivantes, reculs annoncés, rebond, niveaux ; avec `--trafic`, trafic aérien face au PIB (par pays, régressions, part expliquée) |
| `data/processed/gdp_projection_bands_calibration.csv` | Test rétrospectif des fourchettes : part des erreurs contenues |
| `data/processed/gdp_bands_realtime_subsamples.csv` | Écart entre la méthode retenue et le seul groupe de revenu, par sous-échantillon (sans la Chine et l'Inde, par période, par groupe) |
| `data/processed/gdp_long_horizon_errors.csv`, `…_bands.csv`, `…_law.csv` | Au-delà de l'horizon du FMI : erreurs des trajectoires prolongées par horizon, quantiles observés et lissés par groupe de revenu, lois de puissance |
| `data/processed/gdp_bands_realtime_scores.csv`, `…_coverage_by_cell.csv`, `…_coverage_by_edition.csv` | Fourchettes éprouvées en temps réel : couverture, largeur, score d'intervalle, CRPS par méthode, avec intervalles de confiance ; couverture par cellule et par édition |
| `data/processed/recession_probability_realtime_scores.csv`, `recession_probability_reliability.csv` | Probabilités de récession en temps réel : score de Brier et compétence par méthode ; fiabilité par tranche |
| `outputs/gdp_master_dataset.xlsx` | Classeur multi-onglets (voir ci-dessous) |
| `outputs/resultats_gdp.html` | Page de résultats autonome, commentée |
| `outputs/gdp_dashboard_interactive.html` | Tableau de bord interactif (Plotly) |
| `outputs/gdp_top10_trajectories_<début>_<horizon>.png` | Trajectoires des dix premières économies |
| `outputs/gdp_cagr_comparison_top15.png` | CAGR historique et prévisionnel |
| `outputs/gdp_nominal_vs_real_cagr_top15.png`, `gdp_nominal_vs_real_trajectories.png` | Nominal contre volume |
| `outputs/gdp_ranking_nominal_vs_ppp_<année>.png` | Classement au taux de marché et à parité |
| `outputs/gdp_source_discrepancy_<année>.png` | Écart entre sources et marche évitée |
| `outputs/gdp_forecast_accuracy.png` | Exactitude des prévisions du FMI depuis 1990 |
| `outputs/gdp_forecast_level_errors.png` | PIB prévu et PIB réalisé : erreur de niveau par horizon et groupe de revenu |
| `outputs/gdp_analysis_notebook_julia.html` | Export du notebook Julia (référence seulement) |

Onglets du classeur Excel : `Top30_Economies` ; `Synthese_Pays` (PIB aux années de référence — 2000, 2010, 2024, 2031 —, CAGR historique et prévisionnel, rangs sur le panel décrit plus haut, population et PIB en volume par habitant) ; `Series_Temporelles_<début>_<horizon>` ; `Donnees_Historiques_Brutes` et `Previsions_FMI_Brutes` (extractions des API) ; `Fourchettes_<horizon>` (fourchettes empiriques, ajoutées par l'évaluation).

---

## 🕓 Provenance des données

Chaque rapport écrit son `extraction_metadata.json` : date d'extraction, bornes du run, indicateurs interrogés, volumes obtenus, couverture par colonne, et le bloc `rapport` (choix de la dernière année observée).

Le champ `derniere_mise_a_jour` reprend le `lastupdated` déclaré par l'API de la Banque Mondiale — le millésime réel des séries historiques, qui sont révisées. L'API DataMapper du FMI n'expose pas le millésime de son WEO (publié en avril et octobre) : seule la date d'extraction permet de le situer.

Ce fichier désigne aussi la série du dernier run. Plusieurs `gdp_unified_<début>_<fin>.csv` peuvent coexister après des runs sur d'autres bornes : les étapes en aval, les notebooks et les tests lisent celle que désignent ses bornes — jamais la plus récemment modifiée, qu'une copie ou une synchronisation suffit à changer.

---

## ✅ Tests des invariants

222 tests, dans `tests/`, sans accès réseau. Ils portent sur les propriétés que les défauts rencontrés violaient **sans lever d'erreur** — le mode de défaillance de ce projet est la colonne vide ou le classement faux, pas l'exception :

| Invariant | Ce qu'il empêche |
|---|---|
| Les agrégats sont absents des classements | *World* et *OECD members* en tête du Top 30 |
| Un seul libellé et un seul code par pays | Un pays scindé en deux séries, PIB projeté et rangs vides ; le Kosovo classé deux fois |
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
| L'horizon suit l'édition du WEO, sans projection isolée | Une année projetée téléchargée puis écartée, ou une série prolongée par un seul pays |
| Une édition lue dans l'API n'est nommée que si l'horizon servi le confirme ; complément cumulatif, classeur prioritaire | Des prévisions d'octobre attribuées à avril, ou une édition perdue quand l'API cesse de la servir |
| Biais pondéré par le PIB ; intervalle groupé par année visée ; récessions exclues à part | Un biais « d'un point » valant pour le pays moyen, présenté comme mondial et précis |
| Erreur de niveau : croissances enchaînées, interrompues au premier réalisé manquant | Un niveau « réalisé » reconstitué par-dessus une année inconnue |
| Fourchette par classe de croissance projetée et groupe de revenu, calibration vérifiée sur une période ultérieure ; bornes dans le bon sens | Une fourchette tirée d'un biais national qui ne se reproduit pas, ou une fourchette inversée |
| Pente d'efficience et croissance cumulée projetée exactes | Un biais mesuré sans tenir compte de l'ampleur de la croissance annoncée |
| Prévision naïve limitée à ce que le FMI savait ; avril et octobre séparés ; monde contre le seul FMI | Un étalon qui voit l'avenir, deux éditions confondues, ou un biais mondial gonflé par une pondération différente |
| Archive : chaque édition et ses métadonnées une seule fois, telles que servies | Une publication d'époque remplacée par une version corrigée après coup |
| PIB en volume par habitant = volume / population raccordée, observé comme projeté ; une population manquante laisse la case vide | Un PIB par habitant projeté sur une population d'une autre source, ou inventé |
| Récessions : pire année des horizons 1 à h, interrompue au premier réalisé manquant ; premières économies comptées par édition | Un recul de l'année de l'édition compté comme imprévu, ou « 20 premières économies » qui n'en comptaient que 10 |
| Révisions entre éditions consécutives seulement, étapes dans l'ordre ; historique contrôlé sur une année observée ; changements de norme et d'année de base lus dans les métadonnées du FMI, indéterminés quand elles manquent | Une révision calculée par-dessus une édition manquante, une révision de l'inflation prévue prise pour un changement d'année de base, ou un changement d'année de base manqué faute d'inflation |
| Commentaires de la page déduits des chiffres | Une conclusion écrite d'avance que la prochaine édition démentirait |
| Scénarios pour le trafic : bornes et corrections dans le bon sens, croissance de l'OCDE du pays sinon de sa région, variantes de population de l'ONU appliquées aux seules années projetées | Un scénario bas plus haut que le central, ou une population « basse » qui modifie le passé observé |
| Au-delà de l'horizon du FMI : dérive tirée des seules années connues à la date de l'édition ; loi ajustée sur les horizons assez fournis, y compris quand un quantile change de signe ; fourchette du pays conservée à l'horizon du FMI puis élargie, bornes basse et haute dans le bon sens | Une dérive qui connaît l'année en cours, une loi tirée de deux éditions, ou une fourchette qui saute en 2032 |
| Fourchettes : cas passés classés selon le groupe de revenu publié avant leur édition (avril : exercice v ; octobre : v + 1), groupe actuel à défaut | Des pays devenus riches en dépassant les prévisions comptés parmi les riches dès 1999 |
| Population : erreur projetée / estimée − 1 après la révision, jusqu'à la dernière année estimée ; taille du pays donnée par la révision pour son année ; bornes calibrées jamais plus étroites que celles de l'ONU, absentes du passé observé | Des bornes calibrées sur des pays rangés selon leur taille future, ou une population « haute » qui modifie le passé |
| Variante élargie des pays riches : identique aux bornes retenues jusqu'en 2031, milieu figé au-delà du dernier horizon ajusté, largeur jamais sous le plancher, autres groupes inchangés | Une variante qui saute en 2032, ou qui touche les pays qu'elle ne vise pas |
| PIB par habitant des tirages : PIB total du tirage divisé par sa population | Une population surprise sans effet sur le revenu par habitant |
| Population des tirages : bornes calibrées de chaque pays gardées exactement, rang parmi tous les cas passés de la classe de taille (le choc commun d'une révision reste commun), position relative constante d'une année à l'autre | Une population tirée qui sort de sa fourchette, ou des surprises communes effacées |
| Chiffres clés : mis en forme comme dans le texte, LaTeX compris ; les anciennes valeurs d'un chiffre changé sont retrouvées ligne par ligne ; la documentation cite les valeurs des sorties | Une relance qui laisse la documentation citer les chiffres de l'édition précédente |
| Trajectoires conjointes : chaque pays garde exactement sa fourchette, le choc commun d'une édition touche tous les pays, la position relative tient au-delà de 2031, le bootstrap tire ensemble avril et octobre | Des tirages qui reprennent le biais propre d'un pays, ou un agrégat dont la précision est surestimée |
| Crises mondiales à part : récessions et historique mondial connus à la date de l'édition ; repli sans période en crise ; mélange pondéré dans le bon sens | Une probabilité qui connaît les crises à venir, ou vide faute d'exemple |
| Calibration en temps réel : aucune erreur encore inconnue à la date de l'édition ; score d'intervalle, CRPS et compétence de Brier exacts ; méthodes comparées sur les mêmes cas | Une calibration flatteuse parce qu'elle voit l'avenir, ou des méthodes comparées sur des échantillons différents |
| Millésimes des WDI : champs lus par nom, chaque édition archivée une fois, première publication réelle seulement, valeur en temps réel à la fin de l'année suivante | Une révision mesurée depuis une édition qui n'était pas la première, ou une référence « en temps réel » qui connaît l'avenir |
| Trafic et PIB : JSON-stat d'Eurostat décodé dans le bon ordre ; retard du trafic mesuré sur la tendance, écart de PIB réalisé moins projeté | Un trafic attribué au mauvais pays ou à la mauvaise année, ou une part expliquée de signe inversé |
| Cas d'étude : estimation actuelle tirée de la dernière édition archivée ; reculs annoncés rapportés aux reculs survenus | Un « réalisé » qui n'est que l'estimation d'il y a deux ans, ou une part calculée à l'envers |

Chaque invariant est **validé par mutation** : le défaut correspondant, réintroduit dans une copie du code, fait bien échouer la suite. Les tests marqués `donnees` contrôlent les CSV réellement produits et se sautent tant que le pipeline n'a pas tourné. Les tests tournent à chaque push (GitHub Actions).

---

## 📜 Historique

`HISTORIQUE.md` retrace les défauts corrigés et les choix de méthode, avec leurs raisons ; `docs/documentation_gdp.pdf` en donne la version de référence.
