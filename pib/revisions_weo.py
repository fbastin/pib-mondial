#!/usr/bin/env python3
"""
revisions_weo.py
----------------
Révisions des prévisions du FMI, d'une édition du WEO à la suivante. Deux lectures :

- Sur toutes les éditions depuis 1990 (classeur historique et son complément) : le sens
  moyen des révisions de croissance, et leur enchaînement. Un prévisionniste qui intègre
  toute l'information disponible produit des révisions imprévisibles ; s'il ne l'intègre
  que par étapes, une révision en annonce une autre de même sens (test de Nordhaus).
- Entre les deux dernières éditions archivées (`data/raw/weo_archive/`) : ce qui change
  dans les projections du rapport, et les révisions de l'historique — changement d'année
  de base, nouvelle estimation des comptes — que le raccord sur la Banque Mondiale
  neutralise.

    python -m pib.revisions_weo
"""

import os
import re
import sys
import json
import logging
import argparse

import numpy as np
import pandas as pd

from pib.evaluate_forecasts import (
    ANNEES_RECESSION_MONDIALE,
    QUANTILES_ROGNAGE,
    WEO_VERS_ISO3,
    _moyenne_ponderee,
    contexte_pays,
    exclure_agregats,
    lire_base_historique,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INDICATEUR = "ngdp_rpch"

# Niveaux lus dans l'archive : PIB en monnaie nationale courante, en volume (prix
# constants de l'année de base nationale) et en dollars courants
NIVEAUX = ("NGDP", "NGDP_R", "NGDPD")

# Révision du niveau d'une année passée au-delà de laquelle ce n'est plus un ajustement
# ordinaire, mais un changement d'année de base ou une nouvelle estimation des comptes
SEUIL_REVISION_HISTORIQUE = 5.0

# Année de contrôle de ces révisions, avant l'année de l'ancienne édition : l'année
# précédente n'est souvent qu'estimée, et sa révision mêlerait prévision et historique
RECUL_ANNEE_CONTROLE = 2

# Révision de la croissance cumulée projetée jugée notable : en volume, 2 % sur six ans
# font un tiers de point de croissance par an ; en dollars courants, où s'ajoutent change
# et inflation, le seuil est celui de l'historique
SEUIL_REVISION_VOLUME = 2.0
SEUIL_REVISION_DOLLARS = SEUIL_REVISION_HISTORIQUE

FICHIER_ARCHIVE = re.compile(r"WEO_([SF]\d{4})\.csv\.gz")


def ordre_edition(annee, saison):
    """Rang chronologique d'une édition : avril (S) puis octobre (F) de chaque année."""
    return annee * 2 + (saison == "F") * 1


def revisions_successives(base: pd.DataFrame) -> pd.DataFrame:
    """
    Révision de chaque prévision par l'édition suivante, pour un même pays et une même
    année visée : valeur de l'édition moins celle de l'édition précédente (`revision`),
    et la révision qui la précédait (`revision_precedente`).

    Seules comptent les éditions consécutives (avril puis octobre, octobre puis avril
    suivant). Les ré-estimations à un an (horizon −1) sont comprises : la dernière mène à
    la valeur de référence de l'évaluation.
    """
    d = base[base["horizon"] >= -1].copy()
    d["ordre"] = ordre_edition(d["annee_millesime"], d["saison"])
    d = d.sort_values(["country_code", "year", "ordre"])
    cles = [d["country_code"], d["year"]]
    consecutive = d["ordre"] - d.groupby(cles)["ordre"].shift(1) == 1
    d["revision"] = (d["valeur"] - d.groupby(cles)["valeur"].shift(1)).where(consecutive)
    d["revision_precedente"] = d.groupby(cles)["revision"].shift(1).where(consecutive)
    return d.drop(columns="ordre").reset_index(drop=True)


def _libelle_etape(horizon: int, saison: str) -> str:
    mois = "avril" if saison == "S" else "octobre"
    return f"{mois}, ré-estimation" if horizon < 0 else f"{mois}, horizon {horizon}"


def synthese_des_revisions(revisions: pd.DataFrame) -> pd.DataFrame:
    """
    Révisions par horizon et saison de l'édition qui révise, dans l'ordre chronologique :
    de l'édition la plus lointaine à la ré-estimation d'octobre suivant l'année visée.

    - `revision_moyenne`, `revision_mediane`, `revision_ponderee_pib` et
      `revision_hors_recessions_mondiales` : le sens dans lequel le FMI corrige ;
    - `part_a_la_baisse_pct` : part des révisions à la baisse parmi celles non nulles ;
    - `pente_nordhaus` et `correlation` : révision régressée sur la précédente, sans les
      valeurs extrêmes (`QUANTILES_ROGNAGE`). Nulles si chaque édition intègre toute
      l'information disponible ; positives si le FMI ne l'intègre que par étapes,
      négatives s'il sur-réagit puis se reprend ;
    - `part_meme_sens_pct` : part des révisions de même sens que la précédente, parmi les
      couples de révisions non nulles.
    """
    valides = revisions.dropna(subset=["revision"])
    poids = valides["poids_pib"] if "poids_pib" in valides.columns else pd.Series(np.nan, index=valides.index)
    lignes = []
    for (horizon, saison), g in valides.groupby(["horizon", "saison"]):
        r = g["revision"]
        non_nulles = r[r != 0]
        ligne = {
            "horizon": horizon, "saison": saison, "etape": _libelle_etape(horizon, saison),
            "revisions": len(r), "revision_moyenne": r.mean(), "revision_mediane": r.median(),
            "revision_ponderee_pib": _moyenne_ponderee(r, poids.loc[g.index]),
            "revision_hors_recessions_mondiales": r[~g["year"].isin(ANNEES_RECESSION_MONDIALE)].mean(),
            "revision_absolue_mediane": r.abs().median(),
            "part_a_la_baisse_pct": (non_nulles < 0).mean() * 100 if len(non_nulles) else np.nan,
        }
        couples = g.dropna(subset=["revision_precedente"])
        bas, haut = QUANTILES_ROGNAGE
        garde = (couples["revision"].between(*couples["revision"].quantile([bas, haut]))
                 & couples["revision_precedente"].between(*couples["revision_precedente"].quantile([bas, haut])))
        c = couples[garde]
        if len(c) >= 10 and c["revision_precedente"].std() > 0:
            ligne["pente_nordhaus"] = np.polyfit(c["revision_precedente"], c["revision"], 1)[0]
            ligne["correlation"] = c["revision"].corr(c["revision_precedente"])
            deux = couples[(couples["revision"] != 0) & (couples["revision_precedente"] != 0)]
            ligne["part_meme_sens_pct"] = ((np.sign(deux["revision"]) == np.sign(deux["revision_precedente"])).mean() * 100
                                           if len(deux) else np.nan)
        lignes.append(ligne)
    table = pd.DataFrame(lignes)
    if table.empty:
        return table
    ordre = -table["horizon"] * 2 + (table["saison"] == "F")
    return table.iloc[ordre.argsort(kind="stable")].reset_index(drop=True).round(3)


def editions_archivees(dossier: str) -> list:
    """Éditions archivées (`WEO_<édition>.csv.gz`), dans l'ordre chronologique."""
    if not os.path.isdir(dossier):
        return []
    editions = [m.group(1) for f in os.listdir(dossier) if (m := FICHIER_ARCHIVE.fullmatch(f))]
    return sorted(editions, key=lambda e: ordre_edition(int(e[1:]), e[0]))


def lire_niveaux(dossier: str, edition: str) -> pd.DataFrame:
    """Niveaux de PIB (`NIVEAUX`) d'une édition archivée : une ligne par pays, une colonne par (indicateur, année)."""
    d = pd.read_csv(os.path.join(dossier, f"WEO_{edition}.csv.gz"))
    d = d[d["indicator"].isin(NIVEAUX)].copy()
    d["country_code"] = d["country_code"].replace(WEO_VERS_ISO3)
    return d.pivot_table(index="country_code", columns=["indicator", "year"], values="value")


def revisions_de_niveau(ancienne: pd.DataFrame, nouvelle: pd.DataFrame,
                        annee_base: int, annee_cible: int, annee_controle: int = None) -> pd.DataFrame:
    """
    Ce que change la nouvelle édition, pays par pays (voir `lire_niveaux` pour le format).

    Le rapport raccorde les projections du FMI au dernier niveau observé par la Banque
    Mondiale : niveau[y] = observé[base] × FMI[y] / FMI[base]. Ce qui passe dans ses
    projections est la révision de FMI[cible] / FMI[base] : la croissance cumulée projetée,
    en volume (`revision_croissance_reelle_pct`) et en dollars courants
    (`revision_croissance_usd_pct`).

    Les révisions du niveau de l'historique, elles, s'éliminent dans le raccord. Elles se
    lisent sur `annee_controle`, observée dans les deux éditions (par défaut `annee_base`) :

    - `revision_historique_usd_pct` : PIB en dollars — nouvelle estimation des comptes, ou
      du taux de change ;
    - `revision_deflateur_historique_pct` : rapport du PIB courant au PIB en volume — un
      changement d'année de base des prix constants, qui change le niveau en volume sans
      rien changer à l'économie mesurée.

    Chacune est signalée au-delà de `SEUIL_REVISION_HISTORIQUE`. En %, sauf les signaux.
    """
    controle = annee_base if annee_controle is None else annee_controle
    pays = ancienne.index.intersection(nouvelle.index)
    a, n = ancienne.loc[pays], nouvelle.loc[pays]

    def valeur(t, indicateur, annee):
        return t[(indicateur, annee)] if (indicateur, annee) in t.columns else pd.Series(np.nan, index=t.index)

    def revision(nouveau, ancien):
        return ((nouveau / ancien - 1) * 100).replace([np.inf, -np.inf], np.nan)

    def croissance(t, indicateur):
        return valeur(t, indicateur, annee_cible) / valeur(t, indicateur, annee_base)

    def deflateur(t):
        return valeur(t, "NGDP", controle) / valeur(t, "NGDP_R", controle)

    table = pd.DataFrame({
        "revision_croissance_reelle_pct": revision(croissance(n, "NGDP_R"), croissance(a, "NGDP_R")),
        "revision_croissance_usd_pct": revision(croissance(n, "NGDPD"), croissance(a, "NGDPD")),
        "revision_pib_usd_cible_pct": revision(valeur(n, "NGDPD", annee_cible), valeur(a, "NGDPD", annee_cible)),
        "revision_historique_usd_pct": revision(valeur(n, "NGDPD", controle), valeur(a, "NGDPD", controle)),
        "revision_deflateur_historique_pct": revision(deflateur(n), deflateur(a)),
    }, index=pays)
    table["changement_annee_de_base"] = table["revision_deflateur_historique_pct"].abs() > SEUIL_REVISION_HISTORIQUE
    table["revision_de_l_historique"] = table["revision_historique_usd_pct"].abs() > SEUIL_REVISION_HISTORIQUE
    table = table.dropna(subset=["revision_croissance_reelle_pct", "revision_croissance_usd_pct"], how="all")
    return table.rename_axis("country_code").reset_index().round(3)


def main():
    parser = argparse.ArgumentParser(description="Révisions des prévisions du FMI d'une édition à la suivante.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--classeur", type=str, default=None, help="Chemin du classeur WEOhistorical.xlsx")
    parser.add_argument("--complement", type=str, default=None,
                        help="Éditions ajoutées depuis l'API (par défaut : weo_editions_api.csv à côté du classeur)")
    parser.add_argument("--archive", type=str, default=None,
                        help="Archive des éditions (par défaut : weo_archive/ à côté du classeur)")
    args = parser.parse_args()

    chemin = args.classeur or os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")
    archive = args.archive or os.path.join(os.path.dirname(chemin), "weo_archive")
    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)

    try:
        base = lire_base_historique(chemin, INDICATEUR, args.complement)
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        sys.exit(1)
    revisions = revisions_successives(exclure_agregats(base, args.data_dir))
    poids, _ = contexte_pays(args.data_dir)
    revisions = revisions.merge(poids, on=["country_code", "year"], how="left")
    synthese = synthese_des_revisions(revisions)
    synthese.to_csv(os.path.join(processed, f"weo_forecast_revisions_{INDICATEUR}.csv"), index=False, encoding="utf-8-sig")
    logging.info("Révisions de la croissance d'une édition à la suivante (points) :\n"
                 + synthese[["etape", "revisions", "revision_moyenne", "revision_hors_recessions_mondiales",
                             "part_a_la_baisse_pct", "correlation", "part_meme_sens_pct"]].to_string(index=False))

    editions = editions_archivees(archive)
    meta_json = os.path.join(args.data_dir, "extraction_metadata.json")
    if len(editions) < 2 or not os.path.exists(meta_json):
        logging.info("Moins de deux éditions archivées, ou métadonnées du rapport absentes : "
                     "révisions de niveau omises.")
        return
    with open(meta_json, encoding="utf-8") as f:
        bornes = json.load(f)["bornes"]
    ancienne, nouvelle = editions[-2], editions[-1]
    niveaux_a, niveaux_n = lire_niveaux(archive, ancienne), lire_niveaux(archive, nouvelle)
    annee_base = bornes["historique"][1]
    annee_cible = min(bornes["prevision"][1], *(int(t.columns.get_level_values("year").max())
                                               for t in (niveaux_a, niveaux_n)))
    annee_controle = int(ancienne[1:]) - RECUL_ANNEE_CONTROLE
    table = exclure_agregats(revisions_de_niveau(niveaux_a, niveaux_n, annee_base, annee_cible, annee_controle),
                             args.data_dir)

    synthese_csv = os.path.join(processed, "gdp_country_summary.csv")
    if os.path.exists(synthese_csv):
        noms = pd.read_csv(synthese_csv, usecols=lambda c: c in ("country_code", "country_name", "income_group"))
        table = noms.merge(table, on="country_code", how="right")
    table.insert(0, "edition_ancienne", ancienne)
    table.insert(1, "edition_nouvelle", nouvelle)
    table.insert(2, "annee_base", annee_base)
    table.insert(3, "annee_cible", annee_cible)
    table.insert(4, "annee_controle", annee_controle)
    table.to_csv(os.path.join(processed, "weo_edition_revisions.csv"), index=False, encoding="utf-8-sig")

    reel, usd = table["revision_croissance_reelle_pct"].abs(), table["revision_croissance_usd_pct"].abs()
    logging.info(f"Révisions {ancienne} → {nouvelle}, croissance cumulée {annee_base}-{annee_cible}, "
                 f"{len(table)} pays : au-delà de {SEUIL_REVISION_VOLUME:g} % en volume pour "
                 f"{int((reel > SEUIL_REVISION_VOLUME).sum())}, de {SEUIL_REVISION_DOLLARS:g} % en dollars "
                 f"pour {int((usd > SEUIL_REVISION_DOLLARS).sum())}. Sur {annee_controle}, changements d'année de base : "
                 f"{', '.join(table.loc[table['changement_annee_de_base'], 'country_code']) or 'aucun'} ; "
                 f"révisions de l'historique : "
                 f"{', '.join(table.loc[table['revision_de_l_historique'], 'country_code']) or 'aucune'}.")


if __name__ == "__main__":
    main()
