#!/usr/bin/env python3
"""
produire_rapports.py
--------------------
Chaîne complète en une commande : collecte et calcul (`pib.gdp_pipeline`), ajout des
éditions récentes du WEO servies par l'API du FMI (`pib.update_weo_editions`) et des
éditions archivées des WDI de la Banque Mondiale (`pib.millesimes_bm`), puis, pour
chaque rapport produit — la référence, et le cas échéant le plus récent, dans
`plus_recent/` —, évaluation des prévisions et de leurs révisions, fourchettes au-delà de
l'horizon du FMI et scénarios pour le trafic, graphiques et page de résultats.

    python produire_rapports.py

Les arguments de bornes sont transmis à `pib.gdp_pipeline`. Les chemins relatifs
(`data/`, `outputs/`) partent du répertoire courant : lancer depuis la racine du dépôt.
S'arrête, avec un code de sortie non nul, à la première étape en échec.
"""

import os
import sys
import logging
import argparse
import subprocess

from pib.gdp_pipeline import SOUS_DOSSIER_RECENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def lancer(module: str, *arguments: str) -> None:
    """Lance `python -m pib.<module>`, le paquet restant importable hors de la racine."""
    chemin = os.pathsep.join(filter(None, [DOSSIER, os.environ.get("PYTHONPATH")]))
    logging.info(f"$ python -m pib.{module} {' '.join(arguments)}")
    subprocess.run([sys.executable, "-m", f"pib.{module}", *arguments], check=True,
                   env={**os.environ, "PYTHONPATH": chemin})


def main():
    parser = argparse.ArgumentParser(description="Collecte, calcul et livrables de chaque rapport PIB.")
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None,
                        help="Impose la dernière année observée (rapport unique)")
    parser.add_argument("--fcst-end", type=int, default=None)
    parser.add_argument("--sans-editions-api", action="store_true",
                        help="Ne pas interroger l'API du FMI : ni éditions récentes du WEO, ni archivage")
    parser.add_argument("--sans-millesimes-bm", action="store_true",
                        help="Ne pas collecter les éditions archivées des WDI (Banque Mondiale)")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()

    bornes = [argument for nom, valeur in (("--start-year", args.start_year),
                                           ("--end-year", args.end_year),
                                           ("--fcst-end", args.fcst_end))
              if valeur is not None for argument in (nom, str(valeur))]

    try:
        lancer("gdp_pipeline", *bornes, "--data-dir", args.data_dir, "--output-dir", args.output_dir)

        rapports = [(args.data_dir, args.output_dir)]
        recent = (os.path.join(args.data_dir, SOUS_DOSSIER_RECENT),
                  os.path.join(args.output_dir, SOUS_DOSSIER_RECENT))
        if os.path.isdir(recent[0]):
            rapports.append(recent)

        # Le classeur des prévisions d'époque, et son complément, sont communs aux deux rapports
        classeur = os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")
        if not args.sans_editions_api:
            lancer("update_weo_editions", "--classeur", classeur)
        # Éditions des WDI : la première collecte prend une vingtaine de minutes, les
        # suivantes n'ajoutent que les éditions parues depuis
        if not args.sans_millesimes_bm:
            lancer("millesimes_bm", "--collecter")
        for data_dir, output_dir in rapports:
            if os.path.exists(classeur):
                lancer("evaluate_forecasts", "--data-dir", data_dir, "--output-dir", output_dir,
                       "--classeur", classeur)
                lancer("revisions_weo", "--data-dir", data_dir, "--classeur", classeur)
                lancer("calibration", "--data-dir", data_dir)
                lancer("long_terme", "--data-dir", data_dir)
                lancer("population", "--data-dir", data_dir)
                lancer("scenarios", "--data-dir", data_dir)
                lancer("tirages", "--data-dir", data_dir)
            else:
                logging.warning(f"{classeur} absent : évaluation des prévisions omise.")
            lancer("millesimes_bm", "--data-dir", data_dir)
            lancer("visualize_gdp", "--data-dir", data_dir, "--output-dir", output_dir)
            lancer("build_results_page", "--data-dir", data_dir, "--output-dir", output_dir)
    except subprocess.CalledProcessError as e:
        logging.error(f"Étape en échec : {e.cmd[2]}. Chaîne interrompue.")
        sys.exit(1)

    logging.info("Rapports produits : " + " ; ".join(sortie for _, sortie in rapports))


if __name__ == "__main__":
    main()
