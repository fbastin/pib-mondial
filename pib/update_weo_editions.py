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

Chaque édition servie est en outre archivée en entier — tous pays, tous indicateurs,
PIB en dollars courants compris — dans `data/raw/weo_archive/`. Le classeur historique
ne contient que des taux : ces archives permettront, édition après édition, de mesurer
aussi les erreurs sur les niveaux en dollars courants. Les métadonnées de méthode de
chaque pays (norme des comptes nationaux, année de base, chaînage) y sont archivées à
côté : leur suite dira quand chaque pays a changé de norme ou d'année de base.

    python -m pib.update_weo_editions
"""

import io
import os
import re
import sys
import logging
import argparse
from datetime import date

import pandas as pd

from pib.http_utils import get_json, get_texte

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SDMX = "https://api.imf.org/external/sdmx/2.1"
AGENCE = "IMF.RES"
FLUX_COURANT = "WEO"
MOTIF_ARCHIVE = re.compile(r"^WEO_(\d{4})_([A-Z]{3})_VINTAGE$")
JSON = {"Accept": "application/json"}
# Les métadonnées de chaque pays ne sont rattachées à leur série que dans le format CSV :
# en JSON, leurs valeurs sont listées sans le pays auquel chacune s'applique
CSV = {"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}

# Onglets du classeur et indicateurs SDMX correspondants. Valeurs identiques, vérifié le
# 29 septembre 2026 sur les éditions d'avril 2026 et d'octobre 2025.
INDICATEURS_SDMX = {
    "ngdp_rpch": "NGDP_RPCH",
    "pcpi_pch": "PCPIPCH",
    "bca_gdp_bp6": "BCA_NGDPD",
}

# Comme le classeur : chaque édition ré-estime deux ans de passé et projette cinq ans
HORIZONS = range(-2, 6)

# Métadonnées de méthode que le FMI attache à la croissance du PIB réel de chaque pays :
# norme des comptes nationaux (SCN 1993, SCN 2008, SEC 2010…), année de base des prix
# constants, chaînage des volumes, notes, dernière année observée, source, mise à jour
ATTRIBUTS_METHODE = ("METHODOLOGY", "BASE_YEAR", "CHAIN_WEIGHTED", "METHODOLOGY_NOTES",
                     "LATEST_ACTUAL_ANNUAL_DATA", "HISTORICAL_DATA_SOURCE", "COUNTRY_UPDATE_DATE")

CLASSEUR = os.path.join("data", "raw", "WEOhistorical.xlsx")
COMPLEMENT = os.path.join("data", "raw", "weo_editions_api.csv")
ARCHIVE = os.path.join("data", "raw", "weo_archive")
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


def lire_edition_complete(flux: str) -> pd.DataFrame:
    """
    Toute une édition du WEO : tous pays et agrégats, tous indicateurs, toutes années.
    Colonnes : country_code, indicator, year, value.
    """
    reponse = get_json(f"{SDMX}/data/{AGENCE},{flux}/..A", headers=JSON, timeout=300)
    if not reponse.get("dataSets"):
        raise RuntimeError(f"Flux {flux} : aucune donnée.")

    dimensions = reponse["structure"]["dimensions"]
    pays, indicateurs = dimensions["series"][0]["values"], dimensions["series"][1]["values"]
    annees = [int(str(v["id"])[:4]) for v in dimensions["observation"][0]["values"]]

    lignes = []
    for cle, serie in reponse["dataSets"][0]["series"].items():
        i_pays, i_indicateur = (int(x) for x in cle.split(":")[:2])
        for position, observation in serie.get("observations", {}).items():
            if observation and observation[0] is not None:
                lignes.append((pays[i_pays]["id"], indicateurs[i_indicateur]["id"],
                               annees[int(position)], float(observation[0])))
    return (pd.DataFrame(lignes, columns=["country_code", "indicator", "year", "value"])
            .sort_values(["indicator", "country_code", "year"], ignore_index=True))


def archiver_editions(noms: dict, dossier: str = ARCHIVE) -> list:
    """
    Archive en entier chaque édition servie qui ne l'est pas encore.

    Une édition est archivée telle qu'elle est servie la première fois, puis jamais
    réécrite : c'est la publication d'époque qui compte pour évaluer une prévision, pas
    une version corrigée après coup. `index.csv` consigne, par édition, le flux d'origine,
    la date d'extraction et le volume archivé. Retourne les éditions ajoutées.
    """
    os.makedirs(dossier, exist_ok=True)
    index_csv = os.path.join(dossier, "index.csv")
    index = (pd.read_csv(index_csv) if os.path.exists(index_csv)
             else pd.DataFrame(columns=["edition", "flux", "extrait_le", "valeurs", "entites", "indicateurs", "annees"]))

    ajoutees = []
    for flux, edition in sorted(noms.items(), key=lambda x: (int(x[1][1:]), x[1][0] == "F")):
        chemin = os.path.join(dossier, f"WEO_{edition}.csv.gz")
        if os.path.exists(chemin):
            continue
        donnees = lire_edition_complete(flux)
        donnees.to_csv(chemin, index=False, compression="gzip")
        index = pd.concat([index[index["edition"] != edition], pd.DataFrame([{
            "edition": edition, "flux": flux, "extrait_le": date.today().isoformat(),
            "valeurs": len(donnees), "entites": donnees["country_code"].nunique(),
            "indicateurs": donnees["indicator"].nunique(),
            "annees": f"{donnees['year'].min()}-{donnees['year'].max()}"}])], ignore_index=True)
        ajoutees.append(edition)
        logging.info(f"-> Édition {edition} archivée ({flux}) : {len(donnees):,} valeurs, "
                     f"{donnees['indicator'].nunique()} indicateurs.")

    if ajoutees:
        index.sort_values("edition", key=lambda e: e.str[1:] + e.str[0].map({"S": "0", "F": "1"})).to_csv(
            index_csv, index=False, encoding="utf-8")
    else:
        logging.info("Toutes les éditions servies sont déjà archivées.")
    return ajoutees


def lire_metadonnees(flux: str, edition: str) -> pd.DataFrame:
    """
    Métadonnées de méthode (`ATTRIBUTS_METHODE`) de chaque pays et agrégat d'un flux, telles
    que le FMI les attache à la croissance du PIB réel : une ligne par entité, codes du FMI.
    Elles valent pour toute la série : seule l'année de l'édition est demandée.
    """
    annee = edition[1:]
    texte = get_texte(f"{SDMX}/data/{AGENCE},{flux}/.{INDICATEURS_SDMX['ngdp_rpch']}.A",
                      params={"startPeriod": annee, "endPeriod": annee}, headers=CSV, timeout=120)
    d = pd.read_csv(io.StringIO(texte), dtype=str)
    manquants = [c for c in ("COUNTRY", *ATTRIBUTS_METHODE) if c not in d.columns]
    if d.empty or manquants:
        raise RuntimeError(f"Flux {flux} : métadonnées absentes"
                           + (f" ({', '.join(manquants)})." if manquants else "."))
    return (d.drop_duplicates("COUNTRY").rename(columns={"COUNTRY": "country_code"})
            [["country_code", *ATTRIBUTS_METHODE]].sort_values("country_code", ignore_index=True))


def archiver_metadonnees(noms: dict, dossier: str = ARCHIVE) -> list:
    """
    Archive les métadonnées de méthode (`lire_metadonnees`) de chaque édition servie qui ne
    les a pas encore, dans `WEO_<édition>_metadonnees.csv`, avec leur date d'extraction.

    Comme les données, elles ne sont jamais réécrites. L'API ne les sert que pour les deux
    dernières éditions : c'est leur suite, archivée édition après édition, qui dira quand
    chaque pays a changé de norme ou d'année de base. Retourne les éditions ajoutées.
    """
    os.makedirs(dossier, exist_ok=True)
    ajoutees = []
    for flux, edition in sorted(noms.items(), key=lambda x: (int(x[1][1:]), x[1][0] == "F")):
        chemin = os.path.join(dossier, f"WEO_{edition}_metadonnees.csv")
        if os.path.exists(chemin):
            continue
        meta = lire_metadonnees(flux, edition).assign(extrait_le=date.today().isoformat())
        meta.to_csv(chemin, index=False, encoding="utf-8")
        ajoutees.append(edition)
        logging.info(f"-> Métadonnées de l'édition {edition} archivées ({flux}) : {len(meta)} entités.")
    return ajoutees


def editions_servies() -> tuple:
    """Éditions servies par l'API, nommées ({flux: édition}), et le flux courant (NGDP_RPCH)."""
    flux = lister_flux()
    courant = lire_flux(FLUX_COURANT, INDICATEURS_SDMX["ngdp_rpch"]) if FLUX_COURANT in flux else None
    noms = nommer_editions(flux, int(courant["year"].max()) if courant is not None else 0)
    logging.info("Éditions servies par l'API : " + ", ".join(f"{n} ({f})" for f, n in sorted(noms.items(), key=lambda x: x[1])))
    return noms, courant


def editions_du_classeur(classeur: str, feuille: str) -> set:
    """Éditions présentes dans un onglet du classeur, d'après ses en-têtes (`S2019ngdp_rpch`)."""
    if not os.path.exists(classeur):
        return set()
    entetes = pd.read_excel(classeur, sheet_name=feuille, nrows=0).columns
    return {c.replace(feuille, "") for c in map(str, entetes) if c.endswith(feuille)}


def mettre_a_jour(classeur: str = CLASSEUR, complement: str = COMPLEMENT,
                  noms: dict = None, courant: pd.DataFrame = None) -> dict:
    """
    Ajoute au complément les éditions servies par l'API et absentes du classeur.

    Retourne, par onglet, les éditions ajoutées ou rafraîchies. Lève `RuntimeError` si
    l'API est injoignable ou si l'édition courante ne peut être datée sans ambiguïté.
    """
    if noms is None:
        noms, courant = editions_servies()

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
    parser.add_argument("--archive", type=str, default=None,
                        help="Dossier d'archive des éditions complètes (par défaut : weo_archive/ à côté du classeur)")
    parser.add_argument("--sans-archive", action="store_true",
                        help="Ne pas archiver les éditions complètes ni leurs métadonnées")
    args = parser.parse_args()

    dossier = os.path.dirname(args.classeur)
    complement = args.complement or os.path.join(dossier, "weo_editions_api.csv")
    try:
        noms, courant = editions_servies()
        mettre_a_jour(args.classeur, complement, noms, courant)
        if not args.sans_archive:
            archive = args.archive or os.path.join(dossier, "weo_archive")
            archiver_editions(noms, archive)
            archiver_metadonnees(noms, archive)
    except RuntimeError as e:
        logging.error(f"Mise à jour des éditions du WEO interrompue : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
