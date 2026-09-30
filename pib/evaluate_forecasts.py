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
Voir `data/raw/LISEZ-MOI-WEOhistorical.md` pour le lien et la marche à suivre. Les
éditions plus récentes que le classeur sont lues dans `weo_editions_api.csv`, tenu à
jour depuis l'API du FMI par `update_weo_editions.py`.

Structure du classeur : une ligne par (pays, année visée), une colonne par édition,
nommée `S2019ngdp_rpch` (printemps) ou `F2019ngdp_rpch` (automne). L'horizon de
projection se déduit de l'écart entre l'année visée et l'année de l'édition : positif
pour une prévision, nul pour l'année en cours, négatif pour une ré-estimation du passé.

    python -m pib.evaluate_forecasts
    python -m pib.evaluate_forecasts --indicateur pcpi_pch     # inflation
"""

import os
import sys
import json
import logging
import argparse
from typing import Optional

import numpy as np
import pandas as pd

from pib.gdp_pipeline import unified_csv_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CLASSEUR = os.path.join("data", "raw", "WEOhistorical.xlsx")

# Onglets du classeur et unité de la valeur
INDICATEURS = {
    "ngdp_rpch": "Croissance du PIB réel (%)",
    "pcpi_pch": "Inflation, prix à la consommation (%)",
    "bca_gdp_bp6": "Balance courante (% du PIB)",
}

# Seul indicateur dont la Banque Mondiale fournit l'équivalent dans la série du pipeline
# (croissance du PIB réel). Confronter une prévision d'inflation à la croissance du PIB
# produirait une erreur dénuée de sens.
INDICATEUR_BANQUE_MONDIALE = "ngdp_rpch"

IDENTIFIANTS = ["country", "WEO_Country_Code", "ISOAlpha_3Code", "year"]

# Codes du classeur qui ne sont pas ceux de la Banque Mondiale pour le même territoire.
# Sans conversion, ces pays seraient écartés comme inconnus de la série du pipeline.
WEO_VERS_ISO3 = {
    "KOS": "XKX",   # Kosovo
    "WBG": "PSE",   # Cisjordanie et Gaza
}

# Au-delà de ce rapport entre erreur absolue moyenne et médiane, la moyenne ne décrit
# plus l'erreur typique mais quelques valeurs extrêmes (hyperinflations).
SEUIL_VALEURS_EXTREMES = 10.0

# Récessions mondiales : leurs erreurs, énormes et communes à tous les pays, pèsent sur
# la moyenne. La synthèse donne aussi le biais sans elles, pour juger de leur poids.
ANNEES_RECESSION_MONDIALE = (2009, 2020)

# Prévision naïve de comparaison : pour une édition de l'année v, la croissance moyenne des
# années v−5 à v−2, telle que ré-estimée par le FMI. Toutes étaient publiées avant
# l'édition (la ré-estimation de v−1 ne paraît qu'à l'automne de v) : la prévision naïve
# n'utilise rien que le FMI ne savait pas déjà.
ANNEES_NAIF = 4
DECALAGE_NAIF = 2
MIN_ANNEES_NAIF = 3

# Agrégat « World » du WEO. Il n'a pas d'équivalent comparable à la Banque Mondiale : le
# FMI agrège la croissance mondiale avec des poids en parité de pouvoir d'achat, la Banque
# Mondiale aux taux de change de marché, qui pèsent moins les économies émergentes. Sa
# croissance mondiale est inférieure de 0,4 point en moyenne (23 années sur 25) : la
# prendre pour référence gonflerait le biais du FMI de ce seul écart de pondération.
CODE_MONDE = "G001"

# Groupes de revenu de la Banque Mondiale (classification courante)
GROUPES_REVENU = {
    "HIC": "Revenu élevé",
    "UMC": "Revenu intermédiaire supérieur",
    "LMC": "Revenu intermédiaire inférieur",
    "LIC": "Faible revenu",
}

# Enchaîner des taux de croissance donne un niveau : l'erreur de niveau n'a de sens que
# pour la croissance du PIB (pour l'inflation, ce serait un niveau de prix).
INDICATEUR_NIVEAU = "ngdp_rpch"

# Références de comparaison : colonne du réalisé et libellé
REFERENCES = {
    "fmi": ("realise_fmi", "FMI (ré-estimation à 1 an)"),
    "bm": ("realise_bm", "Banque Mondiale (série observée)"),
}

# Fourchette empirique autour des projections : 10e à 90e centile des erreurs de niveau
# passées au même horizon, parmi les projections comparables — même classe (quintile) de
# croissance cumulée projetée et même groupe de revenu. Le FMI surestime d'autant plus
# qu'il annonce de croissance, et ses erreurs sont plus dispersées pour les pays pauvres.
# Le biais propre à un pays, lui, ne se reproduit pas d'une période à l'autre : une
# fourchette tirée de l'historique du pays, calculée sur 1990-2007, ne contenait que 67 %
# des erreurs suivantes au lieu de 80 % (voir `calibration_fourchettes`). Une cellule de
# moins de `MIN_CAS_CELLULE` cas se replie sur la seule classe de croissance.
QUANTILES_FOURCHETTE = (0.10, 0.90)
CLASSES_CROISSANCE = 5
MIN_CAS_CELLULE = 100
ANNEE_COUPURE_CALIBRATION = 2007
GRANDES_ECONOMIES = 20

# Récessions mondiales : années de recul du PIB mondial réel par habitant, série de la Banque
# Mondiale depuis 1961 écrite par le pipeline (1975, 1982, 1991, 2009, 2020). Leur fréquence
# sur cet historique long, plutôt que dans les seules périodes couvertes par les éditions du
# WEO, fixe le poids des crises dans la probabilité de recul d'un pays : éprouvée en temps
# réel, une probabilité apprise sans ce découpage dépend des crises que contenait la période
# d'apprentissage (voir `pib.calibration`).
FICHIER_MONDE = "world_gdp_per_capita_growth.csv"

# Test d'efficience : la droite est ajustée sans le 1 % de valeurs extrêmes de chaque côté
# (croissances de guerre ou d'après-guerre, hors de portée de toute prévision)
QUANTILES_ROGNAGE = (0.01, 0.99)

# Le FMI publie ses agrégats dans le même onglet, sous des codes en G suivis de chiffres
PREFIXE_AGREGAT = "G"


def lire_base_historique(chemin: str = CLASSEUR, indicateur: str = "ngdp_rpch",
                         complement: Optional[str] = None) -> pd.DataFrame:
    """
    Lit un onglet du classeur et le remet au format long.

    Les éditions absentes du classeur sont ajoutées depuis `complement` (par défaut
    `weo_editions_api.csv` à côté du classeur, s'il existe) ; pour une édition présente
    des deux côtés, le classeur fait foi.

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

    complement = complement or os.path.join(os.path.dirname(chemin), "weo_editions_api.csv")
    if os.path.exists(complement):
        api = pd.read_csv(complement)
        api = api[(api["indicateur"] == indicateur) & ~api["vintage"].isin(set(long["vintage"]))]
        if not api.empty:
            logging.info(f"-> Éditions ajoutées depuis l'API du FMI : {', '.join(sorted(api['vintage'].unique()))}")
            # Libellés du classeur quand il connaît le code (« Aruba » plutôt que
            # « Aruba, Kingdom of the Netherlands »), pour une sortie homogène
            noms = long.drop_duplicates("ISOAlpha_3Code").set_index("ISOAlpha_3Code")["country"]
            api = api.assign(country=api["country_code"].map(noms).fillna(api["country"]))
            long = pd.concat([long, api.rename(columns={"country_code": "ISOAlpha_3Code"})
                              [["country", "ISOAlpha_3Code", "year", "vintage", "valeur"]]],
                             ignore_index=True)

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
    long["country_code"] = long["country_code"].replace(WEO_VERS_ISO3)
    long = long[["country", "country_code", "year", "vintage", "saison",
                 "annee_millesime", "horizon", "valeur", "est_projection"]]

    logging.info(f"-> {len(long):,} valeurs, {long['vintage'].nunique()} éditions, "
                 f"{long['country_code'].nunique()} entités, "
                 f"horizons {long['horizon'].min()} à {long['horizon'].max()}")
    return long


def serie_unifiee(data_dir: str, **options) -> Optional[pd.DataFrame]:
    """Série unifiée du dernier run du pipeline, ou None si elle n'est pas disponible."""
    try:
        chemin = unified_csv_path(data_dir)
    except FileNotFoundError as e:
        logging.warning(f"Série unifiée indisponible : {e}")
        return None
    return pd.read_csv(chemin, **options)


def exclure_agregats(df: pd.DataFrame, data_dir: str = "data") -> pd.DataFrame:
    """
    Écarte les agrégats du FMI (World, zones monétaires...), publiés dans le même onglet.

    La liste des vrais pays vient du pipeline, qui la tient des métadonnées de la Banque
    Mondiale ; à défaut, on se rabat sur le préfixe `G` des codes d'agrégats du WEO.
    """
    unifie = serie_unifiee(data_dir, usecols=["country_code", "is_aggregate"])
    if unifie is not None:
        pays = set(unifie.loc[~unifie["is_aggregate"].astype(bool), "country_code"])
        garde = df[df["country_code"].isin(pays)]
    else:
        logging.warning("Repli sur le préfixe des codes d'agrégats.")
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


def realise_selon_banque_mondiale(data_dir: str = "data",
                                  indicateur: str = "ngdp_rpch") -> pd.DataFrame:
    """
    Croissance réelle finalement constatée par la Banque Mondiale, série du pipeline.

    Cette référence n'existe que pour la croissance du PIB : pour un autre indicateur, la
    table retournée est vide et seule la référence FMI est calculée.
    """
    vide = pd.DataFrame(columns=["country_code", "year", "realise_bm"])
    if indicateur != INDICATEUR_BANQUE_MONDIALE:
        logging.info(f"Pas de série Banque Mondiale équivalente à « {indicateur} » : "
                     "seule la référence FMI est calculée.")
        return vide

    unifie = serie_unifiee(data_dir)
    if unifie is None:
        logging.warning("Référence Banque Mondiale indisponible.")
        return vide

    observe = unifie[~unifie["is_forecast"].astype(bool)]
    return (observe[["country_code", "year", "GDP_Growth_Pct"]]
            .rename(columns={"GDP_Growth_Pct": "realise_bm"})
            .dropna(subset=["realise_bm"]))


def contexte_pays(data_dir: str) -> tuple:
    """
    Poids et groupes tirés de la série du pipeline : PIB nominal observé par pays et
    année (Banque Mondiale, milliards USD), et groupe de revenu de chaque pays.
    Tables vides si la série, ou la colonne, est absente.
    """
    poids = pd.DataFrame(columns=["country_code", "year", "poids_pib"])
    groupes = pd.DataFrame(columns=["country_code", "income_group"])
    unifie = serie_unifiee(data_dir)
    if unifie is None:
        return poids, groupes
    if "GDP_Nominal_Billions_USD" in unifie.columns:
        observe = unifie[~unifie["is_forecast"].astype(bool)]
        poids = (observe[["country_code", "year", "GDP_Nominal_Billions_USD"]]
                 .rename(columns={"GDP_Nominal_Billions_USD": "poids_pib"}).dropna())
    if "income_group" in unifie.columns:
        groupes = (unifie.dropna(subset=["income_group"])
                   .drop_duplicates(subset=["country_code"])[["country_code", "income_group"]])
    return poids, groupes


def evaluer(df: pd.DataFrame, data_dir: str = "data", indicateur: str = "ngdp_rpch") -> pd.DataFrame:
    """
    Rapproche chaque projection des deux références disponibles.

    Les deux sont conservées plutôt qu'arbitrées : une conclusion qui ne tiendrait qu'à
    l'une d'elles ne serait pas robuste, et le lecteur doit pouvoir le constater.
    L'erreur est exprimée en points de croissance, jamais en relatif — rapporter l'erreur
    d'un taux à sa propre valeur donne des rapports aberrants dès qu'il approche de zéro.
    """
    projections = df[df["est_projection"]].copy()
    realise = realise_selon_fmi(df)

    evaluation = (projections
                  .merge(realise, on=["country_code", "year"], how="left")
                  .merge(realise_selon_banque_mondiale(data_dir, indicateur),
                         on=["country_code", "year"], how="left"))

    evaluation["erreur_vs_fmi"] = evaluation["valeur"] - evaluation["realise_fmi"]
    evaluation["erreur_vs_bm"] = evaluation["valeur"] - evaluation["realise_bm"]

    # PIB de l'année visée (poids) et groupe de revenu, pour les synthèses pondérées et par groupe
    poids, groupes = contexte_pays(data_dir)
    evaluation = (evaluation.merge(poids, on=["country_code", "year"], how="left")
                  .merge(groupes, on="country_code", how="left"))
    evaluation = ajouter_prevision_naive(evaluation, realise)

    exploitables = int(evaluation["erreur_vs_fmi"].notna().sum())
    logging.info(f"-> {len(evaluation):,} projections, {exploitables:,} confrontables "
                 "à la ré-estimation du FMI.")
    return evaluation


def ajouter_prevision_naive(evaluation: pd.DataFrame, realise: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute à chaque projection la prévision naïve (`naif`) et son erreur (`erreur_naif`).

    Naïf : pour une édition de l'année v, la moyenne des croissances ré-estimées par le FMI
    pour les années v−5 à v−2 (au moins trois des quatre), la même pour tous les horizons.
    Une prévision qui ne fait pas mieux n'apporte rien de plus que le passé récent.
    """
    if realise.empty:
        return evaluation.assign(naif=np.nan, erreur_naif=np.nan)
    large = realise.pivot_table(index="year", columns="country_code", values="realise_fmi")
    large = large.reindex(range(int(large.index.min()), int(large.index.max()) + 1))
    moyenne = large.rolling(ANNEES_NAIF, min_periods=MIN_ANNEES_NAIF).mean()   # années t−3 à t
    naif = (moyenne.stack().rename("naif").reset_index()
            .assign(annee_millesime=lambda d: d["year"] + DECALAGE_NAIF)[["country_code", "annee_millesime", "naif"]])
    evaluation = evaluation.merge(naif, on=["country_code", "annee_millesime"], how="left")
    evaluation["erreur_naif"] = evaluation["naif"] - evaluation["realise_fmi"]
    return evaluation


def ic95_par_annee(erreurs: pd.Series, annees: pd.Series) -> tuple:
    """
    Intervalle de confiance à 95 % du biais moyen, robuste à la corrélation des erreurs
    d'une même année visée.

    Les pays d'une même année subissent les mêmes chocs (2009, 2020) : leurs erreurs ne
    sont pas indépendantes. Les supposer indépendantes diviserait l'erreur type par six
    sur la croissance à un an. L'erreur type est donc calculée par grappes d'années
    visées, avec la correction G/(G−1) ; l'intervalle suit l'approximation normale.
    """
    annees_visees = annees.nunique()
    if annees_visees < 2:
        return np.nan, np.nan
    moyenne = erreurs.mean()
    sommes = (erreurs - moyenne).groupby(annees.values).sum()
    erreur_type = np.sqrt(annees_visees / (annees_visees - 1) * (sommes ** 2).sum()) / len(erreurs)
    return moyenne - 1.96 * erreur_type, moyenne + 1.96 * erreur_type


def _moyenne_ponderee(valeurs: pd.Series, poids: pd.Series) -> float:
    garde = valeurs.notna() & poids.notna() & (poids > 0)
    return float(np.average(valeurs[garde], weights=poids[garde])) if garde.any() else np.nan


def synthese_par_horizon(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Biais et dispersion par horizon.

    Le biais moyen dit si le FMI penche systématiquement d'un côté (positif = trop
    optimiste) ; l'erreur absolue moyenne dit de combien il se trompe, quel que soit
    le sens. Les deux sont nécessaires : un biais nul peut cacher de fortes erreurs
    qui se compensent.

    Leurs équivalents médians (`mediane`, `erreur_absolue_mediane`) résistent aux
    valeurs extrêmes : pour l'inflation, une seule projection d'hyperinflation (le
    Venezuela à 10 000 000 %) suffit à porter la moyenne à des milliers de points.

    Le biais moyen compte chaque pays pour un. Trois lectures le complètent :
    `biais_pondere_pib` (pondéré par le PIB de l'année visée, là où la série du pipeline
    le donne : ce que l'erreur représente pour l'économie mondiale), `ic95_bas` et
    `ic95_haut` (voir `ic95_par_annee`), et `biais_hors_recessions_mondiales` (sans les
    années de `ANNEES_RECESSION_MONDIALE`).
    """
    poids = evaluation["poids_pib"] if "poids_pib" in evaluation.columns else pd.Series(np.nan, index=evaluation.index)
    lignes = []
    for colonne, reference in (("erreur_vs_fmi", REFERENCES["fmi"][1]), ("erreur_vs_bm", REFERENCES["bm"][1])):
        valides = evaluation.dropna(subset=[colonne])
        if valides.empty:
            continue
        for horizon, g in valides.groupby("horizon"):
            e = g[colonne]
            # Sans année visée, ni intervalle groupé ni exclusion des récessions
            annees = g["year"] if "year" in g.columns else pd.Series(np.nan, index=g.index)
            bas, haut = ic95_par_annee(e, annees)
            lignes.append({
                "reference": reference, "horizon": horizon, "observations": len(e),
                "biais_moyen": e.mean(), "erreur_absolue_moyenne": e.abs().mean(),
                "mediane": e.median(), "erreur_absolue_mediane": e.abs().median(),
                "biais_pondere_pib": _moyenne_ponderee(e, poids.loc[g.index]),
                "ic95_bas": bas, "ic95_haut": haut, "annees_visees": annees.nunique(),
                "biais_hors_recessions_mondiales": (e[~annees.isin(ANNEES_RECESSION_MONDIALE)].mean()
                                                    if annees.notna().any() else np.nan),
            })
    return pd.DataFrame(lignes).round(3)


def synthese_par_saison(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Biais par horizon et saison d'édition, contre la ré-estimation du FMI.

    Pour une même année visée, l'édition d'octobre (`F`) dispose de six mois d'information
    de plus que celle d'avril (`S`) : les mélanger sous un même horizon moyenne deux
    situations différentes, surtout pour l'année en cours.
    """
    valides = evaluation.dropna(subset=["erreur_vs_fmi"])
    poids = valides["poids_pib"] if "poids_pib" in valides.columns else pd.Series(np.nan, index=valides.index)
    lignes = [{"horizon": horizon, "saison": saison, "observations": len(g),
               "biais_moyen": g["erreur_vs_fmi"].mean(), "mediane": g["erreur_vs_fmi"].median(),
               "erreur_absolue_moyenne": g["erreur_vs_fmi"].abs().mean(),
               "biais_pondere_pib": _moyenne_ponderee(g["erreur_vs_fmi"], poids.loc[g.index])}
              for (horizon, saison), g in valides.groupby(["horizon", "saison"])]
    table = pd.DataFrame(lignes)
    if table.empty:
        return table
    return table.sort_values(["horizon", "saison"], key=lambda c: c.map({"S": 0, "F": 1}) if c.name == "saison" else c,
                             ignore_index=True).round(3)


def comparaison_naive(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Le FMI face à la prévision naïve, par horizon, sur les mêmes projections : erreurs
    absolues moyenne et médiane de chacun, rapport des erreurs absolues moyennes (sous 1 :
    le FMI fait mieux) et part des projections où le FMI est plus proche du réalisé.
    """
    if "erreur_naif" not in evaluation.columns:
        return pd.DataFrame()
    valides = evaluation.dropna(subset=["erreur_vs_fmi", "erreur_naif"])
    lignes = []
    for horizon, g in valides.groupby("horizon"):
        fmi, naif = g["erreur_vs_fmi"].abs(), g["erreur_naif"].abs()
        lignes.append({"horizon": horizon, "observations": len(g),
                       "eam_fmi": fmi.mean(), "eam_naif": naif.mean(), "rapport_eam": fmi.mean() / naif.mean(),
                       "mediane_abs_fmi": fmi.median(), "mediane_abs_naif": naif.median(),
                       "part_fmi_meilleur": (fmi < naif).mean() * 100})
    return pd.DataFrame(lignes).round(3)


def evaluer_monde(base: pd.DataFrame) -> pd.DataFrame:
    """
    Les prévisions de l'agrégat « World » du FMI, contre sa propre ré-estimation à un an
    — seule référence comparable (voir `CODE_MONDE`). `base` doit contenir les agrégats :
    l'évaluation par pays les écarte.
    """
    monde = base[base["country_code"] == CODE_MONDE]
    if monde.empty:
        return pd.DataFrame()
    evaluation = monde[monde["est_projection"]].merge(realise_selon_fmi(monde), on=["country_code", "year"], how="left")
    evaluation["erreur_vs_fmi"] = evaluation["valeur"] - evaluation["realise_fmi"]
    evaluation["erreur_vs_bm"] = np.nan
    return evaluation


def synthese_par_revenu(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Biais par horizon et groupe de revenu, contre la ré-estimation du FMI : le biais
    optimiste n'a pas la même ampleur pour les économies avancées et les plus pauvres.
    """
    if "income_group" not in evaluation.columns:
        return pd.DataFrame()
    valides = evaluation.dropna(subset=["erreur_vs_fmi", "income_group"])
    valides = valides[valides["income_group"].isin(GROUPES_REVENU)]
    if valides.empty:
        return pd.DataFrame()
    return (valides.groupby(["horizon", "income_group"])["erreur_vs_fmi"]
            .agg(observations="size", biais_moyen="mean", mediane="median",
                 erreur_absolue_mediane=lambda e: e.abs().median())
            .reset_index().round(3))


def erreurs_de_niveau(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Erreur sur le niveau du PIB en volume, par pays, édition et horizon.

    Une édition projette la croissance de l'année en cours (horizon 0) et des cinq
    suivantes. Enchaînées, ces croissances donnent le niveau prévu, rapporté à celui de
    l'année précédant l'édition ; enchaînées de même, les croissances réalisées donnent
    le niveau atteint. Leur rapport mesure l'erreur de niveau, en % :

        niveau prévu / niveau réalisé − 1 = Π(1 + g_prévu) / Π(1 + g_réalisé) − 1

    Le niveau de départ, commun aux deux, s'élimine. Une année sans croissance réalisée
    interrompt l'enchaînement : les horizons suivants restent sans erreur de niveau.

    `pire_croissance_prevue` et `pire_croissance_realisee` donnent la plus faible croissance
    des horizons 1 à h, projetée et réalisée : négative, elle signale au moins une année de
    recul sur la période (voir `risque_de_recession`).
    """
    colonnes = ["country", "country_code", "income_group", "vintage", "saison", "annee_millesime",
                "year", "horizon", "poids_pib", "croissance_prevue_cumulee_pct",
                "pire_croissance_prevue", "pire_croissance_realisee"]
    d = evaluation[evaluation["horizon"] >= 0].sort_values(["country_code", "vintage", "horizon"]).copy()
    for c in ("income_group", "poids_pib"):
        if c not in d.columns:
            d[c] = np.nan
    cles = [d["country_code"], d["vintage"]]
    attendu = d.groupby(["country_code", "vintage"]).cumcount()

    # Croissance cumulée que l'édition projetait jusqu'à cet horizon : l'ampleur de la
    # projection, à laquelle l'erreur est liée (voir `efficience`)
    projete = np.log1p(d["valeur"] / 100)
    rompu = (projete.isna() | (d["horizon"] != attendu)).astype(int).groupby(cles).cummax().astype(bool)
    d["croissance_prevue_cumulee_pct"] = ((np.exp(projete.where(~rompu).groupby(cles).cumsum()) - 1) * 100).where(~rompu)
    suivantes = d["horizon"] >= 1
    d["pire_croissance_prevue"] = d["valeur"].where(suivantes).groupby(cles).cummin().where(~rompu & suivantes)

    for ref, (realise, _) in REFERENCES.items():
        ecart = np.log1p(d["valeur"] / 100) - np.log1p(d[realise] / 100)
        rompu = (ecart.isna() | (d["horizon"] != attendu)).astype(int).groupby(cles).cummax().astype(bool)
        cumul = ecart.where(~rompu).groupby(cles).cumsum()
        d[f"erreur_niveau_vs_{ref}_pct"] = ((np.exp(cumul) - 1) * 100).where(~rompu)
        if ref == "fmi":
            d["pire_croissance_realisee"] = (d[realise].where(suivantes).groupby(cles).cummin()
                                             .where(~rompu & suivantes))

    return d[colonnes + [f"erreur_niveau_vs_{ref}_pct" for ref in REFERENCES]].reset_index(drop=True)


def synthese_niveau(niveaux: pd.DataFrame) -> pd.DataFrame:
    """
    Erreur de niveau par horizon : moyenne, médiane, moyenne pondérée par le PIB,
    quantiles, et part des cas où le niveau prévu dépasse le réalisé de plus de 5 %
    (ou lui est inférieur de plus de 5 %).
    """
    lignes = []
    for ref, (_, libelle) in REFERENCES.items():
        colonne = f"erreur_niveau_vs_{ref}_pct"
        valides = niveaux.dropna(subset=[colonne])
        for horizon, g in valides.groupby("horizon"):
            e = g[colonne]
            lignes.append({
                "reference": libelle, "horizon": horizon, "observations": len(e),
                "moyenne": e.mean(), "mediane": e.median(),
                "moyenne_ponderee_pib": _moyenne_ponderee(e, g["poids_pib"]),
                "p10": e.quantile(0.10), "p25": e.quantile(0.25),
                "p75": e.quantile(0.75), "p90": e.quantile(0.90),
                "part_trop_haut_5pct": (e > 5).mean() * 100,
                "part_trop_bas_5pct": (e < -5).mean() * 100,
            })
    return pd.DataFrame(lignes).round(3)


def synthese_niveau_par_revenu(niveaux: pd.DataFrame) -> pd.DataFrame:
    """Erreur de niveau par horizon et groupe de revenu, contre la ré-estimation du FMI."""
    colonne = "erreur_niveau_vs_fmi_pct"
    valides = niveaux.dropna(subset=[colonne])
    valides = valides[valides["income_group"].isin(GROUPES_REVENU)]
    if valides.empty:
        return pd.DataFrame()
    return (valides.groupby(["horizon", "income_group"])[colonne]
            .agg(observations="size", moyenne="mean", mediane="median",
                 p10=lambda e: e.quantile(0.10), p90=lambda e: e.quantile(0.90))
            .reset_index().round(3))


def classes_de_croissance(croissance: pd.Series, bornes: list = None) -> tuple:
    """
    Classe (1 à `CLASSES_CROISSANCE`) de chaque croissance projetée. Les bornes sont les
    quantiles de `croissance`, sauf si elles sont fournies (celles de l'historique, pour
    classer une projection actuelle). Retourne les classes et les bornes.
    """
    if bornes is None:
        bornes = croissance.quantile(np.linspace(0, 1, CLASSES_CROISSANCE + 1)[1:-1]).tolist()
    classes = pd.Series(np.digitize(croissance, bornes) + 1, index=croissance.index, dtype=float)
    return classes.where(croissance.notna()), bornes


def croissance_projetee_actuelle(base: pd.DataFrame, annee_edition: int, horizon: int) -> pd.Series:
    """
    Croissance cumulée projetée par la dernière édition de l'année `annee_edition` (octobre
    si elle est parue, sinon avril), de l'année de l'édition à `horizon` ans : celle des
    projections du rapport. Pays dont un horizon manque : absents.
    """
    edition = base[base["annee_millesime"] == annee_edition]
    saison = "F" if (edition["saison"] == "F").any() else "S"
    edition = edition[(edition["saison"] == saison) & edition["horizon"].between(0, horizon)]
    par_pays = edition.groupby("country_code")
    complet = par_pays["horizon"].nunique() == horizon + 1
    cumul = par_pays["valeur"].apply(lambda g: (np.prod(1 + g / 100) - 1) * 100)
    return cumul[complet]


def _frequence_recul(pire: pd.Series) -> float:
    """Part (%) des périodes dont la pire année réalisée est un recul, parmi celles connues."""
    pire = pire.dropna()
    return (pire < 0).mean() * 100 if len(pire) else np.nan


def _statistiques_de_recul(pire: pd.Series) -> dict:
    """Fréquence d'au moins une année de recul, et pire année médiane quand il en survient une."""
    return {"recul": _frequence_recul(pire), "pire_recul": pire[pire < 0].median()}


def _quantiles_fourchette(cas: pd.DataFrame, cles: list) -> pd.DataFrame:
    """
    Quantiles de la fourchette, médiane et effectif des erreurs de niveau, par cellule
    `cles` ; avec les pires années réalisées, fréquence et profondeur des reculs.
    """
    q_bas, q_haut = QUANTILES_FOURCHETTE
    valides = cas.dropna(subset=cles)
    g = valides.groupby(cles)["erreur_niveau_vs_fmi_pct"]
    table = pd.DataFrame({"bas": g.quantile(q_bas), "haut": g.quantile(q_haut), "mediane": g.median(), "cas": g.size()})
    if "pire_croissance_realisee" in valides.columns:
        table = table.join(valides.groupby(cles)["pire_croissance_realisee"]
                           .apply(lambda p: pd.Series(_statistiques_de_recul(p))).unstack())
    return table


def _grandes_economies(cas: pd.DataFrame) -> pd.Series:
    """
    Vrai pour les `GRANDES_ECONOMIES` premiers PIB de chaque édition et horizon. Le rang
    se prend par édition : par année visée, chaque pays compterait deux fois (avril et
    octobre visent la même année au même horizon), et seuls dix pays seraient retenus.
    """
    edition = ["vintage"] if "vintage" in cas.columns else ["annee_millesime"]
    return cas.groupby(["horizon", *edition])["poids_pib"].rank(ascending=False, method="first") <= GRANDES_ECONOMIES


def _quantiles_retenus(cas: pd.DataFrame) -> tuple:
    """
    Quantiles par classe × groupe de revenu, et par classe seule pour le repli. Les
    cellules de moins de `MIN_CAS_CELLULE` cas sont retirées : elles se replient.
    """
    par_cellule = _quantiles_fourchette(cas, ["classe", "income_group"])
    return par_cellule[par_cellule["cas"] >= MIN_CAS_CELLULE], _quantiles_fourchette(cas, ["classe"])


def _choisir(par_cellule, par_classe, ensemble, classe, groupe):
    """Quantiles de la cellule (classe, groupe), à défaut de la classe, à défaut de l'ensemble."""
    if pd.notna(classe) and (classe, groupe) in par_cellule.index:
        return par_cellule.loc[(classe, groupe)], "classe × groupe de revenu"
    if pd.notna(classe) and classe in par_classe.index:
        return par_classe.loc[classe], "classe de croissance"
    return ensemble, "ensemble des projections"


def fourchettes_projections(niveaux: pd.DataFrame, croissance_actuelle: pd.Series, synthese_pays: pd.DataFrame,
                            annee_fin: int, annee_edition: int, monde: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Fourchette empirique autour du PIB en volume projeté pour `annee_fin`.

    Les projections passées au même horizon (`annee_fin` − `annee_edition`) sont réparties
    en classes de croissance cumulée projetée (`classes_de_croissance`) et en groupes de
    revenu. Chaque pays reçoit le 10e et le 90e centile des erreurs de niveau de sa
    cellule, selon la croissance que l'édition actuelle lui projette (`croissance_actuelle`)
    et son groupe de revenu (voir `_choisir` pour les replis). Le niveau réalisé valant le
    niveau prévu divisé par (1 + erreur), une erreur passée de +10 % abaisse la projection
    de 9,1 %.

    Ce n'est pas une prévision corrigée, mais la marge dans laquelle sont tombées 80 % des
    projections comparables. Elle porte sur le volume : en dollars courants s'ajoutent les
    erreurs de change et d'inflation, que la base historique ne mesure pas.

    Des mêmes projections comparables vient `probabilite_recul_pct` : la part où il est
    survenu au moins une année de recul entre l'année suivant l'édition et `annee_fin`,
    quand la trajectoire du FMI n'en montre presque jamais ; `pire_annee_mediane_pct` en
    donne la profondeur typique.

    Avec `monde` (croissance mondiale par habitant depuis 1961), les crises mondiales sont
    traitées à part : la probabilité mêle la fréquence des reculs dans les périodes passées
    qui contenaient une récession mondiale (`probabilite_recul_si_crise_mondiale_pct`) et
    dans les autres (`…_hors_crise_mondiale_pct`), pondérées par la part des périodes de
    même durée qui en contiennent une sur l'historique long (`probabilite_crise_mondiale_pct`).
    """
    horizon = annee_fin - annee_edition
    colonne = "erreur_niveau_vs_fmi_pct"
    niveau = f"GDP_Reel_{annee_fin}_Billion_USD_2015"
    passe = niveaux[niveaux["horizon"] == horizon].dropna(subset=[colonne, "croissance_prevue_cumulee_pct"]).copy()
    if passe.empty or niveau not in synthese_pays.columns:
        logging.warning(f"Pas d'erreur de niveau historique à l'horizon {horizon} : fourchettes omises.")
        return pd.DataFrame()

    passe["classe"], bornes = classes_de_croissance(passe["croissance_prevue_cumulee_pct"])
    par_cellule, par_classe = _quantiles_retenus(passe)
    q_bas, q_haut = QUANTILES_FOURCHETTE
    ensemble = pd.Series({"bas": passe[colonne].quantile(q_bas), "haut": passe[colonne].quantile(q_haut),
                          "mediane": passe[colonne].median(), "cas": len(passe)})
    if "pire_croissance_realisee" in passe.columns:
        ensemble = pd.concat([ensemble, pd.Series(_statistiques_de_recul(passe["pire_croissance_realisee"]))])
    limites = [-np.inf, *bornes, np.inf]
    melange = None
    if monde is not None and "pire_croissance_realisee" in passe.columns:
        crise = periodes_en_crise(passe["annee_millesime"], horizon, recessions_mondiales(monde))
        pi = probabilite_crise_mondiale(monde, horizon)
        melange = (pi, frequences_de_recul(passe[crise]), frequences_de_recul(passe[~crise]), frequences_de_recul(passe))

    lignes = []
    for _, pays in synthese_pays.dropna(subset=[niveau]).iterrows():
        croissance = croissance_actuelle.get(pays["country_code"], np.nan)
        classe = (classes_de_croissance(pd.Series([croissance]), bornes)[0].iloc[0]
                  if pd.notna(croissance) else np.nan)
        groupe = pays.get("income_group")
        q, reference = _choisir(par_cellule, par_classe, ensemble, classe, groupe)
        libelle = ("" if pd.isna(classe) else
                   f"moins de {bornes[0]:.0f} %" if classe == 1 else
                   f"plus de {bornes[-1]:.0f} %" if classe == CLASSES_CROISSANCE else
                   f"{limites[int(classe) - 1]:.0f} à {limites[int(classe)]:.0f} %")
        # Erreur passée élevée (p90) -> réalisé bien en dessous : borne basse, et inversement
        borne_basse = (1 / (1 + q["haut"] / 100) - 1) * 100
        borne_haute = (1 / (1 + q["bas"] / 100) - 1) * 100
        recul = {"probabilite_recul_pct": q.get("recul", np.nan)}
        if melange is not None:
            proba, f_crise, f_hors = probabilite_de_recul(melange, classe, groupe)
            recul = {"probabilite_recul_pct": proba * 100,
                     "probabilite_recul_si_crise_mondiale_pct": f_crise * 100,
                     "probabilite_recul_hors_crise_mondiale_pct": f_hors * 100,
                     "probabilite_crise_mondiale_pct": melange[0] * 100}
        lignes.append({
            "country_code": pays["country_code"], "country_name": pays["country_name"],
            "income_group": groupe, "horizon": horizon,
            "croissance_projetee_pct": croissance, "classe_de_croissance": classe,
            "croissance_de_la_classe": libelle, "projections_de_reference": reference,
            "cas_historiques": int(q["cas"]),
            "erreur_niveau_p10_pct": q["bas"], "erreur_niveau_mediane_pct": q["mediane"],
            "erreur_niveau_p90_pct": q["haut"],
            "borne_basse_pct": borne_basse, "borne_haute_pct": borne_haute,
            **recul, "pire_annee_mediane_pct": q.get("pire_recul", np.nan),
            niveau: pays[niveau],
            f"GDP_Reel_{annee_fin}_Bas": pays[niveau] * (1 + borne_basse / 100),
            f"GDP_Reel_{annee_fin}_Haut": pays[niveau] * (1 + borne_haute / 100),
        })
    return pd.DataFrame(lignes).round(3)


def calibration_fourchettes(niveaux: pd.DataFrame, horizon: int,
                            coupure: int = ANNEE_COUPURE_CALIBRATION) -> pd.DataFrame:
    """
    Test rétrospectif des fourchettes : calculées sur les éditions jusqu'à `coupure`,
    quelle part des erreurs des éditions suivantes contiennent-elles ? Une fourchette 80 %
    bien calibrée en contient 80 %. La méthode retenue (classe de croissance projetée ×
    groupe de revenu) est comparée à trois autres, et sa couverture détaillée pour les
    `GRANDES_ECONOMIES` premières économies de l'année visée, les pays à faible revenu,
    et en pondérant par le PIB.
    """
    colonne = "erreur_niveau_vs_fmi_pct"
    q_bas, q_haut = QUANTILES_FOURCHETTE
    cas = niveaux[niveaux["horizon"] == horizon].dropna(subset=[colonne, "croissance_prevue_cumulee_pct"]).copy()
    cas["grande"] = _grandes_economies(cas)
    avant = cas[cas["annee_millesime"] <= coupure].copy()
    apres = cas[cas["annee_millesime"] > coupure].copy()
    if avant.empty or apres.empty:
        return pd.DataFrame()
    avant["classe"], bornes = classes_de_croissance(avant["croissance_prevue_cumulee_pct"])
    apres["classe"], _ = classes_de_croissance(apres["croissance_prevue_cumulee_pct"], bornes)

    def bornes_retenues(x):
        par_cellule, par_classe = _quantiles_retenus(avant)
        choix = [_choisir(par_cellule, par_classe, pd.Series({"bas": np.nan, "haut": np.nan}), c, g)[0]
                 for c, g in zip(x["classe"], x["income_group"])]
        return pd.DataFrame({"bas": [q["bas"] for q in choix], "haut": [q["haut"] for q in choix]}, index=x.index)

    lignes = []
    for methode, cle in (("classe de croissance × groupe de revenu", None),
                         ("classe de croissance projetée", "classe"),
                         ("groupe de revenu", "income_group"), ("historique du pays", "country_code")):
        if cle is None:
            x = apres.join(bornes_retenues(apres))
        else:
            q = _quantiles_fourchette(avant, [cle])[["bas", "haut"]]
            x = apres.join(q, on=cle)
        x = x.dropna(subset=["bas", "haut"])
        x["dedans"] = x[colonne].between(x["bas"], x["haut"])
        ponderes = x.dropna(subset=["poids_pib"])
        lignes.append({
            "methode": methode, "retenue": cle is None, "horizon": horizon,
            "editions_de_calcul": f"{int(avant['annee_millesime'].min())}-{coupure}",
            "editions_de_test": f"{coupure + 1}-{int(apres['annee_millesime'].max())}",
            "cas_testes": len(x), "cible_pct": (q_haut - q_bas) * 100,
            "couverture_pct": x["dedans"].mean() * 100,
            "largeur_mediane_pts": (x["haut"] - x["bas"]).median(),
            "couverture_grandes_economies_pct": x.loc[x["grande"], "dedans"].mean() * 100,
            "couverture_faible_revenu_pct": x.loc[x["income_group"] == "LIC", "dedans"].mean() * 100,
            "couverture_ponderee_pib_pct": (np.average(ponderes["dedans"], weights=ponderes["poids_pib"]) * 100
                                            if len(ponderes) else np.nan),
        })
    return pd.DataFrame(lignes).round(2)


def efficience(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Test d'efficience de Mincer et Zarnowitz, par horizon, contre la ré-estimation du FMI :
    réalisé = a + b × prévu. Une prévision efficace donne b = 1. Sous 1, le réalisé ne suit
    qu'en partie les écarts de croissance annoncés d'un pays à l'autre : plus le FMI annonce
    de croissance, plus il surestime. La droite est ajustée sans les valeurs extrêmes
    (`QUANTILES_ROGNAGE`) ; le biais médian par quintile de prévision montre la même chose
    sans modèle.
    """
    valides = evaluation.dropna(subset=["valeur", "realise_fmi"])
    lignes = []
    for horizon, g in valides.groupby("horizon"):
        bas, haut = QUANTILES_ROGNAGE
        garde = (g["valeur"].between(*g["valeur"].quantile([bas, haut]))
                 & g["realise_fmi"].between(*g["realise_fmi"].quantile([bas, haut])))
        c = g[garde]
        if len(c) < 10:
            continue
        pente, constante = np.polyfit(c["valeur"], c["realise_fmi"], 1)
        ligne = {"horizon": horizon, "observations": len(c), "pente": pente, "constante": constante}
        quintile = pd.qcut(g["valeur"], 5, labels=False, duplicates="drop")
        for k, q in g.groupby(quintile):
            ligne[f"prevision_mediane_q{int(k) + 1}"] = q["valeur"].median()
            ligne[f"biais_median_q{int(k) + 1}"] = (q["valeur"] - q["realise_fmi"]).median()
        lignes.append(ligne)
    return pd.DataFrame(lignes).round(3)


def lire_croissance_mondiale(data_dir: str) -> Optional[pd.Series]:
    """Croissance mondiale par habitant écrite par le pipeline (`FICHIER_MONDE`), ou None."""
    chemin = os.path.join(data_dir, "processed", FICHIER_MONDE)
    if not os.path.exists(chemin):
        return None
    t = pd.read_csv(chemin)
    return t.set_index("year").iloc[:, 0]


def recessions_mondiales(monde: pd.Series, jusqu_a: int = None) -> list:
    """Années de recul du PIB mondial par habitant, connues jusqu'à `jusqu_a` inclus."""
    m = monde if jusqu_a is None else monde[monde.index <= jusqu_a]
    return [int(a) for a, v in m.items() if v < 0]


def probabilite_crise_mondiale(monde: pd.Series, duree: int, jusqu_a: int = None) -> float:
    """
    Part des périodes de `duree` années consécutives de l'historique (connu jusqu'à
    `jusqu_a`) qui contiennent au moins une récession mondiale : la probabilité qu'une
    période à venir en contienne une.
    """
    m = monde if jusqu_a is None else monde[monde.index <= jusqu_a]
    annees = list(m.index)
    periodes = [m.loc[a:a + duree - 1].lt(0).any() for a in annees if a + duree - 1 <= annees[-1]]
    return float(np.mean(periodes)) if periodes else np.nan


def periodes_en_crise(annee_millesime: pd.Series, duree: int, recessions: list) -> pd.Series:
    """Vrai si la période suivant l'édition (années m + 1 à m + duree) contient une récession mondiale."""
    return annee_millesime.apply(lambda m: any(m + 1 <= a <= m + duree for a in recessions))


def frequences_de_recul(cas: pd.DataFrame) -> tuple:
    """
    Part des périodes avec au moins une année de recul : par classe de croissance × groupe
    de revenu (cellules d'au moins `MIN_CAS_CELLULE` cas), par classe, et pour l'ensemble.
    """
    recul = (cas["pire_croissance_realisee"] < 0).astype(float)
    par_cellule = recul.groupby([cas["classe"], cas["income_group"]]).agg(["mean", "size"])
    par_cellule = par_cellule.loc[par_cellule["size"] >= MIN_CAS_CELLULE, "mean"]
    return par_cellule, recul.groupby(cas["classe"]).mean(), recul.mean() if len(recul) else np.nan


def frequence_de_recul(tables: tuple, classe, groupe) -> float:
    """Fréquence de la cellule (classe, groupe), à défaut de la classe, à défaut de l'ensemble (NaN si vide)."""
    par_cellule, par_classe, ensemble = tables
    if pd.notna(classe) and (classe, groupe) in par_cellule.index:
        return float(par_cellule.loc[(classe, groupe)])
    if pd.notna(classe) and classe in par_classe.index:
        return float(par_classe.loc[classe])
    return float(ensemble)


def probabilite_de_recul(melange: tuple, classe, groupe) -> tuple:
    """
    Probabilité de recul, crises mondiales à part : `melange` = (probabilité de crise
    mondiale, fréquences en crise, fréquences hors crise, fréquences toutes périodes).
    Sans période passée en crise (ou hors crise) pour l'estimer, la fréquence toutes
    périodes la remplace. Retourne (probabilité, fréquence en crise, fréquence hors crise).
    """
    pi, en_crise, hors_crise, toutes = melange
    defaut = frequence_de_recul(toutes, classe, groupe)
    f_crise, f_hors = frequence_de_recul(en_crise, classe, groupe), frequence_de_recul(hors_crise, classe, groupe)
    f_crise = defaut if pd.isna(f_crise) else f_crise
    f_hors = defaut if pd.isna(f_hors) else f_hors
    return pi * f_crise + (1 - pi) * f_hors, f_crise, f_hors


def synthese_niveau_par_croissance(niveaux: pd.DataFrame) -> pd.DataFrame:
    """
    Erreur de niveau par horizon et classe de croissance cumulée projetée ; avec les pires
    années réalisées, part des périodes où il est survenu au moins une année de recul, sur
    toutes les éditions, puis jusqu'à `ANNEE_COUPURE_CALIBRATION` et après.
    """
    colonne = "erreur_niveau_vs_fmi_pct"
    lignes = []
    for horizon, g in niveaux.dropna(subset=[colonne, "croissance_prevue_cumulee_pct"]).groupby("horizon"):
        classes, _ = classes_de_croissance(g["croissance_prevue_cumulee_pct"])
        for classe, c in g.groupby(classes):
            ligne = {"horizon": horizon, "classe_de_croissance": int(classe), "observations": len(c),
                     "croissance_projetee_mediane_pct": c["croissance_prevue_cumulee_pct"].median(),
                     "mediane": c[colonne].median(), "p10": c[colonne].quantile(0.10),
                     "p90": c[colonne].quantile(0.90)}
            if "pire_croissance_realisee" in c.columns:
                avant = c["annee_millesime"] <= ANNEE_COUPURE_CALIBRATION
                pire = c["pire_croissance_realisee"]
                ligne.update(recul_survenu_pct=_frequence_recul(pire),
                             recul_survenu_avant_coupure_pct=_frequence_recul(pire[avant]),
                             recul_survenu_apres_coupure_pct=_frequence_recul(pire[~avant]))
            lignes.append(ligne)
    return pd.DataFrame(lignes).round(3)


def reculs_par_horizon(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Années de recul (croissance négative), annoncées et survenues, par horizon, contre la
    ré-estimation du FMI : part des projections en recul, part des croissances réalisées
    en recul, part des reculs survenus que l'édition annonçait, et part des reculs
    annoncés qui sont survenus.
    """
    valides = evaluation.dropna(subset=["valeur", "realise_fmi"])
    lignes = []
    for horizon, g in valides.groupby("horizon"):
        annonce, survenu = g["valeur"] < 0, g["realise_fmi"] < 0
        lignes.append({"horizon": horizon, "projections": len(g),
                       "recul_annonce_pct": annonce.mean() * 100, "recul_survenu_pct": survenu.mean() * 100,
                       "reculs_survenus": int(survenu.sum()),
                       "reculs_survenus_annonces_pct": annonce[survenu].mean() * 100 if survenu.any() else np.nan,
                       "reculs_annonces_survenus_pct": survenu[annonce].mean() * 100 if annonce.any() else np.nan})
    return pd.DataFrame(lignes).round(3)


def risque_de_recession(niveaux: pd.DataFrame) -> pd.DataFrame:
    """
    Au moins une année de recul sur les h années suivant l'édition (horizons 1 à h), par
    horizon h et par groupe — tous les pays, les `GRANDES_ECONOMIES` premières, chaque
    groupe de revenu :

    - part des éditions qui en annonçaient une (`recul_annonce_pct`) ;
    - part où il en est survenu une : toutes, pondérées par le PIB, hors des périodes
      contenant une récession mondiale (`ANNEES_RECESSION_MONDIALE`), puis pour les
      éditions jusqu'à `ANNEE_COUPURE_CALIBRATION` et après ;
    - pire année médiane quand il en est survenu une.

    La trajectoire du FMI est lisse : elle ne montre presque jamais le recul qui survient
    pourtant, dans une période de cinq ans, pour un pays sur deux.
    """
    colonnes = ["pire_croissance_prevue", "pire_croissance_realisee"]
    if not set(colonnes) <= set(niveaux.columns):
        return pd.DataFrame()
    cas = niveaux[niveaux["horizon"] >= 1].dropna(subset=colonnes).copy()
    if cas.empty:
        return pd.DataFrame()
    cas["grande"] = _grandes_economies(cas)
    cas["recul_survenu"] = (cas["pire_croissance_realisee"] < 0).astype(float)
    debut = cas["annee_millesime"] + 1
    cas["crise_mondiale"] = np.logical_or.reduce([(debut <= a) & (cas["year"] >= a) for a in ANNEES_RECESSION_MONDIALE])
    avant = cas["annee_millesime"] <= ANNEE_COUPURE_CALIBRATION

    groupes = [("Tous les pays", None, pd.Series(True, index=cas.index)),
               (f"{GRANDES_ECONOMIES} premières économies", None, cas["grande"])]
    groupes += [(libelle, code, cas["income_group"] == code) for code, libelle in GROUPES_REVENU.items()]
    lignes = []
    for horizon, g in cas.groupby("horizon"):
        for libelle, code, masque in groupes:
            x = g[masque.loc[g.index]]
            if x.empty:
                continue
            pire = x["pire_croissance_realisee"]
            lignes.append({
                "horizon": horizon, "groupe": libelle, "income_group": code, "periodes": len(x),
                "recul_annonce_pct": (x["pire_croissance_prevue"] < 0).mean() * 100,
                "recul_survenu_pct": _frequence_recul(pire),
                "recul_survenu_pondere_pib_pct": _moyenne_ponderee(x["recul_survenu"], x["poids_pib"]) * 100,
                "recul_survenu_hors_crises_mondiales_pct": _frequence_recul(pire[~x["crise_mondiale"]]),
                "recul_survenu_avant_coupure_pct": _frequence_recul(pire[avant.loc[x.index]]),
                "recul_survenu_apres_coupure_pct": _frequence_recul(pire[~avant.loc[x.index]]),
                "pire_annee_mediane_pct": pire[pire < 0].median(),
            })
    return pd.DataFrame(lignes).round(3)


def moyennes_dominees(synthese: pd.DataFrame, seuil: float = SEUIL_VALEURS_EXTREMES) -> bool:
    """
    Vrai si, à un horizon au moins, l'erreur absolue moyenne dépasse `seuil` fois la
    médiane : les moyennes décrivent alors quelques cas extrêmes, pas l'erreur typique.
    """
    if synthese.empty:
        return False
    rapport = synthese["erreur_absolue_moyenne"] / synthese["erreur_absolue_mediane"]
    return bool((rapport > seuil).any())


def main():
    parser = argparse.ArgumentParser(
        description="Évaluation des prévisions FMI contre les valeurs observées.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--output-dir", type=str, default="outputs",
                        help="Dossier du classeur Excel, qui reçoit l'onglet des fourchettes")
    parser.add_argument("--classeur", type=str, default=None,
                        help="Chemin du classeur WEOhistorical.xlsx")
    parser.add_argument("--complement", type=str, default=None,
                        help="Éditions ajoutées depuis l'API (par défaut : weo_editions_api.csv à côté du classeur)")
    parser.add_argument("--indicateur", type=str, default="ngdp_rpch",
                        choices=sorted(INDICATEURS), help="Onglet à évaluer")
    parser.add_argument("--garder-agregats", action="store_true",
                        help="Conserver les agrégats du FMI (World, zones monétaires...)")
    args = parser.parse_args()

    chemin = args.classeur or os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")

    try:
        base = lire_base_historique(chemin, args.indicateur, args.complement)
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        sys.exit(1)
    base_complete = base      # agrégats compris, pour la croissance mondiale

    if not args.garder_agregats:
        base = exclure_agregats(base, args.data_dir)

    evaluation = evaluer(base, args.data_dir, args.indicateur)
    if evaluation.empty:
        logging.error("Aucune projection exploitable.")
        sys.exit(1)

    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)

    sortie = os.path.join(processed, f"weo_forecast_evaluation_{args.indicateur}.csv")
    evaluation.to_csv(sortie, index=False, encoding="utf-8-sig")
    logging.info(f"Évaluation enregistrée : {sortie}")

    synthese = synthese_par_horizon(evaluation)
    sortie_synthese = os.path.join(processed, f"weo_forecast_bias_{args.indicateur}.csv")
    synthese.to_csv(sortie_synthese, index=False, encoding="utf-8-sig")
    synthese_par_revenu(evaluation).to_csv(
        os.path.join(processed, f"weo_forecast_bias_by_income_{args.indicateur}.csv"),
        index=False, encoding="utf-8-sig")
    synthese_par_saison(evaluation).to_csv(
        os.path.join(processed, f"weo_forecast_bias_by_season_{args.indicateur}.csv"),
        index=False, encoding="utf-8-sig")
    naif = comparaison_naive(evaluation)
    naif.to_csv(os.path.join(processed, f"weo_forecast_vs_naive_{args.indicateur}.csv"), index=False, encoding="utf-8-sig")
    logging.info("FMI face à la prévision naïve (croissance moyenne des années v−5 à v−2) :\n" + naif.to_string(index=False))
    efficience(evaluation).to_csv(
        os.path.join(processed, f"weo_forecast_efficiency_{args.indicateur}.csv"), index=False, encoding="utf-8-sig")
    monde = synthese_par_horizon(evaluer_monde(base_complete))
    if not monde.empty:
        monde.to_csv(os.path.join(processed, f"weo_world_bias_{args.indicateur}.csv"), index=False, encoding="utf-8-sig")
        logging.info("Agrégat World — biais par horizon :\n"
                     + monde[["reference", "horizon", "observations", "biais_moyen", "mediane",
                              "erreur_absolue_moyenne"]].to_string(index=False))

    logging.info(f"{INDICATEURS[args.indicateur]} — biais par horizon :\n"
                 + synthese.to_string(index=False))

    if moyennes_dominees(synthese):
        logging.warning("Les moyennes sont dominées par quelques valeurs extrêmes : l'erreur "
                        "typique se lit dans les colonnes `mediane` et `erreur_absolue_mediane`.")

    if args.indicateur == INDICATEUR_NIVEAU:
        evaluer_niveaux(evaluation, base, args.data_dir, args.output_dir)


def evaluer_niveaux(evaluation: pd.DataFrame, base: pd.DataFrame, data_dir: str, output_dir: str) -> None:
    """Erreurs de niveau, leurs synthèses, et la fourchette autour des projections actuelles."""
    processed = os.path.join(data_dir, "processed")
    niveaux = erreurs_de_niveau(evaluation)
    niveaux.to_csv(os.path.join(processed, "weo_level_evaluation_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    synthese = synthese_niveau(niveaux)
    synthese.to_csv(os.path.join(processed, "weo_level_bias_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    synthese_niveau_par_revenu(niveaux).to_csv(
        os.path.join(processed, "weo_level_bias_by_income_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    synthese_niveau_par_croissance(niveaux).to_csv(
        os.path.join(processed, "weo_level_bias_by_projected_growth_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    logging.info("Erreur sur le niveau du PIB en volume (prévu / réalisé − 1, en %) :\n"
                 + synthese.to_string(index=False))

    reculs_par_horizon(evaluation).to_csv(
        os.path.join(processed, "weo_recession_by_horizon_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    risque = risque_de_recession(niveaux)
    risque.to_csv(os.path.join(processed, "weo_recession_risk_ngdp_rpch.csv"), index=False, encoding="utf-8-sig")
    if not risque.empty:
        logging.info("Au moins une année de recul dans les h années suivant l'édition (%) :\n"
                     + risque[risque["income_group"].isna()][["horizon", "groupe", "periodes", "recul_annonce_pct",
                                                             "recul_survenu_pct", "pire_annee_mediane_pct"]]
                     .to_string(index=False))

    # Fourchettes autour des projections du rapport, à l'horizon de sa dernière année
    synthese_csv = os.path.join(processed, "gdp_country_summary.csv")
    meta_json = os.path.join(data_dir, "extraction_metadata.json")
    if not (os.path.exists(synthese_csv) and os.path.exists(meta_json)):
        logging.warning("Synthèse du pipeline absente : fourchettes des projections omises.")
        return
    with open(meta_json, encoding="utf-8") as f:
        annee_fin = json.load(f)["bornes"]["prevision"][1]
    annee_edition = int(base["annee_millesime"].max())
    horizon = annee_fin - annee_edition
    monde = lire_croissance_mondiale(data_dir)
    if monde is None:
        logging.warning(f"{FICHIER_MONDE} absent : probabilités de récession sans les crises mondiales à part.")
    fourchettes = fourchettes_projections(niveaux, croissance_projetee_actuelle(base, annee_edition, horizon),
                                          pd.read_csv(synthese_csv), annee_fin, annee_edition, monde)
    if fourchettes.empty:
        return
    calibration = calibration_fourchettes(niveaux, horizon)
    calibration.to_csv(os.path.join(processed, "gdp_projection_bands_calibration.csv"), index=False, encoding="utf-8-sig")
    logging.info("Calibration des fourchettes (test rétrospectif) :\n" + calibration.to_string(index=False))
    fourchettes.to_csv(os.path.join(processed, "gdp_projection_bands.csv"), index=False, encoding="utf-8-sig")
    logging.info(f"Fourchettes empiriques du PIB {annee_fin} (édition {annee_edition}, horizon "
                 f"{annee_fin - annee_edition}) : {len(fourchettes)} pays.")

    excel = os.path.join(output_dir, "gdp_master_dataset.xlsx")
    if os.path.exists(excel):
        with pd.ExcelWriter(excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            fourchettes.to_excel(writer, sheet_name=f"Fourchettes_{annee_fin}", index=False)
        logging.info(f"Onglet Fourchettes_{annee_fin} ajouté à {excel}")


if __name__ == "__main__":
    main()
