#!/usr/bin/env python3
"""
classeur.py
-----------
Le classeur Excel d'un rapport, `gdp_master_dataset.xlsx` : son écriture, et sa
reconstruction depuis les CSV du rapport.

Chaque onglet reprend un fichier de `data/processed/` : la synthèse (et ses trente
premières lignes), la série unifiée, les deux extractions brutes, puis les fourchettes
ajoutées par l'évaluation. Le pipeline et l'évaluation l'écrivent par `ecrire` et
`ajouter_fourchettes` ; `reconstruire` relit les mêmes CSV et passe par les mêmes
fonctions, si bien que le classeur reconstruit est celui du pipeline, cellule par cellule.

C'est ce qui permet de restaurer les sorties d'une sauvegarde qui n'a gardé que les données,
sans rappeler les API, dont les valeurs ont changé depuis : le classeur par ce module, les
graphiques et la page de résultats par `pib.visualize_gdp` et `pib.build_results_page`.

Les flottants sont relus avec `float_precision="round_trip"` : la lecture par défaut de
pandas arrondit le dernier chiffre d'environ un nombre sur cinq.

    python -m pib.classeur --data-dir data --output-dir outputs
"""

import os
import json
import logging
import argparse

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

NOM = "gdp_master_dataset.xlsx"
FOURCHETTES = "gdp_projection_bands.csv"


def ecrire(chemin: str, synthese: pd.DataFrame, unifie: pd.DataFrame, historique: pd.DataFrame,
           prevision: pd.DataFrame, debut: int, horizon: int) -> None:
    """Classeur d'un rapport : synthèse, série unifiée et extractions brutes des deux sources."""
    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        synthese.head(30).to_excel(writer, sheet_name="Top30_Economies", index=False)
        synthese.to_excel(writer, sheet_name="Synthese_Pays", index=False)
        unifie.to_excel(writer, sheet_name=f"Series_Temporelles_{debut}_{horizon}", index=False)
        historique.to_excel(writer, sheet_name="Donnees_Historiques_Brutes", index=False)
        prevision.to_excel(writer, sheet_name="Previsions_FMI_Brutes", index=False)


def ajouter_fourchettes(chemin: str, fourchettes: pd.DataFrame, annee_fin: int) -> None:
    """Onglet `Fourchettes_<année>` : les fourchettes empiriques autour des projections."""
    with pd.ExcelWriter(chemin, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        fourchettes.to_excel(writer, sheet_name=f"Fourchettes_{annee_fin}", index=False)


def _lire(chemin: str) -> pd.DataFrame:
    return pd.read_csv(chemin, encoding="utf-8-sig", float_precision="round_trip")


def reconstruire(data_dir: str, output_dir: str) -> str:
    """
    Reconstruit le classeur d'un rapport depuis ses CSV ; rend son chemin.

    Les noms des fichiers suivent les bornes de `extraction_metadata.json`, comme les
    écrit `gdp_pipeline.write_report`. L'onglet des fourchettes n'est ajouté que si
    l'évaluation les a produites. Lève `FileNotFoundError` si un fichier manque.
    """
    from pib.gdp_pipeline import unified_csv_path  # gdp_pipeline importe ce module

    with open(os.path.join(data_dir, "extraction_metadata.json"), encoding="utf-8") as f:
        bornes = json.load(f)["bornes"]
    (debut, fin), horizon = bornes["historique"], bornes["prevision"][1]
    processed = os.path.join(data_dir, "processed")
    os.makedirs(output_dir, exist_ok=True)
    chemin = os.path.join(output_dir, NOM)

    ecrire(chemin,
           _lire(os.path.join(processed, "gdp_country_summary.csv")),
           _lire(unified_csv_path(data_dir)),
           _lire(os.path.join(processed, f"gdp_historical_{debut}_{fin}.csv")),
           _lire(os.path.join(processed, f"gdp_forecast_{fin + 1}_{horizon}.csv")),
           debut, horizon)
    fourchettes = os.path.join(processed, FOURCHETTES)
    if os.path.exists(fourchettes):
        ajouter_fourchettes(chemin, _lire(fourchettes), horizon)
    else:
        logging.warning(f"{fourchettes} absent : classeur sans l'onglet des fourchettes.")
    return chemin


def main():
    parser = argparse.ArgumentParser(description="Reconstruit le classeur Excel d'un rapport depuis ses CSV.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()
    logging.info(f"Classeur reconstruit : {reconstruire(args.data_dir, args.output_dir)}")


if __name__ == "__main__":
    main()
