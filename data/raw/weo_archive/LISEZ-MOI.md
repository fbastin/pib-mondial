# Archive des éditions du WEO

Chaque édition du *World Economic Outlook* servie par l'API SDMX du FMI
(`api.imf.org`) est archivée ici en entier, telle qu'elle a été servie la première fois :
tous les pays et agrégats, tous les indicateurs (145 : PIB en dollars courants, en monnaie
nationale, en volume, en PPA, par habitant, population, prix, finances publiques,
commerce…), toutes les années de l'édition.

`python -m pib.update_weo_editions` s'en charge, et `python produire_rapports.py` le lance
à chaque exécution : une édition nouvelle est archivée dès que l'API la sert, une édition
déjà archivée n'est jamais réécrite. `index.csv` consigne, pour chacune, le flux d'origine,
la date d'extraction et le volume archivé.

## Pourquoi

La *WEO Historical Forecasts Database* (`../WEOhistorical.xlsx`) ne contient que des taux :
croissance, inflation, balance courante. Elle permet d'évaluer les prévisions de croissance,
et d'en déduire l'erreur sur le niveau du PIB en volume, mais pas l'erreur sur le PIB en
dollars courants, qui ajoute les erreurs de change et d'inflation. Or l'API ne sert que
l'édition courante et la précédente. Archiver chaque édition dès sa parution constitue,
édition après édition, la base qui permettra de mesurer ces erreurs.

Dès maintenant, `python -m pib.revisions_weo` (lancé par `produire_rapports.py`) compare
les deux dernières éditions archivées : révision de la croissance cumulée projetée, en
volume et en dollars, révisions de l'historique — nouvelle estimation des comptes, forte
révision du déflateur —, et changements de norme et d'année de base selon les métadonnées
(`data/processed/weo_edition_revisions.csv`).

## Format

`WEO_<édition>.csv.gz` — `S2026` pour avril 2026, `F2025` pour octobre 2025 — en CSV
compressé, lisible directement par `pandas.read_csv` :

| Colonne | Contenu |
|---|---|
| `country_code` | Code du FMI (`KOS` pour le Kosovo, `WBG` pour la Cisjordanie et Gaza, `G001`… pour les agrégats) |
| `indicator` | Code de l'indicateur (`NGDPD`, `NGDP_RPCH`, `LP`…) |
| `year` | Année |
| `value` | Valeur, dans l'unité de l'indicateur |

Premières éditions archivées le 29 septembre 2026 : `F2025` (flux `WEO_2025_OCT_VINTAGE`)
et `S2026` (flux `WEO`).

## Métadonnées des pays

`WEO_<édition>_metadonnees.csv`, en CSV simple : une ligne par pays et agrégat, avec les
métadonnées que le FMI attache à la croissance de son PIB réel. Elles disent sur quelle
définition reposent les chiffres de chaque pays ; leur suite, édition après édition, dira
quand il en a changé. L'API ne les sert que pour les deux dernières éditions, et
seulement dans son format CSV : en JSON, leurs valeurs ne sont pas rattachées à leur pays.

| Colonne | Contenu |
|---|---|
| `country_code` | Code du FMI, comme dans les données |
| `METHODOLOGY` | Norme des comptes nationaux : SCN 1993, SCN 2008, SEC 2010… |
| `BASE_YEAR` | Année de base des prix constants (`2017`, `FY2022/23`…) |
| `CHAIN_WEIGHTED` | Volumes chaînés, et depuis quand (`Yes, from 1980`, `No`) |
| `METHODOLOGY_NOTES` | Notes du FMI : changements de base récents, sources, particularités |
| `LATEST_ACTUAL_ANNUAL_DATA` | Dernière année observée ; les suivantes sont estimées ou projetées |
| `HISTORICAL_DATA_SOURCE` | Source des données historiques |
| `COUNTRY_UPDATE_DATE` | Date de mise à jour des données du pays |
| `extrait_le` | Date d'extraction |

Premières métadonnées archivées le 2 octobre 2026, pour `F2025` et `S2026`. Les fiches ne
sont pas exemptes d'erreurs : entre ces deux éditions, le début du chaînage de cinq pays
européens change sans raison apparente (Pologne : « depuis 2020 », puis « depuis 1995 »).
