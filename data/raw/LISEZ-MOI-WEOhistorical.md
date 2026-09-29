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
`evaluate_forecasts.py` convertit vers les codes de la Banque Mondiale : `KOS` (Kosovo,
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

## Utilisation

```bash
python evaluate_forecasts.py                        # croissance du PIB réel
python evaluate_forecasts.py --indicateur pcpi_pch  # inflation
```

Produit dans `data/processed/` :

* `weo_forecast_evaluation_<indicateur>.csv` — une ligne par projection, avec son horizon
  et son erreur face à la ré-estimation du FMI à un an et, pour la croissance du PIB
  seulement, à la série observée de la Banque Mondiale ;
* `weo_forecast_bias_<indicateur>.csv` — biais et erreur absolue par horizon, en moyenne
  et en médiane.

Pour l'inflation, lire les médianes : quelques projections d'hyperinflation (le Venezuela
à 10 000 000 %) portent les moyennes à des milliers de points. Le script le signale.

Le graphique `outputs/gdp_forecast_accuracy.png` est ensuite produit par `visualize_gdp.py`.
