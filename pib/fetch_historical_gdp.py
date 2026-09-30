#!/usr/bin/env python3
"""
fetch_historical_gdp.py
-----------------------
Récupère les données historiques du PIB (GDP) par pays sur une période d'au moins 20 ans
depuis la Banque Mondiale (World Bank WDI API).

Indicateurs inclus :
- PIB Nominal (USD courants)
- Taux de croissance annuel du PIB (%)
- PIB par habitant (USD courants)
- PIB PPA (USD internationaux courants)
- PIB en volume (USD constants 2015) et à PPA constante ($ internationaux 2021)
"""

import os
import sys
import logging
import argparse
import pandas as pd
from datetime import datetime
from typing import Dict

from pib.http_utils import get_json

# Configuration du logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

WB_API = "https://api.worldbank.org/v2"

# Indicateurs de la Banque Mondiale.
# Les séries en prix courants (CD) subissent l'inflation et les mouvements de change ;
# les séries en prix constants (KD) mesurent le volume, à prix et taux de change figés.
WB_INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP_Nominal_USD",
    "NY.GDP.MKTP.KD.ZG": "GDP_Growth_Annual_Pct",
    "NY.GDP.PCAP.CD": "GDP_Per_Capita_USD",
    "NY.GDP.MKTP.PP.CD": "GDP_PPP_USD",
    "NY.GDP.MKTP.KD": "GDP_Real_USD",          # USD constants 2015
    "NY.GDP.MKTP.PP.KD": "GDP_Real_PPP_Intl",  # $ internationaux constants 2021
    "SP.POP.TOTL": "Population",               # habitants, au milieu de l'année
}


# Millésime de chaque série, tel que déclaré par l'API (champ `lastupdated`).
# La Banque Mondiale révise son historique : sans cette trace, impossible de savoir
# de quelle version proviennent des chiffres déjà exportés.
WB_LAST_UPDATED: Dict[str, str] = {}


def fetch_worldbank_pages(url: str, params: dict) -> tuple:
    """
    Parcourt toutes les pages d'une réponse de l'API Banque Mondiale.

    Retourne l'en-tête de la première page et la concaténation des enregistrements.
    Une réponse tronquée à sa première page passerait inaperçue : les pages suivantes
    sont donc demandées tant que l'en-tête en annonce.
    """
    entete, enregistrements, page = {}, [], 1
    while True:
        data = get_json(url, params={**params, "page": page})
        if not isinstance(data, list) or len(data) < 2:
            message = data[0].get("message") if isinstance(data, list) and data else data
            raise RuntimeError(f"Réponse inattendue de {url} : {message}")
        if page == 1:
            entete = data[0] if isinstance(data[0], dict) else {}
        enregistrements.extend(data[1] or [])
        if page >= int(entete.get("pages", 1) or 1):
            return entete, enregistrements
        page += 1


def fetch_worldbank_country_codes() -> Dict[str, str]:
    """
    Récupère la liste officielle des pays (hors agrégats) depuis l'API de métadonnées
    de la Banque Mondiale. Un agrégat se reconnaît à sa région codée "NA".

    Retourne, pour chaque code ISO3 de vrai pays, son groupe de revenu selon la
    classification courante de la Banque Mondiale (`HIC`, `UMC`, `LMC`, `LIC`, ou `INX`
    s'il n'est pas classé). Sans cette liste, rien ne distingue *World* ou *OECD members*
    d'un pays : l'échec interrompt la collecte plutôt que de laisser des agrégats entrer
    dans les classements.
    """
    logging.info("Récupération de la liste officielle des pays (métadonnées Banque Mondiale)...")
    _, items = fetch_worldbank_pages(f"{WB_API}/country", {"format": "json", "per_page": 400})

    countries = {
        item["id"]: (item.get("incomeLevel") or {}).get("id") or "INX"
        for item in items
        if item.get("region", {}).get("id") not in (None, "NA")
    }
    if not countries:
        raise RuntimeError("Liste des pays de la Banque Mondiale vide.")

    logging.info(f"-> {len(countries)} pays identifiés ({len(items) - len(countries)} agrégats exclus).")
    return countries


def fetch_worldbank_indicator(indicator_code: str, start_year: int, end_year: int,
                              country_codes: set) -> pd.DataFrame:
    """
    Interroge l'API de la Banque Mondiale pour un indicateur spécifique sur la plage d'années spécifiée.

    `country_codes` : ensemble des codes ISO3 de vrais pays servant à marquer les agrégats.
    Lève `RuntimeError` si l'indicateur ne peut être obtenu : une colonne manquante
    viderait silencieusement toutes les métriques qui en dépendent.
    """
    indicator_name = WB_INDICATORS.get(indicator_code, indicator_code)
    logging.info(f"Récupération de l'indicateur Banque Mondiale '{indicator_code}' ({indicator_name})...")

    entete, items = fetch_worldbank_pages(
        f"{WB_API}/country/all/indicator/{indicator_code}",
        {"format": "json", "per_page": 20000, "date": f"{start_year}:{end_year}"})

    if entete.get("lastupdated"):
        WB_LAST_UPDATED[indicator_code] = entete["lastupdated"]

    records = []
    for item in items:
        country_iso = item.get("countryiso3code")
        country_name = item.get("country", {}).get("value")
        year = item.get("date")
        value = item.get("value")

        if country_iso and year and value is not None:
            records.append({
                "country_code": country_iso,
                "country_name": country_name,
                "year": int(year),
                "indicator": indicator_name,
                "value": float(value),
                "is_aggregate": country_iso not in country_codes
            })

    if not records:
        raise RuntimeError(f"Aucune donnée renvoyée pour l'indicateur {indicator_code}.")

    df = pd.DataFrame(records)
    logging.info(f"-> {len(df)} enregistrements récupérés pour {indicator_name}.")
    return df


def fetch_world_per_capita_growth(start_year: int = 1961, end_year: int = None) -> pd.Series:
    """
    Croissance du PIB mondial réel par habitant (agrégat `WLD`, `NY.GDP.PCAP.KD.ZG`), en %,
    depuis `start_year` : son recul définit les récessions mondiales (1975, 1982, 1991,
    2009, 2020), dont la fréquence sert aux probabilités de récession. Lève `RuntimeError`
    si la série ne peut être obtenue.
    """
    end_year = end_year or datetime.now().year
    reponse = get_json(f"{WB_API}/country/WLD/indicator/NY.GDP.PCAP.KD.ZG",
                       params={"format": "json", "date": f"{start_year}:{end_year}", "per_page": 1000})
    if not isinstance(reponse, list) or len(reponse) < 2 or not reponse[1]:
        raise RuntimeError("Croissance mondiale par habitant indisponible.")
    serie = pd.Series({int(x["date"]): float(x["value"]) for x in reponse[1] if x["value"] is not None},
                      name="croissance_pib_mondial_par_habitant").sort_index()
    serie.index.name = "year"
    return serie


def fetch_all_historical_gdp(start_year: int = 2000, end_year: int = 2024) -> pd.DataFrame:
    """
    Récupère l'ensemble des indicateurs PIB historiques de la Banque Mondiale.

    Lève `RuntimeError` si une source ou un indicateur reste injoignable.
    """
    country_codes = fetch_worldbank_country_codes()

    dfs = [fetch_worldbank_indicator(code, start_year, end_year, country_codes=country_codes)
           for code in WB_INDICATORS]
    combined_df = pd.concat(dfs, ignore_index=True)

    # Pivot pour obtenir une structure propre : country_code, country_name, year, indicator columns
    pivoted_df = combined_df.pivot_table(
        index=["country_code", "country_name", "year", "is_aggregate"],
        columns="indicator",
        values="value"
    ).reset_index()

    # Groupe de revenu (classification courante, appliquée à toute la période)
    pivoted_df["income_group"] = pivoted_df["country_code"].map(country_codes)

    pivoted_df.sort_values(by=["country_code", "year"], inplace=True)
    return pivoted_df


def main():
    parser = argparse.ArgumentParser(description="Extraction des données historiques de GDP (>20 ans).")
    parser.add_argument("--start-year", type=int, default=2000, help="Année de début (par défaut: 2000 pour 25+ ans)")
    parser.add_argument("--end-year", type=int, default=2024, help="Année de fin (par défaut: 2024)")
    parser.add_argument("--output-dir", type=str, default="data", help="Dossier de sortie des données")
    args = parser.parse_args()

    raw_dir = os.path.join(args.output_dir, "raw")
    processed_dir = os.path.join(args.output_dir, "processed")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    logging.info(f"Début de la récupération des données historiques ({args.start_year} - {args.end_year})...")
    try:
        df_historical = fetch_all_historical_gdp(start_year=args.start_year, end_year=args.end_year)
    except RuntimeError as e:
        logging.error(f"Échec de la constitution du jeu de données historique : {e}")
        sys.exit(1)

    csv_path = os.path.join(processed_dir, f"gdp_historical_{args.start_year}_{args.end_year}.csv")
    df_historical.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logging.info(f"Données historiques enregistrées avec succès dans : {csv_path}")

    # Aperçu
    logging.info(f"Aperçu des 5 premières lignes :\n{df_historical.head()}")


if __name__ == "__main__":
    main()
