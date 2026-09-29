# Historique du Projet PIB mondial

Journal des défauts corrigés et des choix de méthode, du plus récent au plus ancien.
L'usage courant est décrit dans le `README.md`, la méthode dans `documentation_gdp.pdf`.

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
