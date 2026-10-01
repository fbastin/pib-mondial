#!/usr/bin/env python3
"""
long_terme.py
-------------
Fourchettes du PIB au-delà de l'horizon du FMI, tirées de ses erreurs passées.

Le FMI ne projette que 5 ans. Pour aller au-delà, on prolonge sa trajectoire ; ce module
mesure, édition par édition depuis 1999, ce que cette pratique a donné contre le réalisé
jusqu'à la dernière année connue (jusqu'à 25 ans d'horizon pour les premières éditions).
Trois prolongements, du même niveau de départ :

- `fmi_puis_derive` : la trajectoire du FMI jusqu'à 5 ans, puis la dérive, c'est-à-dire la
  croissance moyenne (logarithmique) des 10 dernières années connues à la date de l'édition :
  les ré-estimations du FMI des années v − 11 à v − 2, comme la prévision naïve de
  `evaluate_forecasts` ;
- `fmi_prolonge` : la trajectoire du FMI, puis la médiane de ses croissances projetées aux
  horizons 3 à 5, sa croissance de moyen terme. La médiane plutôt que la 5e année seule :
  celle-ci porte parfois un saut de niveau ponctuel, comme une mise en production pétrolière ;
- `derive` : la dérive dès la première année.

Erreur de niveau comme dans `evaluate_forecasts.erreurs_de_niveau` : niveau prévu / niveau
réalisé − 1, en %, croissances enchaînées depuis l'année précédant l'édition ; réalisé : la
ré-estimation du FMI à un an.

Les fourchettes des scénarios (`pib.scenarios`) s'en déduisent au-delà de l'horizon du FMI.
Par groupe de revenu connu à la date de l'édition (`pib.groupes_revenu`) et par horizon, les
quantiles à 10 et 90 % de l'erreur de `fmi_puis_derive` sont lissés par une loi
log(1 + q) = α + β · (h + 1)^b, monotone en h. Elle peut changer de signe : pour les pays
alors riches, le 10e centile devient positif au-delà d'une dizaine d'années, le réalisé
n'ayant presque jamais dépassé la trajectoire prolongée. La loi est ajustée sur les
horizons qui comptent au moins `ANNEES_MIN` années d'édition, puis extrapolée. La
fourchette de l'horizon du FMI, propre à chaque pays, s'élargit ensuite comme ces quantiles
entre l'horizon 5 et l'horizon h (`elargissement`).

Les fourchettes écartent les trajectoires dont la dérive est négative (`cas_pour_les_fourchettes`).
Prolonger une croissance passée négative, c'est extrapoler un effondrement : les éditions de
1999-2003 l'ont fait pour les économies issues de l'URSS (Géorgie, Kazakhstan, Turkménistan,
Ukraine), dont le réalisé a ensuite atteint jusqu'à 16 fois la trajectoire prolongée. Les
scénarios, eux, suivent au-delà de l'horizon du FMI la croissance de long terme de l'OCDE, qui
ne prolonge aucun effondrement : ces erreurs ne représentent pas leur incertitude. Écartées
(5 % des trajectoires), elles gonflaient le haut des fourchettes des pays non riches (facteur
d'élargissement de 2031 à 2050 de 1,84 au lieu de 1,17 pour le revenu intermédiaire
inférieur). La synthèse des prolongements (`gdp_long_horizon_errors.csv`) les garde.

Sorties dans `data/processed/` :

- `gdp_long_horizon_errors.csv` : par horizon, quantiles et erreurs absolues des trois
  prolongements, et part des cas où le FMI prolongé fait mieux que la dérive ;
- `gdp_long_horizon_bands.csv` : par groupe de revenu et horizon, quantiles observés et lissés ;
- `gdp_long_horizon_law.csv` : paramètres des lois lissées.

    python -m pib.long_terme --data-dir data
"""

import os
import logging
import argparse

import numpy as np
import pandas as pd

from pib import groupes_revenu

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

H_MAX = 25
H_FMI = 5
FENETRE = 10
PART_MIN = 0.8
PREMIERE_EDITION = 1999
# Les fourchettes ne retiennent que les trajectoires dont la dérive atteint ce seuil (%/an)
DERIVE_MIN = 0.0
PROLONGEMENTS = ("fmi_puis_derive", "fmi_prolonge", "derive")

# Horizons qui servent à ajuster la loi : au moins autant d'années d'édition distinctes
ANNEES_MIN = 10
# Extrapolation des fourchettes : jusqu'à cet horizon (2026 + 40 dépasse 2050)
H_EXTRAPOLATION = 40
TOUS = "tous"
# Exposants essayés pour la loi lissée (pas de scipy : recherche sur une grille)
EXPOSANTS = np.round(np.arange(0.2, 2.0001, 0.01), 2)

FICHIER_EVALUATION = "weo_forecast_evaluation_ngdp_rpch.csv"
FICHIER_ERREURS = "gdp_long_horizon_errors.csv"
FICHIER_BANDES = "gdp_long_horizon_bands.csv"
FICHIER_LOIS = "gdp_long_horizon_law.csv"


# ------------------------------------------------------------------ erreurs

def croissance_realisee(evaluation: pd.DataFrame) -> pd.DataFrame:
    """Ré-estimation du FMI à un an, par année (lignes) et pays (colonnes)."""
    return (evaluation.dropna(subset=["realise_fmi"]).drop_duplicates(["country_code", "year"])
            .pivot_table(index="year", columns="country_code", values="realise_fmi"))


def derive(realise: pd.Series, annee_edition: int, fenetre: int = FENETRE) -> float:
    """
    Croissance moyenne (%, moyenne des logarithmes) des `fenetre` années v − fenetre − 1 à
    v − 2, connues à la date de l'édition ; NaN s'il en manque plus de 20 %.
    """
    c = realise.reindex(range(annee_edition - fenetre - 1, annee_edition - 1)).dropna()
    if len(c) < PART_MIN * fenetre:
        return np.nan
    return 100 * np.expm1(np.log1p(c / 100).mean())


def croissances_prevues(fmi: np.ndarray, derive_pct: float, h_max: int = H_MAX) -> dict:
    """Croissances annuelles (%) des trois prolongements, de l'horizon 0 à `h_max`."""
    reste = h_max - H_FMI
    return {"fmi_puis_derive": np.r_[fmi, np.full(reste, derive_pct)],
            "fmi_prolonge": np.r_[fmi, np.full(reste, np.median(fmi[3:6]))],
            "derive": np.full(h_max + 1, derive_pct)}


def erreurs_cumulees(prevues: np.ndarray, realisees: np.ndarray) -> np.ndarray:
    """Erreur de niveau (%) à chaque horizon ; s'arrête à la première année sans réalisé."""
    manquant = np.flatnonzero(np.isnan(realisees))
    n = manquant[0] if len(manquant) else len(realisees)
    return 100 * np.expm1(np.cumsum(np.log1p(prevues[:n] / 100)) - np.cumsum(np.log1p(realisees[:n] / 100)))


def erreurs_prolongees(evaluation: pd.DataFrame, h_max: int = H_MAX,
                       premiere_edition: int = PREMIERE_EDITION) -> pd.DataFrame:
    """Une ligne par pays, édition et horizon : erreur de niveau des trois prolongements."""
    reel = croissance_realisee(evaluation)
    e = evaluation[(evaluation["annee_millesime"] >= premiere_edition) & evaluation["horizon"].between(0, H_FMI)]
    t = e.pivot_table(index=["country_code", "vintage", "annee_millesime"], columns="horizon", values="valeur").dropna()
    groupes = (evaluation.dropna(subset=["income_group"]).drop_duplicates("country_code")
               .set_index("country_code")["income_group"])
    lignes = []
    for (code, vintage, annee), fmi in zip(t.index, t.to_numpy(dtype=float)):
        if code not in reel.columns:
            continue
        d = derive(reel[code], int(annee))
        if np.isnan(d):
            continue
        realisees = reel[code].reindex(range(int(annee), int(annee) + h_max + 1)).to_numpy()
        resultats = {nom: erreurs_cumulees(p, realisees) for nom, p in croissances_prevues(fmi, d, h_max).items()}
        for h in range(len(resultats["derive"])):
            lignes.append((code, groupes.get(code), vintage, int(annee), h, d, *(resultats[n][h] for n in PROLONGEMENTS)))
    return pd.DataFrame(lignes, columns=["country_code", "income_group", "vintage", "annee_millesime", "horizon",
                                         "derive_pct"] + [f"erreur_{n}" for n in PROLONGEMENTS])


def cas_pour_les_fourchettes(erreurs: pd.DataFrame, derive_min: float = DERIVE_MIN) -> pd.DataFrame:
    """Trajectoires retenues pour les fourchettes : dérive d'au moins `derive_min` (voir le module)."""
    return erreurs[erreurs["derive_pct"] >= derive_min]


def synthese(erreurs: pd.DataFrame) -> pd.DataFrame:
    """
    Par horizon : quantiles (10, 50, 90 %), erreur absolue médiane et au 80e centile de
    chaque prolongement ; part des cas où chaque trajectoire du FMI prolongée est plus proche
    du réalisé que la dérive. Mesures robustes : enchaînées sur 20 ans, quelques
    effondrements (Libye, Venezuela) domineraient tout écart quadratique.
    """
    lignes = []
    for h, g in erreurs.groupby("horizon"):
        ligne = {"horizon": h, "cas": len(g), "annees_edition": g["annee_millesime"].nunique()}
        for n in PROLONGEMENTS:
            x = g[f"erreur_{n}"].to_numpy()
            ligne.update({f"p10_{n}": np.quantile(x, 0.1), f"p50_{n}": np.median(x), f"p90_{n}": np.quantile(x, 0.9),
                          f"erreur_abs_mediane_{n}": np.median(np.abs(x)),
                          f"erreur_abs_p80_{n}": np.quantile(np.abs(x), 0.8)})
        for n in ("fmi_puis_derive", "fmi_prolonge"):
            ligne[f"part_{n}_plus_proche_que_derive"] = np.mean(np.abs(g[f"erreur_{n}"]) < np.abs(g["erreur_derive"]))
        lignes.append(ligne)
    return pd.DataFrame(lignes)


# ------------------------------------------------------------------ fourchettes

def quantiles_par_groupe(erreurs: pd.DataFrame, prolongement: str = "fmi_puis_derive") -> pd.DataFrame:
    """Quantiles à 10, 50 et 90 % de l'erreur, par groupe de revenu (et tous pays) et horizon."""
    x = f"erreur_{prolongement}"
    morceaux = [erreurs.assign(groupe=TOUS)] + [g.assign(groupe=n) for n, g in erreurs.groupby("income_group")]
    return (pd.concat(morceaux).groupby(["groupe", "horizon"])
            .agg(cas=(x, "size"), annees_edition=("annee_millesime", "nunique"),
                 p10=(x, lambda v: v.quantile(0.1)), p50=(x, "median"), p90=(x, lambda v: v.quantile(0.9)))
            .reset_index())


def ajuster_loi(horizons: np.ndarray, quantiles_pct: np.ndarray) -> tuple:
    """
    log(1 + q) = α + β · (h + 1)^b : b sur la grille `EXPOSANTS`, α et β par moindres carrés
    pour chaque b, la plus petite somme des carrés l'emportant. Monotone en h, la loi peut
    changer de signe. Rend (α, β, b).
    """
    y = np.log1p(np.asarray(quantiles_pct, dtype=float) / 100)
    x = np.asarray(horizons, dtype=float) + 1
    meilleur = None
    for b in EXPOSANTS:
        X = np.column_stack([np.ones_like(x), x ** b])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        carres = float(np.sum((y - X @ coef) ** 2))
        if meilleur is None or carres < meilleur[0] - 1e-12:
            meilleur = (carres, coef[0], coef[1], b)
    _, alpha, beta, b = meilleur
    return float(alpha), float(beta), float(b)


def lisser(quantiles: pd.DataFrame, annees_min: int = ANNEES_MIN, h_max: int = H_EXTRAPOLATION) -> tuple:
    """
    Pour chaque groupe : lois des 10e et 90e centiles (`ajuster_loi`), ajustées de l'horizon 1
    au dernier horizon qui compte au moins `annees_min` années d'édition, et quantiles lissés
    de l'horizon 1 à `h_max`. L'horizon 0, hors de la plage d'ajustement, n'est pas extrapolé :
    la loi y donnait parfois un 90e centile sous le 10e. Rend (fourchettes lissées jointes aux
    observées, lois).
    """
    lissees, lois = [], []
    for groupe, g in quantiles.groupby("groupe"):
        fiable = g[(g["horizon"] >= 1) & (g["annees_edition"] >= annees_min)]
        if len(fiable) < 3:
            continue
        h = np.arange(1, h_max + 1)
        ligne_loi = {"groupe": groupe, "horizon_max_ajuste": int(fiable["horizon"].max())}
        lisse = pd.DataFrame({"groupe": groupe, "horizon": h})
        for q in ("p10", "p90"):
            alpha, beta, b = ajuster_loi(fiable["horizon"].to_numpy(), fiable[q].to_numpy())
            ligne_loi.update({f"alpha_{q}": alpha, f"beta_{q}": beta, f"b_{q}": b})
            lisse[f"{q}_lisse"] = 100 * np.expm1(alpha + beta * (h + 1) ** b)
        lissees.append(lisse)
        lois.append(ligne_loi)
    bandes = pd.concat(lissees, ignore_index=True).merge(quantiles, on=["groupe", "horizon"], how="left")
    return bandes, pd.DataFrame(lois)


def elargissement(bandes: pd.DataFrame, groupe: str, h0: int, h: int) -> tuple:
    """
    Facteurs par lesquels multiplier les bornes basse et haute du réalisé (relatives à la
    trajectoire centrale) de l'horizon h0 à l'horizon h. L'erreur étant prévu / réalisé − 1,
    le réalisé bas vaut prévu / (1 + p90) et le haut prévu / (1 + p10) :

        bas(h) = bas(h0) · (1 + p90(h0)) / (1 + p90(h))
        haut(h) = haut(h0) · (1 + p10(h0)) / (1 + p10(h))

    Le groupe inconnu prend les quantiles de tous les pays.
    """
    b = bandes[bandes["groupe"] == (groupe if groupe in set(bandes["groupe"]) else TOUS)].set_index("horizon")
    h = min(h, int(b.index.max()))
    bas = (1 + b.loc[h0, "p90_lisse"] / 100) / (1 + b.loc[h, "p90_lisse"] / 100)
    haut = (1 + b.loc[h0, "p10_lisse"] / 100) / (1 + b.loc[h, "p10_lisse"] / 100)
    return float(bas), float(haut)


# ------------------------------------------------------------------ chaîne

def main():
    parser = argparse.ArgumentParser(description="Fourchettes du PIB au-delà de l'horizon du FMI.")
    parser.add_argument("--data-dir", type=str, default="data")
    args = parser.parse_args()
    processed = os.path.join(args.data_dir, "processed")
    chemin = os.path.join(processed, FICHIER_EVALUATION)
    if not os.path.exists(chemin):
        logging.warning(f"{chemin} absent : lancer d'abord pib.evaluate_forecasts. Fourchettes de long terme omises.")
        return
    evaluation = pd.read_csv(chemin)
    # Groupe de revenu connu à la date de l'édition : le groupe actuel introduirait un biais de sélection
    erreurs = groupes_revenu.a_l_edition(erreurs_prolongees(evaluation), groupes_revenu.charger())
    synthese(erreurs).to_csv(os.path.join(processed, FICHIER_ERREURS), index=False, encoding="utf-8-sig")
    retenues = cas_pour_les_fourchettes(erreurs)
    bandes, lois = lisser(quantiles_par_groupe(retenues))
    bandes.to_csv(os.path.join(processed, FICHIER_BANDES), index=False, encoding="utf-8-sig")
    lois.to_csv(os.path.join(processed, FICHIER_LOIS), index=False, encoding="utf-8-sig")
    n = erreurs[["country_code", "vintage"]].drop_duplicates().shape[0]
    n_retenues = retenues[["country_code", "vintage"]].drop_duplicates().shape[0]
    logging.info(f"-> {n:,} trajectoires prolongées, dont {n_retenues:,} retenues pour les fourchettes "
                 f"(dérive d'au moins {DERIVE_MIN:g} %) ; fourchettes de long terme dans {processed}")


if __name__ == "__main__":
    main()
