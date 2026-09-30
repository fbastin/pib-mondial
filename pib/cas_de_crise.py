#!/usr/bin/env python3
"""
cas_de_crise.py
---------------
Cas d'étude d'une récession mondiale dans les prévisions du FMI : la chute avait-elle
été prévue, le rebond qui a suivi l'avait-il été, et le niveau du PIB a-t-il retrouvé
la trajectoire attendue avant le choc ?

Quatre tableaux, écrits dans `data/processed/` :

- `weo_cas_<année>_croissance.csv` : croissance de l'année du choc et de la suivante,
  selon chaque édition, pour le monde, les grands agrégats et les premières économies ;
- `weo_cas_<année>_reculs.csv` : pays dont chaque édition annonçait le recul l'année du
  choc, face à ceux qui ont reculé ;
- `weo_cas_<année>_rebond.csv` : erreur de chaque édition sur la croissance de l'année
  suivante ;
- `weo_cas_<année>_niveaux.csv` : niveau du PIB en volume projeté par chaque édition et
  réalisé, base 100 deux ans avant le choc.

Le réalisé se lit de deux façons : la ré-estimation du FMI un an après, référence de
l'évaluation, et l'estimation actuelle, tirée de la dernière édition archivée
(`data/raw/weo_archive/`), qui intègre toutes les révisions des comptes depuis.

    python -m pib.cas_de_crise --annee 2009      # crise financière
    python -m pib.cas_de_crise --annee 2020      # pandémie

Le classeur historique ne contient que les éditions d'avril et d'octobre : les mises à
jour intermédiaires du WEO (janvier, juillet, et celle de novembre 2008) n'y figurent pas.
"""

import os
import sys
import logging
import argparse

import numpy as np
import pandas as pd

from pib.evaluate_forecasts import (
    CODE_MONDE,
    WEO_VERS_ISO3,
    _moyenne_ponderee,
    contexte_pays,
    exclure_agregats,
    lire_base_historique,
    realise_selon_fmi,
)
from pib.revisions_weo import editions_archivees

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Agrégats du WEO suivis à côté des pays : monde, économies avancées, émergentes
AGREGATS = {CODE_MONDE: "Monde", "G110": "Économies avancées", "G200": "Économies émergentes et en développement"}
PREMIERES_ECONOMIES = 10

# Années après le choc où le niveau est comparé : le rebond, puis la moyenne période
ANNEES_NIVEAU = (0, 2, 4)


def editions_autour(annee: int) -> list:
    """Éditions de l'année précédant le choc à l'année qui le suit : avril et octobre."""
    return [f"{saison}{a}" for a in (annee - 1, annee, annee + 1) for saison in ("S", "F")]


def estimation_actuelle(archive: str) -> pd.Series:
    """
    Croissance réelle selon la dernière édition archivée, par pays et année, aux codes de
    la Banque Mondiale. Le classeur historique ne peut pas la donner : chaque édition n'y
    ré-estime que les deux années précédentes.
    """
    editions = editions_archivees(archive)
    if not editions:
        return pd.Series(dtype=float, index=pd.MultiIndex.from_arrays([[], []], names=["country_code", "year"]))
    d = pd.read_csv(os.path.join(archive, f"WEO_{editions[-1]}.csv.gz"))
    d = d[d["indicator"] == "NGDP_RPCH"].assign(country_code=lambda x: x["country_code"].replace(WEO_VERS_ISO3))
    logging.info(f"Estimation actuelle : édition {editions[-1]}.")
    return d.set_index(["country_code", "year"])["value"]


def croissance_par_edition(base: pd.DataFrame, annee: int, codes: dict, actuel: pd.Series) -> pd.DataFrame:
    """
    Croissance de `annee` et de `annee + 1` selon chaque édition (`editions_autour`),
    la ré-estimation du FMI un an après (`realise_fmi`) et l'estimation actuelle (`actuel`).
    """
    editions = editions_autour(annee)
    premier = realise_selon_fmi(base).set_index(["country_code", "year"])["realise_fmi"]
    lignes = []
    for visee in (annee, annee + 1):
        d = base[(base["year"] == visee) & base["vintage"].isin(editions) & base["country_code"].isin(codes)]
        t = d.pivot_table(index="country_code", columns="vintage", values="valeur").reindex(index=list(codes),
                                                                                           columns=editions)
        t.insert(0, "annee_visee", visee)
        t.insert(0, "nom", [codes[c] for c in t.index])
        t["realise_fmi"] = [premier.get((c, visee), np.nan) for c in t.index]
        t["estimation_actuelle"] = [actuel.get((c, visee), np.nan) for c in t.index]
        lignes.append(t)
    return pd.concat(lignes).rename_axis("country_code").reset_index()


def reculs_annonces(pays: pd.DataFrame, annee: int, poids: pd.Series) -> pd.DataFrame:
    """
    Pour chaque édition, les pays dont elle annonçait le recul en `annee`, face à ceux qui
    ont reculé selon la ré-estimation à un an : nombre, part du PIB mondial (`poids`, par
    pays), et part des reculs survenus que l'édition annonçait.
    """
    realise = realise_selon_fmi(pays)
    realise = realise[realise["year"] == annee].set_index("country_code")["realise_fmi"]
    lignes = []
    for edition in editions_autour(annee)[:4]:
        prevu = pays[(pays["year"] == annee) & (pays["vintage"] == edition)].set_index("country_code")["valeur"]
        if prevu.empty:
            continue
        reel = realise.reindex(prevu.index)
        connus = reel.notna()
        w = poids.reindex(prevu.index)
        annonce, survenu = prevu < 0, reel < 0
        lignes.append({
            "edition": edition, "pays": len(prevu),
            "recul_annonce": int(annonce.sum()),
            "recul_annonce_part_pib_pct": _moyenne_ponderee(annonce.astype(float), w) * 100,
            "recul_survenu": int(survenu.sum()),
            "recul_survenu_part_pib_pct": _moyenne_ponderee(survenu[connus].astype(float), w[connus]) * 100,
            "reculs_survenus_annonces_pct": (annonce & survenu).sum() / survenu.sum() * 100 if survenu.any() else np.nan,
        })
    return pd.DataFrame(lignes).round(2)


def erreurs_du_rebond(pays: pd.DataFrame, annee: int, poids: pd.Series) -> pd.DataFrame:
    """
    Erreur de chaque édition sur la croissance de `annee + 1`, contre la ré-estimation à un
    an (prévu − réalisé, en points) : médiane, pondérée par le PIB, et part des pays dont le
    rebond a été sous-estimé.
    """
    visee = annee + 1
    realise = realise_selon_fmi(pays)
    realise = realise[realise["year"] == visee].set_index("country_code")["realise_fmi"]
    lignes = []
    for edition in editions_autour(annee):
        prevu = pays[(pays["year"] == visee) & (pays["vintage"] == edition)].set_index("country_code")["valeur"]
        erreur = (prevu - realise.reindex(prevu.index)).dropna()
        if erreur.empty:
            continue
        lignes.append({"edition": edition, "annee_visee": visee, "pays": len(erreur),
                       "erreur_mediane": erreur.median(),
                       "erreur_ponderee_pib": _moyenne_ponderee(erreur, poids.reindex(erreur.index)),
                       "rebond_sous_estime_pct": (erreur < 0).mean() * 100})
    return pd.DataFrame(lignes).round(3)


def indice_de_niveau(croissance: pd.Series, debut: int, fin: int) -> pd.Series:
    """Niveau base 100 l'année précédant `debut`, en enchaînant les croissances de `debut` à `fin`."""
    annees = range(debut, fin + 1)
    return pd.Series(100 * np.cumprod(1 + croissance.reindex(annees).to_numpy() / 100), index=annees)


def niveaux_par_edition(base: pd.DataFrame, annee: int, codes: dict, actuel: pd.Series) -> pd.DataFrame:
    """
    Niveau du PIB en volume, base 100 deux ans avant le choc, aux années `annee + k`
    (`ANNEES_NIVEAU`) : projeté par la dernière édition d'avant le choc (octobre de l'année
    précédente) et par les suivantes, puis réalisé — ré-estimations à un an enchaînées
    (`realise_fmi`), et estimation actuelle (`actuel`). Chaque édition enchaîne ses propres
    valeurs : estimations pour les années écoulées, projections ensuite.
    """
    debut, fin = annee - 1, annee + max(ANNEES_NIVEAU)
    editions = editions_autour(annee)[1:5]
    premier = realise_selon_fmi(base).set_index(["country_code", "year"])["realise_fmi"]
    lignes = []
    for code, nom in codes.items():
        series = {e: base[(base["country_code"] == code) & (base["vintage"] == e)].set_index("year")["valeur"]
                  for e in editions}
        for source, realise in (("realise_fmi", premier), ("estimation_actuelle", actuel)):
            series[source] = (realise.xs(code, level="country_code") if code in realise.index.get_level_values(0)
                              else pd.Series(dtype=float))
        for source, croissance in series.items():
            niveau = indice_de_niveau(croissance, debut, fin)
            lignes.append({"country_code": code, "nom": nom, "source": source,
                           **{f"niveau_{annee + k}": niveau[annee + k] for k in ANNEES_NIVEAU}})
    return pd.DataFrame(lignes).round(2)


def main():
    parser = argparse.ArgumentParser(description="Une récession mondiale dans les prévisions du FMI.")
    parser.add_argument("--annee", type=int, default=2009, help="Année du recul (2009, 2020…)")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--classeur", type=str, default=None, help="Chemin du classeur WEOhistorical.xlsx")
    parser.add_argument("--archive", type=str, default=None,
                        help="Archive des éditions (par défaut : weo_archive/ à côté du classeur)")
    args = parser.parse_args()

    chemin = args.classeur or os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")
    try:
        base = lire_base_historique(chemin, "ngdp_rpch")
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        sys.exit(1)
    manquantes = [e for e in editions_autour(args.annee) if e not in set(base["vintage"])]
    if manquantes:
        logging.error(f"Éditions absentes du classeur : {', '.join(manquantes)}.")
        sys.exit(1)

    pays = exclure_agregats(base, args.data_dir)
    poids, _ = contexte_pays(args.data_dir)
    if poids.empty:
        logging.error("Série du pipeline indisponible : poids et premières économies inconnus.")
        sys.exit(1)
    avant = poids[poids["year"] == args.annee - 1].set_index("country_code")["poids_pib"]
    premieres = avant[avant.index.isin(set(pays["country_code"]))].nlargest(PREMIERES_ECONOMIES).index
    noms = pays.drop_duplicates("country_code").set_index("country_code")["country"]
    codes = {**AGREGATS, **{c: noms[c] for c in premieres}}

    actuel = estimation_actuelle(args.archive or os.path.join(os.path.dirname(chemin), "weo_archive"))
    if actuel.empty:
        logging.warning("Aucune édition archivée : pas d'estimation actuelle.")

    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)
    tableaux = {
        "croissance": croissance_par_edition(base, args.annee, codes, actuel),
        "reculs": reculs_annonces(pays, args.annee, poids[poids["year"] == args.annee].set_index("country_code")["poids_pib"]),
        "rebond": erreurs_du_rebond(pays, args.annee, poids[poids["year"] == args.annee + 1].set_index("country_code")["poids_pib"]),
        "niveaux": niveaux_par_edition(base, args.annee, codes, actuel),
    }
    for nom, tableau in tableaux.items():
        chemin_csv = os.path.join(processed, f"weo_cas_{args.annee}_{nom}.csv")
        tableau.to_csv(chemin_csv, index=False, encoding="utf-8-sig")
        logging.info(f"{chemin_csv} :\n{tableau.round(1).to_string(index=False)}")


if __name__ == "__main__":
    main()
