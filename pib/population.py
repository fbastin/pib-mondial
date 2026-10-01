#!/usr/bin/env python3
"""
population.py
-------------
Erreurs passées des projections de population de l'ONU, et calibration de leurs bornes.

Les scénarios (`pib.scenarios`) prolongent la population par la variante médiane des
*World Population Prospects* 2024, avec ses bornes à 80 %. Ce module mesure, comme pour le
FMI, ce qu'ont donné les révisions passées : celles de 1998 à 2022 (archives de l'ONU),
confrontées aux estimations de la révision 2024 jusqu'à 2023, soit jusqu'à 25 ans d'horizon.

- **Erreur de niveau :** population projetée (variante médiane) / estimée − 1, en %, comme
  pour le PIB. L'horizon est l'écart entre l'année visée et l'année de la révision.
- **Bornes de l'ONU appliquées au passé :** les bornes à 80 % de la révision 2024 de chaque
  pays, à l'horizon h, appliquées aux erreurs passées du même pays au même horizon. Bien
  calibrées, elles en contiendraient 80 %.
- **Calibration.** En logarithme, chaque réalisé passé, relatif à la projection, est
  exprimé en demi-largeurs des bornes de l'ONU, côté haut s'il est au-dessus, côté bas
  sinon. Ses 10e et 90e centiles, par horizon et par classe de taille, donnent les
  multiplicateurs qui portent les bornes à 80 % de couverture. Lissés par
  k(h) = a + b · (h + 1)^c, ajustés sur les horizons qu'atteignent au moins
  `REVISIONS_MIN` révisions, ils ne descendent jamais sous 1 : on élargit les bornes de
  l'ONU, on ne les resserre pas. Les révisions évaluables couvrent une période
  d'immigration forte, qui ne dit rien du risque inverse.
- **Classes de taille :** plus de 5 millions d'habitants, ou moins, selon la population
  que donnait la révision pour son année. Les petits pays portent les plus fortes
  révisions de la population de départ (Bhoutan, Érythrée, Qatar).

Seul le fichier de la population totale est lu dans chaque archive (lecture par plages
HTTP) : l'archive de 2022 pèse 3,5 Go.

Sorties dans `data/processed/` :

- `population_projection_errors.csv` : par groupe de revenu connu à la révision, classe de
  taille, et pour tous les pays, et par horizon : quantiles de l'erreur, bornes du réalisé
  qui s'en déduisent, bornes de l'ONU (médiane des pays), part des erreurs passées
  contenues dans les bornes de l'ONU ;
- `population_bounds_calibration.csv` : par classe de taille et horizon, multiplicateurs
  observés et lissés des bornes de l'ONU, et part des erreurs passées contenues dans les
  bornes de l'ONU et dans les bornes calibrées ;
- `population_calibrated_bounds.csv` : par pays et année projetée, bornes à 80 % de l'ONU
  et bornes calibrées, en rapport à la variante médiane, que `pib.scenarios` applique à
  sa population centrale.

    python -m pib.population --data-dir data
"""

import io
import os
import logging
import zipfile
import argparse

import numpy as np
import pandas as pd
import requests

from pib import groupes_revenu
from pib.gdp_pipeline import unified_csv_path
from pib.http_utils import HEADERS
from pib.long_terme import TOUS
from pib.scenarios import CACHE, FICHIER_BORNES_POPULATION as FICHIER_BORNES, FICHIER_WPP, WPP, telecharger

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ARCHIVE = "https://population.un.org/wpp/assets/Excel%20Files/5_Archive/WPP{revision}-CSV-data.zip"
REVISIONS = (1998, 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2015, 2017, 2019, 2022)
REVISION_ACTUELLE = 2024
DOSSIER = os.path.join("data", "raw", "wpp_archive")
# Horizons qui servent à ajuster les multiplicateurs : atteints par au moins autant de révisions
REVISIONS_MIN = 4
H_EXTRAPOLATION = 40
SEUIL_TAILLE = 5000          # milliers d'habitants
GRANDS, PETITS = "plus de 5 millions", "5 millions ou moins"
EXPOSANTS = np.round(np.arange(-3.0, -0.0999, 0.01), 2)
FICHIER_ERREURS = "population_projection_errors.csv"
FICHIER_CALIBRATION = "population_bounds_calibration.csv"


# ------------------------------------------------------------------ données

class _FichierDistant(io.RawIOBase):
    """Fichier HTTP lu par plages (en-tête Range) : de quoi ouvrir une archive zip sans la télécharger."""

    def __init__(self, url: str):
        self.url, self.position = url, 0
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        reponse = self.session.head(url, allow_redirects=True, timeout=60)
        reponse.raise_for_status()
        self.taille = int(reponse.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, decalage, origine=0):
        self.position = {0: decalage, 1: self.position + decalage, 2: self.taille + decalage}[origine]
        return self.position

    def readinto(self, tampon):
        if self.position >= self.taille or len(tampon) == 0:
            return 0
        fin = min(self.position + len(tampon), self.taille) - 1
        reponse = self.session.get(self.url, headers={"Range": f"bytes={self.position}-{fin}"}, timeout=300)
        if reponse.status_code != 206:
            raise requests.RequestException(f"{self.url} : lecture par plages refusée ({reponse.status_code}).")
        tampon[:len(reponse.content)] = reponse.content
        self.position += len(reponse.content)
        return len(reponse.content)


def chemin_revision(revision: int, dossier: str = DOSSIER) -> str:
    return os.path.join(dossier, f"WPP{revision}_TotalPopulationBySex.csv")


def collecter(revisions=REVISIONS, dossier: str = DOSSIER) -> list:
    """Extrait des archives de l'ONU le fichier de la population totale de chaque révision absente."""
    os.makedirs(dossier, exist_ok=True)
    obtenues = []
    for revision in revisions:
        chemin = chemin_revision(revision, dossier)
        if not os.path.exists(chemin):
            try:
                archive = zipfile.ZipFile(io.BufferedReader(_FichierDistant(ARCHIVE.format(revision=revision)),
                                                            buffer_size=1 << 20))
                membre = next(i for i in archive.infolist()
                              if i.filename.endswith(f"WPP{revision}_TotalPopulationBySex.csv"))
                with archive.open(membre) as source, open(chemin + ".partiel", "wb") as cible:
                    cible.write(source.read())
                os.replace(chemin + ".partiel", chemin)
                logging.info(f"-> révision {revision} : {membre.file_size / 1e6:.1f} Mo.")
            except (requests.RequestException, zipfile.BadZipFile, StopIteration, OSError) as e:
                logging.warning(f"Révision {revision} indisponible ({e}).")
                continue
        obtenues.append(revision)
    return obtenues


def lire_revision(chemin: str) -> pd.DataFrame:
    """Variante médiane d'une révision : LocID, year, population (milliers)."""
    t = pd.read_csv(chemin, usecols=["LocID", "Variant", "Time", "PopTotal"], encoding="latin-1", low_memory=False)
    t = t[t["Variant"] == "Medium"]
    return t.rename(columns={"Time": "year", "PopTotal": "population"})[["LocID", "year", "population"]]


def lire_actuelle(chemin: str) -> pd.DataFrame:
    """
    Révision actuelle, pays seulement : country_code, LocID, year, et population (milliers)
    des variantes médiane, basse et haute à 80 %.
    """
    t = pd.read_csv(chemin, usecols=["LocID", "ISO3_code", "LocTypeName", "Variant", "Time", "PopTotal"],
                    low_memory=False)
    t = t[(t["LocTypeName"] == "Country/Area") & t["ISO3_code"].notna()
          & t["Variant"].isin(["Medium", "Lower 80 PI", "Upper 80 PI"])]
    large = t.pivot_table(index=["ISO3_code", "LocID", "Time"], columns="Variant", values="PopTotal").reset_index()
    return large.rename(columns={"ISO3_code": "country_code", "Time": "year", "Medium": "mediane",
                                 "Lower 80 PI": "basse", "Upper 80 PI": "haute"})


# ------------------------------------------------------------------ erreurs

def classe_de_taille(population_milliers):
    return np.where(np.asarray(population_milliers) > SEUIL_TAILLE, GRANDS, PETITS)


def erreurs(revisions: dict, actuelle: pd.DataFrame) -> pd.DataFrame:
    """
    Une ligne par révision, pays et année visée postérieure à la révision, jusqu'à la
    dernière année estimée par la révision actuelle : erreur de niveau (%), horizon, et
    classe de taille selon la population que donnait la révision pour son année.
    `revisions` : année -> table de `lire_revision`.
    """
    estimee = actuelle[actuelle["year"] < REVISION_ACTUELLE][["country_code", "LocID", "year", "mediane"]]
    morceaux = []
    for revision, t in revisions.items():
        depart = t[t["year"] == revision].set_index("LocID")["population"]
        m = t[t["year"] > revision].merge(estimee, on=["LocID", "year"])
        m = m[(m["population"] > 0) & (m["mediane"] > 0)]
        morceaux.append(m.assign(revision=revision, horizon=m["year"] - revision,
                                 erreur_pct=100 * (m["population"] / m["mediane"] - 1),
                                 classe_taille=classe_de_taille(m["LocID"].map(depart).fillna(0))))
    return pd.concat(morceaux, ignore_index=True)[["revision", "country_code", "year", "horizon", "classe_taille",
                                                   "erreur_pct"]]


def avec_groupe(e: pd.DataFrame, groupes_actuels: pd.Series, historique) -> pd.DataFrame:
    """Groupe de revenu connu l'année de la révision (exercice de cette année), l'actuel à défaut."""
    cas = e.assign(vintage="S" + e["revision"].astype(str), annee_millesime=e["revision"],
                   income_group=e["country_code"].map(groupes_actuels))
    return groupes_revenu.a_l_edition(cas, historique).drop(columns=["vintage", "annee_millesime"])


def bornes_actuelles(actuelle: pd.DataFrame) -> pd.DataFrame:
    """Bornes à 80 % de la révision actuelle, en % de la médiane, par pays et horizon (année − 2024)."""
    a = actuelle[actuelle["year"] >= REVISION_ACTUELLE]
    return pd.DataFrame({"country_code": a["country_code"], "horizon": a["year"] - REVISION_ACTUELLE,
                         "onu_bas_pct": 100 * (a["basse"] / a["mediane"] - 1),
                         "onu_haut_pct": 100 * (a["haute"] / a["mediane"] - 1)}).dropna()


def ecarts_normalises(e: pd.DataFrame, bornes: pd.DataFrame) -> pd.DataFrame:
    """
    Joint à chaque erreur passée les bornes actuelles de l'ONU pour le même pays et le même
    horizon (1 et au-delà). `z` : logarithme du réalisé relatif à la projection,
    log(1 / (1 + erreur)), en demi-largeurs des bornes, côté haut s'il est positif, côté
    bas sinon. `dedans` : le réalisé tombe dans les bornes de l'ONU (|z| ≤ 1 du bon côté).
    """
    m = e[e["horizon"] >= 1].merge(bornes, on=["country_code", "horizon"])
    bas, haut = np.log1p(m["onu_bas_pct"] / 100), np.log1p(m["onu_haut_pct"] / 100)
    m = m[(bas < 0) & (haut > 0)]
    bas, haut = np.log1p(m["onu_bas_pct"] / 100), np.log1p(m["onu_haut_pct"] / 100)
    rho = -np.log1p(m["erreur_pct"] / 100)
    z = np.where(rho >= 0, rho / haut, rho / -bas)
    return m.assign(z=z, dedans=(z >= -1) & (z <= 1))


def synthese(m: pd.DataFrame) -> pd.DataFrame:
    """
    Par groupe de revenu connu à la révision, classe de taille et tous pays, et par
    horizon : cas, révisions, quantiles de l'erreur, bornes du réalisé qui s'en déduisent,
    bornes de l'ONU (médiane des pays), part des erreurs passées dans ces bornes.
    """
    groupes = ([(TOUS, m)] + [(g, x) for g, x in m.groupby("income_group")]
               + [(c, x) for c, x in m.groupby("classe_taille")])
    lignes = []
    for groupe, g in groupes:
        for h, x in g.groupby("horizon"):
            p10, p50, p90 = x["erreur_pct"].quantile([0.1, 0.5, 0.9])
            lignes.append({"groupe": groupe, "horizon": h, "cas": len(x), "revisions": x["revision"].nunique(),
                           "p10": p10, "p50": p50, "p90": p90,
                           "erreur_absolue_mediane": x["erreur_pct"].abs().median(),
                           "realise_bas_pct": 100 * (1 / (1 + p90 / 100) - 1),
                           "realise_haut_pct": 100 * (1 / (1 + p10 / 100) - 1),
                           "onu_bas_pct": x["onu_bas_pct"].median(), "onu_haut_pct": x["onu_haut_pct"].median(),
                           "part_dans_bornes_onu": x["dedans"].mean()})
    return pd.DataFrame(lignes)


# ------------------------------------------------------------------ calibration

def ajuster_multiplicateur(horizons: np.ndarray, k: np.ndarray) -> tuple:
    """k(h) = a + b · (h + 1)^c : c sur la grille `EXPOSANTS`, a et b par moindres carrés. Rend (a, b, c)."""
    x, y = np.asarray(horizons, dtype=float) + 1, np.asarray(k, dtype=float)
    meilleur = None
    for c in EXPOSANTS:
        X = np.column_stack([np.ones_like(x), x ** c])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        carres = float(np.sum((y - X @ coef) ** 2))
        if meilleur is None or carres < meilleur[0] - 1e-12:
            meilleur = (carres, coef[0], coef[1], c)
    return float(meilleur[1]), float(meilleur[2]), float(meilleur[3])


def multiplicateurs(m: pd.DataFrame, revisions_min: int = REVISIONS_MIN, h_max: int = H_EXTRAPOLATION) -> pd.DataFrame:
    """
    Par classe de taille et horizon (1 à `h_max`) : multiplicateurs observés des bornes de
    l'ONU (opposé du 10e centile de z côté bas, 90e centile côté haut), lissés et ramenés à
    1 au moins ; part des erreurs passées dans les bornes de l'ONU et dans les bornes
    calibrées (lissées).
    """
    morceaux = []
    for classe, g in m.groupby("classe_taille"):
        obs = g.groupby("horizon").agg(cas=("z", "size"), revisions=("revision", "nunique"),
                                       k_bas_observe=("z", lambda z: -z.quantile(0.1)),
                                       k_haut_observe=("z", lambda z: z.quantile(0.9)),
                                       part_dans_bornes_onu=("dedans", "mean"))
        fiable = obs[obs["revisions"] >= revisions_min]
        h = np.arange(1, h_max + 1)
        table = pd.DataFrame({"classe_taille": classe, "horizon": h,
                              "horizon_max_ajuste": int(fiable.index.max())}).set_index("horizon")
        for cote in ("bas", "haut"):
            a, b, c = ajuster_multiplicateur(fiable.index.to_numpy(), fiable[f"k_{cote}_observe"].to_numpy())
            table[f"k_{cote}"] = np.maximum(1.0, a + b * (h + 1.0) ** c)
        table = table.join(obs)
        z = g.join(table[["k_bas", "k_haut"]], on="horizon")
        table["part_dans_bornes_calibrees"] = ((z["z"] >= -z["k_bas"]) & (z["z"] <= z["k_haut"])).groupby(z["horizon"]).mean()
        morceaux.append(table.reset_index())
    return pd.concat(morceaux, ignore_index=True)


def bornes_par_pays(actuelle: pd.DataFrame, calibration: pd.DataFrame) -> pd.DataFrame:
    """
    Par pays et année projetée (horizon 1 à celui de `calibration`) : bornes de l'ONU et
    bornes calibrées, en rapport à la médiane. La borne calibrée vaut le rapport de l'ONU
    élevé à la puissance k (multiplicateur de la classe de taille du pays, selon sa
    population de 2024, à cet horizon) : le logarithme de l'écart est multiplié par k.
    """
    taille = actuelle[actuelle["year"] == REVISION_ACTUELLE].set_index("country_code")["mediane"]
    a = actuelle[actuelle["year"] > REVISION_ACTUELLE].dropna(subset=["mediane", "basse", "haute"])
    a = a.assign(horizon=a["year"] - REVISION_ACTUELLE,
                 classe_taille=classe_de_taille(a["country_code"].map(taille).fillna(0)))
    a = a.merge(calibration[["classe_taille", "horizon", "k_bas", "k_haut"]], on=["classe_taille", "horizon"])
    onu_basse, onu_haute = a["basse"] / a["mediane"], a["haute"] / a["mediane"]
    return pd.DataFrame({"country_code": a["country_code"], "year": a["year"], "classe_taille": a["classe_taille"],
                         "onu_basse": onu_basse, "onu_haute": onu_haute,
                         "calibree_basse": np.exp(a["k_bas"] * np.log(onu_basse)),
                         "calibree_haute": np.exp(a["k_haut"] * np.log(onu_haute))}).sort_values(["country_code", "year"])


# ------------------------------------------------------------------ chaîne

def main():
    parser = argparse.ArgumentParser(description="Erreurs passées des projections de population de l'ONU.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--cache", type=str, default=CACHE)
    args = parser.parse_args()
    processed = os.path.join(args.data_dir, "processed")
    try:
        actuelle = lire_actuelle(telecharger(WPP, os.path.join(args.cache, FICHIER_WPP)))
    except RuntimeError as e:
        logging.error(f"{e} Évaluation de la population omise.")
        return
    obtenues = collecter()
    if not obtenues:
        logging.warning("Aucune révision passée de l'ONU disponible : évaluation de la population omise.")
        return
    revisions = {r: lire_revision(chemin_revision(r)) for r in obtenues}
    unifie = pd.read_csv(unified_csv_path(args.data_dir), usecols=["country_code", "income_group"])
    groupes = unifie.drop_duplicates("country_code").set_index("country_code")["income_group"]
    e = avec_groupe(erreurs(revisions, actuelle), groupes, groupes_revenu.charger())
    m = ecarts_normalises(e, bornes_actuelles(actuelle))
    table = synthese(m)
    table.round(3).to_csv(os.path.join(processed, FICHIER_ERREURS), index=False, encoding="utf-8-sig")
    calibration = multiplicateurs(m)
    calibration.round(3).to_csv(os.path.join(processed, FICHIER_CALIBRATION), index=False, encoding="utf-8-sig")
    bornes_par_pays(actuelle, calibration).round(5).to_csv(os.path.join(processed, FICHIER_BORNES), index=False,
                                                           encoding="utf-8-sig")
    vue = table[table["horizon"].isin([5, 10, 20]) & table["groupe"].isin([TOUS, GRANDS, PETITS])]
    logging.info(f"-> {len(e)} erreurs, révisions {obtenues[0]}-{obtenues[-1]} :\n"
                 + vue[["groupe", "horizon", "cas", "revisions", "p10", "p50", "p90", "onu_bas_pct", "onu_haut_pct",
                        "part_dans_bornes_onu"]].round(2).to_string(index=False) + "\n"
                 + calibration[calibration["horizon"].isin([1, 2, 5, 10, 15, 20, 26])]
                 [["classe_taille", "horizon", "cas", "k_bas_observe", "k_bas", "k_haut_observe", "k_haut",
                   "part_dans_bornes_onu", "part_dans_bornes_calibrees"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
