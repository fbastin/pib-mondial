#!/usr/bin/env python3
"""
create_notebook_julia.py
------------------------
Génère le notebook Julia gdp_analysis_notebook_julia.ipynb, transposition du
notebook Python gdp_analysis_notebook.ipynb (mêmes sections, mêmes analyses).

Pile Julia : CSV.jl + DataFrames.jl pour les données, Plots.jl pour les graphiques,
avec bascule du backend GR (statique) vers plotly (interactif).

PlotlyJS.jl a été écarté : son affichage passe par WebIO, dont les messages
corrompent la signature HMAC du noyau IJulia et interrompent la connexion
(« Invalid Signature »). Le backend plotly de Plots.jl, adossé à PlotlyBase.jl,
produit le même graphique interactif sans WebIO ni Blink.
"""

import json
import os

JULIA_VERSION = "1.12"


def md(source: str) -> dict:
    """Cellule Markdown."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.strip("\n").splitlines(keepends=True),
    }


def code(source: str) -> dict:
    """Cellule de code Julia."""
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.strip("\n").splitlines(keepends=True),
    }


cells = [
    md("""
# 📊 Analyse du PIB (GDP) en Julia : Historique (2000-2024) & Prévisions (2025-2030)

Transposition Julia du notebook Python. Les données proviennent des mêmes fichiers,
produits par `gdp_pipeline.py` à partir des API de la **Banque Mondiale** (2000-2024)
et du **FMI WEO** (2025-2030).

> **Avant de commencer.** Depuis le dossier du projet :
> ```julia
> using Pkg
> Pkg.activate(".")   # environnement décrit par Project.toml
> Pkg.instantiate()   # installe CSV, DataFrames, Plots, PlotlyBase
> Pkg.add("IJulia")   # noyau Jupyter, si absent
> ```
> Les données doivent avoir été générées au préalable : `python gdp_pipeline.py`.

Les classements ne portent que sur de vrais pays : les agrégats (*World*, *OECD members*,
zone euro…) sont marqués `is_aggregate` et déjà écartés de `gdp_country_summary.csv`.

---
"""),

    md("## 1. Chargement des Bibliothèques"),
    code("""
using CSV
using DataFrames
using Statistics
using Printf
using Plots
using Plots.PlotMeasures
import PlotlyBase        # active le backend interactif `plotly()` de Plots

gr()                     # backend par défaut : graphiques statiques
default(fontfamily = "sans-serif", grid = true, framestyle = :box)

println("[OK] Bibliothèques chargées. Backend courant : ", backend())
"""),

    md("## 2. Chargement des Jeux de Données"),
    code("""
# Le nom du fichier unifié porte les bornes du run : on le retrouve par motif
series = filter(f -> startswith(f, "gdp_unified_") && endswith(f, ".csv"),
                readdir(joinpath("data", "processed")))
isempty(series) && error("Aucune série unifiée dans data/processed/. Lancez d'abord : python gdp_pipeline.py")

unified_csv = joinpath("data", "processed", last(sort(series)))
summary_csv = joinpath("data", "processed", "gdp_country_summary.csv")

df_unified = CSV.read(unified_csv, DataFrame)
df_summary = CSV.read(summary_csv, DataFrame)

@printf("Jeu de données unifié : %d lignes, %d colonnes\\n", nrow(df_unified), ncol(df_unified))
@printf("Synthèse par pays     : %d pays\\n", nrow(df_summary))
@printf("Agrégats conservés dans les séries : %d entités\\n",
        length(unique(df_unified[df_unified.is_aggregate, :country_code])))

# Les colonnes de synthèse portent les années du run : on les reconstruit plutôt que
# de les figer, pour que le notebook suive un pipeline lancé sur d'autres bornes.
an_debut = minimum(df_unified.year)
an_obs   = maximum(df_unified[.!df_unified.is_forecast, :year])
an_fin   = maximum(df_unified.year)

C_GDP_DEBUT  = Symbol("GDP_$(an_debut)_Billion_USD")
C_GDP_OBS    = Symbol("GDP_$(an_obs)_Billion_USD")
C_GDP_FIN    = Symbol("GDP_$(an_fin)_Forecast_Billion_USD")
C_CAGR_H     = Symbol("CAGR_Historique_$(an_debut)_$(an_obs)_Pct")
C_CAGR_P     = Symbol("CAGR_Prevision_$(an_obs)_$(an_fin)_Pct")
C_CAGR_RH    = Symbol("CAGR_Reel_Historique_$(an_debut)_$(an_obs)_Pct")
C_CAGR_RP    = Symbol("CAGR_Reel_Prevision_$(an_obs)_$(an_fin)_Pct")
C_ECART      = Symbol("Ecart_Nominal_Reel_$(an_debut)_$(an_obs)_Pts")
C_PPA_OBS    = Symbol("GDP_PPA_$(an_obs)_Billion_Intl_2021")
C_RANK       = Symbol("Rank_$(an_obs)")
C_RANK_FIN   = Symbol("Rank_$(an_fin)_Forecast")
C_RANK_PPA   = Symbol("Rank_PPA_$(an_obs)")
C_ECART_RANG = Symbol("Ecart_Rang_Nominal_PPA_$(an_obs)")

println("Période : $an_debut → $an_obs observé → $an_fin projeté")

# Plots.jl n'accepte pas `missing` : conversion en NaN, simplement non tracé
tonum(v) = [ismissing(x) ? NaN : Float64(x) for x in v]
"""),

    md("## 3. Inspection des Données : Top 10 des Économies Mondiales (2024)"),
    code("""
first(select(df_summary,
    :country_code, :country_name,
    C_GDP_DEBUT, C_GDP_OBS, C_GDP_FIN,
    C_CAGR_H, C_CAGR_P, C_RANK, C_RANK_FIN), 10)
"""),

    md("""
## 4. Visualisation Interactive : Trajectoire du PIB par Pays (2000 - 2030)

Backend `plotly()` de Plots.jl : zoom, survol et masquage d'un pays par clic sur la légende.
Trait plein pour l'historique Banque Mondiale, trait pointillé pour la prévision FMI ;
seul le segment historique porte l'étiquette, pour ne pas doubler les entrées de légende.

> Le rendu charge `plotly.js` depuis un CDN : une connexion est nécessaire à l'affichage.
> Plots signale au premier appel que l'intégration PlotlyKaleido est absente : cet
> avertissement est sans effet ici, Kaleido ne servant qu'à exporter une figure plotly
> en image statique. Il n'est volontairement pas installé, son sous-processus Chromium
> faisant échouer la cellule lorsqu'il ne parvient pas à démarrer.
"""),
    code("""
plotly()   # bascule vers le backend interactif

selected = ["USA", "CHN", "DEU", "JPN", "IND", "FRA", "GBR", "BRA"]
df_sel = subset(df_unified, :country_code => ByRow(in(selected)))

palette10 = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
             "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

p4 = plot(size = (1000, 600), legend = :outertopright,
    title = "Évolution du PIB Nominal ($(an_debut)-$(an_fin))",
    xlabel = "Année", ylabel = "PIB (Milliards USD)", xlims = (an_debut, an_fin))

for (i, cd) in enumerate(selected)
    cdata = sort(df_sel[df_sel.country_code .== cd, :], :year)
    isempty(cdata) && continue
    cname = first(cdata.country_name)
    color = palette10[mod1(i, length(palette10))]

    hist = cdata[cdata.year .<= an_obs, :]
    plot!(p4, hist.year, tonum(hist.GDP_Nominal_Billions_USD);
        color = color, lw = 2.2, label = cname)

    # 2024 est repris pour raccorder la prévision à l'historique
    fcst = cdata[cdata.year .>= an_obs, :]
    plot!(p4, fcst.year, tonum(fcst.GDP_Nominal_Billions_USD);
        color = color, lw = 2.2, linestyle = :dash, label = "")
end

vline!(p4, [an_obs]; color = :red, linestyle = :dot, lw = 1.5,
       label = "Frontière $(an_obs)/$(an_obs + 1)")
p4
"""),

    md("""
## 5. Comparaison des Taux de Croissance Annuels Composés (CAGR)

Croissance annuelle moyenne observée (2000-2024) face à la croissance projetée (2024-2030),
pour les 15 premières économies.
"""),
    code("""
gr()   # retour au backend statique

df15 = sort(first(df_summary, 15), C_CAGR_P)
ypos = 1:nrow(df15)

p = bar(ypos .- 0.2, tonum(df15[!, C_CAGR_H]);
    orientation = :h, bar_width = 0.4, linecolor = :match, color = "#3498db",
    label = "CAGR Historique ($(an_debut)-$(an_obs))")
bar!(p, ypos .+ 0.2, tonum(df15[!, C_CAGR_P]);
    orientation = :h, bar_width = 0.4, linecolor = :match, color = "#2ecc71",
    label = "CAGR Prévisionnel ($(an_obs)-$(an_fin))")

# ylims explicite : avec `orientation = :h`, Plots déduit les bornes verticales des
# valeurs et non des positions des barres, ce qui écrase l'axe dès que les deux
# grandeurs diffèrent en ordre.
plot!(p; yticks = (ypos, df15.country_name), ylims = (0.4, nrow(df15) + 0.6),
    xlabel = "CAGR (%)",
    title = "CAGR du PIB : Historique vs Prévisions FMI (Top 15)",
    size = (1000, 620), dpi = 150, legend = :bottomright,
    left_margin = 5mm, bottom_margin = 4mm)
"""),

    md("## 6. Carte de Chaleur des Taux de Croissance (2015 - 2030)"),
    code("""
gr()   # les annotations de la heatmap sont rendues par GR

top10_codes = first(df_summary, 10).country_code
dfg = subset(df_unified,
    :country_code => ByRow(in(top10_codes)),
    :year => ByRow(>=(max(an_debut, an_obs - 9))))

years  = sort(unique(dfg.year))
cnames = [first(dfg[dfg.country_code .== c, :country_name]) for c in top10_codes]

# Matrice pays × années, NaN pour les valeurs absentes
M = fill(NaN, length(top10_codes), length(years))
for (i, c) in enumerate(top10_codes), (j, y) in enumerate(years)
    row = dfg[(dfg.country_code .== c) .& (dfg.year .== y), :]
    if nrow(row) == 1 && !ismissing(row.GDP_Growth_Pct[1])
        M[i, j] = row.GDP_Growth_Pct[1]
    end
end

h = heatmap(string.(years), cnames, M;
    c = :YlGnBu, yflip = true, size = (1300, 560), dpi = 150,
    xlabel = "Année", ylabel = "Pays", colorbar_title = "Croissance (%)",
    title = "Taux de Croissance Annuel du PIB (%) - Top 10 Économies",
    left_margin = 8mm, bottom_margin = 6mm, right_margin = 4mm)

for i in eachindex(cnames), j in eachindex(years)
    isnan(M[i, j]) && continue
    annotate!(h, j - 0.5, i - 0.5, text(@sprintf("%.1f", M[i, j]), 6, :black))
end

h
"""),

    md("""
## 7. PIB Nominal vs PIB en Volume : Corriger l'Effet Change

Le PIB nominal en USD courants mélange trois choses : la croissance réelle, l'inflation et
les mouvements de change. Le PIB en volume (USD constants 2015) neutralise les deux dernières.

Le Japon l'illustre : son PIB nominal en dollars **recule** sur 2000-2024 alors que son
économie **croît** en volume — l'écart est la dépréciation du yen.
"""),
    code("""
gr()

df_cmp = dropmissing(df_summary, [C_CAGR_H, C_CAGR_RH])
df_cmp = sort(first(df_cmp, 15), C_CAGR_RH)

ypos    = 1:nrow(df_cmp)
nominal = tonum(df_cmp[!, C_CAGR_H])
reel    = tonum(df_cmp[!, C_CAGR_RH])

p7 = plot(size = (1000, 640), dpi = 150, legend = :bottomright,
    xlabel = "CAGR $(an_debut)-$(an_obs) (%)",
    title = "Effet de l'inflation et du change sur la croissance affichée",
    yticks = (ypos, df_cmp.country_name), left_margin = 5mm, bottom_margin = 4mm)

# Un segment par pays : sa longueur est l'effet prix + change
for (i, (n, r)) in enumerate(zip(nominal, reel))
    plot!(p7, [r, n], [i, i]; color = n < r ? "#c0392b" : "#95a5a6",
          lw = 2, alpha = 0.6, label = "")
end

vline!(p7, [0]; color = :gray, lw = 0.9, label = "")
scatter!(p7, reel, ypos; ms = 6, color = "#27ae60", markerstrokewidth = 0,
         label = "CAGR réel (USD constants 2015)")
scatter!(p7, nominal, ypos; ms = 6, color = "#2980b9", markerstrokewidth = 0,
         label = "CAGR nominal (USD courants)")
p7
"""),

    md("""
Les cinq écarts les plus marqués dans un sens et dans l'autre. Un écart positif signifie que
l'inflation et le change gonflent la croissance affichée ; négatif, qu'ils la masquent.
"""),
    code("""
ecarts = first(dropmissing(df_summary, C_ECART), 30)
cols = [:country_name, C_CAGR_H, C_CAGR_RH, C_ECART]

println("Écart le plus fort (croissance nominale gonflée) :")
show(first(sort(ecarts, C_ECART, rev = true), 5)[:, cols],
     allcols = true, eltypes = false)
println("\\n\\nÉcart le plus faible ou négatif (croissance masquée) :")
show(first(sort(ecarts, C_ECART), 5)[:, cols],
     allcols = true, eltypes = false)
"""),

    md("""
## 8. Comparer des Niveaux : Parité de Pouvoir d'Achat

Corriger l'effet change sur la **croissance** ne suffit pas à comparer des **niveaux** :
le PIB en volume reste converti en dollars au taux de l'année de base. Or le taux de marché
reflète les flux financiers, pas ce qu'une unité de production permet d'acheter sur place.

La parité de pouvoir d'achat corrige ce biais, et le classement mondial s'en trouve
nettement modifié.
"""),
    code("""
gr()

df_ppa = dropmissing(df_summary, C_PPA_OBS)
df_ppa = sort(first(sort(df_ppa, C_RANK_PPA), 12), C_PPA_OBS)

ypos = 1:nrow(df_ppa)

p8 = bar(ypos .- 0.19, tonum(df_ppa[!, C_GDP_OBS]);
    orientation = :h, bar_width = 0.38, linecolor = :match, color = "#2980b9",
    label = "Nominal (USD courants, taux de marché)")
bar!(p8, ypos .+ 0.19, tonum(df_ppa[!, C_PPA_OBS]);
    orientation = :h, bar_width = 0.38, linecolor = :match, color = "#8e44ad",
    label = "PPA (\\$ internationaux constants 2021)")

plot!(p8; yticks = (ypos, df_ppa.country_name), ylims = (0.4, nrow(df_ppa) + 0.6),
    xlabel = "PIB $(an_obs) (Milliards)",
    title = "Niveaux de PIB $(an_obs) : taux de marché contre parité de pouvoir d'achat",
    size = (1000, 620), dpi = 150, legend = :bottomright,
    left_margin = 5mm, bottom_margin = 4mm)
"""),

    md("""
Le déplacement de rang entre les deux bases. Un écart positif signifie que le pays est mieux
classé à parité de pouvoir d'achat, sa monnaie sous-évaluant sa production au taux de marché.
"""),
    code("""
classement = first(sort(dropmissing(df_summary, C_RANK_PPA), C_RANK_PPA), 15)

show(select(classement,
        :country_name,
        C_GDP_OBS => :PIB_nominal,
        C_PPA_OBS => :PIB_PPA,
        C_RANK => :Rang_nominal,
        C_RANK_PPA => :Rang_PPA,
        C_ECART_RANG => :Ecart),
     allrows = true, allcols = true, eltypes = false)
"""),

    md("""
## 9. Fonction d'Interrogation Personnalisée par Pays

`analyze_country` accepte un code ISO3 (`"FRA"`) ou un nom (`"France"`) et renvoie
les dix dernières années disponibles, prévisions comprises.
"""),
    code("""
fmt(x)     = ismissing(x) ? "n/d" : @sprintf("%.2f", x)
fmtrank(x) = ismissing(x) ? "n/d" : string("#", Int(x))

\"\"\"
    analyze_country(query)

Affiche les indicateurs clés d'un pays (code ISO3 ou nom) et retourne ses dix
derniers points de série. Retourne `nothing` si le pays est introuvable.
\"\"\"
function analyze_country(query::AbstractString)
    q = uppercase(query)
    cdata = df_unified[(df_unified.country_code .== q) .|
                       (uppercase.(df_unified.country_name) .== q), :]

    if isempty(cdata)
        println("Aucun pays trouvé pour '", query, "'.")
        return nothing
    end

    code  = first(cdata.country_code)
    cname = first(cdata.country_name)
    println("=== Rapport PIB : ", cname, " (", code, ") ===")

    srow = df_summary[df_summary.country_code .== code, :]
    if !isempty(srow)
        r = first(srow)
        println("• PIB 2000                : ", fmt(r[C_GDP_DEBUT]), " Md USD")
        println("• PIB 2024                : ", fmt(r[C_GDP_OBS]), " Md USD")
        println("• PIB 2030 (prévision)    : ", fmt(r[C_GDP_FIN]), " Md USD")
        println("• CAGR 2000-2024          : ", fmt(r[C_CAGR_H]), " % nominal · ",
                                                fmt(r[C_CAGR_RH]), " % en volume")
        println("• CAGR 2024-2030          : ", fmt(r[C_CAGR_P]), " % nominal · ",
                                                fmt(r[C_CAGR_RP]), " % en volume")
        println("• Rang mondial 2024       : ", fmtrank(r[C_RANK]), " nominal · ",
                                                fmtrank(r[C_RANK_PPA]), " à PPA")
        println("• Rang mondial 2030       : ", fmtrank(r[C_RANK_FIN]))
    else
        println("(agrégat : absent des classements par pays)")
    end

    last(sort(select(cdata, :year, :data_type, :GDP_Nominal_Billions_USD,
                     :GDP_Real_Billions_USD, :GDP_Growth_Pct, :GDP_Per_Capita_USD), :year), 10)
end

analyze_country("France")
"""),
]

notebook_content = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": f"Julia {JULIA_VERSION}",
            "language": "julia",
            "name": f"julia-{JULIA_VERSION}",
        },
        "language_info": {
            "file_extension": ".jl",
            "mimetype": "application/julia",
            "name": "julia",
            "version": JULIA_VERSION,
        },
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}

output_path = os.path.join("gdp_analysis_notebook_julia.ipynb")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(notebook_content, f, indent=1, ensure_ascii=False)

print(f"[OK] Notebook Julia cree avec succes : {output_path}")
