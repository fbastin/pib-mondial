#!/usr/bin/env python3
"""
update_weo_editions.py
----------------------
Complète la WEO Historical Forecasts Database par les éditions que l'API SDMX du FMI
sert déjà, sans attendre le téléchargement manuel d'un nouveau classeur.

`data/raw/WEOhistorical.xlsx` ne se télécharge qu'à la main : le site du FMI refuse les
scripts (403). L'API SDMX (api.imf.org), elle, les accepte. Elle sert l'édition courante
du WEO (flux `WEO`) et quelques éditions archivées (`WEO_2025_OCT_VINTAGE`…), aux mêmes
valeurs que le classeur, codes pays compris (`KOS`, `WBG`). Ce script en extrait les
éditions absentes du classeur et les ajoute à `data/raw/weo_editions_api.csv`, que
`evaluate_forecasts.py` lit en complément.

Le fichier est cumulatif : une édition que l'API ne sert plus y reste, puisque l'API ne
garde que les éditions récentes. Une édition présente dans le classeur n'y figure pas :
le classeur fait foi.

    python update_weo_editions.py
"""

import os
import re
import sys
import logging
import argparse
from datetime import date

import pandas as pd

from http_utils import get_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SDMX = "https://api.imf.org/external/sdmx/2.1"
AGENCE = "IMF.RES"
FLUX_COURANT = "WEO"
MOTIF_ARCHIVE = re.compile(r"^WEO_(\d{4})_([A-Z]{3})_VINTAGE$")
JSON = {"Accept": "application/json"}

# Onglets du classeur et indicateurs SDMX correspondants. Valeurs identiques, vérifié le
# 29 septembre 2026 sur les éditions d'avril 2026 et d'octobre 2025.
INDICATEURS_SDMX = {
    "ngdp_rpch": "NGDP_RPCH",
    "pcpi_pch": "PCPIPCH",
    "bca_gdp_bp6": "BCA_NGDPD",
}

# Comme le classeur : chaque édition ré-estime deux ans de passé et projette cinq ans
HORIZONS = range(-2, 6)

CLASSEUR = os.path.join("data", "raw", "WEOhistorical.xlsx")
COMPLEMENT = os.path.join("data", "raw", "weo_editions_api.csv")
COLONNES = ["indicateur", "vintage", "flux", "country", "country_code", "year", "valeur", "extrait_le"]


def lister_flux() -> list:
    """Flux WEO servis par l'API : l'édition courante et les éditions archivées."""
    flux = get_json(f"{SDMX}/dataflow", headers=JSON)["data"]["dataflows"]
    return sorted(f["id"] for f in flux if f["id"] == FLUX_COURANT or MOTIF_ARCHIVE.match(f["id"]))


def nommer_editions(flux: list, horizon_courant: int) -> dict:
    """
    Associe à chaque flux le nom d'édition du classeur (`S2026`, `F2025`).

    Les archives portent leur date (`WEO_2025_OCT_VINTAGE` : octobre, donc `F2025`). Le
    flux courant, non : c'est l'édition qui suit la plus récente archive — le printemps
    suivant après un automne, l'automne de la même année après un printemps. Sa dernière
    année servie, cinq ans après celle de l'édition, doit le confirmer ; sinon rien n'est
    deviné.
    """
    noms = {}
    for f in flux:
        m = MOTIF_ARCHIVE.match(f)
        if m:
            annee, mois = int(m.group(1)), m.group(2)
            saison = "S" if mois in ("JAN", "FEB", "MAR", "APR", "MAY", "JUN") else "F"
            noms[f] = f"{saison}{annee}"

    if FLUX_COURANT in flux:
        if not noms:
            raise RuntimeError("Aucune édition archivée : impossible de dater l'édition courante du WEO.")
        derniere = max(noms.values(), key=lambda n: (int(n[1:]), n[0] == "F"))
        annee = int(derniere[1:])
        courante = f"S{annee + 1}" if derniere[0] == "F" else f"F{annee}"
        if horizon_courant != int(courante[1:]) + 5:
            raise RuntimeError(
                f"Édition courante du WEO incohérente : après {derniere}, {courante} devrait "
                f"s'étendre jusqu'en {int(courante[1:]) + 5}, l'API sert jusqu'en {horizon_courant}.")
        noms[FLUX_COURANT] = courante
    return noms


def lire_flux(flux: str, indicateur_sdmx: str) -> pd.DataFrame:
    """
    Toutes les valeurs d'un indicateur dans un flux WEO, tous pays et agrégats confondus.

    Colonnes : country_code, country, year, valeur. Dans la réponse, les années ne sont
    pas ordonnées et les valeurs sont du texte : tout passe par les identifiants.
    """
    reponse = get_json(f"{SDMX}/data/{AGENCE},{flux}/.{indicateur_sdmx}.A", headers=JSON, timeout=120)
    if not reponse.get("dataSets"):
        raise RuntimeError(f"Flux {flux} : aucune donnée pour {indicateur_sdmx}.")

    dimensions = reponse["structure"]["dimensions"]
    pays = dimensions["series"][0]["values"]
    annees = [int(str(v["id"])[:4]) for v in dimensions["observation"][0]["values"]]

    lignes = []
    for cle, serie in reponse["dataSets"][0]["series"].items():
        entite = pays[int(cle.split(":")[0])]
        for position, observation in serie.get("observations", {}).items():
            if observation and observation[0] is not None:
                lignes.append({"country_code": entite["id"], "country": entite.get("name", entite["id"]),
                               "year": annees[int(position)], "valeur": float(observation[0])})
    return pd.DataFrame(lignes, columns=["country_code", "country", "year", "valeur"])


def editions_du_classeur(classeur: str, feuille: str) -> set:
    """Éditions présentes dans un onglet du classeur, d'après ses en-têtes (`S2019ngdp_rpch`)."""
    if not os.path.exists(classeur):
        return set()
    entetes = pd.read_excel(classeur, sheet_name=feuille, nrows=0).columns
    return {c.replace(feuille, "") for c in map(str, entetes) if c.endswith(feuille)}


def mettre_a_jour(classeur: str = CLASSEUR, complement: str = COMPLEMENT) -> dict:
    """
    Ajoute au complément les éditions servies par l'API et absentes du classeur.

    Retourne, par onglet, les éditions ajoutées ou rafraîchies. Lève `RuntimeError` si
    l'API est injoignable ou si l'édition courante ne peut être datée sans ambiguïté.
    """
    flux = lister_flux()
    courant = lire_flux(FLUX_COURANT, INDICATEURS_SDMX["ngdp_rpch"]) if FLUX_COURANT in flux else None
    noms = nommer_editions(flux, int(courant["year"].max()) if courant is not None else 0)
    logging.info("Éditions servies par l'API : " + ", ".join(f"{n} ({f})" for f, n in sorted(noms.items(), key=lambda x: x[1])))

    existant = pd.read_csv(complement) if os.path.exists(complement) else pd.DataFrame(columns=COLONNES)
    morceaux, ajouts = [], {}
    for feuille, indicateur_sdmx in INDICATEURS_SDMX.items():
        dans_classeur = editions_du_classeur(classeur, feuille)
        # Le classeur fait foi : ce qu'il contient sort du complément
        garde = existant[(existant["indicateur"] == feuille) & ~existant["vintage"].isin(dans_classeur)]

        for f, edition in sorted(noms.items()):
            if edition in dans_classeur:
                continue
            valeurs = courant if (f == FLUX_COURANT and feuille == "ngdp_rpch") else lire_flux(f, indicateur_sdmx)
            annee = int(edition[1:])
            valeurs = valeurs[valeurs["year"].isin([annee + h for h in HORIZONS])]
            valeurs = valeurs.assign(indicateur=feuille, vintage=edition, flux=f,
                                     extrait_le=date.today().isoformat())
            garde = pd.concat([garde[garde["vintage"] != edition], valeurs[COLONNES]], ignore_index=True)
            ajouts.setdefault(feuille, []).append(edition)
        morceaux.append(garde)

    resultat = pd.concat(morceaux, ignore_index=True)[COLONNES]
    if resultat.empty and not os.path.exists(complement):
        logging.info("Le classeur contient déjà toutes les éditions servies par l'API : rien à ajouter.")
        return ajouts

    resultat = resultat.sort_values(["indicateur", "vintage", "country_code", "year"])
    resultat.to_csv(complement, index=False, encoding="utf-8")
    for feuille in INDICATEURS_SDMX:
        editions = sorted(resultat.loc[resultat["indicateur"] == feuille, "vintage"].unique())
        logging.info(f"-> {feuille} : complément {', '.join(editions) or 'vide'}"
                     + (f" (ajout ou rafraîchissement : {', '.join(ajouts[feuille])})" if feuille in ajouts else ""))
    logging.info(f"Complément enregistré : {complement}")
    return ajouts


def main():
    parser = argparse.ArgumentParser(
        description="Ajoute les éditions récentes du WEO, servies par l'API du FMI, au complément du classeur.")
    parser.add_argument("--classeur", type=str, default=CLASSEUR)
    parser.add_argument("--complement", type=str, default=None,
                        help="Fichier complément (par défaut : weo_editions_api.csv à côté du classeur)")
    args = parser.parse_args()

    complement = args.complement or os.path.join(os.path.dirname(args.classeur), "weo_editions_api.csv")
    try:
        mettre_a_jour(args.classeur, complement)
    except RuntimeError as e:
        logging.error(f"Mise à jour des éditions du WEO interrompue : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
