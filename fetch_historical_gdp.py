#!/usr/bin/env python3
"""
fetch_historical_gdp.py
-----------------------
Récupère les données historiques du PIB (GDP) par pays sur une période d'au moins 20 ans
depuis la Banque Mondiale (World Bank WDI API) et le FMI (IMF DataMapper API).

Indicateurs inclus :
- PIB Nominal (USD courants)
- Taux de croissance annuel du PIB (%)
- PIB par habitant (USD courants)
- PIB PPA (USD internationaux courants)
"""

import os
import json
import logging
import argparse
import requests
import pandas as pd
from typing import Dict, List, Optional

# Configuration du logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Indicateurs de la Banque Mondiale.
# Les séries en prix courants (CD) subissent l'inflation et les mouvements de change ;
# les séries en prix constants (KD) mesurent le volume, à prix et taux de change figés.
WB_INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP_Nominal_USD",
    "NY.GDP.MKTP.KD.ZG": "GDP_Growth_Annual_Pct",
    "NY.GDP.PCAP.CD": "GDP_Per_Capita_USD",
    "NY.GDP.MKTP.PP.CD": "GDP_PPP_USD",
    "NY.GDP.MKTP.KD": "GDP_Real_USD",          # USD constants 2015
    "NY.GDP.MKTP.PP.KD": "GDP_Real_PPP_Intl"   # $ internationaux constants 2021
}

# Codes d'agrégats régionaux / groupes de revenu utilisés en repli si l'API
# de métadonnées pays est indisponible (liste non exhaustive).
WB_AGGREGATES = {
    "WLD", "OED", "EUU", "EAS", "ECS", "LCN", "MEA", "NAC", "SAS", "SSF",
    "HIC", "MIC", "LIC", "LMC", "UMC", "EAP", "ECA", "LAC", "MNA", "SSA"
}


# Millésime de chaque série, tel que déclaré par l'API (champ `lastupdated`).
# La Banque Mondiale révise son historique : sans cette trace, impossible de savoir
# de quelle version proviennent des chiffres déjà exportés.
WB_LAST_UPDATED: Dict[str, str] = {}


def fetch_worldbank_country_codes() -> Optional[set]:
    """
    Récupère la liste officielle des pays (hors agrégats) depuis l'API de métadonnées
    de la Banque Mondiale. Un agrégat se reconnaît à sa région codée "NA".

    Retourne l'ensemble des codes ISO3 de vrais pays, ou None si l'API est injoignable.
    """
    logging.info("Récupération de la liste officielle des pays (métadonnées Banque Mondiale)...")
    url = "https://api.worldbank.org/v2/country"
    params = {"format": "json", "per_page": 400}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if len(data) < 2 or not data[1]:
            logging.warning("Liste des pays vide, repli sur la liste d'agrégats statique.")
            return None

        countries = {
            item["id"] for item in data[1]
            if item.get("region", {}).get("id") not in (None, "NA")
        }
        logging.info(f"-> {len(countries)} pays identifiés ({len(data[1]) - len(countries)} agrégats exclus).")
        return countries

    except Exception as e:
        logging.error(f"Erreur lors de la récupération des métadonnées pays : {e}")
        return None


def fetch_worldbank_indicator(indicator_code: str, start_year: int = 2000, end_year: int = 2024,
                              country_codes: Optional[set] = None) -> pd.DataFrame:
    """
    Interroge l'API de la Banque Mondiale pour un indicateur spécifique sur la plage d'années spécifiée.

    `country_codes` : ensemble des codes ISO3 de vrais pays servant à marquer les agrégats.
    Si None, repli sur la liste statique WB_AGGREGATES.
    """
    indicator_name = WB_INDICATORS.get(indicator_code, indicator_code)
    logging.info(f"Récupération de l'indicateur Banque Mondiale '{indicator_code}' ({indicator_name})...")
    
    url = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}"
    params = {
        "format": "json",
        "per_page": 20000,
        "date": f"{start_year}:{end_year}"
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if len(data) < 2 or not data[1]:
            logging.warning(f"Aucune donnée renvoyée pour l'indicateur {indicator_code}.")
            return pd.DataFrame()

        if isinstance(data[0], dict) and data[0].get("lastupdated"):
            WB_LAST_UPDATED[indicator_code] = data[0]["lastupdated"]

        records = []
        for item in data[1]:
            country_iso = item.get("countryiso3code")
            country_name = item.get("country", {}).get("value")
            year = item.get("date")
            value = item.get("value")
            
            if country_iso and year and value is not None:
                if country_codes is not None:
                    is_aggregate = country_iso not in country_codes
                else:
                    is_aggregate = country_iso in WB_AGGREGATES or len(country_iso) != 3

                records.append({
                    "country_code": country_iso,
                    "country_name": country_name,
                    "year": int(year),
                    "indicator": indicator_name,
                    "value": float(value),
                    "is_aggregate": is_aggregate
                })
                
        df = pd.DataFrame(records)
        logging.info(f"-> {len(df)} enregistrements récupérés pour {indicator_name}.")
        return df
        
    except Exception as e:
        logging.error(f"Erreur lors de la récupération de {indicator_code} : {e}")
        return pd.DataFrame()


def fetch_all_historical_gdp(start_year: int = 2000, end_year: int = 2024) -> pd.DataFrame:
    """
    Récupère l'ensemble des indicateurs PIB historiques de la Banque Mondiale.
    """
    country_codes = fetch_worldbank_country_codes()

    dfs = []
    for code in WB_INDICATORS.keys():
        df_ind = fetch_worldbank_indicator(code, start_year, end_year, country_codes=country_codes)
        if not df_ind.empty:
            dfs.append(df_ind)
            
    if not dfs:
        logging.error("Aucune donnée historique récupérée.")
        return pd.DataFrame()
        
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # Pivot pour obtenir une structure propre : country_code, country_name, year, indicator columns
    pivoted_df = combined_df.pivot_table(
        index=["country_code", "country_name", "year", "is_aggregate"],
        columns="indicator",
        values="value"
    ).reset_index()
    
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
    df_historical = fetch_all_historical_gdp(start_year=args.start_year, end_year=args.end_year)

    if not df_historical.empty:
        csv_path = os.path.join(processed_dir, f"gdp_historical_{args.start_year}_{args.end_year}.csv")
        df_historical.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logging.info(f"Données historiques enregistrées avec succès dans : {csv_path}")

        # Aperçu
        logging.info(f"Aperçu des 5 premières lignes :\n{df_historical.head()}")
    else:
        logging.error("Échec de la constitution du jeu de données historique.")


if __name__ == "__main__":
    main()
