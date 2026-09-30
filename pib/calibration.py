#!/usr/bin/env python3
"""
calibration.py
--------------
Évaluation probabiliste des fourchettes de niveau et des probabilités de récession tirées
des erreurs passées du FMI (voir `evaluate_forecasts.fourchettes_projections`).

Le test rétrospectif de `evaluate_forecasts` coupe une fois, en 2007. Celui-ci se fait en
temps réel : chaque édition de `PREMIERE_EDITION_TEST` à la dernière dont l'erreur est
connue reçoit des fourchettes et des probabilités calculées sur les seules erreurs connues
à sa date. Pour une projection à h ans de l'édition v, l'erreur d'une édition m n'est
connue qu'une fois publiée la ré-estimation de son année visée, en octobre m + h + 1 :
avant l'édition d'avril v, il faut donc m ≤ v − h − 2.

Les méthodes (comment choisir les projections comparables) sont comparées sur les mêmes
cas :

- fourchettes : couverture de l'intervalle à 80 %, largeur, score d'intervalle et CRPS
  (Gneiting et Raftery, 2007), plus petits pour une meilleure prévision ;
- probabilités d'au moins une année de recul : score de Brier, compétence face à la
  fréquence moyenne, et fiabilité (fréquence observée par tranche de probabilité).

Les intervalles de confiance viennent d'un bootstrap par blocs d'années visées : les
erreurs d'une même année visée, communes à tous les pays (2009, 2020), sont tirées ensemble.

    python -m pib.calibration --data-dir data
"""

import os
import logging
import argparse

import numpy as np
import pandas as pd

from pib.evaluate_forecasts import (
    MIN_CAS_CELLULE,
    QUANTILES_FOURCHETTE,
    classes_de_croissance,
    frequences_de_recul,
    lire_croissance_mondiale,
    periodes_en_crise,
    probabilite_crise_mondiale,
    probabilite_de_recul,
    recessions_mondiales,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HORIZON = 5
PREMIERE_EDITION_TEST = 2000
# Nombre minimal d'erreurs passées pour une fourchette tirée de l'historique d'un pays
MIN_CAS_PAYS = 8
TIRAGES = 500
GRAINE = 20260930
ALPHA = 1 - (QUANTILES_FOURCHETTE[1] - QUANTILES_FOURCHETTE[0])
TRANCHES_PROBABILITE = np.linspace(0, 1, 11)

METHODE_RETENUE = "classe × groupe de revenu"
METHODES = (METHODE_RETENUE, "classe de croissance", "groupe de revenu", "inconditionnelle", "historique du pays")
METHODE_FMI = "trajectoire du FMI"      # probabilité 0 ou 1 : l'édition annonçait-elle un recul ?
# Probabilité de recul retenue en production : crises mondiales à part (voir
# `evaluate_forecasts.fourchettes_projections`). Méthode propre aux probabilités.
METHODE_MELANGE = "classe × groupe, crises mondiales à part"

COLONNES = ["erreur_niveau_vs_fmi_pct", "croissance_prevue_cumulee_pct", "pire_croissance_realisee",
            "pire_croissance_prevue"]


# ------------------------------------------------------------------ scores

def score_intervalle(bas, haut, y, alpha: float = ALPHA):
    """
    Score d'intervalle de Gneiting et Raftery (2007) pour l'intervalle central de niveau
    1 − alpha : largeur, plus 2 / alpha fois le dépassement de la borne franchie.
    """
    bas, haut, y = np.asarray(bas, float), np.asarray(haut, float), np.asarray(y, float)
    return (haut - bas) + 2 / alpha * (bas - y) * (y < bas) + 2 / alpha * (y - haut) * (y > haut)


class Distribution:
    """Distribution empirique d'un échantillon : quantiles et CRPS en O(log n) par valeur."""

    def __init__(self, echantillon):
        x = np.sort(np.asarray(echantillon, float))
        self.x, self.n = x, len(x)
        self.cumul = np.concatenate([[0.0], np.cumsum(x)])
        rangs = np.arange(1, self.n + 1)
        # Somme des |x_i − x_j| sur tous les couples, par la formule des rangs
        self.dispersion = 2 * np.sum((2 * rangs - self.n - 1) * x) / self.n ** 2 if self.n else np.nan

    def quantile(self, q: float) -> float:
        return float(np.quantile(self.x, q)) if self.n else np.nan

    def crps(self, y) -> np.ndarray:
        """CRPS(F, y) = E|X − y| − E|X − X'| / 2, pour la distribution empirique F."""
        y = np.atleast_1d(np.asarray(y, float))
        if not self.n:
            return np.full(len(y), np.nan)
        k = np.searchsorted(self.x, y, side="right")
        ecart = (y * k - self.cumul[k]) + (self.cumul[-1] - self.cumul[k]) - y * (self.n - k)
        return ecart / self.n - self.dispersion / 2


# ------------------------------------------------------------------ prévisions en temps réel

def _cellules(entrainement: pd.DataFrame, cles: list) -> dict:
    """Distribution des erreurs et fréquence des reculs par cellule `cles`."""
    cellules = {}
    for cle, g in entrainement.groupby(cles):
        cle = cle if isinstance(cle, tuple) else (cle,)
        cle = cle[0] if len(cles) == 1 else cle
        cellules[cle] = (Distribution(g["erreur_niveau_vs_fmi_pct"]), (g["pire_croissance_realisee"] < 0).mean(), len(g))
    return cellules


def previsions_en_temps_reel(niveaux: pd.DataFrame, horizon: int = HORIZON,
                             premiere: int = PREMIERE_EDITION_TEST, monde: pd.Series = None) -> pd.DataFrame:
    """
    Pour chaque cas testé (pays, édition de `premiere` à la dernière dont l'erreur est
    connue) et chaque méthode : bornes de la fourchette, CRPS, probabilité de recul, avec
    l'erreur et le recul réalisés. Une ligne par cas et par méthode.

    Avec `monde`, la méthode `METHODE_MELANGE` ne connaît, à l'édition v, que les
    récessions mondiales et l'historique mondial jusqu'à v − 2.
    """
    cas = niveaux[niveaux["horizon"] == horizon].dropna(subset=COLONNES).copy()
    derniere = int(cas["annee_millesime"].max())
    q_bas, q_haut = QUANTILES_FOURCHETTE
    lignes = []
    for v in range(premiere, derniere + 1):
        entrainement = cas[cas["annee_millesime"] <= v - horizon - 2].copy()
        test = cas[cas["annee_millesime"] == v].copy()
        if len(entrainement) < MIN_CAS_CELLULE or test.empty:
            continue
        entrainement["classe"], bornes = classes_de_croissance(entrainement["croissance_prevue_cumulee_pct"])
        test["classe"], _ = classes_de_croissance(test["croissance_prevue_cumulee_pct"], bornes)
        par_cellule = {k: c for k, c in _cellules(entrainement, ["classe", "income_group"]).items()
                       if c[2] >= MIN_CAS_CELLULE}
        par_classe = _cellules(entrainement, ["classe"])
        par_groupe = _cellules(entrainement, ["income_group"])
        par_pays = {k: c for k, c in _cellules(entrainement, ["country_code"]).items() if c[2] >= MIN_CAS_PAYS}
        ensemble = (Distribution(entrainement["erreur_niveau_vs_fmi_pct"]),
                    (entrainement["pire_croissance_realisee"] < 0).mean(), len(entrainement))
        melange = None
        if monde is not None:
            crise = periodes_en_crise(entrainement["annee_millesime"], horizon, recessions_mondiales(monde, v - 2))
            melange = (probabilite_crise_mondiale(monde, horizon, v - 2), frequences_de_recul(entrainement[crise]),
                       frequences_de_recul(entrainement[~crise]), frequences_de_recul(entrainement))

        def choix(ligne) -> dict:
            retenue = (par_cellule.get((ligne.classe, ligne.income_group)) or par_classe.get(ligne.classe) or ensemble)
            return {METHODE_RETENUE: retenue,
                    "classe de croissance": par_classe.get(ligne.classe, ensemble),
                    "groupe de revenu": par_groupe.get(ligne.income_group, ensemble),
                    "inconditionnelle": ensemble,
                    "historique du pays": par_pays.get(ligne.country_code)}

        for ligne in test.itertuples():
            y = ligne.erreur_niveau_vs_fmi_pct
            commun = dict(country_code=ligne.country_code, income_group=ligne.income_group,
                          annee_millesime=v, year=ligne.year, poids_pib=ligne.poids_pib, classe=ligne.classe,
                          erreur=y, recul=float(ligne.pire_croissance_realisee < 0))
            for methode, cellule in choix(ligne).items():
                if cellule is None:
                    continue
                distribution, frequence, _ = cellule
                lignes.append({**commun, "methode": methode, "bas": distribution.quantile(q_bas),
                               "haut": distribution.quantile(q_haut), "crps": float(distribution.crps(y)[0]),
                               "proba_recul": frequence})
            lignes.append({**commun, "methode": METHODE_FMI, "bas": np.nan, "haut": np.nan, "crps": np.nan,
                           "proba_recul": float(ligne.pire_croissance_prevue < 0)})
            if melange is not None:
                proba = probabilite_de_recul(melange, ligne.classe, ligne.income_group)[0]
                lignes.append({**commun, "methode": METHODE_MELANGE, "bas": np.nan, "haut": np.nan, "crps": np.nan,
                               "proba_recul": proba})
    previsions = pd.DataFrame(lignes)
    if not previsions.empty:
        previsions["couvert"] = previsions["erreur"].between(previsions["bas"], previsions["haut"]).astype(float)
        previsions.loc[previsions["bas"].isna(), "couvert"] = np.nan
        previsions["score_intervalle"] = score_intervalle(previsions["bas"], previsions["haut"], previsions["erreur"])
        previsions["brier"] = (previsions["proba_recul"] - previsions["recul"]) ** 2
    return previsions


def cas_communs(previsions: pd.DataFrame, methodes=METHODES) -> pd.DataFrame:
    """Les cas pour lesquels toutes les `methodes` ont une prévision : comparaison à armes égales."""
    p = previsions[previsions["methode"].isin(methodes)]
    complets = p.groupby(["country_code", "annee_millesime", "year"])["methode"].nunique() == len(methodes)
    cles = complets[complets].index
    return p.set_index(["country_code", "annee_millesime", "year"]).loc[
        lambda d: d.index.isin(cles)].reset_index()


# ------------------------------------------------------------------ synthèses

def _bootstrap(table: pd.DataFrame, statistiques, tirages: int = TIRAGES, graine: int = GRAINE) -> dict:
    """
    Intervalles à 95 % par bootstrap en blocs d'années visées : `statistiques(table)`
    retourne un dictionnaire de valeurs ; chaque tirage rééchantillonne les années.
    """
    rng = np.random.default_rng(graine)
    annees = table["year"].unique()
    blocs = {a: g for a, g in table.groupby("year")}
    tirages_valeurs = []
    for _ in range(tirages):
        echantillon = pd.concat([blocs[a] for a in rng.choice(annees, size=len(annees), replace=True)])
        tirages_valeurs.append(statistiques(echantillon))
    t = pd.DataFrame(tirages_valeurs)
    return {f"{k}_ic95_bas": t[k].quantile(0.025) for k in t} | {f"{k}_ic95_haut": t[k].quantile(0.975) for k in t}


def scores_fourchettes(previsions: pd.DataFrame, tirages: int = TIRAGES) -> pd.DataFrame:
    """
    Par méthode, sur les cas communs : couverture de l'intervalle à 80 %, largeur médiane,
    score d'intervalle moyen, CRPS moyen, avec leurs intervalles de confiance, et l'écart de
    score d'intervalle à la méthode retenue (positif : la méthode comparée fait mieux).
    Score et écart sont aussi donnés pondérés par le PIB de l'année visée : ce que vaut la
    fourchette là où se concentre l'activité, donc le trafic.
    """
    p = cas_communs(previsions)
    retenue = p[p["methode"] == METHODE_RETENUE].set_index(["country_code", "annee_millesime", "year"])
    lignes = []
    for methode in METHODES:
        m = p[p["methode"] == methode].set_index(["country_code", "annee_millesime", "year"])
        table = m.assign(ecart=retenue["score_intervalle"] - m["score_intervalle"]).reset_index()
        table["poids"] = table["poids_pib"].fillna(0)

        def stats(t):
            return {"couverture_pct": t["couvert"].mean() * 100, "score_intervalle": t["score_intervalle"].mean(),
                    "crps": t["crps"].mean(), "ecart_score_retenue": t["ecart"].mean(),
                    "score_intervalle_pondere_pib": np.average(t["score_intervalle"], weights=t["poids"]),
                    "ecart_score_retenue_pondere_pib": np.average(t["ecart"], weights=t["poids"])}
        lignes.append({"methode": methode, "retenue": methode == METHODE_RETENUE, "cas": len(table),
                       "editions_testees": f"{int(table['annee_millesime'].min())}-{int(table['annee_millesime'].max())}",
                       "largeur_mediane": (table["haut"] - table["bas"]).median(), **stats(table),
                       **_bootstrap(table, stats, tirages)})
    return pd.DataFrame(lignes).round(3)


def couverture_par_cellule(previsions: pd.DataFrame) -> pd.DataFrame:
    """Couverture de la méthode retenue par classe de croissance et groupe de revenu (tous cas)."""
    p = previsions[previsions["methode"] == METHODE_RETENUE]
    return (p.groupby(["classe", "income_group"])
            .agg(cas=("couvert", "size"), couverture_pct=("couvert", "mean"),
                 largeur_mediane=("haut", lambda h: (h - p.loc[h.index, "bas"]).median()))
            .assign(couverture_pct=lambda t: t["couverture_pct"] * 100).reset_index().round(2))


def couverture_par_periode(previsions: pd.DataFrame) -> pd.DataFrame:
    """Couverture de la méthode retenue par édition testée : où la calibration tient, où elle cède."""
    p = previsions[previsions["methode"] == METHODE_RETENUE]
    return (p.groupby("annee_millesime")
            .agg(cas=("couvert", "size"), couverture_pct=("couvert", "mean"),
                 trop_haut_pct=("erreur", lambda e: (e > p.loc[e.index, "haut"]).mean()),
                 trop_bas_pct=("erreur", lambda e: (e < p.loc[e.index, "bas"]).mean()))
            .assign(couverture_pct=lambda t: t["couverture_pct"] * 100, trop_haut_pct=lambda t: t["trop_haut_pct"] * 100,
                    trop_bas_pct=lambda t: t["trop_bas_pct"] * 100).reset_index().round(2))


def scores_recession(previsions: pd.DataFrame, tirages: int = TIRAGES) -> pd.DataFrame:
    """
    Par méthode, sur les cas communs : score de Brier et compétence face à la probabilité
    inconditionnelle (1 − Brier / Brier inconditionnel), avec intervalles de confiance, et
    gain de Brier sur la classe × groupe sans découpage des crises (positif : la méthode
    fait mieux). La trajectoire du FMI donne une probabilité de 0 ou 1. `retenue` désigne
    la méthode de production : crises mondiales à part quand elle est évaluée.
    """
    methodes = tuple(m for m in (*METHODES, METHODE_MELANGE, METHODE_FMI) if m in set(previsions["methode"]))
    production = METHODE_MELANGE if METHODE_MELANGE in methodes else METHODE_RETENUE
    p = cas_communs(previsions, methodes)
    cles = ["country_code", "annee_millesime", "year"]
    reference = p[p["methode"] == "inconditionnelle"].set_index(cles)["brier"]
    sans_decoupage = p[p["methode"] == METHODE_RETENUE].set_index(cles)["brier"]
    lignes = []
    for methode in methodes:
        m = p[p["methode"] == methode].set_index(cles)
        table = m.assign(brier_reference=reference, brier_sans_decoupage=sans_decoupage).reset_index()

        def stats(t):
            return {"brier": t["brier"].mean(), "competence": 1 - t["brier"].mean() / t["brier_reference"].mean(),
                    "gain_sur_classe_groupe": t["brier_sans_decoupage"].mean() - t["brier"].mean()}
        lignes.append({"methode": methode, "retenue": methode == production, "cas": len(table),
                       "proba_moyenne": table["proba_recul"].mean(), "frequence_observee": table["recul"].mean(),
                       **stats(table), **_bootstrap(table, stats, tirages)})
    return pd.DataFrame(lignes).round(4)


def fiabilite_recession(previsions: pd.DataFrame, methodes=(METHODE_RETENUE, METHODE_MELANGE)) -> pd.DataFrame:
    """Fiabilité des probabilités, par méthode et tranche : probabilité moyenne et fréquence observée."""
    tables = []
    for methode in methodes:
        p = previsions[previsions["methode"] == methode]
        if p.empty:
            continue
        tranche = pd.cut(p["proba_recul"], TRANCHES_PROBABILITE, include_lowest=True)
        tables.append(p.groupby(tranche, observed=True)
                      .agg(cas=("recul", "size"), proba_moyenne=("proba_recul", "mean"),
                           frequence_observee=("recul", "mean"))
                      .reset_index().rename(columns={"proba_recul": "tranche"})
                      .assign(methode=methode, tranche=lambda t: t["tranche"].astype(str)))
    if not tables:
        return pd.DataFrame(columns=["methode", "tranche", "cas", "proba_moyenne", "frequence_observee"])
    t = pd.concat(tables, ignore_index=True)
    return t[["methode", "tranche", "cas", "proba_moyenne", "frequence_observee"]].round(3)


def main():
    parser = argparse.ArgumentParser(description="Évaluation probabiliste des fourchettes et des probabilités de récession.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--tirages", type=int, default=TIRAGES)
    args = parser.parse_args()

    processed = os.path.join(args.data_dir, "processed")
    niveaux_csv = os.path.join(processed, "weo_level_evaluation_ngdp_rpch.csv")
    if not os.path.exists(niveaux_csv):
        logging.warning(f"{niveaux_csv} absent : lancer d'abord pib.evaluate_forecasts. Évaluation omise.")
        return
    monde = lire_croissance_mondiale(args.data_dir)
    if monde is None:
        logging.warning("Croissance mondiale absente : pas de probabilités avec les crises mondiales à part.")
    previsions = previsions_en_temps_reel(pd.read_csv(niveaux_csv), args.horizon, monde=monde)
    if previsions.empty:
        logging.warning("Aucune édition testable en temps réel.")
        return
    tableaux = {
        "gdp_bands_realtime_scores.csv": scores_fourchettes(previsions, args.tirages),
        "gdp_bands_realtime_coverage_by_cell.csv": couverture_par_cellule(previsions),
        "gdp_bands_realtime_coverage_by_edition.csv": couverture_par_periode(previsions),
        "recession_probability_realtime_scores.csv": scores_recession(previsions, args.tirages),
        "recession_probability_reliability.csv": fiabilite_recession(previsions),
    }
    for nom, table in tableaux.items():
        table.to_csv(os.path.join(processed, nom), index=False, encoding="utf-8-sig")
    logging.info(f"Fourchettes en temps réel, horizon {args.horizon} :\n"
                 + tableaux["gdp_bands_realtime_scores.csv"][["methode", "cas", "couverture_pct", "couverture_pct_ic95_bas",
                     "couverture_pct_ic95_haut", "largeur_mediane", "score_intervalle", "crps"]].to_string(index=False))
    logging.info("Probabilités de récession en temps réel :\n"
                 + tableaux["recession_probability_realtime_scores.csv"][["methode", "cas", "brier", "competence",
                     "competence_ic95_bas", "competence_ic95_haut", "gain_sur_classe_groupe",
                     "gain_sur_classe_groupe_ic95_bas", "gain_sur_classe_groupe_ic95_haut", "proba_moyenne",
                     "frequence_observee"]].to_string(index=False))


if __name__ == "__main__":
    main()
