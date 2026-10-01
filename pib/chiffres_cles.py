#!/usr/bin/env python3
"""
chiffres_cles.py
----------------
Chiffres clés cités dans la documentation, et où les corriger quand une relance les change.

La documentation (README, `docs/*.md`, `docs/documentation_gdp.tex`) cite en clair des
chiffres tirés des sorties : fourchettes du Canada, tirages conjoints, population calibrée,
calibration en temps réel. Une nouvelle édition du WEO les change tous. Ce module :

1. les recalcule depuis `data/processed/` (`FIGURES`), mis en forme comme dans le texte
   (virgule décimale, espace des milliers) ;
2. les compare à la dernière version publiée, `docs/chiffres_cles.json` (versionnée) ;
3. pour chaque chiffre qui a changé, liste les fichiers et lignes où sa forme ancienne
   apparaît encore (`MOTIFS` de chaque chiffre ; le LaTeX est lu sans `$`, `\\,` ni `{,}`).

Après correction de la documentation, `--enregistrer` met la version publiée à jour.

    python -m pib.chiffres_cles --data-dir data [--enregistrer]
"""

import os
import re
import json
import glob
import logging
import argparse
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIES = os.path.join(RACINE, "docs", "chiffres_cles.json")
DOCUMENTS = ("README.md", os.path.join("docs", "*.md"), os.path.join("docs", "*.tex"))


def fr(x: float, decimales: int = 0) -> str:
    """Nombre à la française : virgule décimale, espace pour les milliers (au-delà de 9 999)."""
    texte = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    entier = texte.split(",")[0].replace("-", "")
    return texte.replace(" ", "", 1) if len(entier.replace(" ", "")) == 4 else texte


def normaliser(ligne: str) -> str:
    """Ligne de LaTeX ramenée à du texte : sans `$`, avec `\\,` en espace, `\\%` en % et `{,}` en virgule."""
    return ligne.replace("$", "").replace("\\,", " ").replace("\\%", "%").replace("{,}", ",")


@dataclass
class Figure:
    nom: str
    description: str
    calcul: Callable                   # sorties -> {valeur: nombre}
    decimales: object                  # nombre de décimales, commun ou par valeur ({valeur: n})
    motifs: list = field(default_factory=list)   # formes du texte, avec {valeur}

    def valeurs(self, sorties: dict) -> dict:
        d = self.decimales
        return {k: fr(v, d.get(k, 1) if isinstance(d, dict) else d) for k, v in self.calcul(sorties).items()}


# ------------------------------------------------------------------ lecture des sorties

def lire_sorties(data_dir: str) -> dict:
    p = os.path.join(data_dir, "processed")
    fichiers = {"scenarios": "scenarios_pib_population.csv", "tirages": "scenarios_pib_tirages_controle.csv",
                "temps_reel": "gdp_bands_realtime_scores.csv", "population": "population_projection_errors.csv"}
    return {k: pd.read_csv(os.path.join(p, f)) for k, f in fichiers.items() if os.path.exists(os.path.join(p, f))}


def _scenario(s, pays, annee, scenario, colonne="pib_reel_par_habitant_usd_2015"):
    x = s["scenarios"]
    return float(x[(x["country_code"] == pays) & (x["year"] == annee) & (x["scenario"] == scenario)][colonne].iloc[0])


def _pct(s, pays, annee, scenario):
    return 100 * _scenario(s, pays, annee, scenario) / _scenario(s, pays, annee, "central_fmi")


def _bande(s, pays, annee, bas="bas", haut="haut"):
    return {"bas": _pct(s, pays, annee, bas), "haut": _pct(s, pays, annee, haut)}


def _niveaux(s, pays, annee):
    return {"bas": _scenario(s, pays, annee, "bas"), "haut": _scenario(s, pays, annee, "haut"),
            "central": _scenario(s, pays, annee, "central_fmi")}


def _population(s, pays, annee):
    return {k: _scenario(s, pays, annee, "central_fmi", f"population_millions_{c}")
            for k, c in (("centrale", "centrale"), ("basse", "basse"), ("haute", "haute"),
                         ("basse_calibree", "basse_calibree"), ("haute_calibree", "haute_calibree"))}


def _agregat(s, agregat, annee):
    x = s["tirages"]
    r = x[(x["agregat"] == agregat) & (x["year"] == annee)].iloc[0]
    return {"p10": r["tirages_p10_pct_central"], "p10_bas": r["tirages_p10_ic95_bas"],
            "p10_haut": r["tirages_p10_ic95_haut"], "p90": r["tirages_p90_pct_central"],
            "somme_bas": r["somme_des_bas_pct_central"], "somme_hauts": r["somme_des_hauts_pct_central"]}


def _temps_reel(s):
    r = s["temps_reel"][s["temps_reel"]["retenue"].astype(bool)].iloc[0]
    return {"couverture": r["couverture_pct"], "bas": r["couverture_pct_ic95_bas"], "haut": r["couverture_pct_ic95_haut"],
            "score": r["score_intervalle"], "score_pondere": r["score_intervalle_pondere_pib"]}


def _part_onu(s, horizon):
    x = s["population"]
    return {"part": 100 * float(x[(x["groupe"] == "tous") & (x["horizon"] == horizon)]["part_dans_bornes_onu"].iloc[0])}


QUATRE = "Canada, États-Unis, France, Royaume-Uni"

FIGURES = [
    Figure("canada_pib_hab_2031", "Canada, PIB par habitant 2031 : bas, haut, central ($ de 2015)",
           lambda s: _niveaux(s, "CAN", 2031), 0, ["{bas} $ (bas) à {haut} $ (haut) autour de {central} $"]),
    Figure("canada_pib_hab_2050", "Canada, PIB par habitant 2050 : bas, haut, central ($ de 2015)",
           lambda s: _niveaux(s, "CAN", 2050), 0, ["{bas} à {haut} $ autour de {central} $",
                                                  "{bas} $ à {haut} $ autour de {central} $"]),
    Figure("canada_bande_2031", "Canada, fourchette 2031 (% du central)", lambda s: _bande(s, "CAN", 2031), 0,
           ["| 2031 | {bas} % | {haut} % |", "{bas} à {haut} % de la trajectoire centrale en 2031"]),
    Figure("canada_bande_2040", "Canada, fourchette 2040 (% du central)", lambda s: _bande(s, "CAN", 2040), 0,
           ["| 2040 | {bas} % | {haut} % |"]),
    Figure("canada_bande_2050", "Canada, fourchette 2050 (% du central)", lambda s: _bande(s, "CAN", 2050), 0,
           ["| 2050 | {bas} % | {haut} % |", "{bas} à {haut} % du central", "de {bas} à {haut} % en 2050",
            "Canada 2050 : {bas} à {haut} %", "en 2050, de {bas} à {haut} %", "au lieu de {bas} à {haut} %",
            "Canada, {bas} à {haut} au lieu", "de {bas} à {haut} % du central pour le Canada"]),
    Figure("canada_elargi_2050", "Canada, variante élargie 2050 (% du central)",
           lambda s: _bande(s, "CAN", 2050, "bas_elargi", "haut_elargi"), 0,
           ["{bas} % | {haut} % |", "de {bas} à {haut} % du central", "Canada 2050: de {bas} à {haut} %"]),
    Figure("inde_bande_2050", "Inde, fourchette 2050 (% du central)", lambda s: _bande(s, "IND", 2050), 0,
           ["Inde 2050, {bas} à {haut} %", "Inde, {bas} à {haut} %", "Inde 2050 : {bas} à {haut} %",
            "Inde 2050, de {bas} à {haut} %"]),
    Figure("canada_population_2031", "Canada, population 2031 (millions)", lambda s: _population(s, "CAN", 2031), 1,
           ["| 2031 | {centrale} | {basse} – {haute} | {basse_calibree} – {haute_calibree} |"]),
    Figure("canada_population_2040", "Canada, population 2040 (millions)", lambda s: _population(s, "CAN", 2040), 1,
           ["| 2040 | {centrale} | {basse} – {haute} | {basse_calibree} – {haute_calibree} |"]),
    Figure("canada_population_2050", "Canada, population 2050 (millions)", lambda s: _population(s, "CAN", 2050), 1,
           ["| 2050 | {centrale} | {basse} – {haute} | {basse_calibree} – {haute_calibree} |",
            "{basse_calibree} à {haute_calibree} millions", "{basse} à {haute}, autour de {centrale}"]),
    Figure("tirages_tous_2031", "Tirages, tous les pays, 2031 (% du central)", lambda s: _agregat(s, "tous les pays", 2031), 1,
           ["| Tous les pays | 2031 | {p10} ({p10_bas} à {p10_haut}) – {p90} | {somme_bas} – {somme_hauts} |"]),
    Figure("tirages_tous_2050", "Tirages, tous les pays, 2050 (% du central)", lambda s: _agregat(s, "tous les pays", 2050), 1,
           ["| Tous les pays | 2050 | {p10} ({p10_bas} à {p10_haut}) – {p90} | {somme_bas} – {somme_hauts} |"]),
    Figure("tirages_tous_2050_arrondis", "Tirages, tous les pays, 2050, arrondis (% du central)",
           lambda s: _agregat(s, "tous les pays", 2050), 0,
           ["de {somme_bas} à {somme_hauts} % de la trajectoire centrale, contre {p10} à {p90} %",
            "de {p10} à {p90} % de la trajectoire centrale en 2050, contre {somme_bas} à {somme_hauts} %",
            "{p10} à {p90} % du central, au lieu de"]),
    Figure("tirages_quatre_2031", f"Tirages, {QUATRE}, 2031 (% du central)", lambda s: _agregat(s, QUATRE, 2031), 1,
           [f"| {QUATRE} | 2031 | {{p10}} ({{p10_bas}} à {{p10_haut}}) – {{p90}} | {{somme_bas}} – {{somme_hauts}} |",
            "{somme_bas} % contre {p10} %", "{somme_bas} contre {p10}"]),
    Figure("tirages_quatre_2050", f"Tirages, {QUATRE}, 2050 (% du central)", lambda s: _agregat(s, QUATRE, 2050), 1,
           [f"| {QUATRE} | 2050 | {{p10}} ({{p10_bas}} à {{p10_haut}}) – {{p90}} | {{somme_bas}} – {{somme_hauts}} |"]),
    Figure("tirages_g7_2050", "Tirages, G7, 2050 (% du central)", lambda s: _agregat(s, "G7", 2050), 1,
           ["| G7 | 2050 | {p10} ({p10_bas} à {p10_haut}) – {p90} | {somme_bas} – {somme_hauts} |"]),
    Figure("temps_reel", "Fourchettes éprouvées en temps réel, méthode retenue : couverture (%) et scores",
           _temps_reel, {"couverture": 1, "bas": 0, "haut": 0, "score": 1, "score_pondere": 1},
           ["{couverture} % ({bas} à {haut}) | {score} | {score_pondere}"]),
    Figure("population_onu_1an", "Part des erreurs passées dans les bornes de l'ONU, à 1 an (%)",
           lambda s: _part_onu(s, 1), 0, ["{part} % à 1 an"]),
    Figure("population_onu_20ans", "Part des erreurs passées dans les bornes de l'ONU, à 20 ans (%)",
           lambda s: _part_onu(s, 20), 0, ["{part} % à 20 ans"]),
]


# ------------------------------------------------------------------ comparaison

def calculer(sorties: dict, figures=FIGURES) -> dict:
    """Nom -> valeurs mises en forme ; un chiffre dont les sorties manquent est omis."""
    resultat = {}
    for f in figures:
        try:
            resultat[f.nom] = f.valeurs(sorties)
        except (KeyError, IndexError):
            logging.warning(f"Chiffre {f.nom} non calculable : sorties absentes.")
    return resultat


def occurrences(motifs: list, valeurs: dict, documents: dict) -> list:
    """(fichier, numéro de ligne, ligne) où apparaît l'un des motifs rempli avec `valeurs`."""
    textes = []
    for m in motifs:
        try:
            textes.append(m.format(**valeurs))
        except KeyError:
            continue
    trouves = []
    for chemin, lignes in documents.items():
        for i, ligne in enumerate(lignes, 1):
            texte = normaliser(ligne) if chemin.endswith(".tex") else ligne
            if any(t in texte for t in textes):
                trouves.append((chemin, i, ligne.strip()))
    return trouves


def lire_documents(racine: str = RACINE) -> dict:
    chemins = sorted({c for motif in DOCUMENTS for c in glob.glob(os.path.join(racine, motif))})
    return {os.path.relpath(c, racine): open(c, encoding="utf-8").read().splitlines() for c in chemins}


def comparer(publies: dict, actuels: dict, documents: dict, figures=FIGURES) -> list:
    """Chiffres changés : (nom, anciennes valeurs, nouvelles, occurrences des anciennes dans les documents)."""
    changes = []
    for f in figures:
        ancien, nouveau = publies.get(f.nom), actuels.get(f.nom)
        if ancien is None or nouveau is None or ancien == nouveau:
            continue
        changes.append((f.nom, ancien, nouveau, occurrences(f.motifs, ancien, documents)))
    return changes


def main():
    parser = argparse.ArgumentParser(description="Chiffres clés de la documentation : ce qui a changé, et où.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--enregistrer", action="store_true", help="publier les valeurs actuelles dans docs/")
    args = parser.parse_args()
    actuels = calculer(lire_sorties(args.data_dir))
    if args.enregistrer:
        with open(PUBLIES, "w", encoding="utf-8") as f:
            json.dump(actuels, f, indent=1, ensure_ascii=False)
        logging.info(f"-> {len(actuels)} chiffres publiés dans {os.path.relpath(PUBLIES, RACINE)}")
        return
    publies = json.load(open(PUBLIES, encoding="utf-8")) if os.path.exists(PUBLIES) else {}
    changes = comparer(publies, actuels, lire_documents())
    if not changes:
        logging.info(f"-> {len(actuels)} chiffres clés, aucun changement depuis la version publiée.")
        return
    lignes = [f"{len(changes)} chiffres clés ont changé depuis la version publiée :"]
    for nom, ancien, nouveau, ou in changes:
        lignes.append(f"  {nom} : " + ", ".join(f"{k} {ancien.get(k)} → {v}" for k, v in nouveau.items()
                                              if ancien.get(k) != v))
        lignes += [f"      {fichier}:{n}" for fichier, n, _ in ou] or ["      (ancienne forme introuvable dans les documents)"]
    lignes.append("Corriger la documentation, puis : python -m pib.chiffres_cles --enregistrer")
    logging.warning("\n".join(lignes))


if __name__ == "__main__":
    main()
