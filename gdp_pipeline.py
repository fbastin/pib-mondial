#!/usr/bin/env python3
"""
gdp_pipeline.py
---------------
Pipeline complet de traitement des données de PIB (GDP) :
1. Extraction des données historiques (2000-2024, >20 ans)
2. Extraction des prévisions de PIB (2025-2030)
3. Nettoyage, alignement et unification des séries temporelles (2000-2030)
4. Calcul des indicateurs clés (CAGR historique & prévisionnel, classements mondiaux)
5. Export des données sous formats CSV et Excel multi-onglets structuré.
"""

import os
import sys
import glob
import json
import logging
import argparse
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from fetch_historical_gdp import fetch_all_historical_gdp, WB_INDICATORS, WB_LAST_UPDATED
from fetch_forecast_gdp import fetch_all_forecasts, IMF_INDICATORS, IMF_API_INFO, BASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Séries de niveau publiées par les deux sources : pour chacune, la colonne où la valeur
# FMI est conservée en regard, et celle du facteur de raccord qui lui est propre.
# Chaque série a son propre écart entre institutions — appliquer à la PPA le facteur
# du nominal recréerait la marche que le raccord doit supprimer.
RACCORDS = {
    "GDP_Nominal_Billions_USD": ("GDP_Nominal_FMI_Billions_USD", "Facteur_Raccord"),
    "GDP_PPP_Billions_USD": ("GDP_PPP_FMI_Billions_USD", "Facteur_Raccord_PPA"),
    "GDP_Per_Capita_USD": ("GDP_Per_Capita_FMI_USD", "Facteur_Raccord_Par_Habitant"),
}


def calculate_cagr(start_val: float, end_val: float, num_years: int) -> float:
    """Calcul du taux de croissance annuel composé (CAGR en %)."""
    if pd.isna(start_val) or pd.isna(end_val) or start_val <= 0 or end_val <= 0 or num_years <= 0:
        return np.nan
    return float(((end_val / start_val) ** (1.0 / num_years) - 1.0) * 100.0)


def build_unified_dataset(hist_df: pd.DataFrame, fcst_df: pd.DataFrame) -> pd.DataFrame:
    """
    Harmonise et fusionne les données historiques et de prévision.
    """
    logging.info("Fusion et alignement des séries historiques et de prévision...")
    
    # 1. Normaliser les colonnes historiques (Banque Mondiale: PIB nominal est en USD bruts, convertir en Milliards USD)
    hist_clean = hist_df.copy()
    for src, dest in [
        ("GDP_Nominal_USD", "GDP_Nominal_Billions_USD"),
        ("GDP_PPP_USD", "GDP_PPP_Billions_USD"),
        ("GDP_Real_USD", "GDP_Real_Billions_USD"),
        ("GDP_Real_PPP_Intl", "GDP_Real_PPP_Billions_Intl"),
    ]:
        if src in hist_clean.columns:
            hist_clean[dest] = hist_clean[src] / 1e9

    hist_clean["data_type"] = "Historique"
    hist_clean["is_forecast"] = False

    # Harmoniser le nom de la colonne de croissance entre les deux sources
    if "GDP_Growth_Annual_Pct" in hist_clean.columns:
        hist_clean.rename(columns={"GDP_Growth_Annual_Pct": "GDP_Growth_Pct"}, inplace=True)

    # 2. Normaliser les données FMI (PIB nominal déjà en Milliards USD).
    # Le WEO couvre aussi les années observées : ces lignes ne rejoignent pas la série
    # principale — la Banque Mondiale y fait autorité — mais servent de point de
    # comparaison et de base au raccord.
    fcst_all = fcst_df.copy()
    observations_fmi = fcst_all[~fcst_all["is_forecast"].astype(bool)].copy()
    fcst_clean = fcst_all[fcst_all["is_forecast"].astype(bool)].copy()
    fcst_clean["data_type"] = "Prévision FMI"

    # Colonnes communes à conserver
    common_cols = [
        "country_code", "country_name", "year", "data_type", "is_forecast", "is_aggregate",
        "GDP_Nominal_Billions_USD", "GDP_Growth_Pct",
        "GDP_PPP_Billions_USD", "GDP_Per_Capita_USD",
        "GDP_Real_Billions_USD", "GDP_Real_PPP_Billions_Intl"
    ]

    # Filtrer les colonnes existantes
    hist_sub = hist_clean[[c for c in common_cols if c in hist_clean.columns]]
    fcst_sub = fcst_clean[[c for c in common_cols if c in fcst_clean.columns]]

    # Fusion
    unified = pd.concat([hist_sub, fcst_sub], ignore_index=True)

    # Harmoniser le libellé du pays : les deux sources nomment différemment un même
    # code ISO ("Korea, Rep." vs "Korea"). On retient le nom de la Banque Mondiale,
    # sans quoi historique et prévision d'un même pays forment deux séries distinctes.
    canonical_names = (
        unified[~unified["is_forecast"]]
        .drop_duplicates(subset=["country_code"])
        .set_index("country_code")["country_name"]
    )
    unified["country_name"] = unified["country_code"].map(canonical_names).fillna(unified["country_name"])

    # Le drapeau d'agrégat doit lui aussi être cohérent sur toute la série du pays.
    # La classification Banque Mondiale fait foi (elle porte sur les codes ISO3) ;
    # le drapeau FMI ne sert que pour les groupes absents de l'historique (ADVEC, EURO...),
    # ce qui évite d'exclure un territoire dont le code entre en collision avec un
    # groupe analytique FMI (ex: MAF = Saint-Martin côté Banque Mondiale).
    canonical_flags = (
        unified[~unified["is_forecast"]]
        .drop_duplicates(subset=["country_code"])
        .set_index("country_code")["is_aggregate"]
    )
    unified["is_aggregate"] = unified["country_code"].map(canonical_flags).fillna(unified["is_aggregate"])

    # Dédoublonner au cas où l'année de jonction (ex: 2024/2025) chevauche
    unified.sort_values(by=["country_code", "year", "is_forecast"], inplace=True)
    unified.drop_duplicates(subset=["country_code", "year"], keep="last", inplace=True)

    # Valeurs FMI en regard, sur toute la période qu'il couvre : sur les années observées
    # elles viennent de ses propres estimations, sur l'horizon de projection c'est le niveau
    # brut avant raccord. Elles rendent l'écart entre sources mesurable au lieu d'invisible.
    en_regard = {serie: fmi for serie, (fmi, _) in RACCORDS.items()
                 if serie in observations_fmi.columns}
    if not observations_fmi.empty and en_regard:
        colonnes = ["country_code", "year", *en_regard]
        regard = pd.concat([observations_fmi[colonnes], fcst_clean[colonnes]],
                           ignore_index=True).rename(columns=en_regard)

        unified = unified.merge(regard, on=["country_code", "year"], how="left")

        observe = ~unified["is_forecast"].astype(bool)
        if "GDP_Nominal_FMI_Billions_USD" in unified.columns:
            ecart = ((unified["GDP_Nominal_FMI_Billions_USD"] - unified["GDP_Nominal_Billions_USD"])
                     / unified["GDP_Nominal_Billions_USD"] * 100.0)
            unified["Ecart_Sources_Pct"] = ecart.where(observe)

            couverts = int(unified.loc[observe, "GDP_Nominal_FMI_Billions_USD"].notna().sum())
            logging.info(f"-> {couverts} années observées disposent d'une valeur FMI en regard.")

    return unified


def splice_forecast_levels(unified_df: pd.DataFrame, base_year: int = 2024) -> pd.DataFrame:
    """
    Raccorde les niveaux de prévision au dernier niveau observé.

    Les deux sources mesurent le même PIB mais pas toujours à l'identique : sur 2024,
    l'écart médian est de 0,03 %, mais il dépasse 5 % pour une quinzaine de pays et
    atteint plus de 50 % pour le Turkménistan ou le Burundi. Juxtaposer les séries y
    produit une marche entre la dernière année observée et la première année projetée
    qui ne doit rien à l'économie, seulement au changement de fournisseur.

    Le raccord conserve la *dynamique* du FMI et le *niveau* de la Banque Mondiale :

        niveau[y] = observé[base] × FMI[y] / FMI[base]

    C'est la même logique que le chaînage des volumes, qui applique déjà les taux du FMI
    à la dernière valeur observée.

    Chaque série de niveau (nominal, PPA courante, par habitant) reçoit son propre
    facteur : les deux institutions ne divergent pas du même rapport sur chacune. Les
    niveaux FMI d'origine restent disponibles dans les colonnes en regard, et les
    facteurs appliqués dans `Facteur_Raccord*` (voir `RACCORDS`).
    """
    series = [(serie, fmi, col_facteur) for serie, (fmi, col_facteur) in RACCORDS.items()
              if serie in unified_df.columns and fmi in unified_df.columns]
    if not series:
        logging.warning("Valeurs FMI en regard absentes : raccord impossible, séries juxtaposées.")
        return unified_df

    logging.info(f"Raccord des niveaux de prévision sur l'année observée {base_year}...")
    df = unified_df.sort_values(["country_code", "year"]).copy()
    base = df[df["year"] == base_year].set_index("country_code")

    for serie, fmi, col_facteur in series:
        facteur = (base[serie] / base[fmi]).replace([np.inf, -np.inf], np.nan)
        facteur = facteur[facteur > 0]

        df[col_facteur] = df["country_code"].map(facteur)
        prevision = df["is_forecast"].astype(bool) & df[col_facteur].notna()
        df.loc[prevision, serie] = df.loc[prevision, serie] * df.loc[prevision, col_facteur]

        ecarts = (facteur - 1.0).abs() * 100
        logging.info(f"-> {serie} : {int(prevision.sum())} lignes raccordées sur {len(facteur)} pays. "
                     f"Correction médiane {ecarts.median():.2f} %, "
                     f"{int((ecarts > 5).sum())} pays au-delà de 5 %.")
    return df


def extend_real_series(unified_df: pd.DataFrame, base_year: int = 2024) -> pd.DataFrame:
    """
    Prolonge les séries en volume sur l'horizon de prévision.

    Le FMI ne publie pas de niveau de PIB en volume, seulement un taux de croissance
    réelle (`NGDP_RPCH`). Les niveaux de prévision sont donc chaînés à partir du dernier
    point observé par la Banque Mondiale :

        réel[y] = réel[y-1] × (1 + croissance_réelle[y] / 100)

    Les deux mesures en volume (USD constants 2015, $ internationaux constants 2021) ne
    diffèrent que par une constante de conversion propre au pays : le même taux de
    croissance leur est appliqué. Une année de croissance manquante — ou une année
    absente de la série — interrompt le chaînage, les années suivantes restant vides
    plutôt qu'extrapolées.
    """
    real_cols = [c for c in ("GDP_Real_Billions_USD", "GDP_Real_PPP_Billions_Intl")
                 if c in unified_df.columns]
    if not real_cols:
        logging.warning("Aucune série en volume à prolonger.")
        return unified_df

    logging.info(f"Chaînage des niveaux réels de prévision à partir de {base_year}...")
    df = unified_df.sort_values(["country_code", "year"]).copy()
    chained = 0

    for _, grp in df.groupby("country_code", sort=False):
        base_rows = grp[grp["year"] == base_year]
        fcst_idx = grp.index[(grp["year"] > base_year) & grp["is_forecast"].astype(bool)]
        if base_rows.empty or len(fcst_idx) == 0:
            continue

        for col in real_cols:
            value = base_rows[col].iloc[0]
            if pd.isna(value):
                continue
            previous_year = base_year
            for i in fcst_idx:
                growth = df.at[i, "GDP_Growth_Pct"]
                # Un taux s'applique au niveau de l'année précédente, jamais par-dessus un trou
                if pd.isna(growth) or df.at[i, "year"] != previous_year + 1:
                    break
                value = value * (1.0 + growth / 100.0)
                df.at[i, col] = value
                previous_year = df.at[i, "year"]
                chained += 1

    logging.info(f"-> {chained} valeurs de PIB en volume reconstituées sur l'horizon de prévision.")
    return df


def reference_years(start_year: int, end_year: int, fcst_end: int) -> dict:
    """
    Détermine les années de référence de la synthèse à partir des bornes du run.

    L'année intermédiaire est la décennie suivant le début (2010 pour un départ en 2000),
    ou le milieu de la période historique si celle-ci est plus courte que dix ans.
    """
    mid = start_year + 10
    if mid >= end_year:
        mid = start_year + (end_year - start_year) // 2
    return {"start": start_year, "mid": mid, "end": end_year, "fcst": fcst_end}


def compute_country_summary(unified_df: pd.DataFrame, years: dict) -> pd.DataFrame:
    """
    Calcule les métriques de synthèse par pays : niveaux de PIB aux années de référence,
    CAGR historique et prévisionnel, rangs mondiaux nominaux et à parité de pouvoir d'achat.

    `years` fixe les années de référence (voir `reference_years`) ; les noms de colonnes
    en portent la trace, afin qu'un run sur d'autres bornes reste lisible sans ambiguïté.

    Seuls les vrais pays entrent dans les classements : les agrégats (World, OECD members,
    zone euro, groupes de revenu...) partagent le format ISO3 et fausseraient les rangs.
    """
    y_start, y_mid, y_end, y_fcst = years["start"], years["mid"], years["end"], years["fcst"]
    n_hist, n_fcst = y_end - y_start, y_fcst - y_end

    logging.info(f"Calcul des métriques de synthèse (référence {y_start}/{y_mid}/{y_end}/{y_fcst})...")

    # Exclure les agrégats régionaux et groupes analytiques marqués à la collecte
    df_countries = unified_df[~unified_df["is_aggregate"].astype(bool)].copy()
    n_excluded = unified_df["country_code"].nunique() - df_countries["country_code"].nunique()
    logging.info(f"-> {n_excluded} agrégats exclus des classements, {df_countries['country_code'].nunique()} pays retenus.")

    # Pivot sur le seul code ISO : le libellé n'est pas une clé fiable, un même pays
    # pouvant porter deux noms selon la source.
    pivoted = df_countries.pivot_table(
        index="country_code",
        columns="year",
        values="GDP_Nominal_Billions_USD"
    ).reset_index()

    # Même pivot sur la série en volume, pour les métriques corrigées du change
    real_pivot = df_countries.pivot_table(
        index="country_code",
        columns="year",
        values="GDP_Real_Billions_USD"
    ) if "GDP_Real_Billions_USD" in df_countries.columns else pd.DataFrame()

    # Volume à parité de pouvoir d'achat : la seule base neutre pour comparer des
    # niveaux entre pays, le taux de change de marché n'y intervenant pas.
    ppp_pivot = df_countries.pivot_table(
        index="country_code",
        columns="year",
        values="GDP_Real_PPP_Billions_Intl"
    ) if "GDP_Real_PPP_Billions_Intl" in df_countries.columns else pd.DataFrame()

    names = df_countries.drop_duplicates(subset=["country_code"]).set_index("country_code")["country_name"]

    summary_rows = []
    for _, row in pivoted.iterrows():
        ccode = row["country_code"]
        cname = names.get(ccode, ccode)

        gdp_start = row.get(y_start, np.nan)
        gdp_mid = row.get(y_mid, np.nan)
        gdp_end = row.get(y_end, np.nan)
        gdp_fcst = row.get(y_fcst, np.nan)

        cagr_hist = calculate_cagr(gdp_start, gdp_end, n_hist)
        cagr_fcst = calculate_cagr(gdp_end, gdp_fcst, n_fcst)

        abs_growth = gdp_fcst - gdp_end if not (pd.isna(gdp_fcst) or pd.isna(gdp_end)) else np.nan

        # Volet en volume : mêmes métriques hors inflation et hors effet de change
        real = real_pivot.loc[ccode] if ccode in real_pivot.index else {}
        real_start = real.get(y_start, np.nan) if len(real) else np.nan
        real_end = real.get(y_end, np.nan) if len(real) else np.nan
        real_fcst = real.get(y_fcst, np.nan) if len(real) else np.nan

        cagr_real_hist = calculate_cagr(real_start, real_end, n_hist)
        cagr_real_fcst = calculate_cagr(real_end, real_fcst, n_fcst)

        # Écart nominal - réel : ce que l'inflation et le change ajoutent à la croissance
        ecart_hist = (cagr_hist - cagr_real_hist
                      if not (pd.isna(cagr_hist) or pd.isna(cagr_real_hist)) else np.nan)

        # Niveaux à parité de pouvoir d'achat, à prix constants
        ppp = ppp_pivot.loc[ccode] if ccode in ppp_pivot.index else {}
        ppp_start = ppp.get(y_start, np.nan) if len(ppp) else np.nan
        ppp_end = ppp.get(y_end, np.nan) if len(ppp) else np.nan
        ppp_fcst = ppp.get(y_fcst, np.nan) if len(ppp) else np.nan

        summary_rows.append({
            "country_code": ccode,
            "country_name": cname,
            f"GDP_{y_start}_Billion_USD": gdp_start,
            f"GDP_{y_mid}_Billion_USD": gdp_mid,
            f"GDP_{y_end}_Billion_USD": gdp_end,
            f"GDP_{y_fcst}_Forecast_Billion_USD": gdp_fcst,
            f"CAGR_Historique_{y_start}_{y_end}_Pct": cagr_hist,
            f"CAGR_Prevision_{y_end}_{y_fcst}_Pct": cagr_fcst,
            f"Croissance_Absolue_{y_end}_{y_fcst}_Milliards_USD": abs_growth,
            f"GDP_Reel_{y_start}_Billion_USD_2015": real_start,
            f"GDP_Reel_{y_end}_Billion_USD_2015": real_end,
            f"GDP_Reel_{y_fcst}_Billion_USD_2015": real_fcst,
            f"CAGR_Reel_Historique_{y_start}_{y_end}_Pct": cagr_real_hist,
            f"CAGR_Reel_Prevision_{y_end}_{y_fcst}_Pct": cagr_real_fcst,
            f"Ecart_Nominal_Reel_{y_start}_{y_end}_Pts": ecart_hist,
            f"GDP_PPA_{y_start}_Billion_Intl_2021": ppp_start,
            f"GDP_PPA_{y_end}_Billion_Intl_2021": ppp_end,
            f"GDP_PPA_{y_fcst}_Billion_Intl_2021": ppp_fcst
        })

    summary_df = pd.DataFrame(summary_rows)

    # Panel de classement : les pays renseignés aux deux dates et sur les deux bases.
    # Classer chaque colonne sur les pays qu'elle couvre ferait porter les écarts de rang
    # sur des ensembles différents : Taïwan (absent de la Banque Mondiale) entrerait au
    # classement projeté, le Pakistan (sans projection FMI) en sortirait, et tous les pays
    # situés en dessous afficheraient un mouvement qui ne doit rien à leur économie.
    niveaux = {
        "nominal": (f"GDP_{y_end}_Billion_USD", f"GDP_{y_fcst}_Forecast_Billion_USD"),
        "ppa": (f"GDP_PPA_{y_end}_Billion_Intl_2021", f"GDP_PPA_{y_fcst}_Billion_Intl_2021"),
    }
    if summary_df[list(niveaux["ppa"])].isna().all().any():
        logging.warning("Série à parité absente : panel de classement réduit au nominal, rangs PPA vides.")
        panel_cols = list(niveaux["nominal"])
    else:
        panel_cols = [*niveaux["nominal"], *niveaux["ppa"]]
    classe = summary_df[panel_cols].notna().all(axis=1)

    def rang(colonne: str) -> pd.Series:
        """Rang au sein du panel ; NaN hors panel (le niveau, lui, reste renseigné)."""
        return summary_df.loc[classe, colonne].rank(ascending=False, method="min").reindex(summary_df.index)

    hors_panel = summary_df[~classe & summary_df[niveaux["nominal"][0]].notna()]
    if not hors_panel.empty:
        noms = hors_panel.nlargest(8, niveaux["nominal"][0])["country_name"].tolist()
        logging.info(f"-> {int(classe.sum())} pays classés ; {len(hors_panel)} sans rang faute de "
                     f"couverture complète, dont : {', '.join(noms)}.")

    # Calcul des rangs, sur les deux bases de comparaison
    summary_df[f"Rank_{y_end}"] = rang(niveaux["nominal"][0])
    summary_df[f"Rank_{y_fcst}_Forecast"] = rang(niveaux["nominal"][1])
    summary_df["Rank_Change"] = summary_df[f"Rank_{y_end}"] - summary_df[f"Rank_{y_fcst}_Forecast"]  # Positif = progression

    # Rangs à parité de pouvoir d'achat : un même volume de production y vaut le même
    # montant partout, alors que le classement nominal dépend du taux de change du jour.
    summary_df[f"Rank_PPA_{y_end}"] = rang(niveaux["ppa"][0])
    summary_df[f"Rank_PPA_{y_fcst}"] = rang(niveaux["ppa"][1])
    # Positif = mieux classé en PPA qu'en nominal (pouvoir d'achat local sous-évalué par le change)
    summary_df[f"Ecart_Rang_Nominal_PPA_{y_end}"] = summary_df[f"Rank_{y_end}"] - summary_df[f"Rank_PPA_{y_end}"]

    summary_df.sort_values(by=f"GDP_{y_end}_Billion_USD", ascending=False, inplace=True)
    return summary_df


def write_extraction_metadata(data_dir: str, years: dict, fcst_start: int,
                              df_hist: pd.DataFrame, df_fcst: pd.DataFrame,
                              df_unified: pd.DataFrame, df_summary: pd.DataFrame) -> str:
    """
    Enregistre la provenance de l'extraction à côté des données.

    La Banque Mondiale révise son historique et le FMI publie deux millésimes de WEO
    par an : sans cette trace, des chiffres exportés ne sont plus rattachables à une
    version des sources. Le champ `lastupdated` de l'API Banque Mondiale donne le
    millésime réel ; l'API du FMI ne l'expose pas, seule la date d'extraction fait foi.
    """
    y_end = years["end"]
    couverture = {
        col: int(df_unified[col].notna().sum())
        for col in ("GDP_Nominal_Billions_USD", "GDP_Real_Billions_USD",
                    "GDP_Real_PPP_Billions_Intl", "GDP_Growth_Pct")
        if col in df_unified.columns
    }

    meta = {
        "date_extraction": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bornes": {
            "historique": [years["start"], y_end],
            "prevision": [fcst_start, years["fcst"]],
            "annees_reference_synthese": [years["start"], years["mid"], y_end, years["fcst"]],
        },
        "sources": {
            "banque_mondiale": {
                "api": "https://api.worldbank.org/v2",
                "indicateurs": WB_INDICATORS,
                # Millésime déclaré par l'API, par indicateur
                "derniere_mise_a_jour": dict(WB_LAST_UPDATED),
            },
            "fmi_weo": {
                "api": BASE_URL,
                "indicateurs": IMF_INDICATORS,
                "api_info": dict(IMF_API_INFO),
                "millesime_weo": "non exposé par l'API DataMapper",
            },
        },
        "volumes": {
            "lignes_historique_brut": int(len(df_hist)),
            "lignes_prevision_brut": int(len(df_fcst)),
            "lignes_serie_unifiee": int(len(df_unified)),
            "entites_serie_unifiee": int(df_unified["country_code"].nunique()),
            "pays_synthese": int(len(df_summary)),
            "pays_classes": int(df_summary[f"Rank_{y_end}"].notna().sum()),
            "agregats_exclus": int(df_unified[df_unified["is_aggregate"].astype(bool)]["country_code"].nunique()),
        },
        "couverture_non_vide": couverture,
    }

    path = os.path.join(data_dir, "extraction_metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logging.info(f"Provenance enregistrée : {path}")
    return path


def unified_csv_path(data_dir: str = "data") -> str:
    """
    Chemin de la série unifiée produite par le dernier run du pipeline.

    Son nom porte les bornes du run, et plusieurs peuvent coexister dans le dossier.
    Le choix ne repose ni sur l'ordre alphabétique ni sur la date de modification (qu'une
    copie ou une synchronisation suffit à changer), mais sur `extraction_metadata.json`,
    écrit par le même run que la synthèse `gdp_country_summary.csv`.

    Lève `FileNotFoundError` si aucune série n'est disponible, ou si plusieurs le sont
    sans métadonnées pour les départager.
    """
    processed = os.path.join(data_dir, "processed")
    meta_path = os.path.join(data_dir, "extraction_metadata.json")

    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            bornes = json.load(f)["bornes"]
        chemin = os.path.join(processed, f"gdp_unified_{bornes['historique'][0]}_{bornes['prevision'][1]}.csv")
        if not os.path.exists(chemin):
            raise FileNotFoundError(f"{chemin}, annoncé par {meta_path}, est introuvable. "
                                    "Relancez : python gdp_pipeline.py")
        return chemin

    candidats = sorted(glob.glob(os.path.join(processed, "gdp_unified_*.csv")))
    if len(candidats) == 1:
        return candidats[0]
    if not candidats:
        raise FileNotFoundError(f"Aucune série unifiée dans {processed}. "
                                "Lancez d'abord : python gdp_pipeline.py")
    raise FileNotFoundError(f"Plusieurs séries unifiées dans {processed} et aucun {meta_path} "
                            "pour désigner celle du dernier run. Relancez : python gdp_pipeline.py")


def run_pipeline(start_year: int = 2000, end_year: int = 2024, fcst_start: Optional[int] = None,
                 fcst_end: int = 2030, data_dir: str = "data", output_dir: str = "outputs"):
    """
    Exécution complète du pipeline.

    La prévision commence l'année suivant la dernière année observée (`fcst_start`, par
    défaut `end_year + 1`). Un trou entre les deux laisserait une année sans aucune
    donnée, qu'un chaînage franchirait ; un chevauchement ferait passer une prévision
    pour la base observée du raccord. Les deux cas sont refusés.

    Lève `ValueError` sur des bornes incohérentes et `RuntimeError` si une source reste
    injoignable : rien n'est alors écrit.
    """
    if fcst_start is None:
        fcst_start = end_year + 1
    if fcst_start != end_year + 1:
        raise ValueError(f"La prévision doit commencer l'année suivant la fin de l'historique "
                         f"({end_year + 1}), pas en {fcst_start}.")
    if not start_year < end_year < fcst_end:
        raise ValueError(f"Bornes incohérentes : {start_year} < {end_year} < {fcst_end} attendu.")

    processed_dir = os.path.join(data_dir, "processed")
    raw_dir = os.path.join(data_dir, "raw")
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Extraction historique
    logging.info("--- 1. Récupération des données historiques ---")
    df_hist = fetch_all_historical_gdp(start_year=start_year, end_year=end_year)

    # 2. Extraction prévisions
    logging.info("--- 2. Récupération des données de prévision ---")
    df_fcst, raw_json = fetch_all_forecasts(forecast_start_year=fcst_start,
                                            forecast_end_year=fcst_end,
                                            history_start_year=start_year)

    if df_hist.empty or df_fcst.empty:
        raise RuntimeError("Une des étapes d'extraction n'a rien produit. Annulation du pipeline.")

    # 2bis. Conservation des extractions brutes de chaque source
    hist_csv = os.path.join(processed_dir, f"gdp_historical_{start_year}_{end_year}.csv")
    fcst_csv = os.path.join(processed_dir, f"gdp_forecast_{fcst_start}_{fcst_end}.csv")
    df_hist.to_csv(hist_csv, index=False, encoding="utf-8-sig")
    df_fcst.to_csv(fcst_csv, index=False, encoding="utf-8-sig")

    if raw_json:
        raw_json_path = os.path.join(raw_dir, "gdp_imf_weo_raw.json")
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, indent=2, ensure_ascii=False)
        logging.info(f"Données brutes FMI enregistrées : {raw_json_path}")

    # 3. Unification
    logging.info("--- 3. Fusion et Unification ---")
    df_unified = build_unified_dataset(df_hist, df_fcst)
    df_unified = splice_forecast_levels(df_unified, base_year=end_year)
    df_unified = extend_real_series(df_unified, base_year=end_year)

    # 4. Synthèse et Rangs
    logging.info("--- 4. Analyse et Synthèse par Pays ---")
    years = reference_years(start_year, end_year, fcst_end)

    # Une année de référence absente viderait silencieusement toute une colonne
    manquantes = [y for y in years.values() if y not in set(df_unified["year"])]
    if manquantes:
        logging.warning(f"Années de référence absentes des données : {manquantes}. "
                        "Les colonnes correspondantes resteront vides.")

    df_summary = compute_country_summary(df_unified, years)

    # 5. Enregistrement des fichiers CSV. Le nom porte les bornes réelles du run :
    # un fichier « 2000_2030 » contenant autre chose serait un piège.
    unified_csv = os.path.join(processed_dir, f"gdp_unified_{start_year}_{fcst_end}.csv")
    summary_csv = os.path.join(processed_dir, "gdp_country_summary.csv")

    df_unified.to_csv(unified_csv, index=False, encoding="utf-8-sig")
    df_summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    logging.info(f"Fichiers CSV générés : \n - {unified_csv}\n - {summary_csv}")

    # 5bis. Provenance : les deux sources révisent leurs séries, il faut pouvoir dater
    write_extraction_metadata(data_dir, years, fcst_start, df_hist, df_fcst, df_unified, df_summary)

    # 6. Export Excel Structuré Multi-Onglets
    excel_path = os.path.join(output_dir, "gdp_master_dataset.xlsx")
    logging.info(f"Création du classeur Excel maître : {excel_path}")

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_summary.head(30).to_excel(writer, sheet_name="Top30_Economies", index=False)
        df_summary.to_excel(writer, sheet_name="Synthese_Pays", index=False)
        df_unified.to_excel(writer, sheet_name=f"Series_Temporelles_{start_year}_{fcst_end}", index=False)
        df_hist.to_excel(writer, sheet_name="Donnees_Historiques_Brutes", index=False)
        df_fcst.to_excel(writer, sheet_name="Previsions_FMI_Brutes", index=False)

    logging.info(f"Classeur Excel enregistré avec succès : {excel_path}")
    logging.info("Pipeline terminé avec succès !")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline complet de collecte et traitement du PIB.")
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--fcst-start", type=int, default=None,
                        help="Début de la prévision (par défaut, et obligatoirement : end-year + 1)")
    parser.add_argument("--fcst-end", type=int, default=2030)
    parser.add_argument("--data-dir", type=str, default="data", help="Dossier des données")
    parser.add_argument("--output-dir", type=str, default="outputs", help="Dossier des livrables")
    args = parser.parse_args()

    # Un échec doit se voir dans le code de sortie : `gdp_pipeline.py && visualize_gdp.py`
    # ne doit pas enchaîner sur des données absentes ou d'un run précédent.
    try:
        run_pipeline(
            start_year=args.start_year,
            end_year=args.end_year,
            fcst_start=args.fcst_start,
            fcst_end=args.fcst_end,
            data_dir=args.data_dir,
            output_dir=args.output_dir
        )
    except (ValueError, RuntimeError) as e:
        logging.error(f"Pipeline interrompu : {e}")
        sys.exit(1)
