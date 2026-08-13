#!/usr/bin/env python3
"""
create_notebook.py
------------------
Génère le notebook Jupyter gdp_analysis_notebook.ipynb prêt à l'emploi.
"""

import json
import os

notebook_content = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 📊 Notebook d'Analyse Interactive du PIB (GDP) : Historique (2000-2024) & Prévisions (2025-2030)\n",
    "\n",
    "Ce notebook permet d'explorer, de visualiser et d'analyser les données de PIB mondial compilées à partir des API de la **Banque Mondiale** (2000-2024, 25 ans) et du **Fonds Monétaire International (FMI WEO)** (2025-2030).\n",
    "\n",
    "---"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 1. Importation des Bibliothèques"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import os\n",
    "import glob\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "import matplotlib.pyplot as plt\n",
    "import seaborn as sns\n",
    "import plotly.express as px\n",
    "import plotly.graph_objects as go\n",
    "\n",
    "# Configuration graphique\n",
    "pd.set_option('display.max_columns', None)\n",
    "pd.set_option('display.float_format', lambda x: '%.2f' % x)\n",
    "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
    "print(\"[OK] Toutes les bibliothèques ont été chargées avec succès.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 2. Chargement des Jeux de Données"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Le nom du fichier unifié porte les bornes du run : on le retrouve par motif\n",
    "series = sorted(glob.glob(os.path.join('data', 'processed', 'gdp_unified_*.csv')))\n",
    "if not series:\n",
    "    raise FileNotFoundError(\"Aucune série unifiée dans data/processed/. Lancez d'abord : python gdp_pipeline.py\")\n",
    "unified_csv = series[-1]\n",
    "summary_csv = os.path.join('data', 'processed', 'gdp_country_summary.csv')\n",
    "\n",
    "# Chargement des DataFrames\n",
    "df_unified = pd.read_csv(unified_csv)\n",
    "df_summary = pd.read_csv(summary_csv)\n",
    "\n",
    "print(f\"Dimensions du jeu de données unifié : {df_unified.shape[0]} lignes, {df_unified.shape[1]} colonnes\")\n",
    "print(f\"Dimensions de la synthèse par pays : {df_summary.shape[0]} pays enregistrés\")\n",
    "\n",
    "# Les colonnes de synthèse portent les années du run : on les reconstruit plutôt\n",
    "# que de les figer, pour que le notebook suive un pipeline lancé sur d'autres bornes.\n",
    "an_debut = int(df_unified['year'].min())\n",
    "an_obs = int(df_unified.loc[~df_unified['is_forecast'].astype(bool), 'year'].max())\n",
    "an_fin = int(df_unified['year'].max())\n",
    "\n",
    "C_GDP_DEBUT = f'GDP_{an_debut}_Billion_USD'\n",
    "C_GDP_OBS = f'GDP_{an_obs}_Billion_USD'\n",
    "C_GDP_FIN = f'GDP_{an_fin}_Forecast_Billion_USD'\n",
    "C_CAGR_H = f'CAGR_Historique_{an_debut}_{an_obs}_Pct'\n",
    "C_CAGR_P = f'CAGR_Prevision_{an_obs}_{an_fin}_Pct'\n",
    "C_CAGR_RH = f'CAGR_Reel_Historique_{an_debut}_{an_obs}_Pct'\n",
    "C_CAGR_RP = f'CAGR_Reel_Prevision_{an_obs}_{an_fin}_Pct'\n",
    "C_ECART = f'Ecart_Nominal_Reel_{an_debut}_{an_obs}_Pts'\n",
    "C_PPA_OBS = f'GDP_PPA_{an_obs}_Billion_Intl_2021'\n",
    "C_RANK = f'Rank_{an_obs}'\n",
    "C_RANK_FIN = f'Rank_{an_fin}_Forecast'\n",
    "C_RANK_PPA = f'Rank_PPA_{an_obs}'\n",
    "C_ECART_RANG = f'Ecart_Rang_Nominal_PPA_{an_obs}'\n",
    "\n",
    "print(f\"Période : {an_debut} → {an_obs} observé → {an_fin} projeté\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 3. Inspection des Données et Aperçu des Premières Lignes"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Top 10 des plus grandes économies mondiales en 2024\n",
    "display(df_summary.head(10)[[\n",
    "    'country_code', 'country_name', C_GDP_DEBUT, C_GDP_OBS,\n",
    "    C_GDP_FIN, C_CAGR_H, C_CAGR_P, C_RANK, C_RANK_FIN\n",
    "]])"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 4. Visualisation Interactive : Trajectoire du PIB par Pays (2000 - 2030)\n",
    "\n",
    "Ce graphique interactif Plotly permet de comparer l'évolution du PIB nominal (en Milliards USD). La ligne pointillée représente la période de prévision FMI (2025-2030)."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Sélection d'un groupe de pays pour comparaison\n",
    "selected_countries = ['USA', 'CHN', 'DEU', 'JPN', 'IND', 'FRA', 'GBR', 'BRA']\n",
    "df_filtered = df_unified[df_unified['country_code'].isin(selected_countries)]\n",
    "\n",
    "fig = px.line(\n",
    "    df_filtered,\n",
    "    x='year',\n",
    "    y='GDP_Nominal_Billions_USD',\n",
    "    color='country_name',\n",
    "    line_dash='is_forecast',\n",
    "    title='<b>Évolution du PIB Nominal (2000 - 2030) - Sélection de Puissances Économiques</b>',\n",
    "    labels={'year': 'Année', 'GDP_Nominal_Billions_USD': 'PIB (Milliards USD)', 'country_name': 'Pays'},\n",
    "    hover_data=['GDP_Growth_Pct']\n",
    ")\n",
    "\n",
    "fig.add_vline(x=an_obs, line_dash=\"dash\", line_color=\"red\",\n",
    "              annotation_text=f\"Frontière {an_obs}/{an_obs + 1} (Prévisions FMI)\")\n",
    "fig.update_layout(template='plotly_white', height=600)\n",
    "fig.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 5. Comparaison des Taux de Croissance Annuels Composés (CAGR)\n",
    "\n",
    "Comparaison entre la croissance annuelle moyenne historique (2000-2024) et la croissance projetée (2024-2030)."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "df_top15 = df_summary.head(15).copy()\n",
    "df_top15.sort_values(by=C_CAGR_P, ascending=True, inplace=True)\n",
    "\n",
    "plt.figure(figsize=(12, 7), dpi=150)\n",
    "y = np.arange(len(df_top15))\n",
    "height = 0.35\n",
    "\n",
    "plt.barh(y - height/2, df_top15[C_CAGR_H], height, label='CAGR Historique (2000-2024)', color='#3498db')\n",
    "plt.barh(y + height/2, df_top15[C_CAGR_P], height, label='CAGR Prévisionnel (2024-2030)', color='#2ecc71')\n",
    "\n",
    "plt.yticks(y, df_top15['country_name'])\n",
    "plt.xlabel('CAGR (%)')\n",
    "plt.title('Comparaison du CAGR (%) : Historique vs Prévisions (Top 15 Économies)')\n",
    "plt.legend()\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 6. Heatmap des Taux de Croissance du PIB (2015 - 2030)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "top10_codes = df_summary.head(10)['country_code'].tolist()\n",
    "df_growth = df_unified[(df_unified['country_code'].isin(top10_codes)) & (df_unified['year'] >= 2015)].copy()\n",
    "\n",
    "pivot_growth = df_growth.pivot_table(index='country_name', columns='year', values='GDP_Growth_Pct')\n",
    "\n",
    "plt.figure(figsize=(14, 6), dpi=150)\n",
    "sns.heatmap(pivot_growth, annot=True, fmt=\".1f\", cmap=\"YlGnBu\", cbar_kws={'label': 'Taux de Croissance du PIB (%)'})\n",
    "plt.title('Carte de Chaleur du Taux de Croissance Annuel du PIB (2015 - 2030)')\n",
    "plt.xlabel('Année')\n",
    "plt.ylabel('Pays')\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 7. PIB Nominal vs PIB en Volume : Corriger l'Effet Change\n",
    "\n",
    "Le PIB nominal en USD courants mélange trois choses : la croissance réelle, l'inflation et les mouvements de change. Le PIB en volume (USD constants 2015) neutralise les deux dernières.\n",
    "\n",
    "Le Japon en est l'illustration : son PIB nominal en dollars **recule** sur 2000-2024 alors que son économie **croît** en volume — la différence est la dépréciation du yen."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "df_cmp = df_summary.dropna(subset=[C_CAGR_H, C_CAGR_RH]).head(15).copy()\n",
    "df_cmp.sort_values(by=C_CAGR_RH, inplace=True)\n",
    "\n",
    "y = np.arange(len(df_cmp))\n",
    "nominal = df_cmp[C_CAGR_H].values\n",
    "reel = df_cmp[C_CAGR_RH].values\n",
    "\n",
    "plt.figure(figsize=(12, 7), dpi=150)\n",
    "for yi, (n, r) in enumerate(zip(nominal, reel)):\n",
    "    plt.plot([r, n], [yi, yi], color='#c0392b' if n < r else '#95a5a6', linewidth=2, alpha=0.6, zorder=1)\n",
    "\n",
    "plt.scatter(reel, y, s=70, color='#27ae60', zorder=3, label='CAGR réel (USD constants 2015)')\n",
    "plt.scatter(nominal, y, s=70, color='#2980b9', zorder=3, label='CAGR nominal (USD courants)')\n",
    "plt.axvline(0, color='#bbbbbb', linewidth=0.9)\n",
    "plt.yticks(y, df_cmp['country_name'])\n",
    "plt.xlabel('CAGR 2000-2024 (%)')\n",
    "plt.title(\"Effet de l'inflation et du change sur la croissance affichée\")\n",
    "plt.legend(loc='lower right')\n",
    "plt.grid(axis='x', linestyle='--', alpha=0.6)\n",
    "plt.tight_layout()\n",
    "plt.show()\n",
    "\n",
    "# Les dix écarts les plus marqués\n",
    "ecarts = df_summary.dropna(subset=[C_ECART]).head(30)\n",
    "display(ecarts.nlargest(5, C_ECART)[[\n",
    "    'country_name', C_CAGR_H, C_CAGR_RH, C_ECART]])\n",
    "display(ecarts.nsmallest(5, C_ECART)[[\n",
    "    'country_name', C_CAGR_H, C_CAGR_RH, C_ECART]])"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 8. Comparer des Niveaux : Parité de Pouvoir d'Achat\n",
    "\n",
    "Corriger l'effet change sur la **croissance** ne suffit pas à comparer des **niveaux** : le PIB en volume reste converti en dollars au taux de l'année de base. Or le taux de marché reflète les flux financiers, pas ce qu'une unité de production permet d'acheter sur place.\n",
    "\n",
    "La parité de pouvoir d'achat corrige ce biais. Le classement mondial s'en trouve nettement modifié."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "df_ppa = df_summary.dropna(subset=[C_PPA_OBS]).nsmallest(12, C_RANK_PPA).copy()\n",
    "df_ppa.sort_values(by=C_PPA_OBS, inplace=True)\n",
    "\n",
    "y = np.arange(len(df_ppa))\n",
    "height = 0.38\n",
    "\n",
    "plt.figure(figsize=(12, 7), dpi=150)\n",
    "plt.barh(y + height/2, df_ppa[C_PPA_OBS], height,\n",
    "         label='PPA ($ internationaux constants 2021)', color='#8e44ad')\n",
    "plt.barh(y - height/2, df_ppa[C_GDP_OBS], height,\n",
    "         label='Nominal (USD courants, taux de marché)', color='#2980b9')\n",
    "\n",
    "plt.yticks(y, df_ppa['country_name'])\n",
    "plt.xlabel('PIB 2024 (Milliards)')\n",
    "plt.title('Niveaux de PIB 2024 : taux de marché contre parité de pouvoir d\\'achat')\n",
    "plt.legend(loc='lower right')\n",
    "plt.grid(axis='x', linestyle='--', alpha=0.6)\n",
    "plt.tight_layout()\n",
    "plt.show()\n",
    "\n",
    "# Déplacements de rang entre les deux bases\n",
    "classement = df_summary.dropna(subset=[C_RANK_PPA]).nsmallest(15, C_RANK_PPA)\n",
    "display(classement[['country_name', C_GDP_OBS, C_PPA_OBS,\n",
    "                    C_RANK, C_RANK_PPA, C_ECART_RANG]])"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 9. Fonction d'Interrogation Personnalisée par Pays"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "def analyze_country(country_code_or_name: str):\n",
    "    \"\"\"\n",
    "    Affiche l'historique et les prévisions détaillées pour un pays spécifique.\n",
    "    \"\"\"\n",
    "    query = country_code_or_name.upper()\n",
    "    cdata = df_unified[(df_unified['country_code'] == query) | (df_unified['country_name'].str.upper() == query)]\n",
    "    \n",
    "    if cdata.empty:\n",
    "        print(f\"Aucun pays trouvé pour '{country_code_or_name}'.\")\n",
    "        return\n",
    "        \n",
    "    cname = cdata['country_name'].iloc[0]\n",
    "    print(f\"=== Rapport PIB pour : {cname} ({cdata['country_code'].iloc[0]}) ===\")\n",
    "    \n",
    "    # Récupérer les valeurs clés\n",
    "    summary_row = df_summary[df_summary['country_code'] == cdata['country_code'].iloc[0]]\n",
    "    if not summary_row.empty:\n",
    "        print(f\"• PIB 2000 : ${summary_row[C_GDP_DEBUT].values[0]:,.2f} M$\")\n",
    "        print(f\"• PIB 2024 : ${summary_row[C_GDP_OBS].values[0]:,.2f} M$\")\n",
    "        print(f\"• PIB 2030 (Prévision) : ${summary_row[C_GDP_FIN].values[0]:,.2f} M$\")\n",
    "        print(f\"• CAGR Historique (2000-2024) : {summary_row[C_CAGR_H].values[0]:.2f}% nominal\")\n",
    "        print(f\"                                 {summary_row[C_CAGR_RH].values[0]:.2f}% en volume\")\n",
    "        print(f\"• CAGR Prévision (2024-2030) : {summary_row[C_CAGR_P].values[0]:.2f}% nominal\")\n",
    "        print(f\"                                 {summary_row[C_CAGR_RP].values[0]:.2f}% en volume\")\n",
    "        print(f\"• Rang Mondial 2024 : #{int(summary_row[C_RANK].values[0])} (nominal)\")\n",
    "        rang_ppa = summary_row[C_RANK_PPA].values[0]\n",
    "        if pd.notna(rang_ppa):\n",
    "            print(f\"                      #{int(rang_ppa)} (parité de pouvoir d'achat)\")\n",
    "        print(f\"• Rang Mondial 2030 (Projeté) : #{int(summary_row[C_RANK_FIN].values[0])}\")\n",
    "    \n",
    "    display(cdata[['year', 'data_type', 'GDP_Nominal_Billions_USD', 'GDP_Real_Billions_USD', 'GDP_Growth_Pct', 'GDP_Per_Capita_USD']].tail(10))\n",
    "\n",
    "# Exemple d'utilisation :\n",
    "analyze_country('France')"
   ]
  }
 ],
 "metadata": {
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}

output_path = os.path.join("gdp_analysis_notebook.ipynb")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(notebook_content, f, indent=1, ensure_ascii=False)

print(f"[OK] Notebook Jupyter cree avec succes : {output_path}")
