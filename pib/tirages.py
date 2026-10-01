#!/usr/bin/env python3
"""
tirages.py
----------
Trajectoires conjointes du PIB par habitant de tous les pays, pour agréger des marchés.

Les scénarios `bas` et `haut` sont calculés pays par pays. Les erreurs des pays sont
pourtant liées, surtout en crise mondiale. Une prévision de trafic qui additionne
des marchés (Canada, États-Unis, Europe…) ne peut donc pas prendre la borne basse de chacun
et l'appeler « scénario bas à 80 % » : cette combinaison n'a pas de probabilité connue.

Chaque tirage rejoue une édition passée du WEO (une des `editions_eligibles`), par le
rééchantillonnage de Schaake (Clark et al., 2004) :

1. **Position de chaque pays dans l'édition rejouée.** Pour chaque horizon h, c'est le
   rang u de son erreur de niveau parmi les projections comparables de l'époque. Les
   cellules sont celles des fourchettes (classe de croissance × groupe de revenu connu à
   l'édition, à défaut classe, à défaut ensemble) ; u vaut (rang − ½) / effectif. Pays
   absent de l'édition : médiane des positions des pays de son groupe de revenu, à défaut
   de tous les pays. On garde ainsi la part commune du choc.
2. **Rang de l'édition dans l'histoire du pays.** Les n éditions sont rangées par u
   croissant, pays par pays : l'édition de rang k reçoit le quantile (k − ½) / n de la
   fourchette actuelle du pays (sa cellule d'aujourd'hui). Chaque pays garde ainsi
   exactement sa fourchette publiée, 10 % des tirages sous `bas`, 10 % au-dessus de `haut`,
   et la dépendance entre pays est celle des rangs. Prendre directement le quantile u
   ferait entrer le biais propre de chaque pays, que la calibration écarte : les
   fourchettes tirées de l'histoire d'un seul pays n'en contiennent que 58,5 %. Le réalisé
   vaut la projection divisée par (1 + erreur).
3. **Au-delà de l'horizon du FMI :** chaque tirage garde sa position relative dans la
   fourchette des scénarios. En logarithme, z = (log r − milieu) / demi-largeur à
   l'horizon du FMI, où r est le rapport à `central_fmi` ; puis log r(t) = milieu(t)
   + z · demi-largeur(t), avec la fourchette `bas`–`haut` de l'année t.

**Population.** Chaque tirage porte aussi une population par pays. Les erreurs passées de
population (révisions de l'ONU) et de PIB (éditions du FMI) ne sont pas liées : corrélation de
rang de 0,00 à 0,04 entre pays comme dans le temps, aux mêmes horizons. La population se tire
donc à part, de la même façon que le PIB :

1. **Position de chaque pays dans une révision passée de l'ONU** (`pib.population`,
   `population_projection_positions.csv`) : à 5 ans, son écart en demi-largeurs des bornes
   de l'ONU, rangé parmi tous les cas passés de sa classe de taille.
2. **Rang de la révision dans l'histoire du pays,** d'où un niveau (k − ½) / R, R révisions.
3. **Position dans la fourchette calibrée :** z = Φ⁻¹(niveau) / Φ⁻¹(0,9), gardée à toutes les
   années, en demi-largeurs de la fourchette calibrée du pays (`population_millions_…_calibree`).
   Chaque pays a ainsi 10 % de tirages sous la borne basse calibrée, 10 % au-dessus de la haute.
4. **Les révisions sont attribuées aux tirages** par blocs consécutifs, dans l'ordre
   chronologique (6 éditions du WEO par révision) : un choix sans conséquence, puisque les deux
   erreurs sont indépendantes. Une même révision donne la même population à ses 6 tirages.
5. **PIB par habitant cohérent avec la population tirée** (`par_habitant`). Les erreurs du FMI
   portent sur le PIB total, indépendant de la population : le PIB total d'un tirage est la
   trajectoire centrale multipliée par son écart, et le PIB par habitant vaut ce total divisé
   par la population tirée. Une population plus forte que prévu abaisse donc le PIB par
   habitant. Par pays, celui-ci est un peu plus dispersé que `bas`–`haut`, qui ignorent
   l'incertitude de la population.

Une même édition fournit les positions de tous les horizons : chaque tirage est une
trajectoire cohérente dans le temps, et la dépendance entre pays est celle qu'a connue cet
épisode. Pour les pays riches, les éditions de 2005 à 2008 rejouent la crise financière,
celles de 1995-1996 l'essor de la fin des années 1990.

Sorties dans `data/processed/` :

- `scenarios_pib_tirages.csv` : tirage (édition rejouée), pays, année, PIB en volume par habitant,
  population (millions), révision de l'ONU dont vient sa position, et PIB en volume total ;
- `scenarios_pib_tirages_controle.csv` : par pays (et pour quelques agrégats), part des
  tirages sous `bas` et au-dessus de `haut`, et quantiles de l'agrégat comparés à la somme
  des bornes.

    python -m pib.tirages --data-dir data
"""

import os
import logging
import argparse

import numpy as np
import pandas as pd

from statistics import NormalDist

from pib import groupes_revenu
from pib.evaluate_forecasts import MIN_CAS_CELLULE, classes_de_croissance
from pib.population import FICHIER_POSITIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PAYS_MIN = 100           # une édition rejouée doit couvrir au moins ce nombre de pays au dernier horizon
COLONNE = "erreur_niveau_vs_fmi_pct"
FICHIER = "scenarios_pib_tirages.csv"
FICHIER_CONTROLE = "scenarios_pib_tirages_controle.csv"
TIRAGES_BOOTSTRAP = 1000
Z80 = NormalDist().inv_cdf(0.9)
GRAINE = 2026

# Agrégats contrôlés : la somme des bornes de chaque pays contre les quantiles des tirages
AGREGATS = {
    "G7": ["USA", "JPN", "DEU", "GBR", "FRA", "ITA", "CAN"],
    "Amérique du Nord": ["USA", "CAN", "MEX"],
    "Canada, États-Unis, France, Royaume-Uni": ["CAN", "USA", "FRA", "GBR"],
}


# ------------------------------------------------------------------ positions et quantiles

def cle_de_cellule(classe, groupe, cellules: set, classes: set) -> tuple:
    """Cellule retenue, comme pour les fourchettes : (classe, groupe), à défaut classe, à défaut ensemble."""
    if pd.notna(classe) and (classe, groupe) in cellules:
        return ("cellule", classe, groupe)
    if pd.notna(classe) and classe in classes:
        return ("classe", classe, None)
    return ("ensemble", None, None)


def cellules_du_passe(passe: pd.DataFrame) -> tuple:
    """
    Pour un horizon : les cas passés avec leur classe, leur cellule retenue (`cle`) et leur
    position u dans celle-ci ; les erreurs de chaque cellule possible, pour les quantiles.
    """
    p = passe.copy()
    p["classe"], _ = classes_de_croissance(p["croissance_prevue_cumulee_pct"])
    taille = p.groupby(["classe", "income_group"]).size()
    cellules = set(taille[taille >= MIN_CAS_CELLULE].index)
    classes = set(p["classe"].dropna())
    p["cle"] = [cle_de_cellule(c, g, cellules, classes) for c, g in zip(p["classe"], p["income_group"])]
    rang = p.groupby("cle")[COLONNE].rank(method="average")
    p["u"] = (rang - 0.5) / p.groupby("cle")[COLONNE].transform("size")

    erreurs = {("ensemble", None, None): p[COLONNE].to_numpy()}
    for c in classes:
        erreurs[("classe", c, None)] = p.loc[p["classe"] == c, COLONNE].to_numpy()
    for c, g in cellules:
        erreurs[("cellule", c, g)] = p.loc[(p["classe"] == c) & (p["income_group"] == g), COLONNE].to_numpy()
    return p, erreurs, cellules, classes


def editions_eligibles(niveaux: pd.DataFrame, horizon: int, pays_min: int = PAYS_MIN) -> list:
    """Éditions dont l'erreur au dernier horizon des fourchettes est connue pour au moins `pays_min` pays."""
    n = niveaux[niveaux["horizon"] == horizon].dropna(subset=[COLONNE]).groupby("vintage")["country_code"].nunique()
    return sorted(n[n >= pays_min].index)


def positions(passe: pd.DataFrame, editions: list, pays: pd.Series) -> pd.DataFrame:
    """
    Position u (pays actuels × éditions rejouées) pour un horizon ; à défaut, médiane des
    positions des pays de même groupe de revenu actuel (`pays` : groupe par code) dans
    l'édition, puis ½.
    """
    p = passe[passe["vintage"].isin(editions)]
    large = p.pivot_table(index="country_code", columns="vintage", values="u").reindex(index=pays.index, columns=editions)
    mediane = large.groupby(pays).transform("median")
    return large.fillna(mediane).fillna(large.median()).fillna(0.5)


def niveaux_de_quantile(u: pd.DataFrame) -> pd.DataFrame:
    """Niveau (k − ½) / n de chaque édition, k étant son rang par u croissant dans l'histoire du pays."""
    return (u.rank(axis=1, method="first") - 0.5) / u.shape[1]


# ------------------------------------------------------------------ tirages

def _niveaux(scenarios: pd.DataFrame, scenario: str) -> pd.DataFrame:
    return scenarios[scenarios["scenario"] == scenario].pivot_table(
        index="country_code", columns="year", values="pib_reel_par_habitant_usd_2015")


def rapports_jusqu_a_l_horizon(niveaux: pd.DataFrame, bandes: pd.DataFrame, editions: list) -> dict:
    """
    Année → rapport réalisé / projeté (pays × éditions rejouées), aux horizons des
    fourchettes. L'erreur tirée est le quantile de la cellule actuelle du pays, au niveau
    donné par le rang de l'édition (`niveaux_de_quantile`), avec l'interpolation des
    fourchettes : un tirage tombe sous la borne basse quand son niveau dépasse 0,9.
    """
    pays = bandes.drop_duplicates("country_code").set_index("country_code")["income_group"]
    annee_edition = int(bandes["year"].min())
    rapports = {}
    for h in sorted(bandes["horizon"].unique()):
        passe = niveaux[niveaux["horizon"] == h].dropna(subset=[COLONNE, "croissance_prevue_cumulee_pct"])
        passe, erreurs, cellules, classes = cellules_du_passe(passe)
        niveau = niveaux_de_quantile(positions(passe, editions, pays))
        actuelles = bandes[bandes["horizon"] == h].set_index("country_code")
        r = pd.DataFrame(index=niveau.index, columns=editions, dtype=float)
        for code in niveau.index:
            classe = actuelles.at[code, "classe_de_croissance"] if code in actuelles.index else np.nan
            dist = erreurs[cle_de_cellule(classe, pays[code], cellules, classes)]
            r.loc[code] = 1 / (1 + np.quantile(dist, niveau.loc[code].to_numpy()) / 100)
        rapports[annee_edition + int(h)] = r
    return rapports


def prolonger(rapports: dict, scenarios: pd.DataFrame, annee_fin: int) -> dict:
    """
    Au-delà de l'horizon du FMI : chaque tirage garde sa position relative z dans la
    fourchette `bas`–`haut` (en logarithme du rapport à `central_fmi`). Une fourchette
    dégénérée garde le rapport de l'horizon du FMI.
    """
    central, bas, haut = (_niveaux(scenarios, s) for s in ("central_fmi", "bas", "haut"))
    horizon_fmi = max(rapports)
    log_r = np.log(rapports[horizon_fmi])

    def milieu_et_demi_largeur(annee):
        lb = np.log(bas[annee] / central[annee]).reindex(log_r.index)
        lh = np.log(haut[annee] / central[annee]).reindex(log_r.index)
        return (lb + lh) / 2, (lh - lb) / 2

    m0, w0 = milieu_et_demi_largeur(horizon_fmi)
    z = log_r.sub(m0, axis=0).div(w0.where(w0 > 1e-9), axis=0)
    sortie = dict(rapports)
    for annee in range(horizon_fmi + 1, annee_fin + 1):
        m, w = milieu_et_demi_largeur(annee)
        sortie[annee] = np.exp(z.mul(w, axis=0).add(m, axis=0)).fillna(rapports[horizon_fmi])
    return sortie


def tirages(niveaux: pd.DataFrame, bandes: pd.DataFrame, scenarios: pd.DataFrame, annee_fin: int,
            pays_min: int = PAYS_MIN) -> pd.DataFrame:
    """
    Une ligne par tirage (édition rejouée), pays et année, de l'année de l'édition actuelle
    à `annee_fin` : PIB en volume par habitant. `niveaux` : erreurs de niveau passées, au
    groupe de revenu connu à l'édition ; `bandes` : fourchettes par horizon ; `scenarios` :
    table de `pib.scenarios`.
    """
    editions = editions_eligibles(niveaux, int(bandes["horizon"].max()), pays_min)
    central = _niveaux(scenarios, "central_fmi")
    bandes = bandes[bandes["country_code"].isin(central.index)]
    rapports = prolonger(rapports_jusqu_a_l_horizon(niveaux, bandes, editions), scenarios, annee_fin)
    lignes = []
    for annee, r in rapports.items():
        niveau = r.mul(central[annee].reindex(r.index), axis=0)
        niveau.index.name, niveau.columns.name = "country_code", "tirage"
        lignes.append(niveau.stack().rename("pib_reel_par_habitant_usd_2015").reset_index().assign(year=annee))
    sortie = pd.concat(lignes, ignore_index=True).dropna()
    return sortie[["tirage", "country_code", "year", "pib_reel_par_habitant_usd_2015"]].sort_values(
        ["tirage", "country_code", "year"]).reset_index(drop=True)


def intervalle_des_quantiles(total: pd.Series, q: float, tirages: int = TIRAGES_BOOTSTRAP,
                             graine: int = GRAINE) -> tuple:
    """
    Intervalle à 95 % du quantile q des tirages, par bootstrap des années d'édition (les
    éditions d'avril et d'octobre d'une même année, très proches, sont tirées ensemble).
    """
    rng = np.random.default_rng(graine)
    annees = total.index.str[1:].astype(int)
    par_annee = {a: total[annees == a].to_numpy() for a in np.unique(annees)}
    cles = list(par_annee)
    valeurs = [np.quantile(np.concatenate([par_annee[a] for a in rng.choice(cles, len(cles))]), q)
               for _ in range(tirages)]
    return tuple(np.quantile(valeurs, [0.025, 0.975]))


def niveaux_population(positions: pd.DataFrame, pays: pd.Index) -> pd.DataFrame:
    """
    Pays × révisions : niveau (k − ½) / R de chaque révision dans l'histoire du pays, k étant
    son rang par position u croissante. u : rang (− ½, rapporté à l'effectif) de l'écart z
    parmi tous les cas passés de la classe de taille, toutes révisions confondues, comme pour
    le PIB : ranger dans la seule révision effacerait le choc commun. À défaut, la médiane des
    positions de la révision, puis ½.
    """
    p = positions.copy()
    rang = p.groupby("classe_taille")["z"].rank(method="average")
    p["u"] = (rang - 0.5) / p.groupby("classe_taille")["z"].transform("size")
    large = p.pivot_table(index="country_code", columns="revision", values="u").reindex(pays)
    return niveaux_de_quantile(large.fillna(large.median()).fillna(0.5))


def affecter_revisions(editions: list, revisions: list) -> dict:
    """Édition -> révision, par blocs consécutifs dans l'ordre chronologique des éditions."""
    ordre = sorted(editions, key=lambda e: (int(e[1:]), e[0] == "F"))
    return {e: revisions[i * len(revisions) // len(ordre)] for i, e in enumerate(ordre)}


def population_tirages(niveaux: pd.DataFrame, affectation: dict, scenarios: pd.DataFrame, annees) -> pd.DataFrame:
    """
    Une ligne par tirage, pays et année : population (millions) à la position
    z = Φ⁻¹(niveau) / Φ⁻¹(0,9) de la fourchette calibrée du pays, en demi-largeurs de
    celle-ci (côté haut si z > 0, bas sinon), autour de la population centrale.
    """
    c = scenarios[(scenarios["scenario"] == "central_fmi") & scenarios["year"].isin(annees)].set_index(["country_code", "year"])
    centrale = c["population_millions_centrale"]
    log_bas = np.log(c["population_millions_basse_calibree"] / centrale)
    log_haut = np.log(c["population_millions_haute_calibree"] / centrale)
    z = niveaux.apply(lambda col: col.map(NormalDist().inv_cdf)) / Z80
    morceaux = []
    for tirage, revision in affectation.items():
        zc = z[revision].reindex(c.index.get_level_values("country_code")).to_numpy()
        ecart = np.where(zc >= 0, zc * log_haut.to_numpy(), -zc * log_bas.to_numpy())
        morceaux.append(pd.DataFrame({"tirage": tirage, "country_code": c.index.get_level_values("country_code"),
                                      "year": c.index.get_level_values("year"),
                                      "population_millions": centrale.to_numpy() * np.exp(ecart),
                                      "revision_onu": revision}))
    return pd.concat(morceaux, ignore_index=True).dropna(subset=["population_millions"])


def par_habitant(t: pd.DataFrame, scenarios: pd.DataFrame) -> pd.DataFrame:
    """
    PIB par habitant divisé par l'écart de la population tirée à la population centrale : le
    PIB total du tirage ne dépend pas de la population. Ajoute le PIB total (milliards).
    """
    centrale = scenarios[scenarios["scenario"] == "central_fmi"].set_index(["country_code", "year"])[
        "population_millions_centrale"]
    c = centrale.reindex(pd.MultiIndex.from_arrays([t["country_code"], t["year"]])).to_numpy()
    pib_total = t["pib_reel_par_habitant_usd_2015"].to_numpy() * c / 1000
    return t.assign(pib_reel_par_habitant_usd_2015=1000 * pib_total / t["population_millions"].to_numpy(),
                    pib_reel_milliards_usd_2015=pib_total)


def controle(t: pd.DataFrame, scenarios: pd.DataFrame, annees=(2031, 2040, 2050)) -> pd.DataFrame:
    """
    Par pays et année : part des tirages sous `bas` et au-dessus de `haut` (10 % de chaque
    côté sans population tirée ; davantage avec, `bas` et `haut` ignorant son incertitude), et
    pour la population, sous et au-dessus des bornes calibrées (10 % par construction). Par agrégat (PIB total, population centrale) : 10e, 50e et 90e
    centiles des tirages, avec l'intervalle à 95 % des deux bornes, contre la somme des
    bornes des pays.
    """
    s = scenarios[scenarios["year"].isin(annees)]
    b = s.pivot_table(index=["country_code", "year"], columns="scenario", values="pib_reel_par_habitant_usd_2015")
    pop = s[s["scenario"] == "central_fmi"].set_index(["country_code", "year"])["population_millions_centrale"]
    tt = t[t["year"].isin(annees)].join(b[["bas", "haut"]], on=["country_code", "year"])
    tt = tt.assign(sous=tt["pib_reel_par_habitant_usd_2015"] < tt["bas"],
                   dessus=tt["pib_reel_par_habitant_usd_2015"] > tt["haut"])
    colonnes = {"sous": "part_sous_bas", "dessus": "part_au_dessus_haut"}
    if "population_millions" in tt.columns:
        p = s[s["scenario"] == "central_fmi"].set_index(["country_code", "year"])[
            ["population_millions_basse_calibree", "population_millions_haute_calibree"]]
        tt = tt.join(p, on=["country_code", "year"])
        tt = tt.assign(pop_sous=tt["population_millions"] < tt["population_millions_basse_calibree"] * (1 - 1e-9),
                       pop_dessus=tt["population_millions"] > tt["population_millions_haute_calibree"] * (1 + 1e-9))
        colonnes.update({"pop_sous": "part_population_sous_basse_calibree",
                         "pop_dessus": "part_population_au_dessus_haute_calibree"})
    par_pays = (tt.groupby(["country_code", "year"])[list(colonnes)].mean().reset_index().rename(columns=colonnes))
    lignes = []
    for nom, membres in {"tous les pays": sorted(set(t["country_code"])), **AGREGATS}.items():
        for annee in annees:
            sel = tt[tt["country_code"].isin(membres) & (tt["year"] == annee)]
            if sel.empty:
                continue
            p = pop.reindex(pd.MultiIndex.from_arrays([sel["country_code"], sel["year"]])).to_numpy()
            # PIB total : celui du tirage s'il est donné (population tirée), sinon par habitant × population centrale
            pib = (sel["pib_reel_milliards_usd_2015"] * 1000 if "pib_reel_milliards_usd_2015" in sel.columns
                   else sel["pib_reel_par_habitant_usd_2015"] * p)
            total = sel.assign(pib=pib).groupby("tirage")["pib"].sum()
            bornes = b.loc[(b.index.get_level_values(0).isin(membres)) & (b.index.get_level_values(1) == annee)]
            pb = pop.reindex(bornes.index).to_numpy()
            central = float((bornes["central_fmi"] * pb).sum())
            relatif = 100 * total / central
            p10_bas, p10_haut = intervalle_des_quantiles(relatif, 0.1)
            p90_bas, p90_haut = intervalle_des_quantiles(relatif, 0.9)
            lignes.append({"agregat": nom, "year": annee, "pays": len(membres), "tirages": total.size,
                           "tirages_p10_pct_central": relatif.quantile(0.1),
                           "tirages_p10_ic95_bas": p10_bas, "tirages_p10_ic95_haut": p10_haut,
                           "tirages_p50_pct_central": relatif.median(),
                           "tirages_p90_pct_central": relatif.quantile(0.9),
                           "tirages_p90_ic95_bas": p90_bas, "tirages_p90_ic95_haut": p90_haut,
                           "somme_des_bas_pct_central": 100 * float((bornes["bas"] * pb).sum()) / central,
                           "somme_des_hauts_pct_central": 100 * float((bornes["haut"] * pb).sum()) / central})
    return pd.concat([par_pays.assign(agregat=np.nan), pd.DataFrame(lignes)], ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Trajectoires conjointes du PIB par habitant (tirages).")
    parser.add_argument("--data-dir", type=str, default="data")
    args = parser.parse_args()
    processed = os.path.join(args.data_dir, "processed")
    chemins = {n: os.path.join(processed, f) for n, f in (("niveaux", "weo_level_evaluation_ngdp_rpch.csv"),
                                                           ("bandes", "gdp_projection_bands_by_horizon.csv"),
                                                           ("scenarios", "scenarios_pib_population.csv"))}
    manquants = [c for c in chemins.values() if not os.path.exists(c)]
    if manquants:
        logging.warning(f"Absents : {manquants}. Tirages omis.")
        return
    niveaux = groupes_revenu.a_l_edition(pd.read_csv(chemins["niveaux"]), groupes_revenu.charger())
    scenarios = pd.read_csv(chemins["scenarios"])
    t = tirages(niveaux, pd.read_csv(chemins["bandes"]), scenarios, int(scenarios["year"].max()))
    chemin_positions = os.path.join(processed, FICHIER_POSITIONS)
    if os.path.exists(chemin_positions) and "population_millions_basse_calibree" in scenarios.columns:
        niveaux_pop = niveaux_population(pd.read_csv(chemin_positions), pd.Index(sorted(t["country_code"].unique())))
        affectation = affecter_revisions(sorted(t["tirage"].unique()), list(niveaux_pop.columns))
        pop = population_tirages(niveaux_pop, affectation, scenarios, sorted(t["year"].unique()))
        t = par_habitant(t.merge(pop, on=["tirage", "country_code", "year"], how="left"), scenarios)
    else:
        logging.warning(f"{chemin_positions} absent (pib.population) : tirages sans population.")
    t.round({"pib_reel_par_habitant_usd_2015": 1, "population_millions": 4, "pib_reel_milliards_usd_2015": 3}).to_csv(
        os.path.join(processed, FICHIER), index=False, encoding="utf-8-sig")
    c = controle(t, scenarios)
    c.round(2).to_csv(os.path.join(processed, FICHIER_CONTROLE), index=False, encoding="utf-8-sig")
    logging.info(f"-> {t['tirage'].nunique()} tirages, {t['country_code'].nunique()} pays, "
                 f"{t['year'].min()}-{t['year'].max()} :\n"
                 + c[c["agregat"].notna()].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
