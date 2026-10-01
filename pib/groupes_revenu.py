#!/usr/bin/env python3
"""
groupes_revenu.py
-----------------
Groupe de revenu de la Banque Mondiale **connu à la date de chaque édition** du WEO.

Les fourchettes tirées des erreurs passées regroupent les projections comparables, dont
celles du même groupe de revenu. Le groupe actuel d'un pays ne convient pas pour ses cas
passés : il rangerait parmi les pays riches ceux qui le sont devenus depuis (Chili,
Pologne, pays baltes, Guyana), justement parce que leur croissance a dépassé les
prévisions. Un biais de sélection, faible à 5 ans, fort au-delà : à 15 ans, il donnait aux
pays riches une queue d'erreurs « réalisé bien au-dessus du prévu » qu'ils n'ont pas connue.

Le classement historique (fichier « OGHIST » de la Banque Mondiale, exercices FY89 à
aujourd'hui) est téléchargé une fois dans `data/raw/` (non versionné). L'édition d'avril
de l'année v connaît l'exercice v, publié en juillet v − 1 ; celle d'octobre, l'exercice
v + 1, publié en juillet v. Un pays sans classement à cette date garde son groupe actuel.
"""

import os
import logging
from typing import Optional

import pandas as pd
import requests

URL = "https://ddh-openapi.worldbank.org/resources/DR0095334/download"
CHEMIN = os.path.join("data", "raw", "bm_groupes_revenu_historiques.xlsx")
CODES = {"L": "LIC", "LM": "LMC", "UM": "UMC", "H": "HIC"}
FEUILLE = "Country Analytical History"


def lire(chemin: str = CHEMIN) -> pd.DataFrame:
    """Groupe par pays et exercice : country_code, exercice (année), groupe (LIC, LMC, UMC, HIC)."""
    d = pd.read_excel(chemin, sheet_name=FEUILLE, header=None)
    exercices = d.iloc[4, 2:].tolist()
    lignes = []
    for _, r in d.iloc[11:].iterrows():
        code = r.iloc[0]
        if not isinstance(code, str) or len(code) != 3:
            continue
        for fy, valeur in zip(exercices, r.iloc[2:]):
            groupe = CODES.get(str(valeur).strip().rstrip("*"))
            if isinstance(fy, str) and fy.startswith("FY") and groupe:
                annee = int(fy[2:])
                lignes.append((code, 1900 + annee if annee >= 50 else 2000 + annee, groupe))
    return pd.DataFrame(lignes, columns=["country_code", "exercice", "groupe"])


def charger(chemin: str = CHEMIN) -> Optional[pd.DataFrame]:
    """Le classement historique, téléchargé s'il manque ; None si indisponible."""
    try:
        if not os.path.exists(chemin):
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            reponse = requests.get(URL, timeout=120, headers={"User-Agent": "pib-mondial"})
            reponse.raise_for_status()
            with open(chemin, "wb") as f:
                f.write(reponse.content)
        return lire(chemin)
    except (requests.RequestException, OSError, ValueError, KeyError) as e:
        logging.warning(f"Classement historique des revenus indisponible ({e}) : groupes actuels conservés.")
        return None


def a_l_edition(cas: pd.DataFrame, groupes: Optional[pd.DataFrame], colonne: str = "income_group") -> pd.DataFrame:
    """
    Copie de `cas` (une ligne par pays et édition : country_code, vintage, annee_millesime)
    où `colonne` prend le groupe connu à la date de l'édition ; le groupe actuel reste à
    défaut. Sans classement historique, `cas` est rendu tel quel.
    """
    if groupes is None or cas.empty:
        return cas
    exercice = cas["annee_millesime"] + cas["vintage"].astype(str).str.startswith("F").astype(int)
    cle = pd.MultiIndex.from_arrays([cas["country_code"], exercice])
    historique = groupes.drop_duplicates(["country_code", "exercice"]).set_index(["country_code", "exercice"])["groupe"]
    a_la_date = pd.Series(historique.reindex(cle).to_numpy(), index=cas.index)
    sortie = cas.copy()
    sortie[colonne] = a_la_date.fillna(cas[colonne]) if colonne in cas else a_la_date
    return sortie
