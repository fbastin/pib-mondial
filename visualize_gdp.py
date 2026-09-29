#!/usr/bin/env python3
"""
visualize_gdp.py
----------------
Génère des visualisations graphiques et un tableau de bord interactif HTML :
1. Graphiques statiques HD (PNG) :
   - Évolution du PIB du Top 10 mondial (2000-2030) avec séparation Historique/Prévision
   - Comparaison des taux de croissance (Heatmap / Bar chart)
   - Comparatif du rang mondial (2000 vs 2024 vs 2030)
2. Dashboard interactif HTML (Plotly) pour une exploration fluide des pays.
"""

import os
import sys
import logging
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gdp_pipeline import unified_csv_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Style seaborn / matplotlib
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8


def load_data(data_dir: str = "data"):
    """
    Charge le jeu de données unifié et le résumé par pays.

    Le nom du fichier unifié porte les bornes du run : c'est celui du dernier run, désigné
    par ses métadonnées (voir `unified_csv_path`), qui accompagne la synthèse.
    """
    summary_csv = os.path.join(data_dir, "processed", "gdp_country_summary.csv")
    try:
        unified_csv = unified_csv_path(data_dir)
    except FileNotFoundError as e:
        logging.error(str(e))
        return None, None
    if not os.path.exists(summary_csv):
        logging.error("Synthèse introuvable. Veuillez exécuter gdp_pipeline.py au préalable.")
        return None, None

    return pd.read_csv(unified_csv), pd.read_csv(summary_csv)


def detect_years(df_unified: pd.DataFrame) -> dict:
    """
    Retrouve les années structurantes dans les données : première année, dernière année
    observée (frontière historique / prévision) et dernière année projetée.
    """
    observed = df_unified.loc[~df_unified["is_forecast"].astype(bool), "year"]
    return {
        "start": int(df_unified["year"].min()),
        "boundary": int(observed.max()) if not observed.empty else int(df_unified["year"].min()),
        "end": int(df_unified["year"].max()),
    }



def plot_top10_gdp_trajectories(df_unified: pd.DataFrame, df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Trace l'évolution du PIB nominal des 10 plus grandes économies mondiales de 2000 à 2030.
    """
    logging.info("Génération du graphique des trajectoires du Top 10 PIB...")
    
    # Obtenir le Top 10 par PIB 2024
    top10_codes = df_summary.head(10)["country_code"].tolist()
    
    df_top10 = df_unified[df_unified["country_code"].isin(top10_codes)].copy()
    
    fig, ax = plt.subplots(figsize=(14, 8), dpi=300)
    palette = sns.color_palette("tab10", n_colors=10)
    
    for idx, ccode in enumerate(top10_codes):
        cdata = df_top10[df_top10["country_code"] == ccode].sort_values("year")
        cname = cdata["country_name"].iloc[0] if not cdata.empty else ccode
        color = palette[idx]
        
        # Données historiques (solid line)
        hist_part = cdata[cdata["year"] <= years["boundary"]]
        ax.plot(hist_part["year"], hist_part["GDP_Nominal_Billions_USD"], label=cname, color=color, linewidth=2.2)
        
        # Données prévisions (dashed line)
        fcst_part = cdata[cdata["year"] >= years["boundary"]]  # Reprendre l'année frontière pour raccorder la ligne
        ax.plot(fcst_part["year"], fcst_part["GDP_Nominal_Billions_USD"], color=color, linewidth=2.2, linestyle="--", alpha=0.85)

    # Ligne verticale de séparation Historique / Prévision
    ax.axvline(x=years["boundary"], color="#e74c3c", linestyle=":", linewidth=1.5,
               label=f"Séparation Historique / Prévision ({years['boundary']})")

    ax.set_title(f"Évolution et Prévisions du PIB ({years['start']} - {years['end']}) - Top 10 Économies Mondiales",
                 fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("Année", fontsize=12, labelpad=10)
    ax.set_ylabel("PIB Nominal (Milliards USD)", fontsize=12, labelpad=10)
    ax.set_xlim(years["start"], years["end"])
    ax.legend(title="Pays", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True, fontsize=10)
    
    # Note de bas de page
    plt.figtext(0.12, 0.01, f"Source: Banque Mondiale ({years['start']}-{years['boundary']}) & Prévisions FMI WEO "
                f"({years['boundary'] + 1}-{years['end']}). Ligne continue = Historique, Ligne pointillée = Prévision.", fontsize=9, fontstyle="italic", color="#555555")
    
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    output_png = os.path.join(output_dir, f"gdp_top10_trajectories_{years['start']}_{years['end']}.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_growth_rate_comparison(df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Compare le CAGR historique (2000-2024) au CAGR prévisionnel (2024-2030) pour les principales économies.
    """
    logging.info("Génération du graphique comparatif des taux de croissance (CAGR)...")
    
    # Sélectionner les 15 plus grandes économies
    df_top15 = df_summary.head(15).copy()
    c_hist = f"CAGR_Historique_{years['start']}_{years['boundary']}_Pct"
    c_prev = f"CAGR_Prevision_{years['boundary']}_{years['end']}_Pct"
    df_top15.sort_values(by=c_prev, ascending=True, inplace=True)
    
    y = np.arange(len(df_top15))
    height = 0.35
    
    fig, ax = plt.subplots(figsize=(12, 7), dpi=300)
    
    rects1 = ax.barh(y - height/2, df_top15[c_hist], height,
                     label=f"CAGR Historique ({years['start']}-{years['boundary']})", color="#3498db", alpha=0.85)
    rects2 = ax.barh(y + height/2, df_top15[c_prev], height,
                     label=f"CAGR Prévisionnel ({years['boundary']}-{years['end']})", color="#2ecc71", alpha=0.85)
    
    ax.set_xlabel("Taux de Croissance Annuel Composé - CAGR (%)", fontsize=11, fontweight="bold")
    ax.set_title("Comparaison des Taux de Croissance du PIB : Historique vs Prévisions FMI", fontsize=14, fontweight="bold", pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(df_top15["country_name"], fontsize=10)
    ax.legend(loc="lower right", frameon=True)
    ax.grid(axis="x", linestyle="--", alpha=0.7)
    
    # Valeurs affichées sur les barres
    for rect in rects2:
        width = rect.get_width()
        if not np.isnan(width):
            ax.annotate(f"{width:.1f}%", xy=(width, rect.get_y() + rect.get_height() / 2),
                        xytext=(3, 0), textcoords="offset points", ha="left", va="center", fontsize=8)

    plt.tight_layout()
    output_png = os.path.join(output_dir, "gdp_cagr_comparison_top15.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_nominal_vs_real_cagr(df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Met en regard la croissance nominale (prix courants, USD courants) et la croissance
    en volume (USD constants 2015) sur 2000-2024.

    L'écart entre les deux points mesure ce que l'inflation et les mouvements de change
    ajoutent — ou retirent — à la croissance affichée. Le Japon est le cas d'école :
    croissance nominale négative en dollars, croissance réelle positive.
    """
    logging.info("Génération du comparatif croissance nominale / croissance en volume...")

    c_nom = f"CAGR_Historique_{years['start']}_{years['boundary']}_Pct"
    c_reel = f"CAGR_Reel_Historique_{years['start']}_{years['boundary']}_Pct"

    df = df_summary.dropna(subset=[c_nom, c_reel]).head(15).copy()
    df.sort_values(by=c_reel, ascending=True, inplace=True)

    y = np.arange(len(df))
    nominal = df[c_nom].values
    real = df[c_reel].values

    fig, ax = plt.subplots(figsize=(12, 7.5), dpi=300)

    # Segment reliant les deux mesures : sa longueur est l'effet prix + change
    for yi, (n, r) in enumerate(zip(nominal, real)):
        color = "#c0392b" if n < r else "#95a5a6"
        ax.plot([r, n], [yi, yi], color=color, linewidth=2.0, alpha=0.55, zorder=1,
                solid_capstyle="round")

    ax.scatter(real, y, s=70, color="#27ae60", zorder=3, label="CAGR réel (volume, USD constants 2015)")
    ax.scatter(nominal, y, s=70, color="#2980b9", zorder=3, label="CAGR nominal (USD courants)")

    for yi, (n, r) in enumerate(zip(nominal, real)):
        gap = n - r
        ax.annotate(f"{gap:+.1f} pt", xy=(max(n, r), yi), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=8,
                    color="#c0392b" if gap < 0 else "#555555")

    ax.axvline(0, color="#bbbbbb", linewidth=0.9, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(df["country_name"], fontsize=10)
    ax.set_xlabel(f"Taux de Croissance Annuel Composé {years['start']}-{years['boundary']} (%)",
                  fontsize=11, fontweight="bold")
    ax.set_title("Croissance du PIB : effet de l'inflation et du change\n"
                 "Nominal (USD courants) vs Volume (USD constants 2015)",
                 fontsize=14, fontweight="bold", pad=15)
    ax.legend(loc="lower right", frameon=True, fontsize=9)
    ax.grid(axis="x", linestyle="--", alpha=0.6)
    ax.margins(x=0.12)

    plt.figtext(0.12, 0.015,
                "Source : Banque Mondiale (NY.GDP.MKTP.CD et NY.GDP.MKTP.KD). "
                "L'écart correspond à l'inflation et aux mouvements de change ; il est négatif "
                "lorsque la devise s'est dépréciée face au dollar.",
                fontsize=8.5, fontstyle="italic", color="#555555", wrap=True)

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    output_png = os.path.join(output_dir, "gdp_nominal_vs_real_cagr_top15.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_real_trajectories(df_unified: pd.DataFrame, df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Trajectoires nominale et en volume côte à côte pour les 6 premières économies,
    afin de visualiser la divergence entre les deux lectures.
    """
    logging.info("Génération des trajectoires nominales et en volume...")

    top6 = df_summary.head(6)["country_code"].tolist()
    df6 = df_unified[df_unified["country_code"].isin(top6)].copy()

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), dpi=300, sharey=True)
    palette = sns.color_palette("tab10", n_colors=6)

    panels = [
        (axes[0], "GDP_Nominal_Billions_USD", "PIB nominal (USD courants)"),
        (axes[1], "GDP_Real_Billions_USD", "PIB en volume (USD constants 2015)"),
    ]

    for ax, col, title in panels:
        for idx, ccode in enumerate(top6):
            cdata = df6[df6["country_code"] == ccode].sort_values("year")
            cname = cdata["country_name"].iloc[0] if not cdata.empty else ccode
            hist = cdata[cdata["year"] <= years["boundary"]]
            fcst = cdata[cdata["year"] >= years["boundary"]]
            ax.plot(hist["year"], hist[col], color=palette[idx], linewidth=2.0, label=cname)
            ax.plot(fcst["year"], fcst[col], color=palette[idx], linewidth=2.0,
                    linestyle="--", alpha=0.85)

        ax.axvline(x=years["boundary"], color="#e74c3c", linestyle=":", linewidth=1.3)
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
        ax.set_xlabel("Année", fontsize=10)
        ax.set_xlim(years["start"], years["end"])

    axes[0].set_ylabel("Milliards USD", fontsize=10)
    axes[1].legend(title="Pays", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)

    fig.suptitle("Deux lectures de la même économie : prix courants et volume",
                 fontsize=14, fontweight="bold")
    plt.figtext(0.09, 0.01,
                "Ligne continue = historique Banque Mondiale · pointillé = prévision. "
                "Les niveaux réels de prévision sont chaînés sur la croissance réelle du FMI.",
                fontsize=8.5, fontstyle="italic", color="#555555")

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    output_png = os.path.join(output_dir, "gdp_nominal_vs_real_trajectories.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_ppp_level_ranking(df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Compare le classement mondial 2024 selon deux bases de niveau :
    - PIB nominal converti au taux de change de marché ;
    - PIB à parité de pouvoir d'achat, à prix constants 2021.

    Le taux de marché reflète les flux financiers, pas ce qu'une unité de production
    permet d'acheter localement. Le classement s'en trouve nettement modifié.
    """
    logging.info("Génération du comparatif de classement nominal / PPA...")

    c_rank = f"Rank_{years['boundary']}"
    c_rank_ppa = f"Rank_PPA_{years['boundary']}"

    df = df_summary.dropna(subset=[c_rank, c_rank_ppa]).copy()
    df = df.nsmallest(15, c_rank_ppa)

    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=300)
    x_nom, x_ppa = 0.0, 1.0

    for _, row in df.iterrows():
        r_nom, r_ppa = row[c_rank], row[c_rank_ppa]
        gain = r_nom - r_ppa
        if gain > 0:
            color, lw = "#27ae60", 2.2
        elif gain < 0:
            color, lw = "#c0392b", 2.2
        else:
            color, lw = "#95a5a6", 1.4

        ax.plot([x_nom, x_ppa], [r_nom, r_ppa], color=color, linewidth=lw, alpha=0.75, zorder=1)
        ax.scatter([x_nom, x_ppa], [r_nom, r_ppa], s=45, color=color, zorder=3)

        ax.annotate(f"{row['country_name']}  {int(r_nom)}", xy=(x_nom, r_nom), xytext=(-10, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=9)
        label = f"{int(r_ppa)}  {row['country_name']}"
        if gain != 0:
            label += f"  ({gain:+.0f})"
        ax.annotate(label, xy=(x_ppa, r_ppa), xytext=(10, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=9,
                    color="#2c3e50" if gain == 0 else color)

    ax.set_xlim(-0.75, 1.75)
    ax.set_ylim(df[[c_rank, c_rank_ppa]].max().max() + 1.5, 0.2)
    ax.set_xticks([x_nom, x_ppa])
    ax.set_xticklabels(["PIB nominal\n(USD courants, taux de marché)",
                        "PIB à PPA\n($ internationaux constants 2021)"],
                       fontsize=10, fontweight="bold")
    ax.set_ylabel(f"Rang mondial {years['boundary']}", fontsize=11, labelpad=10)
    ax.set_title("Le classement mondial dépend de la base de conversion\n"
                 f"Taux de change de marché contre parité de pouvoir d'achat, {years['boundary']}",
                 fontsize=14, fontweight="bold", pad=18)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.tick_params(axis="x", length=0)

    plt.figtext(0.5, 0.015,
                "En vert, les pays mieux classés à parité de pouvoir d'achat : leur monnaie "
                "sous-évalue leur production intérieure au taux de marché.",
                fontsize=9, fontstyle="italic", color="#555555", ha="center")

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    output_png = os.path.join(output_dir, f"gdp_ranking_nominal_vs_ppp_{years['boundary']}.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_source_discrepancy(df_unified: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Écart entre les deux sources sur l'année de jonction, et marche qu'il produirait.

    Les deux institutions mesurent le même PIB : sur la plupart des pays elles
    concordent au centième de pourcent. Là où elles divergent, juxtaposer l'observation
    de l'une et la projection de l'autre fabrique une croissance apparente qui n'existe
    pas — d'où le raccord appliqué par le pipeline.
    """
    if "Ecart_Sources_Pct" not in df_unified.columns:
        logging.warning("Écart entre sources indisponible : graphique omis.")
        return

    logging.info("Génération du comparatif entre sources...")
    borne = years["boundary"]

    jonction = df_unified[(df_unified["year"] == borne) & (~df_unified["is_aggregate"].astype(bool))]
    jonction = jonction.dropna(subset=["Ecart_Sources_Pct"]).copy()
    if jonction.empty:
        logging.warning("Aucun pays comparable sur l'année de jonction : graphique omis.")
        return

    # Croissance apparente que produirait la juxtaposition, contre celle réellement projetée
    suivant = df_unified[df_unified["year"] == borne + 1].set_index("country_code")
    jonction = jonction.set_index("country_code")
    jonction["croissance_projetee"] = (
        suivant["GDP_Nominal_Billions_USD"] / jonction["GDP_Nominal_Billions_USD"] - 1) * 100
    jonction["croissance_apparente"] = (
        suivant["GDP_Nominal_FMI_Billions_USD"] / jonction["GDP_Nominal_Billions_USD"] - 1) * 100

    df = jonction.reindex(jonction["Ecart_Sources_Pct"].abs().sort_values().index).tail(15)
    if df.empty:
        return

    y = np.arange(len(df))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7), dpi=300,
                                   gridspec_kw={"width_ratios": [1, 1.15]})

    couleurs = ["#c0392b" if v > 0 else "#2980b9" for v in df["Ecart_Sources_Pct"]]
    ax1.barh(y, df["Ecart_Sources_Pct"], color=couleurs, alpha=0.85)
    ax1.axvline(0, color="#888888", linewidth=0.9)
    ax1.set_yticks(y)
    ax1.set_yticklabels(df["country_name"], fontsize=9)
    ax1.set_xlabel(f"Écart FMI − Banque Mondiale en {borne} (%)", fontsize=10, fontweight="bold")
    ax1.set_title("Les deux sources ne mesurent pas\ntoujours le même niveau",
                  fontsize=12, fontweight="bold", pad=12)
    ax1.grid(axis="x", linestyle="--", alpha=0.5)

    hauteur = 0.38
    ax2.barh(y - hauteur / 2, df["croissance_apparente"], hauteur,
             color="#e67e22", alpha=0.9, label="Sans raccord (sources juxtaposées)")
    ax2.barh(y + hauteur / 2, df["croissance_projetee"], hauteur,
             color="#27ae60", alpha=0.9, label="Après raccord (dynamique du FMI)")
    ax2.axvline(0, color="#888888", linewidth=0.9)
    ax2.set_yticks(y)
    ax2.set_yticklabels([])
    ax2.set_xlabel(f"Croissance nominale {borne}→{borne + 1} (%)", fontsize=10, fontweight="bold")
    ax2.set_title("Ce que la juxtaposition ferait croire\nde la première année projetée",
                  fontsize=12, fontweight="bold", pad=12)
    ax2.legend(loc="lower right", fontsize=9, frameon=True)
    ax2.grid(axis="x", linestyle="--", alpha=0.5)

    fig.suptitle("Confrontation des deux sources sur les années observées",
                 fontsize=14, fontweight="bold")
    concordants = int((jonction["Ecart_Sources_Pct"].abs() < 0.1).sum())
    plt.figtext(0.5, 0.015,
                f"Quinze pays où l'écart est le plus marqué, sur {len(jonction)} comparables. "
                f"L'écart est inférieur à 0,1 % pour {concordants} d'entre eux.",
                fontsize=9, fontstyle="italic", color="#555555", ha="center")

    plt.tight_layout(rect=[0, 0.04, 1, 0.94])
    output_png = os.path.join(output_dir, f"gdp_source_discrepancy_{borne}.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def plot_forecast_accuracy(data_dir: str = "data", output_dir: str = "outputs"):
    """
    Exactitude des prévisions du FMI, par horizon et par année visée.

    Alimenté par `evaluate_forecasts.py`, qui confronte chaque édition du WEO depuis
    1990 à ce qui s'est réellement produit. Omis si cette évaluation n'a pas été lancée.
    """
    chemin = os.path.join(data_dir, "processed", "weo_forecast_evaluation_ngdp_rpch.csv")
    if not os.path.exists(chemin):
        logging.warning("Évaluation des prévisions absente : graphique omis "
                        "(lancer python evaluate_forecasts.py).")
        return

    logging.info("Génération du graphique d'exactitude des prévisions...")
    ev = pd.read_csv(chemin).dropna(subset=["erreur_vs_fmi"])
    if ev.empty:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5), dpi=300,
                                   gridspec_kw={"width_ratios": [1, 1.4]})

    # --- Biais et dispersion par horizon
    par_h = ev.groupby("horizon")["erreur_vs_fmi"].agg(
        biais="mean", absolue=lambda s: s.abs().mean()).reset_index()

    x = par_h["horizon"]
    ax1.bar(x - 0.2, par_h["biais"], 0.4, color="#e67e22", label="Biais moyen")
    ax1.bar(x + 0.2, par_h["absolue"], 0.4, color="#7f8c8d", alpha=0.85,
            label="Erreur absolue moyenne")
    ax1.axhline(0, color="#555555", linewidth=0.9)
    ax1.set_xticks(x)
    ax1.set_xlabel("Horizon de projection (années)", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Points de croissance", fontsize=10)
    ax1.set_title("Biais et erreur absolue\npar horizon de projection",
                  fontsize=12, fontweight="bold", pad=12)
    ax1.legend(fontsize=9, frameon=True)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    for _, r in par_h.iterrows():
        ax1.annotate(f"{r['biais']:+.2f}", xy=(r["horizon"] - 0.2, r["biais"]),
                     xytext=(0, 4 if r["biais"] >= 0 else -12), textcoords="offset points",
                     ha="center", fontsize=8, color="#b9611a")

    # --- Erreur médiane par année visée : les chocs que personne n'a vus venir
    par_annee = (ev[ev["horizon"] >= 1].groupby("year")["erreur_vs_fmi"]
                 .median().reset_index())
    par_annee = par_annee[par_annee["year"] <= ev["year"].max() - 1]

    couleurs = ["#c0392b" if v > 1.5 else "#2980b9" if v < -1.5 else "#95a5a6"
                for v in par_annee["erreur_vs_fmi"]]
    ax2.bar(par_annee["year"], par_annee["erreur_vs_fmi"], color=couleurs, alpha=0.9)
    ax2.axhline(0, color="#555555", linewidth=0.9)
    ax2.set_xlabel("Année visée par la prévision", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Erreur médiane (points)", fontsize=10)
    ax2.set_title("Erreur médiane par année visée\n(rouge / bleu : sur- / sous-estimation de plus de 1,5 pt)",
                  fontsize=12, fontweight="bold", pad=12)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    for _, r in par_annee.nlargest(3, "erreur_vs_fmi").iterrows():
        ax2.annotate(f"{int(r['year'])}", xy=(r["year"], r["erreur_vs_fmi"]),
                     xytext=(0, 6), textcoords="offset points", ha="center",
                     fontsize=9, fontweight="bold", color="#c0392b")

    fig.suptitle("Les prévisions de croissance du FMI, confrontées aux faits "
                 f"(éditions {ev['annee_millesime'].min()}-{ev['annee_millesime'].max()})",
                 fontsize=14, fontweight="bold")
    plt.figtext(0.5, 0.015,
                f"{len(ev):,} projections de croissance réelle, {ev['country_code'].nunique()} pays. "
                "Erreur = projeté − ré-estimé un an après. Positif = trop optimiste.",
                fontsize=9, fontstyle="italic", color="#555555", ha="center")

    plt.tight_layout(rect=[0, 0.04, 1, 0.93])
    output_png = os.path.join(output_dir, "gdp_forecast_accuracy.png")
    plt.savefig(output_png)
    plt.close()
    logging.info(f"Graphique enregistré : {output_png}")


def create_interactive_dashboard(df_unified: pd.DataFrame, df_summary: pd.DataFrame, years: dict, output_dir: str = "outputs"):
    """
    Génère un tableau de bord HTML interactif complet avec Plotly.
    """
    logging.info("Génération du tableau de bord HTML interactif (Plotly)...")
    
    top20_codes = df_summary.head(20)["country_code"].tolist()
    df_top20 = df_unified[df_unified["country_code"].isin(top20_codes)].copy()
    
    fig = px.line(
        df_top20,
        x="year",
        y="GDP_Nominal_Billions_USD",
        color="country_name",
        line_dash="is_forecast",
        title=f"<b>Tableau de Bord Interactif du PIB Mondial ({years['start']} - {years['end']})</b><br><sup>Ligne continue = Historique (Banque Mondiale) | Ligne pointillée = Prévision (FMI WEO)</sup>",
        labels={
            "year": "Année",
            "GDP_Nominal_Billions_USD": "PIB Nominal (Milliards USD)",
            "country_name": "Pays",
            "is_forecast": "Est une prévision"
        },
        hover_data=["GDP_Growth_Pct", "GDP_Per_Capita_USD", "GDP_Real_Billions_USD"]
    )
    
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Inter, Roboto, Helvetica, Arial, sans-serif", size=12),
        hovermode="x unified",
        legend=dict(title="Pays & Statut", orientation="v", y=1, x=1.02),
        xaxis=dict(dtick=2, range=[years["start"], years["end"]]),
        yaxis=dict(title="PIB Nominal (Milliards USD)"),
        height=700
    )
    
    # Ajout d'une ligne verticale pour 2024
    fig.add_vline(x=years["boundary"], line_width=1.5, line_dash="dash", line_color="red",
                  annotation_text=f"Frontière {years['boundary']} (Prévisions ->)", annotation_position="top left")
    
    dashboard_html = os.path.join(output_dir, "gdp_dashboard_interactive.html")
    fig.write_html(dashboard_html)
    logging.info(f"Tableau de bord HTML interactif enregistré dans : {dashboard_html}")


def main():
    parser = argparse.ArgumentParser(description="Génération des graphiques et du dashboard PIB.")
    parser.add_argument("--data-dir", type=str, default="data", help="Dossier des données")
    parser.add_argument("--output-dir", type=str, default="outputs", help="Dossier des livrables")
    args = parser.parse_args()

    unified_df, summary_df = load_data(args.data_dir)
    if unified_df is None or summary_df is None:
        sys.exit(1)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    years = detect_years(unified_df)
    logging.info(f"Années détectées : {years['start']} → {years['boundary']} observé "
                 f"→ {years['end']} projeté")

    plot_top10_gdp_trajectories(unified_df, summary_df, years, output_dir)
    plot_growth_rate_comparison(summary_df, years, output_dir)
    plot_nominal_vs_real_cagr(summary_df, years, output_dir)
    plot_real_trajectories(unified_df, summary_df, years, output_dir)
    plot_ppp_level_ranking(summary_df, years, output_dir)
    plot_source_discrepancy(unified_df, years, output_dir)
    plot_forecast_accuracy(args.data_dir, output_dir)
    create_interactive_dashboard(unified_df, summary_df, years, output_dir)
    logging.info("Toutes les visualisations ont été générées avec succès.")


if __name__ == "__main__":
    main()
