#!/usr/bin/env python3
"""
produire_rapports.py
--------------------
Chaîne complète en une commande : collecte et calcul (`gdp_pipeline.py`), puis, pour
chaque rapport produit — la référence, et le cas échéant le plus récent, dans
`plus_recent/` —, évaluation des prévisions, graphiques et page de résultats.

    python produire_rapports.py

Les arguments de bornes sont transmis à `gdp_pipeline.py`. S'arrête, avec un code de
sortie non nul, à la première étape en échec.
"""

import os
import sys
import logging
import argparse
import subprocess

from gdp_pipeline import SOUS_DOSSIER_RECENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def lancer(script: str, *arguments: str) -> None:
    commande = [sys.executable, os.path.join(DOSSIER, script), *arguments]
    logging.info(f"$ {script} {' '.join(arguments)}")
    subprocess.run(commande, check=True)


def main():
    parser = argparse.ArgumentParser(description="Collecte, calcul et livrables de chaque rapport PIB.")
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None,
                        help="Impose la dernière année observée (rapport unique)")
    parser.add_argument("--fcst-end", type=int, default=None)
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()

    bornes = [argument for nom, valeur in (("--start-year", args.start_year),
                                           ("--end-year", args.end_year),
                                           ("--fcst-end", args.fcst_end))
              if valeur is not None for argument in (nom, str(valeur))]

    try:
        lancer("gdp_pipeline.py", *bornes, "--data-dir", args.data_dir, "--output-dir", args.output_dir)

        rapports = [(args.data_dir, args.output_dir)]
        recent = (os.path.join(args.data_dir, SOUS_DOSSIER_RECENT),
                  os.path.join(args.output_dir, SOUS_DOSSIER_RECENT))
        if os.path.isdir(recent[0]):
            rapports.append(recent)

        # Le classeur des prévisions d'époque est commun aux deux rapports
        classeur = os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")
        for data_dir, output_dir in rapports:
            if os.path.exists(classeur):
                lancer("evaluate_forecasts.py", "--data-dir", data_dir, "--classeur", classeur)
            else:
                logging.warning(f"{classeur} absent : évaluation des prévisions omise.")
            lancer("visualize_gdp.py", "--data-dir", data_dir, "--output-dir", output_dir)
            lancer("build_results_page.py", "--data-dir", data_dir, "--output-dir", output_dir)
    except subprocess.CalledProcessError as e:
        logging.error(f"Étape en échec : {os.path.basename(e.cmd[1])}. Chaîne interrompue.")
        sys.exit(1)

    logging.info("Rapports produits : " + " ; ".join(sortie for _, sortie in rapports))


if __name__ == "__main__":
    main()
