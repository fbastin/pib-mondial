#!/usr/bin/env python3
"""
scenarios.py
------------
Scénarios de PIB par habitant et de population pour la prévision du trafic aérien
(projet Aéroports de Montréal, méthode de Kenza), jusqu'en `ANNEE_FIN`.

Jusqu'à l'horizon du FMI, cinq scénarios de PIB en volume par habitant, tirés des erreurs
passées du FMI (voir `evaluate_forecasts.fourchettes_projections`, à chaque horizon) :

- `central_fmi` : la trajectoire du FMI, telle que raccordée par le pipeline ;
- `central_corrige` : divisée par (1 + erreur de niveau médiane passée) ;
- `bas`, `haut` : bornes de la fourchette à 80 % ;
- `bas_groupe_seul`, `haut_groupe_seul` : les mêmes bornes tirées du seul groupe de revenu, publiées
  pour comparaison (éprouvées en temps réel, les deux méthodes se valent hors de la Chine et de
  l'Inde d'avant 2008) ;
- `crise_mondiale` : divisée par (1 + erreur médiane des périodes passées en crise mondiale).

Au-delà, les scénarios centraux et de crise suivent la croissance du PIB potentiel par
habitant du scénario de référence de l'OCDE (`SCENARIO_OCDE_CENTRAL`, Perspectives
économiques n° 117) : celle du pays, à défaut de sa région, à défaut du monde. Le niveau
atteint à l'horizon du FMI est conservé : après une crise, pas de rattrapage (voir
`docs/cas_crise_2008.md`).

`bas` et `haut` gardent, autour de la trajectoire `central_fmi`, la fourchette du pays à
l'horizon du FMI, puis l'élargissent comme se sont élargies les erreurs passées des
trajectoires du FMI prolongées, pour son groupe de revenu (`pib.long_terme`). Sans ces
fourchettes de long terme, ils suivent à défaut le scénario de l'OCDE le moins et le plus
favorable pour la zone, qui ne diffèrent que par le climat et la transition énergétique.

`bas_elargi`, `haut_elargi` : pour les pays à revenu élevé, une variante de ces bornes au-delà
de l'horizon du FMI (`elargir`), publiée à côté. Deux ajustements, en logarithme du rapport
à `central_fmi` :

- **le milieu de la fourchette est figé** au-delà du dernier horizon où la loi de long terme
  est ajustée (16 ans) : le décalage sous la trajectoire centrale, l'optimisme passé du FMI
  prolongé, n'est plus extrapolé. Il venait des éditions 1999-2009, toutes traversées par la
  crise de 2008 ; les éditions 2010-2014 montrent un biais plus faible ;
- **la demi-largeur ne descend pas sous un plancher** tiré de Müller, Stock et Watson
  (2022) : leur intervalle à 67 % pour la croissance moyenne des États-Unis sur 50 ans, de
  0,6 à 2,7 % par an, donne un écart-type de la croissance moyenne d'environ 1,1 point,
  soit, à l'horizon h, un écart-type du logarithme du niveau d'au moins 0,011 · h. Ce
  plancher suppose la croissance moyenne au moins aussi incertaine sur moins de 50 ans que
  sur 50, comme dans leur modèle entre 50 et 100 ans.

Pour les autres pays, la variante reprend `bas` et `haut`.

Population : celle du pipeline (Banque Mondiale, puis FMI jusqu'à son horizon), prolongée
par la croissance de la variante médiane de l'ONU (World Population Prospects 2024) ;
variantes basse et haute tirées de ses intervalles de prédiction à 80 %. Ces intervalles
sont trop étroits : appliqués aux révisions passées de l'ONU, ils n'en contiennent que 19 %
à 1 an, 54 % à 20 ans. Les variantes `…_calibree` les élargissent pour en contenir 80 % (`pib.population`,
`population_calibrated_bounds.csv`) ; sans ce fichier, elles reprennent celles de l'ONU.

Sortie, pour le projet trafic, sous un nom qui ne change pas avec l'horizon :

- `scenarios_pib_population.csv` : une ligne par pays, année et scénario ;
- `scenarios_pib_population_pays.csv` : par pays, zone de croissance retenue, bornes et
  probabilités de recul d'ici l'horizon du FMI.

Les données de l'OCDE et de l'ONU sont téléchargées une fois dans `data/raw/scenarios_long_terme/`
(non versionné).

    python -m pib.scenarios --data-dir data
"""

import os
import json
import time
import logging
import argparse

from statistics import NormalDist

import numpy as np
import pandas as pd
import requests

from pib.gdp_pipeline import unified_csv_path
from pib.http_utils import get_json
from pib.long_terme import ANNEES_MIN, FICHIER_BANDES, H_FMI, TOUS, elargissement

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ANNEE_FIN = 2050
CACHE = os.path.join("data", "raw", "scenarios_long_terme")

OCDE = ("https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO_LTB@DF_EO_LTB,1.0/"
        ".GDPVTRD_CAP..A")
FICHIER_OCDE = "ocde_eo117_long_terme_pib_potentiel_par_habitant.csv"
SCENARIO_OCDE_CENTRAL = "BAU1"

WPP = ("https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/"
       "WPP2024_TotalPopulationBySex.csv.gz")
FICHIER_WPP = "WPP2024_TotalPopulationBySex.csv.gz"
VARIANTES_WPP = {"centrale": "Medium", "basse": "Lower 80 PI", "haute": "Upper 80 PI"}
FICHIER_BORNES_POPULATION = "population_calibrated_bounds.csv"

# Régions de la Banque Mondiale -> agrégats de l'OCDE, pour les pays qu'elle ne projette pas
REGIONS_OCDE = {"NAC": "A2", "LCN": "A9", "ECS": "E_S4", "SSF": "F6", "MEA": "F98", "EAS": "O_S2_S8", "SAS": "S7"}
MONDE_OCDE = "W"

SCENARIOS = ("central_fmi", "central_corrige", "bas", "haut", "crise_mondiale", "bas_groupe_seul", "haut_groupe_seul",
             "bas_elargi", "haut_elargi")
BORNES = {"bas": "bas", "haut": "haut", "bas_groupe_seul": "bas", "haut_groupe_seul": "haut",
          "bas_elargi": "bas", "haut_elargi": "haut"}
ELARGIS = {"bas_elargi": "bas", "haut_elargi": "haut"}

# Variante élargie, pour les pays à revenu élevé : plancher de l'écart-type du logarithme du
# niveau, par année d'horizon, tiré de l'intervalle à 67 % de Müller, Stock et Watson (2022)
# pour la croissance moyenne des États-Unis sur 50 ans (0,6 à 2,7 % par an)
GROUPE_ELARGI = "HIC"
ECART_TYPE_ANNUEL_MSW = (0.027 - 0.006) / (2 * NormalDist().inv_cdf(0.835))
Z80 = NormalDist().inv_cdf(0.9)


# ------------------------------------------------------------------ sources

def telecharger(url: str, chemin: str, params: dict = None, tentatives: int = 3) -> str:
    """Télécharge `url` dans `chemin` s'il n'y est pas déjà ; lève `RuntimeError` en cas d'échec."""
    if os.path.exists(chemin):
        return chemin
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    for essai in range(1, tentatives + 1):
        try:
            r = requests.get(url, params=params, timeout=600)
            r.raise_for_status()
            with open(chemin + ".partiel", "wb") as f:
                f.write(r.content)
            os.replace(chemin + ".partiel", chemin)
            logging.info(f"-> {os.path.basename(chemin)} téléchargé ({len(r.content) / 1e6:.1f} Mo).")
            return chemin
        except requests.RequestException as e:
            logging.warning(f"{url} : tentative {essai} échouée ({e}).")
            time.sleep(5)
    raise RuntimeError(f"{url} injoignable.")


def lire_ocde(chemin: str) -> pd.DataFrame:
    """PIB potentiel par habitant de l'OCDE : zone, scenario, year, valeur."""
    t = pd.read_csv(chemin)
    return (t[["REF_AREA", "SCENARIO", "TIME_PERIOD", "OBS_VALUE"]]
            .rename(columns={"REF_AREA": "zone", "SCENARIO": "scenario", "TIME_PERIOD": "year", "OBS_VALUE": "valeur"})
            .dropna())


def lire_wpp(chemin: str) -> pd.DataFrame:
    """Population de l'ONU par pays (ISO3), année et variante de `VARIANTES_WPP` : millions."""
    t = pd.read_csv(chemin, usecols=["ISO3_code", "Variant", "Time", "PopTotal"], low_memory=False)
    inverse = {v: k for k, v in VARIANTES_WPP.items()}
    t = t[t["Variant"].isin(inverse) & t["ISO3_code"].notna()]
    return (t.assign(variante=t["Variant"].map(inverse), population=t["PopTotal"] / 1000)
            .rename(columns={"ISO3_code": "country_code", "Time": "year"})[["country_code", "year", "variante", "population"]])


def regions_banque_mondiale() -> dict:
    """Code ISO3 -> région de la Banque Mondiale (NAC, LCN, ECS, SSF, MEA, EAS, SAS)."""
    reponse = get_json("https://api.worldbank.org/v2/country", params={"format": "json", "per_page": 500})
    return {p["id"]: p["region"]["id"] for p in reponse[1] if p.get("region", {}).get("id") not in (None, "NA")}


# ------------------------------------------------------------------ construction

def zone_de_croissance(code: str, region: str, zones: set) -> tuple:
    """Zone de l'OCDE dont suivre la croissance : le pays, à défaut sa région, à défaut le monde."""
    if code in zones:
        return code, "pays"
    if REGIONS_OCDE.get(region) in zones:
        return REGIONS_OCDE[region], "région"
    return MONDE_OCDE, "monde"


def croissances_long_terme(ocde: pd.DataFrame, zone: str, debut: int, fin: int) -> dict:
    """
    Taux de croissance annuels (rapports) du PIB potentiel par habitant de `zone`, de `debut`
    + 1 à `fin` : pour le scénario central de l'OCDE, et pour les scénarios le moins et le
    plus favorables sur la période (`bas`, `haut`).
    """
    z = ocde[ocde["zone"] == zone].pivot_table(index="year", columns="scenario", values="valeur")
    z = z.reindex(range(debut, fin + 1))
    rapports = (z / z.shift(1)).loc[debut + 1:fin]
    cumul = rapports.prod()
    return {"central": rapports[SCENARIO_OCDE_CENTRAL], "bas": rapports[cumul.idxmin()],
            "haut": rapports[cumul.idxmax()], "scenario_bas": cumul.idxmin(), "scenario_haut": cumul.idxmax()}


def facteurs_par_scenario(bandes: pd.DataFrame) -> pd.DataFrame:
    """
    Facteur appliqué à la trajectoire du FMI, par pays, année et scénario, à partir des
    fourchettes à chaque horizon : 1 / (1 + erreur médiane), bornes, 1 / (1 + erreur de crise).
    """
    b = bandes.copy()
    crise = b["erreur_niveau_mediane_si_crise_mondiale_pct"].fillna(b["erreur_niveau_mediane_pct"]) \
        if "erreur_niveau_mediane_si_crise_mondiale_pct" in b.columns else b["erreur_niveau_mediane_pct"]
    # Variante : bornes du seul groupe de revenu (à défaut, celles de la méthode retenue)
    for borne in ("borne_basse_pct", "borne_haute_pct"):
        if f"{borne}_groupe_seul" not in b.columns:
            b[f"{borne}_groupe_seul"] = b[borne]
    return pd.DataFrame({
        "country_code": b["country_code"], "year": b["year"],
        "central_fmi": 1.0,
        "central_corrige": 1 / (1 + b["erreur_niveau_mediane_pct"] / 100),
        "bas": 1 + b["borne_basse_pct"] / 100,
        "haut": 1 + b["borne_haute_pct"] / 100,
        "crise_mondiale": 1 / (1 + crise / 100),
        "bas_groupe_seul": 1 + b["borne_basse_pct_groupe_seul"] / 100,
        "haut_groupe_seul": 1 + b["borne_haute_pct_groupe_seul"] / 100,
        "bas_elargi": 1 + b["borne_basse_pct"] / 100,
        "haut_elargi": 1 + b["borne_haute_pct"] / 100,
    })


def horizon_ajuste(bandes_long_terme: pd.DataFrame, groupe: str):
    """Dernier horizon où la loi de long terme du groupe est ajustée (assez d'années d'édition), ou None."""
    if bandes_long_terme is None or "annees_edition" not in bandes_long_terme.columns:
        return None
    b = bandes_long_terme[(bandes_long_terme["groupe"] == groupe) & (bandes_long_terme["annees_edition"] >= ANNEES_MIN)]
    return int(b["horizon"].max()) if not b.empty else None


def elargir(log_bas: np.ndarray, log_haut: np.ndarray, horizons: np.ndarray, h_ajuste) -> tuple:
    """
    Variante élargie de bornes (logarithme du rapport à la trajectoire centrale), aux
    horizons croissants `horizons` comptés depuis l'édition : au-delà de `h_ajuste`, milieu
    figé à sa valeur au dernier horizon qui ne le dépasse pas ; demi-largeur d'au moins
    Z80 · ECART_TYPE_ANNUEL_MSW · h. Rend (log_bas, log_haut).
    """
    log_bas, log_haut, horizons = (np.asarray(x, dtype=float) for x in (log_bas, log_haut, horizons))
    milieu, demi = (log_bas + log_haut) / 2, (log_haut - log_bas) / 2
    if h_ajuste is not None and (horizons <= h_ajuste).any() and (horizons > h_ajuste).any():
        milieu = np.where(horizons > h_ajuste, milieu[horizons <= h_ajuste][-1], milieu)
    demi = np.maximum(demi, Z80 * ECART_TYPE_ANNUEL_MSW * horizons)
    return milieu - demi, milieu + demi


def construire_scenarios(unifie: pd.DataFrame, bandes: pd.DataFrame, ocde: pd.DataFrame, wpp: pd.DataFrame,
                         regions: dict, annee_fin: int = ANNEE_FIN, bandes_long_terme: pd.DataFrame = None,
                         bornes_population: pd.DataFrame = None) -> tuple:
    """
    Trajectoires par pays, année et scénario, de la première année de la série à `annee_fin`,
    et table par pays (zone de croissance, bornes de long terme retenues). Voir le module.
    `bandes_long_terme` : fourchettes lissées de `pib.long_terme` ; à défaut, `bas` et `haut`
    suivent les scénarios extrêmes de l'OCDE. `bornes_population` : bornes calibrées de
    `pib.population`, en rapport à la médiane de l'ONU ; à défaut, celles de l'ONU.
    """
    pays = unifie[~unifie["is_aggregate"].astype(bool)].sort_values(["country_code", "year"])
    derniere_obs = int(pays.loc[~pays["is_forecast"].astype(bool), "year"].max())
    horizon_fmi = int(pays["year"].max())
    facteurs = facteurs_par_scenario(bandes).set_index(["country_code", "year"])
    zones = set(ocde["zone"])
    wpp_large = wpp.pivot_table(index=["country_code", "year"], columns="variante", values="population")
    calibrees = (bornes_population.set_index(["country_code", "year"])[["calibree_basse", "calibree_haute"]]
                 if bornes_population is not None else None)

    lignes, fiches = [], []
    for code, serie in pays.groupby("country_code"):
        serie = serie.set_index("year")
        hab = serie["GDP_Real_Per_Capita_USD_2015"]
        pop = serie["Population_Millions"]
        if pd.isna(hab.get(horizon_fmi)) or pd.isna(pop.get(horizon_fmi)):
            continue
        zone, niveau_zone = zone_de_croissance(code, regions.get(code), zones)
        croissance = croissances_long_terme(ocde, zone, horizon_fmi, annee_fin)

        # Population : pipeline jusqu'à l'horizon du FMI, puis croissance médiane de l'ONU ;
        # variantes : rapport de la variante à la médiane de l'ONU, appliqué à la centrale
        annees = range(int(serie.index.min()), annee_fin + 1)
        population = pd.DataFrame(index=annees, columns=[*VARIANTES_WPP, "basse_calibree", "haute_calibree"],
                                  dtype=float)
        population.loc[pop.index, "centrale"] = pop.values
        onu = wpp_large.xs(code, level="country_code") if code in wpp_large.index.get_level_values(0) else None
        if onu is not None and {"centrale", "basse", "haute"} <= set(onu.columns):
            onu = onu.reindex(annees)
            for a in range(horizon_fmi + 1, annee_fin + 1):
                population.loc[a, "centrale"] = population.loc[a - 1, "centrale"] * onu.loc[a, "centrale"] / onu.loc[a - 1, "centrale"]
            ecart = onu[["basse", "haute"]].div(onu["centrale"], axis=0)
            ecart.loc[ecart.index <= derniere_obs] = 1.0     # le passé observé n'a pas de variante
            population["basse"] = population["centrale"] * ecart["basse"].fillna(1.0)
            population["haute"] = population["centrale"] * ecart["haute"].fillna(1.0)
        else:
            population["basse"] = population["haute"] = population["centrale"]
        calibree = (calibrees.xs(code, level="country_code").reindex(annees)
                    if calibrees is not None and code in calibrees.index.get_level_values(0) else None)
        if calibree is not None:
            calibree.loc[calibree.index <= derniere_obs] = 1.0
            population["basse_calibree"] = population["centrale"] * calibree["calibree_basse"].fillna(1.0)
            population["haute_calibree"] = population["centrale"] * calibree["calibree_haute"].fillna(1.0)
        else:
            population["basse_calibree"], population["haute_calibree"] = population["basse"], population["haute"]

        groupe = serie["income_group"].iloc[0] if "income_group" in serie else None
        central = pd.Series({horizon_fmi: float(hab[horizon_fmi])})
        for a in range(horizon_fmi + 1, annee_fin + 1):
            central[a] = central[a - 1] * croissance["central"].get(a, np.nan)
        elargie = groupe == GROUPE_ELARGI and bandes_long_terme is not None
        trajectoires = {}
        for scenario in SCENARIOS:
            niveau = hab.copy().astype(float)
            for a in range(derniere_obs + 1, horizon_fmi + 1):
                f = facteurs[scenario].get((code, a), 1.0)
                niveau[a] = hab[a] * (1.0 if pd.isna(f) else f)
            if scenario in ELARGIS and elargie:
                # Bornes retenues au-delà de l'horizon du FMI, élargies (voir `elargir`)
                annees_lt = np.arange(horizon_fmi + 1, annee_fin + 1)
                c = central.reindex(annees_lt).to_numpy()
                lb, lh = elargir(np.log(trajectoires["bas"].reindex(annees_lt).to_numpy() / c),
                                 np.log(trajectoires["haut"].reindex(annees_lt).to_numpy() / c),
                                 H_FMI + annees_lt - horizon_fmi, horizon_ajuste(bandes_long_terme, groupe))
                for a, x in zip(annees_lt, c * np.exp(lb if ELARGIS[scenario] == "bas" else lh)):
                    niveau[a] = x
            elif scenario in BORNES and bandes_long_terme is not None:
                # Fourchette du pays à l'horizon du FMI, élargie comme les erreurs passées
                ecart = niveau[horizon_fmi] / hab[horizon_fmi]
                for a in range(horizon_fmi + 1, annee_fin + 1):
                    f_bas, f_haut = elargissement(bandes_long_terme, groupe, H_FMI, H_FMI + a - horizon_fmi)
                    niveau[a] = central[a] * ecart * (f_bas if BORNES[scenario] == "bas" else f_haut)
            else:
                voie = {"bas": croissance["bas"], "haut": croissance["haut"]}.get(BORNES.get(scenario), croissance["central"])
                for a in range(horizon_fmi + 1, annee_fin + 1):
                    niveau[a] = niveau[a - 1] * voie.get(a, np.nan)
            trajectoires[scenario] = niveau
            for a in annees:
                periode = ("observé" if a <= derniere_obs else "projection du FMI" if a <= horizon_fmi else "long terme")
                lignes.append({"country_code": code, "country_name": serie["country_name"].iloc[0],
                               "income_group": serie["income_group"].iloc[0] if "income_group" in serie else None,
                               "year": a, "periode": periode, "scenario": scenario,
                               "pib_reel_par_habitant_usd_2015": niveau.get(a, np.nan),
                               "population_millions_centrale": population.loc[a, "centrale"],
                               "population_millions_basse": population.loc[a, "basse"],
                               "population_millions_haute": population.loc[a, "haute"],
                               "population_millions_basse_calibree": population.loc[a, "basse_calibree"],
                               "population_millions_haute_calibree": population.loc[a, "haute_calibree"],
                               "pib_par_habitant_usd_courants": (serie["GDP_Per_Capita_USD"].get(a, np.nan)
                                                                 if scenario == "central_fmi" and a <= horizon_fmi else np.nan)})
        if bandes_long_terme is not None:
            source_bornes = f"erreurs passées du FMI prolongé ({groupe if groupe in set(bandes_long_terme['groupe']) else TOUS})"
        else:
            source_bornes = f"scénarios de l'OCDE {croissance['scenario_bas']} et {croissance['scenario_haut']}"
        fiches.append({"country_code": code, "country_name": serie["country_name"].iloc[0],
                       "zone_croissance_long_terme": zone, "niveau_zone": niveau_zone,
                       "bornes_long_terme": source_bornes,
                       "bornes_elargies": bool(elargie),
                       "population_onu_disponible": onu is not None,
                       "population_bornes_calibrees": calibree is not None})
    table = pd.DataFrame(lignes)
    table["pib_reel_milliards_usd_2015"] = table["pib_reel_par_habitant_usd_2015"] * table["population_millions_centrale"] / 1000
    return table, pd.DataFrame(fiches)


def main():
    parser = argparse.ArgumentParser(description="Scénarios de PIB par habitant et de population pour le projet trafic.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--annee-fin", type=int, default=ANNEE_FIN)
    parser.add_argument("--cache", type=str, default=CACHE)
    args = parser.parse_args()

    processed = os.path.join(args.data_dir, "processed")
    bandes_csv = os.path.join(processed, "gdp_projection_bands_by_horizon.csv")
    if not os.path.exists(bandes_csv):
        logging.warning(f"{bandes_csv} absent : lancer d'abord pib.evaluate_forecasts. Scénarios omis.")
        return
    try:
        ocde = lire_ocde(telecharger(OCDE, os.path.join(args.cache, FICHIER_OCDE), params={"format": "csvfile"}))
        wpp = lire_wpp(telecharger(WPP, os.path.join(args.cache, FICHIER_WPP)))
        regions = regions_banque_mondiale()
    except RuntimeError as e:
        logging.error(f"{e} Scénarios de long terme omis.")
        return

    unifie = pd.read_csv(unified_csv_path(args.data_dir))
    chemin_long_terme = os.path.join(processed, FICHIER_BANDES)
    long_terme = pd.read_csv(chemin_long_terme) if os.path.exists(chemin_long_terme) else None
    if long_terme is None:
        logging.warning(f"{chemin_long_terme} absent (pib.long_terme) : au-delà de l'horizon du FMI, "
                        "bornes tirées des scénarios extrêmes de l'OCDE.")
    chemin_population = os.path.join(processed, FICHIER_BORNES_POPULATION)
    bornes_population = pd.read_csv(chemin_population) if os.path.exists(chemin_population) else None
    if bornes_population is None:
        logging.warning(f"{chemin_population} absent (pib.population) : variantes de population calibrées "
                        "= celles de l'ONU.")
    table, fiches = construire_scenarios(unifie, pd.read_csv(bandes_csv), ocde, wpp, regions, args.annee_fin,
                                         bandes_long_terme=long_terme, bornes_population=bornes_population)

    # Par pays : bornes et probabilités de recul à l'horizon du FMI
    bandes_csv_final = os.path.join(processed, "gdp_projection_bands.csv")
    if os.path.exists(bandes_csv_final):
        colonnes = [c for c in ("country_code", "horizon", "borne_basse_pct", "borne_haute_pct", "erreur_niveau_mediane_pct",
                                "erreur_niveau_mediane_si_crise_mondiale_pct", "probabilite_recul_pct",
                                "probabilite_recul_si_crise_mondiale_pct", "probabilite_recul_hors_crise_mondiale_pct",
                                "probabilite_crise_mondiale_pct", "pire_annee_mediane_pct")
                    if c in pd.read_csv(bandes_csv_final, nrows=0).columns]
        fiches = fiches.merge(pd.read_csv(bandes_csv_final, usecols=colonnes), on="country_code", how="left")
    table.round(4).to_csv(os.path.join(processed, "scenarios_pib_population.csv"), index=False, encoding="utf-8-sig")
    fiches.to_csv(os.path.join(processed, "scenarios_pib_population_pays.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(processed, "scenarios_pib_population_sources.json"), "w", encoding="utf-8") as f:
        json.dump({"ocde": {"flux": "OECD.ECO.MAD:DSD_EO_LTB@DF_EO_LTB(1.0)", "mesure": "GDPVTRD_CAP",
                            "scenario_central": SCENARIO_OCDE_CENTRAL, "url": OCDE},
                   "onu": {"source": "World Population Prospects 2024", "variantes": VARIANTES_WPP, "url": WPP},
                   "population_calibree": (
                       {"methode": "bornes à 80 % de l'ONU élargies pour contenir 80 % des erreurs passées de ses "
                                   "révisions 1998-2022, par classe de taille et horizon",
                        "fichier": FICHIER_BORNES_POPULATION}
                       if bornes_population is not None else {"methode": "bornes de l'ONU, faute de calibration"}),
                   "bornes_long_terme": (
                       {"methode": "fourchette du pays à l'horizon du FMI, élargie comme les erreurs passées des "
                                   "trajectoires du FMI prolongées par la dérive, par groupe de revenu",
                        "fichier": FICHIER_BANDES}
                       if long_terme is not None else
                       {"methode": "scénarios de l'OCDE le moins et le plus favorables pour la zone"}),
                   "bornes_elargies": {
                       "groupe": GROUPE_ELARGI,
                       "methode": "au-delà de l'horizon du FMI, milieu de la fourchette figé au dernier horizon "
                                  "ajusté de la loi de long terme, demi-largeur d'au moins Z80 · σ · h",
                       "ecart_type_annuel": round(ECART_TYPE_ANNUEL_MSW, 5),
                       "source": "Müller, Stock et Watson (2022), intervalle à 67 % de la croissance moyenne "
                                 "des États-Unis sur 50 ans, 0,6 à 2,7 % par an"},
                   "annee_fin": args.annee_fin}, f, indent=2, ensure_ascii=False)
    apercu = table[(table["country_code"].isin(["CAN", "USA"])) & (table["year"].isin([2024, 2031, 2040, args.annee_fin]))]
    logging.info(f"Scénarios pour {table['country_code'].nunique()} pays, jusqu'en {args.annee_fin} :\n"
                 + apercu.pivot_table(index=["country_code", "year"], columns="scenario",
                                      values="pib_reel_par_habitant_usd_2015").round(0).to_string())


if __name__ == "__main__":
    main()
