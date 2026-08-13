#!/usr/bin/env python3
"""
fetch_forecast_gdp.py
---------------------
Récupère les prévisions et projections de PIB (GDP) par pays depuis l'API du FMI
(World Economic Outlook / IMF DataMapper API).

Indicateurs extraits :
- NGDPD: PIB Nominal (Milliards USD)
- NGDP_RPCH: Taux de croissance réel du PIB (%)
- PPPGDP: PIB en PPA (Milliards d'USD internationaux)
- NGDPDPC: PIB par habitant (USD)
"""

import os
import json
import logging
import argparse
import requests
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

IMF_INDICATORS = {
    "NGDPD": "GDP_Nominal_Billions_USD",
    "NGDP_RPCH": "GDP_Growth_Pct",
    "PPPGDP": "GDP_PPP_Billions_USD",
    "NGDPDPC": "GDP_Per_Capita_USD"
}

BASE_URL = "https://www.imf.org/external/datamapper/api/v1"

# L'API DataMapper ne publie pas le millésime du WEO ; seule la version de l'API est
# exposée. La date d'extraction, enregistrée par le pipeline, sert donc de repère.
IMF_API_INFO: Dict[str, Any] = {}


def fetch_imf_countries() -> Optional[Dict[str, str]]:
    """
    Récupère la liste officielle des pays du FMI (endpoint /countries).
    Les codes absents de cette liste sont des groupes analytiques (ADVEC, EURO, MENA...).

    Les payloads d'indicateurs ne contiennent pas les libellés : c'est ici qu'on
    récupère la correspondance code -> nom lisible.

    Retourne le dictionnaire {code: libellé}, ou None si l'API est injoignable.
    """
    logging.info("Récupération de la liste officielle des pays (FMI DataMapper)...")
    url = f"{BASE_URL}/countries"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        countries = {
            code: meta.get("label", code)
            for code, meta in response.json().get("countries", {}).items()
        }

        if not countries:
            logging.warning("Liste des pays FMI vide, les groupes ne seront pas filtrés.")
            return None

        logging.info(f"-> {len(countries)} pays identifiés côté FMI.")
        return countries

    except Exception as e:
        logging.error(f"Erreur lors de la récupération de la liste des pays FMI : {e}")
        return None


def fetch_imf_groups() -> Dict[str, str]:
    """
    Récupère les libellés des groupes analytiques du FMI (endpoint /groups),
    afin que les agrégats conservés dans les séries temporelles portent un nom
    lisible ("Advanced economies") plutôt que leur code (ADVEC).
    """
    url = f"{BASE_URL}/groups"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return {
            code: meta.get("label", code).strip()
            for code, meta in response.json().get("groups", {}).items()
        }
    except Exception as e:
        logging.warning(f"Libellés des groupes FMI indisponibles : {e}")
        return {}


def fetch_imf_indicator(indicator_code: str) -> Dict[str, Any]:
    """
    Télécharge les données brutes d'un indicateur depuis l'API IMF DataMapper.
    """
    logging.info(f"Récupération des prévisions FMI pour l'indicateur '{indicator_code}'...")
    url = f"{BASE_URL}/{indicator_code}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload.get("api"), dict):
            IMF_API_INFO.update(payload["api"])
        return payload
    except Exception as e:
        logging.error(f"Erreur lors du téléchargement de {indicator_code} : {e}")
        return {}


def parse_imf_data(raw_data: Dict[str, Any], indicator_code: str, forecast_start_year: int = 2025,
                   countries: Optional[Dict[str, str]] = None,
                   labels: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Transforme les données brutes FMI en DataFrame structuré.

    `countries` : correspondance {code: libellé} issue de /countries. Un code absent
    de ce dictionnaire désigne un groupe analytique et non un pays.
    `labels` : correspondance {code: libellé} élargie aux groupes, pour l'affichage.
    """
    indicator_name = IMF_INDICATORS.get(indicator_code, indicator_code)
    values = raw_data.get("values", {}).get(indicator_code, {})
    # Repli : certains payloads embarquent les libellés, la plupart non.
    country_names = raw_data.get("countries", {})

    records = []
    for country_code, year_data in values.items():
        # Nom lisible : /countries et /groups en priorité, puis le payload, puis le code brut
        country_name = country_code
        if labels and country_code in labels:
            country_name = labels[country_code]
        elif country_code in country_names:
            country_name = country_names[country_code].get("label", country_code)

        for year_str, val in year_data.items():
            try:
                year = int(year_str)
                records.append({
                    "country_code": country_code,
                    "country_name": country_name,
                    "year": year,
                    "indicator": indicator_name,
                    "value": float(val),
                    "is_forecast": year >= forecast_start_year,
                    "is_aggregate": countries is not None and country_code not in countries
                })
            except ValueError:
                continue
                
    return pd.DataFrame(records)


def fetch_all_forecasts(forecast_start_year: int = 2025, forecast_end_year: int = 2030,
                        history_start_year: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Récupère et combine les séries FMI.

    Le WEO couvre 1980 à l'horizon de projection, pas seulement les années à venir.
    `history_start_year` fixe l'année à partir de laquelle ces estimations passées sont
    conservées : elles permettent de confronter les deux sources sur les mêmes années et
    de mesurer la marche que produirait un simple changement de fournisseur à la jonction.
    Sans cet argument, seule la période de projection est retournée (comportement d'origine).

    Retourne le DataFrame pivoté et le dictionnaire des réponses brutes par indicateur.
    """
    countries = fetch_imf_countries()
    # Les libellés couvrent pays et groupes ; seuls les pays servent à qualifier les agrégats.
    labels = {**fetch_imf_groups(), **(countries or {})}

    raw_responses = {}
    parsed_dfs = []

    for code in IMF_INDICATORS.keys():
        data = fetch_imf_indicator(code)
        if data:
            raw_responses[code] = data
            df_ind = parse_imf_data(data, code, forecast_start_year=forecast_start_year,
                                    countries=countries, labels=labels)
            parsed_dfs.append(df_ind)
            
    if not parsed_dfs:
        logging.error("Aucune donnée de prévision n'a pu être extraite du FMI.")
        return pd.DataFrame(), raw_responses
        
    combined_df = pd.concat(parsed_dfs, ignore_index=True)
    
    borne_basse = history_start_year if history_start_year is not None else forecast_start_year
    filtered_df = combined_df[(combined_df["year"] >= borne_basse) &
                              (combined_df["year"] <= forecast_end_year)]

    if history_start_year is not None:
        n_hist = int((filtered_df["year"] < forecast_start_year).sum())
        logging.info(f"-> {n_hist} observations FMI conservées avant {forecast_start_year} "
                     "pour la comparaison des sources.")

    # Pivot pour obtenir des colonnes propres par indicateur
    pivoted_df = filtered_df.pivot_table(
        index=["country_code", "country_name", "year", "is_forecast", "is_aggregate"],
        columns="indicator",
        values="value"
    ).reset_index()
    
    pivoted_df.sort_values(by=["country_code", "year"], inplace=True)
    return pivoted_df, raw_responses


def main():
    parser = argparse.ArgumentParser(description="Extraction des prévisions de GDP FMI WEO.")
    parser.add_argument("--forecast-start", type=int, default=2025, help="Année de début des prévisions (par défaut: 2025)")
    parser.add_argument("--forecast-end", type=int, default=2030, help="Année de fin des prévisions (par défaut: 2030)")
    parser.add_argument("--output-dir", type=str, default="data", help="Dossier de sortie des données")
    args = parser.parse_args()

    raw_dir = os.path.join(args.output_dir, "raw")
    processed_dir = os.path.join(args.output_dir, "processed")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    logging.info(f"Début de la récupération des prévisions FMI ({args.forecast_start} - {args.forecast_end})...")
    df_forecast, raw_json = fetch_all_forecasts(forecast_start_year=args.forecast_start, forecast_end_year=args.forecast_end)

    if raw_json:
        raw_json_path = os.path.join(raw_dir, "gdp_imf_weo_raw.json")
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, indent=2, ensure_ascii=False)
        logging.info(f"Données brutes JSON enregistrées dans : {raw_json_path}")

    if not df_forecast.empty:
        csv_path = os.path.join(processed_dir, f"gdp_forecast_{args.forecast_start}_{args.forecast_end}.csv")
        df_forecast.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logging.info(f"Prévisions enregistrées avec succès dans : {csv_path}")

        # Aperçu
        logging.info(f"Aperçu des prévisions (5 premières lignes) :\n{df_forecast.head()}")
    else:
        logging.error("Échec de l'extraction des prévisions.")


if __name__ == "__main__":
    main()
