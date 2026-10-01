#!/usr/bin/env python3
"""
miroir.py
---------
Copie le dépôt et ses sorties vers un dossier, par exemple un dossier partagé.

Fichiers copiés : ceux que git suit ou ne fait pas ignorer, plus les sorties non versionnées
(`outputs/`, `data/processed/`, `data/plus_recent/`, métadonnées d'extraction, réponse brute
du FMI). Un fichier n'est copié que si son contenu diffère de celui de la destination
(empreinte SHA-256), puis vérifié après copie. Rien n'est jamais supprimé de la
destination : un fichier qu'on y a laissé exprès (pour un projet qui le lit encore) y reste.

    python miroir.py --destination "/chemin/du/dossier" [--simulation]
"""

import os
import sys
import shutil
import hashlib
import argparse
import subprocess

RACINE = os.path.dirname(os.path.abspath(__file__))
DOSSIERS_DE_SORTIE = ("outputs", os.path.join("data", "processed"), os.path.join("data", "plus_recent"))
FICHIERS_DE_SORTIE = (os.path.join("data", "extraction_metadata.json"), os.path.join("data", "raw", "gdp_imf_weo_raw.json"))


def empreinte(chemin: str) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def liste_fichiers(racine: str = RACINE) -> list:
    """Chemins relatifs à copier : suivis ou non ignorés par git, et sorties non versionnées."""
    git = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=racine, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    sorties = [os.path.relpath(os.path.join(d, f), racine)
               for dossier in DOSSIERS_DE_SORTIE for d, _, fs in os.walk(os.path.join(racine, dossier)) for f in fs]
    sorties += [f for f in FICHIERS_DE_SORTIE if os.path.isfile(os.path.join(racine, f))]
    return sorted({f.replace(os.sep, "/") for f in git + sorties if os.path.isfile(os.path.join(racine, f))})


def copier(fichiers: list, racine: str, destination: str, simulation: bool = False) -> dict:
    """
    Copie chaque fichier dont le contenu diffère à la destination ; ne supprime rien.
    Rend {"copies": [...], "identiques": n, "erreurs": [...]}.
    """
    bilan = {"copies": [], "identiques": 0, "erreurs": []}
    for rel in fichiers:
        source, cible = os.path.join(racine, rel), os.path.join(destination, rel)
        h = empreinte(source)
        if os.path.isfile(cible) and empreinte(cible) == h:
            bilan["identiques"] += 1
            continue
        if not simulation:
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            shutil.copyfile(source, cible)
            if empreinte(cible) != h:
                bilan["erreurs"].append(rel)
                continue
        bilan["copies"].append(rel)
    return bilan


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--destination", required=True)
    p.add_argument("--simulation", action="store_true", help="lister sans copier")
    a = p.parse_args(argv)
    if not os.path.isdir(a.destination):
        print(f"Destination introuvable : {a.destination}", file=sys.stderr)
        return 2
    bilan = copier(liste_fichiers(), RACINE, a.destination, a.simulation)
    for rel in bilan["copies"]:
        print(("à copier " if a.simulation else "copié    ") + rel)
    for rel in bilan["erreurs"]:
        print("ERREUR   " + rel)
    print(f"{'à copier' if a.simulation else 'copiés'} : {len(bilan['copies'])}, identiques : {bilan['identiques']}, "
          f"erreurs : {len(bilan['erreurs'])}")
    return 1 if bilan["erreurs"] else 0


if __name__ == "__main__":
    sys.exit(main())
