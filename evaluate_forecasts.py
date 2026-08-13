#!/usr/bin/env python3
"""
evaluate_forecasts.py
---------------------
Confronte les prévisions publiées par le FMI aux valeurs finalement observées.

Pourquoi un fichier source distinct : l'API DataMapper ne sert que le **millésime
courant** du WEO. Sa valeur pour 2020 est l'estimation d'aujourd'hui, pas ce que le FMI
projetait en 2018. Évaluer des prévisions suppose les publications d'époque.

Le FMI les consolide dans la *WEO Historical Forecasts Database*, un classeur unique
couvrant toutes les éditions depuis 1990 — bien plus commode que de réconcilier une
centaine de fichiers d'éditions séparés.

    data/raw/WEOhistorical.xlsx

Le téléchargement reste manuel : le site refuse les requêtes automatisées (403).
Voir `data/raw/LISEZ-MOI-WEOhistorical.md` pour le lien et la marche à suivre.

Structure du classeur : une ligne par (pays, année visée), une colonne par édition,
nommée `S2019ngdp_rpch` (printemps) ou `F2019ngdp_rpch` (automne). L'horizon de
projection se déduit de l'écart entre l'année visée et l'année de l'édition : positif
pour une prévision, nul pour l'année en cours, négatif pour une ré-estimation du passé.

    python evaluate_forecasts.py
    python evaluate_forecasts.py --indicateur pcpi_pch     # inflation
"""

import os
import glob
import logging
import argparse

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CLASSEUR = os.path.join("data", "raw", "WEOhistorical.xlsx")

# Onglets du classeur et unité de la valeur
INDICATEURS = {
    "ngdp_rpch": "Croissance du PIB réel (%)",
    "pcpi_pch": "Inflation, prix à la consommation (%)",
    "bca_gdp_bp6": "Balance courante (% du PIB)",
}

IDENTIFIANTS = ["country", "WEO_Country_Code", "ISOAlpha_3Code", "year"]

# Le FMI publie ses agrégats dans le même onglet, sous des codes en G suivis de chiffres
PREFIXE_AGREGAT = "G"


def lire_base_historique(chemin: str = CLASSEUR, indicateur: str = "ngdp_rpch") -> pd.DataFrame:
    """
    Lit un onglet du classeur et le remet au format long.

    Retourne les colonnes : country, country_code, year, vintage, saison,
    annee_millesime, horizon, valeur, est_projection.
    """
    if not os.path.exists(chemin):
        raise FileNotFoundError(
            f"Classeur introuvable : {chemin}. "
            "Voir data/raw/LISEZ-MOI-WEOhistorical.md pour le téléchargement.")
    if indicateur not in INDICATEURS:
        raise ValueError(f"Indicateur inconnu : {indicateur}. "
                         f"Disponibles : {', '.join(INDICATEURS)}")

    logging.info(f"Lecture de {os.path.basename(chemin)}, onglet « {indicateur} »...")
    large = pd.read_excel(chemin, sheet_name=indicateur)

    manquantes = [c for c in IDENTIFIANTS if c not in large.columns]
    if manquantes:
        raise ValueError(f"Colonnes d'identification absentes : {manquantes}")

    editions = [c for c in large.columns if c not in IDENTIFIANTS]
    long = large.melt(id_vars=IDENTIFIANTS, value_vars=editions,
                      var_name="vintage", value_name="valeur")

    # « S2019ngdp_rpch » -> « S2019 »
    long["vintage"] = long["vintage"].str.replace(indicateur, "", regex=False)

    # Les valeurs manquantes sont notées « . » dans le classeur
    long["valeur"] = pd.to_numeric(long["valeur"], errors="coerce")
    long = long.dropna(subset=["valeur"])

    long["saison"] = long["vintage"].str[0]
    long["annee_millesime"] = pd.to_numeric(long["vintage"].str[1:], errors="coerce")
    long = long.dropna(subset=["annee_millesime"])
    long["annee_millesime"] = long["annee_millesime"].astype(int)

    # Horizon : ce qui sépare l'année visée de l'édition qui la projette.
    # Négatif = ré-estimation d'une année déjà écoulée, ce n'est pas une prévision.
    long["horizon"] = long["year"] - long["annee_millesime"]
    long["est_projection"] = long["horizon"] >= 0

    long = long.rename(columns={"ISOAlpha_3Code": "country_code"})
    long = long[["country", "country_code", "year", "vintage", "saison",
                 "annee_millesime", "horizon", "valeur", "est_projection"]]

    logging.info(f"-> {len(long):,} valeurs, {long['vintage'].nunique()} éditions, "
                 f"{long['country_code'].nunique()} entités, "
                 f"horizons {long['horizon'].min()} à {long['horizon'].max()}")
    return long


def exclure_agregats(df: pd.DataFrame, data_dir: str = "data") -> pd.DataFrame:
    """
    Écarte les agrégats du FMI (World, zones monétaires...), publiés dans le même onglet.

    La liste des vrais pays vient du pipeline, qui la tient des métadonnées de la Banque
    Mondiale ; à défaut, on se rabat sur le préfixe `G` des codes d'agrégats du WEO.
    """
    series = sorted(glob.glob(os.path.join(data_dir, "processed", "gdp_unified_*.csv")))
    if series:
        unifie = pd.read_csv(max(series, key=os.path.getmtime),
                             usecols=["country_code", "is_aggregate"])
        pays = set(unifie.loc[~unifie["is_aggregate"].astype(bool), "country_code"])
        garde = df[df["country_code"].isin(pays)]
    else:
        logging.warning("Série unifiée absente : repli sur le préfixe des codes d'agrégats.")
        garde = df[~df["country_code"].astype(str).str.match(rf"{PREFIXE_AGREGAT}\d")]

    logging.info(f"-> {df['country_code'].nunique() - garde['country_code'].nunique()} "
                 f"agrégats écartés, {garde['country_code'].nunique()} pays retenus.")
    return garde.copy()


def realise_selon_fmi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Valeur de référence tirée du FMI lui-même : sa ré-estimation de l'année écoulée,
    publiée à l'automne suivant (horizon −1).

    Comparer une prévision au chiffre définitif d'aujourd'hui la pénaliserait pour des
    révisions statistiques intervenues des années plus tard, que le prévisionniste ne
    pouvait pas connaître. La référence à un an reste proche de ce qui était mesurable.
    """
    reference = df[(df["horizon"] == -1) & (df["saison"] == "F")]
    if reference.empty:
        reference = df[df["horizon"] == -1]
    return (reference.sort_values("annee_millesime")
            .drop_duplicates(subset=["country_code", "year"], keep="first")
            [["country_code", "year", "valeur"]]
            .rename(columns={"valeur": "realise_fmi"}))


def realise_selon_banque_mondiale(data_dir: str = "data") -> pd.DataFrame:
    """Croissance réelle finalement constatée par la Banque Mondiale, série du pipeline."""
    series = sorted(glob.glob(os.path.join(data_dir, "processed", "gdp_unified_*.csv")))
    if not series:
        logging.warning("Série unifiée absente : référence Banque Mondiale indisponible.")
        return pd.DataFrame(columns=["country_code", "year", "realise_bm"])

    unifie = pd.read_csv(max(series, key=os.path.getmtime))
    observe = unifie[~unifie["is_forecast"].astype(bool)]
    return (observe[["country_code", "year", "GDP_Growth_Pct"]]
            .rename(columns={"GDP_Growth_Pct": "realise_bm"})
            .dropna(subset=["realise_bm"]))


def evaluer(df: pd.DataFrame, data_dir: str = "data") -> pd.DataFrame:
    """
    Rapproche chaque projection des deux références disponibles.

    Les deux sont conservées plutôt qu'arbitrées : une conclusion qui ne tiendrait qu'à
    l'une d'elles ne serait pas robuste, et le lecteur doit pouvoir le constater.
    L'erreur est exprimée en points de croissance, jamais en relatif — rapporter l'erreur
    d'un taux à sa propre valeur donne des rapports aberrants dès qu'il approche de zéro.
    """
    projections = df[df["est_projection"]].copy()

    evaluation = (projections
                  .merge(realise_selon_fmi(df), on=["country_code", "year"], how="left")
                  .merge(realise_selon_banque_mondiale(data_dir),
                         on=["country_code", "year"], how="left"))

    evaluation["erreur_vs_fmi"] = evaluation["valeur"] - evaluation["realise_fmi"]
    evaluation["erreur_vs_bm"] = evaluation["valeur"] - evaluation["realise_bm"]

    exploitables = int(evaluation["erreur_vs_fmi"].notna().sum())
    logging.info(f"-> {len(evaluation):,} projections, {exploitables:,} confrontables "
                 "à la ré-estimation du FMI.")
    return evaluation


def synthese_par_horizon(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Biais et dispersion par horizon.

    Le biais moyen dit si le FMI penche systématiquement d'un côté (positif = trop
    optimiste) ; l'erreur absolue moyenne dit de combien il se trompe, quel que soit
    le sens. Les deux sont nécessaires : un biais nul peut cacher de fortes erreurs
    qui se compensent.
    """
    lignes = []
    for reference, colonne in (("FMI (ré-estimation à 1 an)", "erreur_vs_fmi"),
                               ("Banque Mondiale (série observée)", "erreur_vs_bm")):
        valides = evaluation.dropna(subset=[colonne])
        if valides.empty:
            continue
        agrege = (valides.groupby("horizon")[colonne]
                  .agg(observations="size", biais_moyen="mean",
                       erreur_absolue_moyenne=lambda s: s.abs().mean(), mediane="median")
                  .reset_index())
        agrege.insert(0, "reference", reference)
        lignes.append(agrege)

    return pd.concat(lignes, ignore_index=True).round(3) if lignes else pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(
        description="Évaluation des prévisions FMI contre les valeurs observées.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--classeur", type=str, default=None,
                        help="Chemin du classeur WEOhistorical.xlsx")
    parser.add_argument("--indicateur", type=str, default="ngdp_rpch",
                        choices=sorted(INDICATEURS), help="Onglet à évaluer")
    parser.add_argument("--garder-agregats", action="store_true",
                        help="Conserver les agrégats du FMI (World, zones monétaires...)")
    args = parser.parse_args()

    chemin = args.classeur or os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")

    try:
        base = lire_base_historique(chemin, args.indicateur)
    except FileNotFoundError as e:
        logging.error(str(e))
        return

    if not args.garder_agregats:
        base = exclure_agregats(base, args.data_dir)

    evaluation = evaluer(base, args.data_dir)
    if evaluation.empty:
        logging.error("Aucune projection exploitable.")
        return

    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)

    sortie = os.path.join(processed, f"weo_forecast_evaluation_{args.indicateur}.csv")
    evaluation.to_csv(sortie, index=False, encoding="utf-8-sig")
    logging.info(f"Évaluation enregistrée : {sortie}")

    synthese = synthese_par_horizon(evaluation)
    sortie_synthese = os.path.join(processed, f"weo_forecast_bias_{args.indicateur}.csv")
    synthese.to_csv(sortie_synthese, index=False, encoding="utf-8-sig")

    logging.info(f"{INDICATEURS[args.indicateur]} — biais par horizon :\n"
                 + synthese.to_string(index=False))


if __name__ == "__main__":
    main()
