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
import sys
import json
import logging
import argparse
import pandas as pd
from typing import Dict, Any, Optional, Tuple

from pib.http_utils import get_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

IMF_INDICATORS = {
    "NGDPD": "GDP_Nominal_Billions_USD",
    "NGDP_RPCH": "GDP_Growth_Pct",
    "PPPGDP": "GDP_PPP_Billions_USD",
    "NGDPDPC": "GDP_Per_Capita_USD"
}

BASE_URL = "https://www.imf.org/external/datamapper/api/v1"

# Codes du FMI qui ne sont pas ceux de la Banque Mondiale pour le même territoire.
# La jointure se faisant sur le code, un écart suffit à scinder un pays en deux
# entités — l'une sans historique, l'autre sans prévision — classées séparément.
IMF_TO_ISO3 = {
    "UVK": "XKX",   # Kosovo
    "WBG": "PSE",   # Cisjordanie et Gaza
}

# L'API DataMapper ne publie pas le millésime du WEO ; seule la version de l'API est
# exposée. La date d'extraction, enregistrée par le pipeline, sert donc de repère.
IMF_API_INFO: Dict[str, Any] = {}


def fetch_imf_countries() -> Dict[str, str]:
    """
    Récupère la liste officielle des pays du FMI (endpoint /countries).
    Les codes absents de cette liste sont des groupes analytiques (ADVEC, EURO, MENA...).

    Les payloads d'indicateurs ne contiennent pas les libellés : c'est ici qu'on
    récupère la correspondance code -> nom lisible.

    Retourne le dictionnaire {code: libellé}. Sans lui, les groupes du FMI seraient pris
    pour des pays et entreraient dans les classements : l'échec interrompt la collecte.
    """
    logging.info("Récupération de la liste officielle des pays (FMI DataMapper)...")
    countries = {
        code: meta.get("label", code)
        for code, meta in get_json(f"{BASE_URL}/countries").get("countries", {}).items()
    }
    if not countries:
        raise RuntimeError("Liste des pays du FMI vide.")

    logging.info(f"-> {len(countries)} pays identifiés côté FMI.")
    return countries


def fetch_imf_groups() -> Dict[str, str]:
    """
    Récupère les libellés des groupes analytiques du FMI (endpoint /groups),
    afin que les agrégats conservés dans les séries temporelles portent un nom
    lisible ("Advanced economies") plutôt que leur code (ADVEC).

    Purement cosmétique : un échec n'est qu'un avertissement.
    """
    try:
        return {
            code: meta.get("label", code).strip()
            for code, meta in get_json(f"{BASE_URL}/groups").get("groups", {}).items()
        }
    except RuntimeError as e:
        logging.warning(f"Libellés des groupes FMI indisponibles : {e}")
        return {}


def fetch_imf_indicator(indicator_code: str) -> Dict[str, Any]:
    """
    Télécharge les données brutes d'un indicateur depuis l'API IMF DataMapper.
    Lève `RuntimeError` si l'indicateur reste injoignable.
    """
    logging.info(f"Récupération des prévisions FMI pour l'indicateur '{indicator_code}'...")
    payload = get_json(f"{BASE_URL}/{indicator_code}")
    if not payload.get("values", {}).get(indicator_code):
        raise RuntimeError(f"Aucune donnée renvoyée pour l'indicateur FMI {indicator_code}.")
    if isinstance(payload.get("api"), dict):
        IMF_API_INFO.update(payload["api"])
    return payload


def parse_imf_data(raw_data: Dict[str, Any], indicator_code: str, forecast_start_year: int = 2025,
                   countries: Optional[Dict[str, str]] = None,
                   labels: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Transforme les données brutes FMI en DataFrame structuré.

    `countries` : correspondance {code: libellé} issue de /countries. Un code absent
    de ce dictionnaire désigne un groupe analytique et non un pays.
    `labels` : correspondance {code: libellé} élargie aux groupes, pour l'affichage.

    Les codes propres au FMI sont convertis vers ceux de la Banque Mondiale
    (`IMF_TO_ISO3`) ; le JSON brut, lui, conserve les codes d'origine.
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
                    "country_code": IMF_TO_ISO3.get(country_code, country_code),
                    "country_name": country_name,
                    "year": year,
                    "indicator": indicator_name,
                    "value": float(val),
                    "is_forecast": year >= forecast_start_year,
                    "is_aggregate": countries is not None and country_code not in countries
                })
            except (TypeError, ValueError):   # valeur nulle ou non numérique
                continue
                
    return pd.DataFrame(records)


def fetch_all_forecasts(forecast_start_year: int = 2025, forecast_end_year: Optional[int] = None,
                        history_start_year: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Récupère et combine les séries FMI.

    Le WEO couvre 1980 à l'horizon de projection, pas seulement les années à venir.
    `history_start_year` fixe l'année à partir de laquelle ces estimations passées sont
    conservées : elles permettent de confronter les deux sources sur les mêmes années et
    de mesurer la marche que produirait un simple changement de fournisseur à la jonction.
    Sans cet argument, seule la période de projection est retournée (comportement d'origine).

    Sans `forecast_end_year`, toutes les années projetées sont conservées : l'API sert
    l'horizon complet de l'édition en cours (2031 pour celle d'avril 2026).

    Retourne le DataFrame pivoté et le dictionnaire des réponses brutes par indicateur.
    Lève `RuntimeError` si une source ou un indicateur reste injoignable.
    """
    countries = fetch_imf_countries()
    # Les libellés couvrent pays et groupes ; seuls les pays servent à qualifier les agrégats.
    labels = {**fetch_imf_groups(), **countries}

    raw_responses = {}
    parsed_dfs = []

    for code in IMF_INDICATORS.keys():
        data = fetch_imf_indicator(code)
        raw_responses[code] = data
        parsed_dfs.append(parse_imf_data(data, code, forecast_start_year=forecast_start_year,
                                         countries=countries, labels=labels))

    combined_df = pd.concat(parsed_dfs, ignore_index=True)
    
    borne_basse = history_start_year if history_start_year is not None else forecast_start_year
    filtered_df = combined_df[combined_df["year"] >= borne_basse]
    if forecast_end_year is not None:
        filtered_df = filtered_df[filtered_df["year"] <= forecast_end_year]

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
    parser.add_argument("--forecast-end", type=int, default=None,
                        help="Année de fin des prévisions (par défaut : horizon complet de l'édition du WEO)")
    parser.add_argument("--output-dir", type=str, default="data", help="Dossier de sortie des données")
    args = parser.parse_args()

    raw_dir = os.path.join(args.output_dir, "raw")
    processed_dir = os.path.join(args.output_dir, "processed")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    logging.info(f"Début de la récupération des prévisions FMI ({args.forecast_start} - {args.forecast_end})...")
    try:
        df_forecast, raw_json = fetch_all_forecasts(forecast_start_year=args.forecast_start,
                                                    forecast_end_year=args.forecast_end)
    except RuntimeError as e:
        logging.error(f"Échec de l'extraction des prévisions : {e}")
        sys.exit(1)

    raw_json_path = os.path.join(raw_dir, "gdp_imf_weo_raw.json")
    with open(raw_json_path, "w", encoding="utf-8") as f:
        json.dump(raw_json, f, indent=2, ensure_ascii=False)
    logging.info(f"Données brutes JSON enregistrées dans : {raw_json_path}")

    csv_path = os.path.join(processed_dir, f"gdp_forecast_{args.forecast_start}_{int(df_forecast['year'].max())}.csv")
    df_forecast.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logging.info(f"Prévisions enregistrées avec succès dans : {csv_path}")

    # Aperçu
    logging.info(f"Aperçu des prévisions (5 premières lignes) :\n{df_forecast.head()}")


if __name__ == "__main__":
    main()
