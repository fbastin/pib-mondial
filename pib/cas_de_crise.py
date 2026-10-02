#!/usr/bin/env python3
"""
cas_de_crise.py
---------------
Cas d'étude d'une récession mondiale dans les prévisions du FMI : la chute avait-elle
été prévue, le rebond qui a suivi l'avait-il été, et le niveau du PIB a-t-il retrouvé
la trajectoire attendue avant le choc ?

Quatre tableaux, écrits dans `data/processed/` :

- `weo_cas_<année>_croissance.csv` : croissance de l'année du choc et des quatre
  suivantes, selon chaque édition, pour le monde, les grands agrégats et les premières
  économies ;
- `weo_cas_<année>_reculs.csv` : pays dont chaque édition annonçait le recul l'année du
  choc, face à ceux qui ont reculé ;
- `weo_cas_<année>_rebond.csv` : erreur de chaque édition sur la croissance de l'année
  suivante ;
- `weo_cas_<année>_niveaux.csv` : niveau du PIB en volume projeté par chaque édition et
  réalisé, base 100 deux ans avant le choc.

Le réalisé se lit de deux façons : la ré-estimation du FMI un an après, référence de
l'évaluation, et l'estimation actuelle, tirée de la dernière édition archivée
(`data/raw/weo_archive/`), qui intègre toutes les révisions des comptes depuis.

Avec `--trafic`, le PIB est confronté au trafic aérien (passagers) : le retard du trafic
sur sa tendance d'avant le choc s'explique-t-il par l'écart du PIB à sa projection
d'avant le choc ? Trois tableaux de plus, `weo_cas_<année>_trafic*.csv` (voir
`trafic_et_pib`). Le trafic vient de sources homogènes dans le temps : Eurostat pour 30
pays européens, comptés par aéroport ; la Banque Mondiale (données de l'OACI) pour les
États-Unis seulement, sa série mondiale présentant une rupture de couverture en 2010.

    python -m pib.cas_de_crise --annee 2009      # crise financière
    python -m pib.cas_de_crise --annee 2009 --trafic
    python -m pib.cas_de_crise --annee 2020      # pandémie

Le classeur historique ne contient que les éditions d'avril et d'octobre : les mises à
jour intermédiaires du WEO (janvier, juillet, et celle de novembre 2008) n'y figurent pas.
"""

import os
import sys
import logging
import argparse

import numpy as np
import pandas as pd

from pib.evaluate_forecasts import (
    CODE_MONDE,
    WEO_VERS_ISO3,
    _moyenne_ponderee,
    contexte_pays,
    exclure_agregats,
    lire_base_historique,
    realise_selon_fmi,
)
from pib.revisions_weo import editions_archivees
from pib.http_utils import get_json
from pib.fetch_historical_gdp import fetch_worldbank_indicator
from pib.gdp_pipeline import unified_csv_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Agrégats du WEO suivis à côté des pays : monde, économies avancées, émergentes
AGREGATS = {CODE_MONDE: "Monde", "G110": "Économies avancées", "G200": "Économies émergentes et en développement"}
PREMIERES_ECONOMIES = 10

# Années après le choc où le niveau est comparé : le choc, le rebond, puis la moyenne période
ANNEES_NIVEAU = (0, 1, 2, 4)

# Trafic aérien. Eurostat (`avia_paoc`, passagers transportés, par pays déclarant) : codes
# du pays vers ISO3. Les États-Unis viennent de la Banque Mondiale (`IS.AIR.PSGR`).
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoc"
PAYS_EUROSTAT = dict(AT="AUT", BE="BEL", BG="BGR", CY="CYP", CZ="CZE", DE="DEU", DK="DNK", EE="EST", EL="GRC",
                     ES="ESP", FI="FIN", FR="FRA", HR="HRV", HU="HUN", IE="IRL", IT="ITA", LT="LTU", LU="LUX",
                     LV="LVA", MT="MLT", NL="NLD", PL="POL", PT="PRT", RO="ROU", SE="SWE", SI="SVN", SK="SVK",
                     UK="GBR", NO="NOR", CH="CHE", IS="ISL")
PAYS_BANQUE_MONDIALE = ("USA",)

# Élasticités-revenu du trafic retenues pour traduire l'écart de PIB en écart de trafic :
# autour de 1,19, la valeur de base de la méta-analyse de Gallet et Doucouliagos (2014)
ELASTICITES = (1.0, 1.5)
# Années de la tendance du trafic avant le choc, et délais après le choc
ANNEES_TENDANCE = 3
DELAIS_TRAFIC = (1, 4)


def editions_autour(annee: int) -> list:
    """Éditions de l'année précédant le choc à l'année qui le suit : avril et octobre."""
    return [f"{saison}{a}" for a in (annee - 1, annee, annee + 1) for saison in ("S", "F")]


def estimation_actuelle(archive: str) -> pd.Series:
    """
    Croissance réelle selon la dernière édition archivée, par pays et année, aux codes de
    la Banque Mondiale. Le classeur historique ne peut pas la donner : chaque édition n'y
    ré-estime que les deux années précédentes.
    """
    editions = editions_archivees(archive)
    if not editions:
        return pd.Series(dtype=float, index=pd.MultiIndex.from_arrays([[], []], names=["country_code", "year"]))
    d = pd.read_csv(os.path.join(archive, f"WEO_{editions[-1]}.csv.gz"))
    d = d[d["indicator"] == "NGDP_RPCH"].assign(country_code=lambda x: x["country_code"].replace(WEO_VERS_ISO3))
    logging.info(f"Estimation actuelle : édition {editions[-1]}.")
    return d.set_index(["country_code", "year"])["value"]


def croissance_par_edition(base: pd.DataFrame, annee: int, codes: dict, actuel: pd.Series) -> pd.DataFrame:
    """
    Croissance de `annee` à la dernière année des niveaux (`ANNEES_NIVEAU`) : le choc, le
    rebond, puis la reprise. Selon chaque édition (`editions_autour`), la ré-estimation du
    FMI un an après (`realise_fmi`) et l'estimation actuelle (`actuel`).
    """
    editions = editions_autour(annee)
    premier = realise_selon_fmi(base).set_index(["country_code", "year"])["realise_fmi"]
    lignes = []
    for visee in range(annee, annee + max(ANNEES_NIVEAU) + 1):
        d = base[(base["year"] == visee) & base["vintage"].isin(editions) & base["country_code"].isin(codes)]
        t = d.pivot_table(index="country_code", columns="vintage", values="valeur").reindex(index=list(codes),
                                                                                           columns=editions)
        t.insert(0, "annee_visee", visee)
        t.insert(0, "nom", [codes[c] for c in t.index])
        t["realise_fmi"] = [premier.get((c, visee), np.nan) for c in t.index]
        t["estimation_actuelle"] = [actuel.get((c, visee), np.nan) for c in t.index]
        lignes.append(t)
    return pd.concat(lignes).rename_axis("country_code").reset_index()


def reculs_annonces(pays: pd.DataFrame, annee: int, poids: pd.Series) -> pd.DataFrame:
    """
    Pour chaque édition, les pays dont elle annonçait le recul en `annee`, face à ceux qui
    ont reculé selon la ré-estimation à un an : nombre, part du PIB mondial (`poids`, par
    pays), et part des reculs survenus que l'édition annonçait.
    """
    realise = realise_selon_fmi(pays)
    realise = realise[realise["year"] == annee].set_index("country_code")["realise_fmi"]
    lignes = []
    for edition in editions_autour(annee)[:4]:
        prevu = pays[(pays["year"] == annee) & (pays["vintage"] == edition)].set_index("country_code")["valeur"]
        if prevu.empty:
            continue
        reel = realise.reindex(prevu.index)
        connus = reel.notna()
        w = poids.reindex(prevu.index)
        annonce, survenu = prevu < 0, reel < 0
        lignes.append({
            "edition": edition, "pays": len(prevu),
            "recul_annonce": int(annonce.sum()),
            "recul_annonce_part_pib_pct": _moyenne_ponderee(annonce.astype(float), w) * 100,
            "recul_survenu": int(survenu.sum()),
            "recul_survenu_part_pib_pct": _moyenne_ponderee(survenu[connus].astype(float), w[connus]) * 100,
            "reculs_survenus_annonces_pct": (annonce & survenu).sum() / survenu.sum() * 100 if survenu.any() else np.nan,
        })
    return pd.DataFrame(lignes).round(2)


def erreurs_du_rebond(pays: pd.DataFrame, annee: int, poids: pd.Series) -> pd.DataFrame:
    """
    Erreur de chaque édition sur la croissance de `annee + 1`, contre la ré-estimation à un
    an (prévu − réalisé, en points) : médiane, pondérée par le PIB, et part des pays dont le
    rebond a été sous-estimé.
    """
    visee = annee + 1
    realise = realise_selon_fmi(pays)
    realise = realise[realise["year"] == visee].set_index("country_code")["realise_fmi"]
    lignes = []
    for edition in editions_autour(annee):
        prevu = pays[(pays["year"] == visee) & (pays["vintage"] == edition)].set_index("country_code")["valeur"]
        erreur = (prevu - realise.reindex(prevu.index)).dropna()
        if erreur.empty:
            continue
        lignes.append({"edition": edition, "annee_visee": visee, "pays": len(erreur),
                       "erreur_mediane": erreur.median(),
                       "erreur_ponderee_pib": _moyenne_ponderee(erreur, poids.reindex(erreur.index)),
                       "rebond_sous_estime_pct": (erreur < 0).mean() * 100})
    return pd.DataFrame(lignes).round(3)


def indice_de_niveau(croissance: pd.Series, debut: int, fin: int) -> pd.Series:
    """Niveau base 100 l'année précédant `debut`, en enchaînant les croissances de `debut` à `fin`."""
    annees = range(debut, fin + 1)
    return pd.Series(100 * np.cumprod(1 + croissance.reindex(annees).to_numpy() / 100), index=annees)


def niveaux_par_edition(base: pd.DataFrame, annee: int, codes: dict, actuel: pd.Series) -> pd.DataFrame:
    """
    Niveau du PIB en volume, base 100 deux ans avant le choc, aux années `annee + k`
    (`ANNEES_NIVEAU`) : projeté par la dernière édition d'avant le choc (octobre de l'année
    précédente) et par les suivantes, puis réalisé — ré-estimations à un an enchaînées
    (`realise_fmi`), et estimation actuelle (`actuel`). Chaque édition enchaîne ses propres
    valeurs : estimations pour les années écoulées, projections ensuite. Une édition qui
    ne projette pas jusqu'à une année la laisse vide (avril 2020 s'arrêtait en 2021).
    """
    debut, fin = annee - 1, annee + max(ANNEES_NIVEAU)
    editions = editions_autour(annee)[1:5]
    premier = realise_selon_fmi(base).set_index(["country_code", "year"])["realise_fmi"]
    lignes = []
    for code, nom in codes.items():
        series = {e: base[(base["country_code"] == code) & (base["vintage"] == e)].set_index("year")["valeur"]
                  for e in editions}
        for source, realise in (("realise_fmi", premier), ("estimation_actuelle", actuel)):
            series[source] = (realise.xs(code, level="country_code") if code in realise.index.get_level_values(0)
                              else pd.Series(dtype=float))
        for source, croissance in series.items():
            niveau = indice_de_niveau(croissance, debut, fin)
            lignes.append({"country_code": code, "nom": nom, "source": source,
                           **{f"niveau_{annee + k}": niveau[annee + k] for k in ANNEES_NIVEAU}})
    return pd.DataFrame(lignes).round(2)


def decoder_jsonstat(donnees: dict) -> pd.DataFrame:
    """Réponse JSON-stat d'Eurostat -> une ligne par (geo, time) : geo, year, value."""
    dims, tailles = donnees["id"], donnees["size"]
    inverses = {d: {i: v for v, i in donnees["dimension"][d]["category"]["index"].items()} for d in dims}
    lignes = []
    for cle, valeur in donnees.get("value", {}).items():
        reste, coords = int(cle), {}
        for dim, taille in zip(reversed(dims), reversed(tailles)):
            coords[dim] = inverses[dim][reste % taille]
            reste //= taille
        lignes.append({"geo": coords["geo"], "year": int(coords["time"]), "value": float(valeur)})
    return pd.DataFrame(lignes, columns=["geo", "year", "value"])


def trafic_aerien(debut: int, fin: int) -> pd.DataFrame:
    """
    Passagers aériens par pays et année (country_code, year, passagers, source) : Eurostat
    pour `PAYS_EUROSTAT`, comptés par aéroport ; Banque Mondiale pour `PAYS_BANQUE_MONDIALE`.
    """
    eurostat = decoder_jsonstat(get_json(EUROSTAT, params={
        "format": "JSON", "lang": "en", "freq": "A", "unit": "PAS", "tra_meas": "PAS_CRD", "tra_cov": "TOTAL",
        "schedule": "TOTAL", "geo": list(PAYS_EUROSTAT), "sinceTimePeriod": str(debut), "untilTimePeriod": str(fin)}))
    eurostat = eurostat.assign(country_code=eurostat["geo"].map(PAYS_EUROSTAT), source="Eurostat")
    bm = fetch_worldbank_indicator("IS.AIR.PSGR", debut, fin, set())
    bm = bm[bm["country_code"].isin(PAYS_BANQUE_MONDIALE)].assign(source="Banque Mondiale (OACI)")
    colonnes = ["country_code", "year", "value", "source"]
    return (pd.concat([eurostat[colonnes], bm[colonnes]], ignore_index=True)
            .rename(columns={"value": "passagers"}))


def _croissance_cumulee(croissance: pd.Series, debut: int, fin: int) -> float:
    """Log du rapport des niveaux de `debut` à `fin`, en enchaînant les croissances (%) ; NaN si un taux manque."""
    taux = croissance.reindex(range(debut + 1, fin + 1))
    return float(np.log1p(taux / 100).sum()) if taux.notna().all() else np.nan


def trafic_et_pib(trafic: pd.DataFrame, base: pd.DataFrame, actuel: pd.Series, annee: int) -> pd.DataFrame:
    """
    Par pays : croissance du trafic et du PIB, en log, de l'année de base (deux ans avant
    le choc) à chaque année `annee + k`, `k` parcourant `DELAIS_TRAFIC`, et sur les `ANNEES_TENDANCE`
    années précédant la base.

    - `croissance_trafic_*` : passagers ;
    - `croissance_pib_*` : PIB en volume réalisé (estimation actuelle) ;
    - `croissance_pib_projetee_*` : PIB que projetait l'édition d'octobre précédant le choc ;
    - `ecart_pib_*` : réalisé moins projeté, la surprise sur le PIB.
    """
    base_annee = annee - 2
    edition = f"F{annee - 1}"
    passagers = trafic.pivot_table(index="country_code", columns="year", values="passagers")
    sources = trafic.drop_duplicates("country_code").set_index("country_code")["source"]
    lignes = []
    for code in passagers.index:
        p = passagers.loc[code]
        reel = actuel.xs(code, level=0) if code in actuel.index.get_level_values(0) else pd.Series(dtype=float)
        projete = base[(base["country_code"] == code) & (base["vintage"] == edition)].set_index("year")["valeur"]
        debut = base_annee - ANNEES_TENDANCE
        ligne = {"country_code": code, "source": sources[code], f"passagers_{base_annee}": p.get(base_annee),
                 "croissance_trafic_avant": np.log(p.get(base_annee) / p.get(debut)) if p.get(debut, 0) > 0 else np.nan,
                 "croissance_pib_avant": _croissance_cumulee(reel, debut, base_annee)}
        for k in DELAIS_TRAFIC:
            fin = annee + k
            ligne[f"croissance_trafic_{fin}"] = (np.log(p.get(fin) / p.get(base_annee))
                                                 if p.get(fin, 0) > 0 and p.get(base_annee, 0) > 0 else np.nan)
            ligne[f"croissance_pib_{fin}"] = _croissance_cumulee(reel, base_annee, fin)
            ligne[f"croissance_pib_projetee_{fin}"] = _croissance_cumulee(projete, base_annee, fin)
            ligne[f"ecart_pib_{fin}"] = ligne[f"croissance_pib_{fin}"] - ligne[f"croissance_pib_projetee_{fin}"]
        lignes.append(ligne)
    return pd.DataFrame(lignes)


def regressions_trafic(table: pd.DataFrame, annee: int) -> pd.DataFrame:
    """
    D'un pays européen à l'autre, croissance du trafic régressée sur celle du PIB : avant
    le choc, puis de la base à chaque délai. Pente (élasticité apparente), IC à 95 %, R².
    """
    europe = table[table["source"] == "Eurostat"]
    periodes = [("avant", f"{annee - 2 - ANNEES_TENDANCE}-{annee - 2}")]
    periodes += [(str(annee + k), f"{annee - 2}-{annee + k}") for k in DELAIS_TRAFIC]
    lignes = []
    for suffixe, libelle in periodes:
        x = europe.dropna(subset=[f"croissance_trafic_{suffixe}", f"croissance_pib_{suffixe}"])
        if len(x) < 5:
            continue
        pib, trafic = x[f"croissance_pib_{suffixe}"], x[f"croissance_trafic_{suffixe}"]
        pente, constante = np.polyfit(pib, trafic, 1)
        residus = trafic - (constante + pente * pib)
        erreur_type = np.sqrt((residus ** 2).sum() / (len(x) - 2) / ((pib - pib.mean()) ** 2).sum())
        lignes.append({"periode": libelle, "pays": len(x), "pente": pente, "ic95_bas": pente - 1.96 * erreur_type,
                       "ic95_haut": pente + 1.96 * erreur_type, "r2": pib.corr(trafic) ** 2})
    return pd.DataFrame(lignes).round(3)


def synthese_trafic(table: pd.DataFrame, pib_base: pd.Series, annee: int) -> pd.DataFrame:
    """
    Pour l'Europe (somme des pays d'Eurostat) et les États-Unis, à chaque délai :

    - `ecart_trafic` : croissance du trafic depuis la base moins sa tendance d'avant le
      choc (croissance annuelle moyenne des `ANNEES_TENDANCE` années précédant la base) ;
    - `ecart_pib` : croissance du PIB réalisée moins projetée avant le choc, les pays
      pondérés par leur PIB de l'année de base (`pib_base`) ;
    - `ecart_trafic_du_pib_*` et `part_expliquee_*` : l'écart de PIB traduit en écart de
      trafic par chaque élasticité de `ELASTICITES`, et la part du retard du trafic qu'il
      représente.

    En log × 100 (écarts de l'ordre de quelques dizaines de %).
    """
    base_annee = annee - 2
    groupes = {"Europe (Eurostat)": table["source"] == "Eurostat",
               "États-Unis": table["country_code"].isin(PAYS_BANQUE_MONDIALE)}
    lignes = []
    for nom, masque in groupes.items():
        for k in DELAIS_TRAFIC:
            fin = annee + k
            x = table[masque].dropna(subset=["croissance_trafic_avant", f"croissance_trafic_{fin}",
                                             f"croissance_pib_{fin}", f"croissance_pib_projetee_{fin}"])
            x = x[x["country_code"].isin(pib_base.dropna().index)]
            if x.empty:
                continue
            passagers = x[f"passagers_{base_annee}"]
            debut = passagers * np.exp(-x["croissance_trafic_avant"])
            tendance = np.log(passagers.sum() / debut.sum()) / ANNEES_TENDANCE
            trafic = np.log((passagers * np.exp(x[f"croissance_trafic_{fin}"])).sum() / passagers.sum())
            y = pib_base.reindex(x["country_code"]).to_numpy()
            pib = np.log((y * np.exp(x[f"croissance_pib_{fin}"])).sum() / y.sum())
            projete = np.log((y * np.exp(x[f"croissance_pib_projetee_{fin}"])).sum() / y.sum())
            ecart_trafic = trafic - tendance * (fin - base_annee)
            ligne = {"groupe": nom, "annee": fin, "pays": len(x), "croissance_trafic": trafic * 100,
                     "tendance_trafic_annuelle": tendance * 100, "ecart_trafic": ecart_trafic * 100,
                     "croissance_pib": pib * 100, "croissance_pib_projetee": projete * 100,
                     "ecart_pib": (pib - projete) * 100}
            for e in ELASTICITES:
                ligne[f"ecart_trafic_du_pib_{e:g}"] = e * (pib - projete) * 100
                ligne[f"part_expliquee_{e:g}_pct"] = (e * (pib - projete) / ecart_trafic * 100
                                                      if ecart_trafic < 0 else np.nan)
            lignes.append(ligne)
    return pd.DataFrame(lignes).round(2)


def main():
    parser = argparse.ArgumentParser(description="Une récession mondiale dans les prévisions du FMI.")
    parser.add_argument("--annee", type=int, default=2009, help="Année du recul (2009, 2020…)")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--classeur", type=str, default=None, help="Chemin du classeur WEOhistorical.xlsx")
    parser.add_argument("--archive", type=str, default=None,
                        help="Archive des éditions (par défaut : weo_archive/ à côté du classeur)")
    parser.add_argument("--trafic", action="store_true",
                        help="Confronter le PIB au trafic aérien (Eurostat, Banque Mondiale)")
    args = parser.parse_args()

    chemin = args.classeur or os.path.join(args.data_dir, "raw", "WEOhistorical.xlsx")
    try:
        base = lire_base_historique(chemin, "ngdp_rpch")
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        sys.exit(1)
    manquantes = [e for e in editions_autour(args.annee) if e not in set(base["vintage"])]
    if manquantes:
        logging.error(f"Éditions absentes du classeur : {', '.join(manquantes)}.")
        sys.exit(1)

    pays = exclure_agregats(base, args.data_dir)
    poids, _ = contexte_pays(args.data_dir)
    if poids.empty:
        logging.error("Série du pipeline indisponible : poids et premières économies inconnus.")
        sys.exit(1)
    avant = poids[poids["year"] == args.annee - 1].set_index("country_code")["poids_pib"]
    premieres = avant[avant.index.isin(set(pays["country_code"]))].nlargest(PREMIERES_ECONOMIES).index
    noms = pays.drop_duplicates("country_code").set_index("country_code")["country"]
    codes = {**AGREGATS, **{c: noms[c] for c in premieres}}

    actuel = estimation_actuelle(args.archive or os.path.join(os.path.dirname(chemin), "weo_archive"))
    if actuel.empty:
        logging.warning("Aucune édition archivée : pas d'estimation actuelle.")

    processed = os.path.join(args.data_dir, "processed")
    os.makedirs(processed, exist_ok=True)
    tableaux = {
        "croissance": croissance_par_edition(base, args.annee, codes, actuel),
        "reculs": reculs_annonces(pays, args.annee, poids[poids["year"] == args.annee].set_index("country_code")["poids_pib"]),
        "rebond": erreurs_du_rebond(pays, args.annee, poids[poids["year"] == args.annee + 1].set_index("country_code")["poids_pib"]),
        "niveaux": niveaux_par_edition(base, args.annee, codes, actuel),
    }
    if args.trafic:
        base_annee = args.annee - 2
        trafic = trafic_aerien(base_annee - ANNEES_TENDANCE, args.annee + max(DELAIS_TRAFIC))
        table = trafic_et_pib(trafic, base, actuel, args.annee)
        unifie = pd.read_csv(unified_csv_path(args.data_dir), usecols=["country_code", "year", "GDP_Real_Billions_USD"])
        pib_base = unifie[unifie["year"] == base_annee].set_index("country_code")["GDP_Real_Billions_USD"]
        tableaux.update({"trafic": table, "trafic_regressions": regressions_trafic(table, args.annee),
                         "trafic_synthese": synthese_trafic(table, pib_base, args.annee)})
    for nom, tableau in tableaux.items():
        chemin_csv = os.path.join(processed, f"weo_cas_{args.annee}_{nom}.csv")
        tableau.to_csv(chemin_csv, index=False, encoding="utf-8-sig")
        logging.info(f"{chemin_csv} :\n{tableau.round(1).to_string(index=False)}")


if __name__ == "__main__":
    main()
