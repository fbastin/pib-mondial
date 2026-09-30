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
volume et en dollars, et révisions de l'historique — changement d'année de base, nouvelle
estimation des comptes (`data/processed/weo_edition_revisions.csv`).

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
