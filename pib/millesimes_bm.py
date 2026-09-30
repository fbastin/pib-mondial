#!/usr/bin/env python3
"""
millesimes_bm.py
----------------
Les données « réalisées » se révisent aussi. La Banque Mondiale archive chaque édition de
ses World Development Indicators : source « WDI Database Archives » de son API, plus de
140 éditions depuis avril 1989. Ce module :

- collecte les éditions manquantes dans `data/raw/wdi_archive/` : croissance du PIB réel
  et PIB en dollars courants, tous pays, toutes années. L'archive n'est pas versionnée,
  puisque l'API sert toutes les éditions ; la première collecte prend une vingtaine de
  minutes, les suivantes n'ajoutent que les éditions nouvelles ;
- mesure les révisions d'une valeur depuis sa première publication : en points pour la
  croissance, en % pour le niveau en dollars (où se lisent les changements d'année de
  base des comptes nationaux) ;
- évalue les prévisions du FMI contre la croissance telle que la Banque Mondiale la
  publiait à la fin de l'année suivant l'année visée : une référence indépendante du FMI
  et connue en temps réel, à côté de la ré-estimation du FMI et de la série actuelle.

    python -m pib.millesimes_bm --collecter                 # éditions manquantes
    python -m pib.millesimes_bm --data-dir data             # analyses d'un rapport
"""

import os
import re
import sys
import logging
import argparse
from datetime import date

import numpy as np
import pandas as pd

from pib.http_utils import get_json
from pib.evaluate_forecasts import GROUPES_REVENU, _moyenne_ponderee, contexte_pays, exclure_agregats

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

API = "https://api.worldbank.org/v2/sources/57"
ARCHIVE = os.path.join("data", "raw", "wdi_archive")
SERIES = {
    "NY.GDP.MKTP.KD.ZG": "croissance",     # croissance du PIB réel, %
    "NY.GDP.MKTP.CD": "pib_usd",           # PIB en dollars courants
}
FICHIER = re.compile(r"WDI_(\d{6})\.csv\.gz")

# Délais après la première publication auxquels la valeur est relue, en années
DELAIS = (1, 2, 5, 10)

# Révisions jugées notables : un point de croissance ; 10 % du niveau en dollars
SEUIL_CROISSANCE = 1.0
SEUIL_NIVEAU = 10.0

# Plus grandes révisions du niveau, parmi les premières économies de la dernière année
PREMIERES_ECONOMIES = 50


# ------------------------------------------------------------------ collecte

def lister_millesimes() -> list:
    """Éditions archivées par la Banque Mondiale (`AAAAMM`), dans l'ordre chronologique."""
    reponse = get_json(f"{API}/version", params={"format": "json", "per_page": 1000})
    variables = reponse["source"][0]["concept"][0]["variable"]
    return sorted(v["id"] for v in variables)


def lire_millesime(version: str, serie: str) -> pd.DataFrame:
    """Valeurs non nulles d'une série dans une édition : country_code, year, value."""
    lignes, page = [], 1
    while True:
        reponse = get_json(f"{API}/country/all/series/{serie}/version/{version}/time/all",
                           params={"format": "json", "per_page": 20000, "page": page})
        for enregistrement in reponse["source"]["data"]:
            if enregistrement.get("value") is None:
                continue
            champs = {v["concept"]: v["id"] for v in enregistrement["variable"]}
            lignes.append({"country_code": champs["Country"], "year": int(champs["Time"][2:]),
                           "value": float(enregistrement["value"])})
        if page >= int(reponse.get("pages", 1)):
            break
        page += 1
    return pd.DataFrame(lignes, columns=["country_code", "year", "value"])


def archiver_millesimes(dossier: str = ARCHIVE, versions: list = None) -> list:
    """
    Collecte les éditions absentes de `dossier`, une fois pour toutes : un fichier
    `WDI_<AAAAMM>.csv.gz` par édition (country_code, series, year, value), et `index.csv`.
    Retourne les éditions ajoutées.
    """
    os.makedirs(dossier, exist_ok=True)
    versions = versions if versions is not None else lister_millesimes()
    presentes = set(millesimes_archives(dossier))
    ajoutees = []
    for version in (v for v in versions if v not in presentes):
        table = pd.concat([lire_millesime(version, serie).assign(series=serie) for serie in SERIES],
                          ignore_index=True)[["country_code", "series", "year", "value"]]
        table.to_csv(os.path.join(dossier, f"WDI_{version}.csv.gz"), index=False)
        index = os.path.join(dossier, "index.csv")
        pd.DataFrame([{"version": version, "extrait_le": date.today().isoformat(), "valeurs": len(table)}]).to_csv(
            index, mode="a", header=not os.path.exists(index), index=False)
        ajoutees.append(version)
        logging.info(f"-> Édition {version} archivée ({len(table):,} valeurs).")
    if not ajoutees:
        logging.info("Toutes les éditions des WDI sont déjà archivées.")
    return ajoutees


def millesimes_archives(dossier: str = ARCHIVE) -> list:
    if not os.path.isdir(dossier):
        return []
    return sorted(m.group(1) for f in os.listdir(dossier) if (m := FICHIER.fullmatch(f)))


def charger_archive(dossier: str = ARCHIVE, serie: str = "NY.GDP.MKTP.KD.ZG") -> pd.DataFrame:
    """Toutes les éditions archivées d'une série : version (entier AAAAMM), country_code, year, value."""
    tables = []
    for version in millesimes_archives(dossier):
        t = pd.read_csv(os.path.join(dossier, f"WDI_{version}.csv.gz"))
        t = t[t["series"] == serie]
        if t.empty:        # les éditions de 1989 à 1993 ne contiennent pas le PIB
            continue
        tables.append(t.drop(columns="series").assign(version=int(version)))
    if not tables:
        return pd.DataFrame(columns=["version", "country_code", "year", "value"])
    return pd.concat(tables, ignore_index=True).astype(
        {"version": int, "country_code": object, "year": int, "value": float})


# ------------------------------------------------------------------ analyses

def revisions_depuis_publication(archive: pd.DataFrame, delais=DELAIS) -> pd.DataFrame:
    """
    Pour chaque pays et année : la première valeur publiée et son édition, puis la valeur
    connue `k` ans plus tard (dernière édition parue au plus `k` ans après la première
    publication), pour chaque `k` de `delais`, et la valeur actuelle (dernière édition).

    Retourne une ligne par pays, année et délai : premiere, valeur, delai (en années, ou
    « actuelle »). Un délai qui dépasse la dernière édition est omis. Les années antérieures
    à la première édition archivée sont écartées : leur première valeur archivée n'est pas
    leur première publication.
    """
    # Clés de même type des deux côtés : la fusion par date (`merge_asof`) l'exige
    a = archive.sort_values("version").astype({"country_code": object})
    premiere = (a.groupby(["country_code", "year"], as_index=False).first()
                .rename(columns={"version": "version_premiere", "value": "premiere"})
                .astype({"country_code": object}))
    premiere = premiere[premiere["year"] >= int(a["version"].min()) // 100 - 1]
    derniere = int(a["version"].max())
    lignes = []
    for k in delais:
        cible = premiere.assign(cible=premiere["version_premiere"] + 100 * k)
        cible = cible[cible["cible"] <= derniere].sort_values("cible")
        if cible.empty:
            continue
        lue = pd.merge_asof(cible, a.rename(columns={"value": "valeur"}), left_on="cible", right_on="version",
                            by=["country_code", "year"], direction="backward")
        lignes.append(lue[["country_code", "year", "version_premiere", "premiere", "valeur"]].assign(delai=str(k)))
    actuelle = a.groupby(["country_code", "year"], as_index=False).last().rename(columns={"value": "valeur"})
    lignes.append(premiere.merge(actuelle[["country_code", "year", "valeur"]], on=["country_code", "year"])
                  [["country_code", "year", "version_premiere", "premiere", "valeur"]].assign(delai="actuelle"))
    return pd.concat(lignes, ignore_index=True)


def _groupes_de_lignes(table: pd.DataFrame) -> list:
    groupes = [("Tous les pays", None, pd.Series(True, index=table.index))]
    if "income_group" in table.columns:
        groupes += [(libelle, code, table["income_group"] == code) for code, libelle in GROUPES_REVENU.items()]
    return groupes


def synthese_croissance(revisions: pd.DataFrame) -> pd.DataFrame:
    """
    Révision de la croissance (valeur au délai − première publication, en points), par
    délai et groupe de revenu : moyenne, médiane, révision absolue moyenne et médiane,
    part des révisions de plus de `SEUIL_CROISSANCE` point, révision absolue pondérée
    par le PIB.
    """
    r = revisions.assign(revision=revisions["valeur"] - revisions["premiere"])
    if "poids_pib" not in r.columns:
        r["poids_pib"] = np.nan
    lignes = []
    for delai, g in r.groupby("delai", sort=False):
        for libelle, code, masque in _groupes_de_lignes(g):
            x = g[masque]
            if x.empty:
                continue
            e = x["revision"]
            lignes.append({"delai": delai, "groupe": libelle, "income_group": code, "valeurs": len(x),
                           "revision_moyenne": e.mean(), "revision_mediane": e.median(),
                           "revision_absolue_moyenne": e.abs().mean(), "revision_absolue_mediane": e.abs().median(),
                           "part_au_dela_du_seuil_pct": (e.abs() > SEUIL_CROISSANCE).mean() * 100,
                           "revision_absolue_ponderee_pib": _moyenne_ponderee(e.abs(), x["poids_pib"])})
    return pd.DataFrame(lignes).round(3)


def synthese_niveau(revisions: pd.DataFrame) -> pd.DataFrame:
    """
    Révision du niveau en dollars (valeur au délai / première publication − 1, en %), par
    délai et groupe de revenu : médiane, révision absolue médiane et 90e centile, parts au-delà
    de 5 % et de `SEUIL_NIVEAU` %.
    """
    r = revisions[revisions["premiere"] > 0]
    r = r.assign(revision=(r["valeur"] / r["premiere"] - 1) * 100)
    lignes = []
    for delai, g in r.groupby("delai", sort=False):
        for libelle, code, masque in _groupes_de_lignes(g):
            x = g[masque]
            if x.empty:
                continue
            e = x["revision"]
            lignes.append({"delai": delai, "groupe": libelle, "income_group": code, "valeurs": len(x),
                           "revision_mediane_pct": e.median(), "revision_absolue_mediane_pct": e.abs().median(),
                           "revision_absolue_p90_pct": e.abs().quantile(0.9),
                           "part_au_dela_de_5pct": (e.abs() > 5).mean() * 100,
                           "part_au_dela_du_seuil_pct": (e.abs() > SEUIL_NIVEAU).mean() * 100})
    return pd.DataFrame(lignes).round(3)


def plus_grandes_revisions(revisions: pd.DataFrame, poids: pd.Series, n: int = 15) -> pd.DataFrame:
    """
    Plus fortes révisions du niveau en dollars, de la première publication à aujourd'hui,
    parmi les `PREMIERES_ECONOMIES` premières économies (`poids`, par pays) : une par pays,
    l'année la plus révisée.
    """
    r = revisions[(revisions["delai"] == "actuelle") & (revisions["premiere"] > 0)]
    r = r[r["country_code"].isin(poids.nlargest(PREMIERES_ECONOMIES).index)]
    r = r.assign(revision_pct=(r["valeur"] / r["premiere"] - 1) * 100)
    r = r.loc[r["revision_pct"].abs().groupby(r["country_code"]).idxmax()]
    return (r.reindex(r["revision_pct"].abs().sort_values(ascending=False).index).head(n)
            [["country_code", "year", "version_premiere", "premiere", "valeur", "revision_pct"]].round(3))


def croissance_en_temps_reel(archive: pd.DataFrame) -> pd.DataFrame:
    """
    Croissance de l'année t telle que la Banque Mondiale la publiait à la fin de l'année
    t + 1 : valeur de la dernière édition parue au plus tard en décembre de t + 1. C'est
    l'équivalent, indépendant du FMI, de sa ré-estimation d'octobre t + 1.
    """
    a = archive.assign(limite=(archive["year"] + 1) * 100 + 12)
    a = a[a["version"] <= a["limite"]].sort_values("version")
    return (a.groupby(["country_code", "year"], as_index=False).last()
            [["country_code", "year", "value"]].rename(columns={"value": "realise_bm_temps_reel"}))


def biais_selon_la_reference(evaluation: pd.DataFrame, temps_reel: pd.DataFrame) -> pd.DataFrame:
    """
    Biais des prévisions de croissance du FMI, par horizon, contre trois références sur les
    mêmes projections : sa propre ré-estimation à un an, la Banque Mondiale en temps réel
    (`croissance_en_temps_reel`) et la série actuelle de la Banque Mondiale.
    """
    references = {"fmi_un_an": "realise_fmi", "bm_temps_reel": "realise_bm_temps_reel", "bm_actuelle": "realise_bm"}
    e = evaluation.merge(temps_reel, on=["country_code", "year"], how="inner").dropna(subset=list(references.values()))
    if "poids_pib" not in e.columns:
        e["poids_pib"] = np.nan
    lignes = []
    for horizon, g in e.groupby("horizon"):
        ligne = {"horizon": horizon, "projections": len(g)}
        for nom, colonne in references.items():
            erreur = g["valeur"] - g[colonne]
            ligne.update({f"biais_moyen_{nom}": erreur.mean(), f"biais_median_{nom}": erreur.median(),
                          f"biais_pondere_pib_{nom}": _moyenne_ponderee(erreur, g["poids_pib"])})
        lignes.append(ligne)
    return pd.DataFrame(lignes).round(3)


def main():
    parser = argparse.ArgumentParser(description="Millésimes des WDI de la Banque Mondiale : révisions du réalisé.")
    parser.add_argument("--collecter", action="store_true", help="Archiver les éditions manquantes")
    parser.add_argument("--data-dir", type=str, default=None, help="Rapport dont produire les analyses")
    parser.add_argument("--archive", type=str, default=ARCHIVE)
    args = parser.parse_args()
    if not args.collecter and args.data_dir is None:
        parser.error("indiquer --collecter, --data-dir, ou les deux")

    if args.collecter:
        try:
            archiver_millesimes(args.archive)
        except RuntimeError as e:
            logging.error(f"Collecte des millésimes interrompue : {e}")
            sys.exit(1)
    if args.data_dir is None:
        return
    if not millesimes_archives(args.archive):
        logging.warning(f"Aucune édition archivée dans {args.archive} : analyses omises "
                        "(lancer d'abord avec --collecter).")
        return

    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)
    poids, groupes = contexte_pays(args.data_dir)
    derniere = poids[poids["year"] == poids["year"].max()].set_index("country_code")["poids_pib"]

    croissance = exclure_agregats(charger_archive(args.archive, "NY.GDP.MKTP.KD.ZG"), args.data_dir)
    niveau = exclure_agregats(charger_archive(args.archive, "NY.GDP.MKTP.CD"), args.data_dir)

    rev_croissance = (revisions_depuis_publication(croissance).merge(poids, on=["country_code", "year"], how="left")
                      .merge(groupes, on="country_code", how="left"))
    rev_niveau = revisions_depuis_publication(niveau).merge(groupes, on="country_code", how="left")
    tableaux = {
        "wdi_growth_revisions.csv": synthese_croissance(rev_croissance),
        "wdi_level_revisions.csv": synthese_niveau(rev_niveau),
        "wdi_largest_level_revisions.csv": plus_grandes_revisions(rev_niveau, derniere),
    }
    evaluation_csv = os.path.join(processed, "weo_forecast_evaluation_ngdp_rpch.csv")
    if os.path.exists(evaluation_csv):
        tableaux["weo_forecast_bias_by_reference_ngdp_rpch.csv"] = biais_selon_la_reference(
            pd.read_csv(evaluation_csv), croissance_en_temps_reel(croissance))
    for nom, table in tableaux.items():
        table.to_csv(os.path.join(processed, nom), index=False, encoding="utf-8-sig")
    t = tableaux["wdi_growth_revisions.csv"]
    logging.info(f"Révisions de la croissance depuis la première publication ({len(millesimes_archives(args.archive))} "
                 "éditions des WDI) :\n" + t[t["income_group"].isna()].to_string(index=False))
    if "weo_forecast_bias_by_reference_ngdp_rpch.csv" in tableaux:
        logging.info("Biais du FMI selon la référence :\n"
                     + tableaux["weo_forecast_bias_by_reference_ngdp_rpch.csv"].to_string(index=False))


if __name__ == "__main__":
    main()
