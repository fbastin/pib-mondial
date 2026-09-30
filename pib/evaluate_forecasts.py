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

# Fourchette empirique autour des projections : 80 % des erreurs de niveau passées,
# tirées de l'historique du pays s'il couvre assez d'années visées, sinon de son groupe
# de revenu. À 5 ans, la France est sortie dans 80 % des cas entre +1,4 % et +9,8 %
# au-dessus du réalisé, quand le groupe des pays à revenu élevé va de −6,5 % à +18 % :
# le groupe ne dit rien de la précision propre à une grande économie.
QUANTILES_FOURCHETTE = (0.10, 0.90)
MIN_ANNEES_PAYS = 20

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
    """
    colonnes = ["country", "country_code", "income_group", "vintage", "saison", "annee_millesime",
                "year", "horizon", "poids_pib"]
    d = evaluation[evaluation["horizon"] >= 0].sort_values(["country_code", "vintage", "horizon"]).copy()
    for c in ("income_group", "poids_pib"):
        if c not in d.columns:
            d[c] = np.nan
    cles = [d["country_code"], d["vintage"]]
    attendu = d.groupby(["country_code", "vintage"]).cumcount()

    for ref, (realise, _) in REFERENCES.items():
        ecart = np.log1p(d["valeur"] / 100) - np.log1p(d[realise] / 100)
        rompu = (ecart.isna() | (d["horizon"] != attendu)).astype(int).groupby(cles).cummax().astype(bool)
        cumul = ecart.where(~rompu).groupby(cles).cumsum()
        d[f"erreur_niveau_vs_{ref}_pct"] = ((np.exp(cumul) - 1) * 100).where(~rompu)

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


def fourchettes_projections(niveaux: pd.DataFrame, synthese_pays: pd.DataFrame,
                            annee_fin: int, annee_edition: int) -> pd.DataFrame:
    """
    Fourchette empirique autour du PIB en volume projeté pour `annee_fin`.

    Elle applique à la projection actuelle les erreurs de niveau passées au même horizon
    (`annee_fin` − `annee_edition`), du 10e au 90e centile : celles du pays lui-même s'il
    en compte sur au moins `MIN_ANNEES_PAYS` années visées, sinon celles de son groupe de
    revenu, à défaut celles de l'ensemble des pays. Le niveau réalisé vaut le niveau
    prévu divisé par (1 + erreur) : une erreur passée de +10 % abaisse la projection de
    9,1 %. Ce n'est pas une prévision corrigée, mais la marge dans laquelle sont tombées
    80 % des projections comparables. Elle porte sur le volume : en dollars courants
    s'ajoutent les erreurs de change et d'inflation, que la base historique ne permet pas
    de mesurer.
    """
    horizon = annee_fin - annee_edition
    colonne = "erreur_niveau_vs_fmi_pct"
    niveau = f"GDP_Reel_{annee_fin}_Billion_USD_2015"
    passe = niveaux[niveaux["horizon"] == horizon].dropna(subset=[colonne])
    if passe.empty or niveau not in synthese_pays.columns:
        logging.warning(f"Pas d'erreur de niveau historique à l'horizon {horizon} : fourchettes omises.")
        return pd.DataFrame()

    q_bas, q_haut = QUANTILES_FOURCHETTE

    def quantiles(cle: str) -> pd.DataFrame:
        g = passe.groupby(cle)
        return pd.DataFrame({"bas": g[colonne].quantile(q_bas), "haut": g[colonne].quantile(q_haut),
                             "cas": g.size(), "annees": g["year"].nunique()})

    par_pays, par_groupe = quantiles("country_code"), quantiles("income_group")
    par_pays = par_pays[par_pays["annees"] >= MIN_ANNEES_PAYS]
    ensemble = pd.Series({"bas": passe[colonne].quantile(q_bas), "haut": passe[colonne].quantile(q_haut),
                          "cas": len(passe)})

    lignes = []
    for _, pays in synthese_pays.dropna(subset=[niveau]).iterrows():
        groupe = pays.get("income_group")
        if pays["country_code"] in par_pays.index:
            q, source = par_pays.loc[pays["country_code"]], "pays"
        elif groupe in par_groupe.index:
            q, source = par_groupe.loc[groupe], groupe
        else:
            q, source = ensemble, "ensemble"
        # Erreur passée élevée (p90) -> réalisé bien en dessous : borne basse, et inversement
        borne_basse = (1 / (1 + q["haut"] / 100) - 1) * 100
        borne_haute = (1 / (1 + q["bas"] / 100) - 1) * 100
        lignes.append({
            "country_code": pays["country_code"], "country_name": pays["country_name"],
            "income_group": groupe, "horizon": horizon,
            "historique_de_reference": source,
            "cas_historiques": int(q["cas"]),
            "erreur_niveau_p10_pct": q["bas"], "erreur_niveau_p90_pct": q["haut"],
            "borne_basse_pct": borne_basse, "borne_haute_pct": borne_haute,
            niveau: pays[niveau],
            f"GDP_Reel_{annee_fin}_Bas": pays[niveau] * (1 + borne_basse / 100),
            f"GDP_Reel_{annee_fin}_Haut": pays[niveau] * (1 + borne_haute / 100),
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
    logging.info("Erreur sur le niveau du PIB en volume (prévu / réalisé − 1, en %) :\n"
                 + synthese.to_string(index=False))

    # Fourchettes autour des projections du rapport, à l'horizon de sa dernière année
    synthese_csv = os.path.join(processed, "gdp_country_summary.csv")
    meta_json = os.path.join(data_dir, "extraction_metadata.json")
    if not (os.path.exists(synthese_csv) and os.path.exists(meta_json)):
        logging.warning("Synthèse du pipeline absente : fourchettes des projections omises.")
        return
    with open(meta_json, encoding="utf-8") as f:
        annee_fin = json.load(f)["bornes"]["prevision"][1]
    annee_edition = int(base["annee_millesime"].max())
    fourchettes = fourchettes_projections(niveaux, pd.read_csv(synthese_csv), annee_fin, annee_edition)
    if fourchettes.empty:
        return
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
