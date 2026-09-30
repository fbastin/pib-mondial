# WEO Historical Forecasts Database

`WEOhistorical.xlsx` rassemble les prévisions du *World Economic Outlook* **telles que
publiées à l'époque**, toutes éditions confondues depuis 1990. C'est la source qui permet
d'évaluer la qualité des prévisions, ce que l'API du FMI ne permet pas : celle-ci ne sert
que le millésime courant, dont les valeurs pour 2020 sont l'estimation d'aujourd'hui — pas
ce qui était projeté en 2018.

## Contenu

| | |
|---|---|
| Éditions | 73, du printemps 1990 au printemps 2026 (S = *Spring*, F = *Fall*) |
| Entités | 201, dont 6 agrégats du FMI (codes en `G…`) |
| Années visées | 1988 à 2031 |
| Horizons | −2 à +5 : chaque édition ré-estime deux ans de passé, cadre l'année en cours et projette cinq ans |

Trois onglets, un par indicateur :

| Onglet | Contenu |
|---|---|
| `ngdp_rpch` | Croissance du PIB réel (%) — utilisé par défaut |
| `pcpi_pch` | Inflation, prix à la consommation (%) |
| `bca_gdp_bp6` | Balance courante (% du PIB) |

## Structure

Une ligne par (pays, année visée) ; une colonne par édition, nommée `S2019ngdp_rpch` ou
`F2019ngdp_rpch`. Les valeurs manquantes sont notées `.` et non vides — un `dropna` naïf
les laisserait passer, et un `fillna(0)` en ferait des croissances nulles.

Les codes pays sont ceux de la colonne `ISOAlpha_3Code`, à deux exceptions près que
`pib/evaluate_forecasts.py` convertit vers les codes de la Banque Mondiale : `KOS` (Kosovo,
`XKX`) et `WBG` (Cisjordanie et Gaza, `PSE`).

L'horizon de projection se déduit de l'écart entre l'année visée et l'année de l'édition :
positif pour une prévision, nul pour l'année en cours, **négatif pour une ré-estimation
d'une année déjà écoulée**. Cette distinction est le cœur de l'exercice : compter les
ré-estimations parmi les prévisions reviendrait à mesurer la capacité du FMI à se souvenir
du passé plutôt qu'à anticiper l'avenir.

## Téléchargement

Le fichier se télécharge manuellement, le site du FMI refusant les requêtes automatisées
(403 sur toutes les variantes d'URL testées) :

* Lien direct utilisé :
  <https://data.imf.org/-/media/iData/External-Storage/Documents/977574FA66914EAD900D3FEC55C7316A/en/WEOhistorical.xlsx>
* Page de recherche officielle, si le lien direct est rompu :
  <https://data.imf.org/en/Search-Results> — rechercher « WEO Historical Forecasts Database »

⚠️ Le FMI réorganise régulièrement ses serveurs et publie deux éditions par an. **Ce lien
direct a de fortes chances d'être caduc d'ici 2027** ; passer alors par la page de recherche.

Déposer le fichier ici, sous ce nom, sans le convertir.

## Complément automatique : `weo_editions_api.csv`

Retélécharger le classeur n'est plus nécessaire pour suivre les nouvelles éditions.
L'API SDMX du FMI (`api.imf.org`), qui accepte les scripts, sert l'édition courante du WEO
(flux `WEO`) et quelques éditions archivées (`WEO_2025_OCT_VINTAGE`…). Leurs valeurs sont
celles du classeur — vérifié sur `S2026` et `F2025`, écart ≤ 0,0005 point — avec les mêmes
codes pays (`KOS`, `WBG`) et agrégats (`G001`…).

`python -m pib.update_weo_editions` (lancé aussi par `produire_rapports.py`) ajoute dans
`weo_editions_api.csv` les éditions servies par l'API et absentes du classeur, pour les
trois onglets, sur les horizons −2 à +5. Correspondance des indicateurs :

| Onglet | Indicateur SDMX |
|---|---|
| `ngdp_rpch` | `NGDP_RPCH` |
| `pcpi_pch` | `PCPIPCH` |
| `bca_gdp_bp6` | `BCA_NGDPD` |

* Le fichier est **cumulatif** : l'API ne garde que les éditions récentes, une édition
  qu'elle ne sert plus reste dans le complément. Il est versionné, comme le classeur.
* Le **classeur fait foi** : une édition qu'il contient sort du complément.
* Le flux courant ne dit pas quelle édition il porte. Le script la déduit de la plus récente
  archive (après `F2025`, c'est `S2026`) et vérifie que la dernière année servie vaut
  l'année de l'édition + 5 ; sinon il s'arrête plutôt que de deviner.

## Archive des éditions complètes

Le même script archive chaque édition servie en entier (tous indicateurs, PIB en dollars
courants compris) dans `weo_archive/` : voir `weo_archive/LISEZ-MOI.md`.

## Utilisation

```bash
python -m pib.evaluate_forecasts                        # croissance du PIB réel
python -m pib.evaluate_forecasts --indicateur pcpi_pch  # inflation
```

Produit dans `data/processed/` :

* `weo_forecast_evaluation_<indicateur>.csv` — une ligne par projection, avec son horizon
  et son erreur face à la ré-estimation du FMI à un an et, pour la croissance du PIB
  seulement, à la série observée de la Banque Mondiale ;
* `weo_forecast_bias_<indicateur>.csv` — biais et erreur absolue par horizon : moyens,
  pondérés par le PIB, médians, avec un intervalle de confiance groupé par année visée et
  le biais hors récessions mondiales (2009, 2020) ;
* `weo_forecast_bias_by_income_<indicateur>.csv` — biais par horizon et groupe de revenu ;
* `weo_forecast_bias_by_season_<indicateur>.csv` — biais par horizon et saison d'édition ;
* `weo_forecast_vs_naive_<indicateur>.csv` — le FMI face à une prévision naïve (croissance
  moyenne des années v−5 à v−2, déjà connues du FMI à l'édition v) ;
* `weo_world_bias_<indicateur>.csv` — l'agrégat mondial `G001`, contre sa seule ré-estimation ;
* pour la croissance du PIB seulement : `weo_level_evaluation_ngdp_rpch.csv` et ses
  synthèses (`weo_level_bias_*`), l'erreur sur le niveau du PIB obtenue en enchaînant les
  croissances, par horizon, groupe de revenu et classe de croissance projetée, et
  `gdp_projection_bands.csv`, la fourchette qu'elle donne autour des projections du rapport,
  avec son test rétrospectif (`gdp_projection_bands_calibration.csv`) ;
* `weo_forecast_efficiency_<indicateur>.csv` — test d'efficience : pente du réalisé sur le
  prévu, et biais médian par quintile de prévision.

Pour l'inflation, lire les médianes : quelques projections d'hyperinflation (le Venezuela
à 10 000 000 %) portent les moyennes à des milliers de points. Le script le signale.

Le graphique `outputs/gdp_forecast_accuracy.png` est ensuite produit par `python -m pib.visualize_gdp`.
`python produire_rapports.py` enchaîne ces étapes, pour chaque rapport.
