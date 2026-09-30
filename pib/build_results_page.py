#!/usr/bin/env python3
"""
build_results_page.py
---------------------
Construit `outputs/resultats_gdp.html`, page de résultats autonome : tableaux lus
dans `data/processed/`, graphiques inlinés depuis `outputs/`.

Rien n'est saisi en dur. Une page dont les chiffres sont recopiés se désynchronise
silencieusement des données au premier nouveau run — c'est précisément le défaut que
le reste du pipeline s'attache à éviter.

    python produire_rapports.py        # référence et, le cas échéant, plus récent
"""

import os
import json
import base64
import logging
import argparse
from datetime import datetime

import pandas as pd

from pib.gdp_pipeline import unified_csv_path
from pib.evaluate_forecasts import GROUPES_REVENU, ANNEES_RECESSION_MONDIALE, GRANDES_ECONOMIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

ESP = " "   # espace fine insécable, séparateur de milliers
MOINS = "−"  # signe moins typographique


# ------------------------------------------------------------ chargement

def charger(data_dir: str):
    """Charge la synthèse et la série unifiée, et en déduit les années du run."""
    synthese_csv = os.path.join(data_dir, "processed", "gdp_country_summary.csv")
    if not os.path.exists(synthese_csv):
        raise FileNotFoundError(
            "Données absentes. Lancez d'abord : python produire_rapports.py")

    unifie = pd.read_csv(unified_csv_path(data_dir))
    synthese = pd.read_csv(synthese_csv)

    annees = {
        "debut": int(unifie["year"].min()),
        "obs": int(unifie.loc[~unifie["is_forecast"].astype(bool), "year"].max()),
        "fin": int(unifie["year"].max()),
    }
    return unifie, synthese, annees


def colonnes(annees: dict) -> dict:
    """Reconstruit les intitulés de colonnes, qui portent les bornes du run."""
    d, o, f = annees["debut"], annees["obs"], annees["fin"]
    return {
        "gdp_debut": f"GDP_{d}_Billion_USD",
        "gdp_obs": f"GDP_{o}_Billion_USD",
        "gdp_fin": f"GDP_{f}_Forecast_Billion_USD",
        "cagr_h": f"CAGR_Historique_{d}_{o}_Pct",
        "cagr_p": f"CAGR_Prevision_{o}_{f}_Pct",
        "cagr_rh": f"CAGR_Reel_Historique_{d}_{o}_Pct",
        "reel_obs": f"GDP_Reel_{o}_Billion_USD_2015",
        "ecart": f"Ecart_Nominal_Reel_{d}_{o}_Pts",
        "ppa_obs": f"GDP_PPA_{o}_Billion_Intl_2021",
        "rang": f"Rank_{o}",
        "rang_fin": f"Rank_{f}_Forecast",
        "rang_ppa": f"Rank_PPA_{o}",
        "ecart_rang": f"Ecart_Rang_Nominal_PPA_{o}",
    }


def liste_pays(noms: list) -> str:
    """Énumère des pays ; un nom qui contient une virgule (« Bahamas, The ») est guillemeté."""
    noms = [f"« {nom} »" if "," in nom else nom for nom in noms]
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def note_rapport(data_dir: str, annee: int) -> str:
    """
    Situe la page parmi les rapports produits : référence ou plus récent, et ce qui les
    sépare. Rien pour un rapport unique (dernière année imposée).
    """
    try:
        with open(os.path.join(data_dir, "extraction_metadata.json"), encoding="utf-8") as f:
            rapport = json.load(f).get("rapport", {})
    except FileNotFoundError:
        return ""
    candidates = rapport.get("candidates", {})
    classes = {int(a): c["pays_classes"] for a, c in candidates.items()}
    reference, recente = rapport.get("annee_reference"), rapport.get("annee_plus_recente")

    if rapport.get("type") == "reference" and rapport.get("autre_rapport"):
        texte = (f"Rapport de référence : {annee} est la dernière année observée dont le classement est "
                 f"quasi complet ({classes.get(annee, '?')} pays classés). Les données {recente}, déjà "
                 f"publiées pour une partie des pays, font l'objet d'un "
                 f'<a href="{rapport["autre_rapport"]}/resultats_gdp.html">rapport plus récent</a>, '
                 f"qui classe {classes.get(recente, '?')} pays.")
    elif rapport.get("type") == "reference":
        texte = (f"{annee} est la dernière année publiée par la Banque Mondiale, et son classement "
                 f"est quasi complet ({classes.get(annee, '?')} pays classés).")
    elif rapport.get("type") == "plus_recent":
        sans_rang = rapport.get("pays_sans_rang_par_rapport_a_la_reference", [])
        texte = (f"Rapport le plus récent : {annee}, dernière année publiée par la Banque Mondiale, "
                 f"encore incomplète. Faute de donnée {annee}, {liste_pays(sans_rang) if sans_rang else 'aucun pays'} "
                 f"sort{'ent' if len(sans_rang) > 1 else ''} du classement ({classes.get(annee, '?')} pays "
                 f'classés contre {classes.get(reference, "?")} dans le <a href="../resultats_gdp.html">'
                 f"rapport de référence</a>, sur {reference}).")
    else:
        return ""
    return f'    <p class="lede note">{texte}</p>\n'


def image(output_dir: str, nom: str):
    """
    Inline un PNG en data URI. Retourne None si le graphique n'a pas été produit.

    Le nom exact porte les années du run : un motif générique pourrait retenir le
    graphique d'un run précédent, sur d'autres bornes.
    """
    chemin = os.path.join(output_dir, nom)
    if not os.path.exists(chemin):
        logging.warning(f"Graphique absent, section omise : {nom}")
        return None
    with open(chemin, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


# ------------------------------------------------------------- formatage

def nb(valeur, decimales: int = 0) -> str:
    if pd.isna(valeur):
        return "n/d"
    texte = f"{valeur:,.{decimales}f}".replace(",", ESP).replace(".", ",")
    return texte.replace("-", MOINS)


def signe(valeur, decimales: int = 2) -> str:
    if pd.isna(valeur):
        return "n/d"
    return f"{valeur:+.{decimales}f}".replace(".", ",").replace("-", MOINS)


def puce_rang(delta) -> str:
    if pd.isna(delta) or delta == 0:
        return '<span class="delta delta-flat">=</span>'
    classe, fleche = ("delta-up", "▲") if delta > 0 else ("delta-down", "▼")
    return f'<span class="delta {classe}">{fleche} {abs(int(delta))}</span>'


def lignes(rows: list) -> str:
    return "\n".join("        <tr>" + "".join(rows_cellules) + "</tr>"
                     for rows_cellules in rows)


# --------------------------------------------------------------- sections

def table_top(synthese, c, annees):
    corps = []
    for _, r in synthese.head(10).iterrows():
        corps.append([
            f'<td class="mono code">{r.country_code}</td>',
            f'<td class="name">{r.country_name}</td>',
            f'<td class="num">{nb(r[c["gdp_debut"]])}</td>',
            f'<td class="num">{nb(r[c["gdp_obs"]])}</td>',
            f'<td class="num">{nb(r[c["gdp_fin"]])}</td>',
            f'<td class="num">{nb(r[c["cagr_h"]], 2)}</td>',
            f'<td class="num">{nb(r[c["cagr_p"]], 2)}</td>',
            f'<td class="num rank">{nb(r[c["rang"]])} → {nb(r[c["rang_fin"]])} '
            f'{puce_rang(r["Rank_Change"])}</td>',
        ])
    entetes = ["Code", "Pays", f"PIB {annees['debut']}", f"PIB {annees['obs']}",
               f"PIB {annees['fin']}", "CAGR hist.", "CAGR prév.", "Rang"]
    return entetes, corps


def sous_ensemble_volume(synthese, c):
    """Lignes du tableau « volume ». Les faits saillants du texte en sont tirés :
    citer un pays absent du tableau rendrait le commentaire incohérent avec ce qu'on voit."""
    return synthese.dropna(subset=[c["cagr_h"], c["cagr_rh"]]).head(10)


def sous_ensemble_ppa(synthese, c):
    """Lignes du tableau « parité », même raison."""
    return synthese.dropna(subset=[c["rang_ppa"]]).nsmallest(15, c["rang_ppa"])


def table_volume(synthese, c):
    df = sous_ensemble_volume(synthese, c)
    corps = []
    for _, r in df.iterrows():
        ecart = r[c["ecart"]]
        classe = "wedge-neg" if (pd.notna(ecart) and ecart < 0) else "wedge-pos"
        corps.append([
            f'<td class="name">{r.country_name}</td>',
            f'<td class="num">{nb(r[c["gdp_obs"]])}</td>',
            f'<td class="num">{nb(r[c["reel_obs"]])}</td>',
            f'<td class="num">{nb(r[c["cagr_h"]], 2)}</td>',
            f'<td class="num">{nb(r[c["cagr_rh"]], 2)}</td>',
            f'<td class="num"><span class="wedge {classe}">{signe(ecart)} pt</span></td>',
        ])
    return ["Pays", "PIB courant", "PIB volume", "CAGR nominal", "CAGR volume", "Écart"], corps


def table_ppa(synthese, c):
    df = sous_ensemble_ppa(synthese, c)
    corps = []
    for _, r in df.iterrows():
        corps.append([
            f'<td class="num rank">{nb(r[c["rang_ppa"]])}</td>',
            f'<td class="name">{r.country_name}</td>',
            f'<td class="num">{nb(r[c["gdp_obs"]])}</td>',
            f'<td class="num">{nb(r[c["ppa_obs"]])}</td>',
            f'<td class="num rank">{nb(r[c["rang"]])} → {nb(r[c["rang_ppa"]])} '
            f'{puce_rang(r[c["ecart_rang"]])}</td>',
        ])
    return ["Rang PPA", "Pays", "PIB nominal", "PIB à PPA", "Rang nominal → PPA"], corps


def table_pays(unifie, code: str):
    df = unifie[unifie.country_code == code].sort_values("year").tail(10)
    corps = []
    for _, r in df.iterrows():
        prevision = bool(r.is_forecast)
        corps.append([
            f'<td class="num">{int(r.year)}</td>',
            f'<td><span class="tag {"tag-f" if prevision else "tag-h"}">{r.data_type}</span></td>',
            f'<td class="num">{nb(r.GDP_Nominal_Billions_USD)}</td>',
            f'<td class="num">{nb(r.GDP_Real_Billions_USD)}</td>',
            f'<td class="num">{nb(r.GDP_Growth_Pct, 2)}</td>',
            f'<td class="num">{nb(r.GDP_Per_Capita_USD)}</td>',
        ])
    return ["Année", "Type", "PIB courant", "PIB volume", "Croissance réelle", "PIB / hab."], corps


def bloc_table(entetes, corps) -> str:
    th = "".join(f"<th>{e}</th>" for e in entetes)
    return (f'    <div class="scroll">\n      <table>\n        <thead><tr>{th}</tr></thead>\n'
            f'        <tbody>\n{lignes(corps)}\n        </tbody>\n      </table>\n    </div>')


# En deçà d'un demi-point, un biais moyen se confond avec l'erreur d'échantillonnage
SEUIL_BIAIS = 0.5


def sens_biais(valeur) -> str:
    return "trop optimiste" if valeur > 0 else "trop pessimiste"


def verdict_biais(table: pd.DataFrame) -> tuple:
    """
    Résumé qualitatif d'une synthèse par horizon : biais notable ou non sur l'année en
    cours, et signe commun du biais au-delà (0 s'il change de signe). Deux références qui
    donnent le même verdict mènent à la même conclusion.
    """
    au_dela = table.loc[table.index >= 1, "biais_moyen"]
    signe_commun = 1 if (au_dela > 0).all() else -1 if (au_dela < 0).all() else 0
    return abs(table.loc[0, "biais_moyen"]) >= SEUIL_BIAIS, signe_commun


def pays_du_groupe(code: str) -> str:
    """« pays à revenu élevé », « pays à faible revenu »…"""
    return f"pays à {GROUPES_REVENU.get(code, code).lower()}"


def extremes_par_groupe(table: pd.DataFrame, colonne: str, unite: str) -> str:
    """Phrase situant les groupes de revenu extrêmes pour `colonne` (une ligne par groupe)."""
    table = table[table["income_group"].isin(GROUPES_REVENU)]
    if len(table) < 2:
        return ""
    haut, bas = table.loc[table[colonne].idxmax()], table.loc[table[colonne].idxmin()]
    return (f"de {signe(bas[colonne], 1)} {unite} pour les {pays_du_groupe(bas['income_group'])} "
            f"à {signe(haut[colonne], 1)} {unite} pour les {pays_du_groupe(haut['income_group'])}")


def et(elements: list) -> str:
    elements = [str(e) for e in elements]
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " et " + elements[-1]


def complements_previsions(processed: str, hmax: int) -> str:
    """
    Trois lectures de plus, chacune omise si son fichier manque : l'édition d'avril face à
    celle d'octobre, le FMI face à une prévision naïve, et la croissance mondiale.
    """
    html = ""

    saison_csv = os.path.join(processed, "weo_forecast_bias_by_season_ngdp_rpch.csv")
    if os.path.exists(saison_csv):
        t = pd.read_csv(saison_csv).set_index(["horizon", "saison"])
        if (0, "S") in t.index and (0, "F") in t.index:
            s0, f0 = t.loc[(0, "S")], t.loc[(0, "F")]
            ecart = s0["erreur_absolue_moyenne"] - f0["erreur_absolue_moyenne"]
            verdict = ("ne se valent pas" if abs(ecart) >= 0.2 else "se valent à peu près")
            html += f"""
    <p class="col">Sur l'année en cours, l'édition d'avril et celle d'octobre, publiée six mois
    plus tard, {verdict} : biais de {signe(s0["biais_moyen"])} point en avril,
    {signe(f0["biais_moyen"])} en octobre, et erreur absolue moyenne de
    {nb(s0["erreur_absolue_moyenne"], 2)} contre {nb(f0["erreur_absolue_moyenne"], 2)} point. Le
    tableau ci-dessus fait la moyenne des deux.</p>"""

    naif_csv = os.path.join(processed, "weo_forecast_vs_naive_ngdp_rpch.csv")
    if os.path.exists(naif_csv):
        t = pd.read_csv(naif_csv).set_index("horizon")
        if 0 in t.index and hmax in t.index:
            corps = [[f'<td class="num">{int(h)}</td>',
                      f'<td class="num">{nb(r["eam_fmi"], 2)} pt</td>',
                      f'<td class="num">{nb(r["eam_naif"], 2)} pt</td>',
                      f'<td class="num">{nb(r["part_fmi_meilleur"])} %</td>'] for h, r in t.iterrows()]
            html += f"""
    <p class="col">Se tromper n'empêche pas d'être utile : encore faut-il faire mieux qu'une règle
    simple. Face à une prévision naïve — la croissance moyenne des quatre années que le FMI
    connaissait déjà —, il est plus proche du réalisé dans {nb(t.loc[0, "part_fmi_meilleur"])} % des cas
    sur l'année en cours, mais dans {nb(t.loc[hmax, "part_fmi_meilleur"])} % seulement à {hmax} ans :
    à cet horizon, son erreur absolue moyenne ({nb(t.loc[hmax, "eam_fmi"], 2)} point) n'est inférieure
    que de {nb((1 - t.loc[hmax, "rapport_eam"]) * 100)} % à celle de la règle naïve
    ({nb(t.loc[hmax, "eam_naif"], 2)} point).</p>
{bloc_table(["Horizon", "Erreur absolue FMI", "Erreur absolue naïve", "FMI plus proche du réalisé"], corps)}"""

    efficience_csv = os.path.join(processed, "weo_forecast_efficiency_ngdp_rpch.csv")
    if os.path.exists(efficience_csv):
        t = pd.read_csv(efficience_csv).set_index("horizon")
        if 1 in t.index and hmax in t.index and "biais_median_q5" in t.columns:
            corps = [[f'<td class="num">{int(h)}</td>', f'<td class="num">{nb(r["pente"], 2)}</td>',
                      f'<td class="num">{signe(r["biais_median_q1"])} pt</td>',
                      f'<td class="num">{signe(r["biais_median_q5"])} pt</td>'] for h, r in t.iterrows()]
            html += f"""
    <p class="col">Le biais n'est pas uniforme : plus le FMI annonce de croissance, plus il
    surestime. Si les prévisions étaient bien calibrées, le réalisé suivrait un à un les écarts de
    croissance annoncés d'un pays à l'autre ; la droite du réalisé sur le prévu aurait une pente
    de 1. Elle vaut {nb(t.loc[1, "pente"], 2)} à un an et {nb(t.loc[hmax, "pente"], 2)} à {hmax} ans.
    À cet horizon, le biais médian va de {signe(t.loc[hmax, "biais_median_q1"])} point pour le
    cinquième des prévisions les plus modestes à {signe(t.loc[hmax, "biais_median_q5"])} pour le
    cinquième des plus fortes.</p>
{bloc_table(["Horizon", "Pente du réalisé sur le prévu", "Biais médian, prévisions les plus faibles",
             "Biais médian, prévisions les plus fortes"], corps)}"""

    monde_csv = os.path.join(processed, "weo_world_bias_ngdp_rpch.csv")
    if os.path.exists(monde_csv):
        t = pd.read_csv(monde_csv).set_index("horizon")
        if 1 in t.index and hmax in t.index:
            html += f"""
    <p class="col">Pour la croissance mondiale elle-même — l'agrégat du FMI —, le biais moyen vaut
    {signe(t.loc[0, "biais_moyen"])} point sur l'année en cours, {signe(t.loc[1, "biais_moyen"])} à un an
    et {signe(t.loc[hmax, "biais_moyen"])} à {hmax} ans (intervalle de confiance de
    {signe(t.loc[hmax, "ic95_bas"])} à {signe(t.loc[hmax, "ic95_haut"])}). Il n'est mesuré que contre
    la ré-estimation du FMI : la Banque Mondiale agrège le monde aux taux de change de marché, et
    non à parité de pouvoir d'achat ; sa croissance mondiale, plus basse, n'est pas comparable.</p>"""
    return html


def section_previsions(data_dir: str, figure_uri) -> str:
    """
    Section « qualité des prévisions », alimentée par pib.evaluate_forecasts.

    Omise si l'évaluation n'a pas été lancée : mieux vaut une page plus courte qu'une
    section aux chiffres inventés.
    """
    processed = os.path.join(data_dir, "processed")
    biais_csv = os.path.join(processed, "weo_forecast_bias_ngdp_rpch.csv")
    if not figure_uri or not os.path.exists(biais_csv):
        return ""

    biais = pd.read_csv(biais_csv)
    fmi = biais[biais["reference"].str.startswith("FMI")].set_index("horizon")
    if fmi.empty:
        return ""

    total = int(fmi["observations"].sum())
    h0 = fmi.loc[0]
    hmax = fmi.loc[fmi.index.max()]
    au_dela = fmi.loc[fmi.index >= 1, "biais_moyen"]

    # Le commentaire se déduit du tableau qu'il accompagne : écrit d'avance, il
    # affirmerait une conclusion que la prochaine édition du WEO pourrait démentir.
    if abs(h0["biais_moyen"]) < SEUIL_BIAIS:
        annee_en_cours = f"le FMI est quasiment sans biais ({signe(h0['biais_moyen'])} point)"
    else:
        annee_en_cours = (f"le FMI est déjà biaisé ({signe(h0['biais_moyen'])} point, "
                          f"{sens_biais(h0['biais_moyen'])})")
    if (au_dela > 0).all() or (au_dela < 0).all():
        verbe = "surestime" if au_dela.iloc[0] > 0 else "sous-estime"
        horizons_suivants = (f"il {verbe} la croissance à tous les horizons suivants, "
                             f"de {signe(au_dela.min())} à {signe(au_dela.max())} point en moyenne")
    else:
        horizons_suivants = (f"le signe du biais varie selon l'horizon, de {signe(au_dela.min())} "
                             f"à {signe(au_dela.max())} point en moyenne")

    # Ce que vaut ce biais moyen : pondération, médiane, poids des récessions, incertitude
    lectures = ""
    if 1 in fmi.index and "biais_pondere_pib" in fmi.columns:
        h1 = fmi.loc[1]
        exclut_zero = h1["ic95_bas"] > 0 or h1["ic95_haut"] < 0
        lectures = f"""
    <p class="col">Ce biais moyen compte chaque pays pour un. À un an, pondéré par le PIB — ce que
    l'erreur représente pour l'économie mondiale —, il vaut {signe(h1["biais_pondere_pib"])} point
    au lieu de {signe(h1["biais_moyen"])}, et la médiane {signe(h1["mediane"])} : quelques fortes
    surestimations tirent la moyenne. Sans les récessions mondiales de
    {et(ANNEES_RECESSION_MONDIALE)}, il serait de {signe(h1["biais_hors_recessions_mondiales"])} point.
    Les pays d'une même année subissant les mêmes chocs, l'incertitude se mesure par année visée :
    l'intervalle de confiance à 95 % du biais moyen va de {signe(h1["ic95_bas"])} à
    {signe(h1["ic95_haut"])} point, {"et exclut donc zéro" if exclut_zero else "et inclut zéro"}.</p>"""
        revenu_csv = os.path.join(processed, "weo_forecast_bias_by_income_ngdp_rpch.csv")
        if os.path.exists(revenu_csv):
            revenu = pd.read_csv(revenu_csv)
            phrase = extremes_par_groupe(revenu[revenu["horizon"] == 1], "biais_moyen", "point")
            if phrase:
                lectures += f"""
    <p class="col">Selon le niveau de revenu, le biais moyen à un an va {phrase}.</p>"""

    lectures += complements_previsions(processed, int(fmi.index.max()))

    bm = biais[biais["reference"].str.startswith("Banque")].set_index("horizon")
    if bm.empty:
        robustesse = "La série observée de la Banque Mondiale n'était pas disponible pour recouper ce résultat."
    elif verdict_biais(bm) == verdict_biais(fmi):
        robustesse = ("Le calcul est aussi mené contre la série observée de la Banque Mondiale, "
                      "et la conclusion ne change pas.")
    else:
        robustesse = ("Le calcul mené contre la série observée de la Banque Mondiale ne conduit pas "
                      "à la même conclusion : le résultat dépend de la référence retenue.")

    avec_lectures = "biais_pondere_pib" in fmi.columns
    corps = [[
        f'<td class="num">{int(h)}{" (année en cours)" if h == 0 else ""}</td>',
        f'<td class="num">{signe(r["biais_moyen"])} pt</td>',
        *([f'<td class="num">{signe(r["biais_pondere_pib"])} pt</td>',
           f'<td class="num">{signe(r["mediane"])} pt</td>',
           f'<td class="num">{signe(r["ic95_bas"])} à {signe(r["ic95_haut"])}</td>'] if avec_lectures else []),
        f'<td class="num">{nb(r["erreur_absolue_moyenne"], 2)} pt</td>',
        f'<td class="num rank">{nb(r["observations"])}</td>',
    ] for h, r in fmi.iterrows()]
    entetes = ["Horizon", "Biais moyen",
               *(["Pondéré par le PIB", "Médiane", "IC 95 % du biais moyen"] if avec_lectures else []),
               "Erreur absolue moyenne", "Projections"]

    return f"""
  <section>
    <div class="sec-head col"><h2>Ces prévisions valent-elles quelque chose ?</h2></div>
    <p class="col">La question ne se règle pas avec les données courantes : l'API du FMI ne
    sert que son millésime du moment. Il faut les publications d'époque, que le FMI consolide
    depuis 1990. Confronter chacune à ce qui s'est réellement produit donne {nb(total)}
    projections de croissance à examiner.</p>
{bloc_figure(figure_uri, "Biais et erreur des prévisions du FMI par horizon et par année visée",
             "À gauche le biais par horizon de projection ; à droite l'erreur médiane selon "
             "l'année visée, où ressortent les récessions.")}
{bloc_table(entetes, corps)}
    <p class="col">Sur l'année en cours, {annee_en_cours}. Au-delà, {horizons_suivants} ;
    l'erreur absolue moyenne passe de {nb(h0["erreur_absolue_moyenne"], 2)} point sur l'année en
    cours à {nb(hmax["erreur_absolue_moyenne"], 2)} à {int(fmi.index.max())} ans.</p>{lectures}
    <p class="col note">L'erreur est mesurée contre la ré-estimation du FMI un an après l'année
    visée, plutôt que contre le chiffre définitif d'aujourd'hui : juger une prévision sur des
    révisions statistiques postérieures la pénaliserait pour une information hors de sa portée.
    {robustesse} Le biais pondéré ne porte que sur les années que couvre la série du pipeline ;
    les groupes de revenu suivent la classification actuelle de la Banque Mondiale.</p>
  </section>
"""


def section_niveaux(data_dir: str, figure_uri) -> str:
    """
    Section « PIB prévu et PIB réalisé » : erreur sur le niveau, croissances enchaînées.
    Omise si l'évaluation des niveaux n'a pas été lancée.
    """
    processed = os.path.join(data_dir, "processed")
    niveau_csv = os.path.join(processed, "weo_level_bias_ngdp_rpch.csv")
    if not figure_uri or not os.path.exists(niveau_csv):
        return ""
    niveaux = pd.read_csv(niveau_csv)
    fmi = niveaux[niveaux["reference"].str.startswith("FMI")].set_index("horizon")
    if fmi.empty:
        return ""
    horizon = int(fmi.index.max())
    fin = fmi.loc[horizon]

    trop_haut, trop_bas = fin["part_trop_haut_5pct"], fin["part_trop_bas_5pct"]
    asymetrie = ("Les erreurs ne se compensent pas : " if trop_haut > 2 * trop_bas else "") + \
        (f"le niveau prévu dépasse le réalisé de plus de 5 % dans {nb(trop_haut)} % des cas, "
         f"et lui est inférieur de plus de 5 % dans {nb(trop_bas)} % des cas.")

    revenu_phrase = ""
    revenu_csv = os.path.join(processed, "weo_level_bias_by_income_ngdp_rpch.csv")
    if os.path.exists(revenu_csv):
        revenu = pd.read_csv(revenu_csv)
        phrase = extremes_par_groupe(revenu[revenu["horizon"] == horizon], "mediane", "%")
        if phrase:
            revenu_phrase = f" Selon le niveau de revenu, l'erreur médiane à {horizon} ans va {phrase}."

    croissance_csv = os.path.join(processed, "weo_level_bias_by_projected_growth_ngdp_rpch.csv")
    if os.path.exists(croissance_csv):
        t = pd.read_csv(croissance_csv)
        t = t[t["horizon"] == horizon].sort_values("classe_de_croissance")
        if len(t) >= 2:
            bas, haut = t.iloc[0], t.iloc[-1]
            revenu_phrase += (f" Surtout, elle croît avec la croissance projetée : {signe(bas['mediane'], 1)} % "
                              f"pour les projections les plus modestes (croissance cumulée médiane de "
                              f"{nb(bas['croissance_projetee_mediane_pct'])} %), {signe(haut['mediane'], 1)} % pour "
                              f"les plus fortes ({nb(haut['croissance_projetee_mediane_pct'])} %).")

    bm = niveaux[niveaux["reference"].str.startswith("Banque")].set_index("horizon")
    recoupement = (f" Contre la série observée de la Banque Mondiale, elle est de {signe(bm.loc[horizon, 'mediane'], 1)} %."
                   if horizon in bm.index else "")

    corps = [[
        f'<td class="num">{int(h)}</td>',
        f'<td class="num">{signe(r["mediane"], 1)} %</td>',
        f'<td class="num">{signe(r["moyenne_ponderee_pib"], 1)} %</td>',
        f'<td class="num">{signe(r["p10"], 1)} à {signe(r["p90"], 1)} %</td>',
        f'<td class="num">{nb(r["part_trop_haut_5pct"])} %</td>',
        f'<td class="num">{nb(r["part_trop_bas_5pct"])} %</td>',
    ] for h, r in fmi.iterrows()]
    entetes = ["Horizon", "Médiane", "Pondérée par le PIB", "80 % des cas", "Prévu trop haut de +5 %",
               "Prévu trop bas de +5 %"]

    return f"""
  <section>
    <div class="sec-head col"><h2>PIB prévu et PIB réalisé</h2></div>
    <p class="col">Une erreur de croissance, répétée d'année en année, se cumule sur le niveau du
    PIB. En enchaînant les croissances projetées par chaque édition, puis les croissances réalisées,
    on compare le niveau prévu au niveau atteint. À {horizon} ans, le niveau prévu dépasse le
    réalisé de {signe(fin["mediane"], 1)} % en médiane ({signe(fin["moyenne_ponderee_pib"], 1)} %
    pondéré par le PIB). {asymetrie}{revenu_phrase}</p>
{bloc_figure(figure_uri, "Erreur sur le niveau du PIB en volume par horizon et par groupe de revenu",
             "À gauche la distribution de l'erreur de niveau par horizon ; à droite sa médiane "
             "par groupe de revenu.")}
{bloc_table(entetes, corps)}
    <p class="col note">Erreur de niveau : niveau prévu / niveau réalisé − 1, en volume. Réalisé :
    croissances ré-estimées par le FMI un an après.{recoupement} En dollars courants s'ajouteraient
    les erreurs de change et d'inflation, que la base historique du FMI, limitée aux taux, ne
    permet pas de mesurer.</p>
  </section>
"""


def qualifier_couverture(couverture: float, cible: float) -> str:
    """Une fourchette qui contient bien plus (moins) d'erreurs que visé est prudente (étroite)."""
    if couverture > cible + 5:
        return "prudentes"
    if couverture < cible - 5:
        return "trop étroites"
    return "justes"


def section_fourchettes(data_dir: str, synthese: pd.DataFrame, c: dict, f: int) -> str:
    """
    Section « projections à l'aune des erreurs passées » : fourchette empirique autour du
    PIB en volume projeté, pour les dix premières économies, et sa calibration. Omise sans
    fourchettes.
    """
    processed = os.path.join(data_dir, "processed")
    chemin = os.path.join(processed, "gdp_projection_bands.csv")
    if not os.path.exists(chemin):
        return ""
    bandes = pd.read_csv(chemin).set_index("country_code")
    niveau, bas, haut = (f"GDP_Reel_{f}_Billion_USD_2015", f"GDP_Reel_{f}_Bas", f"GDP_Reel_{f}_Haut")
    if niveau not in bandes.columns or "croissance_projetee_pct" not in bandes.columns:
        return ""
    tete = [code for code in synthese.dropna(subset=[c["rang"]]).nsmallest(10, c["rang"])["country_code"]
            if code in bandes.index]
    if not tete:
        return ""
    horizon = int(bandes["horizon"].iloc[0])
    edition = f - horizon
    liees = bandes.dropna(subset=["croissance_projetee_pct"])
    penchant = (" Plus la croissance projetée est forte, plus la fourchette penche vers le bas."
                if len(liees) > 2 and liees["croissance_projetee_pct"].corr(liees["borne_haute_pct"]) < 0 else "")

    corps = [[
        f'<td class="name">{bandes.loc[code, "country_name"]}</td>',
        f'<td class="num">{signe(bandes.loc[code, "croissance_projetee_pct"], 1)} %</td>',
        f'<td class="num">{nb(bandes.loc[code, niveau])}</td>',
        f'<td class="num">{nb(bandes.loc[code, bas])} – {nb(bandes.loc[code, haut])}</td>',
        f'<td class="num">{signe(bandes.loc[code, "borne_basse_pct"], 1)} à {signe(bandes.loc[code, "borne_haute_pct"], 1)} %</td>',
    ] for code in tete]

    calibration = ""
    calibration_csv = os.path.join(processed, "gdp_projection_bands_calibration.csv")
    if os.path.exists(calibration_csv):
        cal = pd.read_csv(calibration_csv)
        retenue, pays = cal[cal["retenue"]], cal[cal["methode"] == "historique du pays"]
        if len(retenue) and len(pays):
            r, cible = retenue.iloc[0], retenue.iloc[0]["cible_pct"]
            par_pays = pays.iloc[0]["couverture_pct"]
            constat_pays = (" : le biais propre à un pays ne se reproduit pas d'une période à l'autre"
                            if par_pays < r["couverture_pct"] - 5 else "")
            calibration = f"""
    <p class="col">Ces fourchettes sont éprouvées sur le passé : calculées sur les éditions
    {r["editions_de_calcul"]}, elles ont contenu {nb(r["couverture_pct"])} % des erreurs des éditions
    {r["editions_de_test"]}, pour une cible de {nb(cible)} %. Elles sont
    {qualifier_couverture(r["couverture_grandes_economies_pct"], cible)} pour les {GRANDES_ECONOMIES}
    premières économies, dont elles ont contenu {nb(r["couverture_grandes_economies_pct"])} % des erreurs,
    et {qualifier_couverture(r["couverture_faible_revenu_pct"], cible)} pour les pays à faible revenu
    ({nb(r["couverture_faible_revenu_pct"])} %). Tirées de l'historique de chaque pays, elles n'en auraient
    contenu que {nb(par_pays)} %{constat_pays}.</p>"""

    return f"""
  <section>
    <div class="sec-head col"><h2>Les projections {f} à l'aune des erreurs passées</h2></div>
    <p class="col">Les projections {f} de ce rapport viennent de l'édition {edition} du WEO, à
    {horizon} ans d'horizon. Appliquer à chacune les erreurs de niveau commises par le passé, au même
    horizon, sur des projections comparables — même ampleur de croissance projetée, même groupe de
    revenu — donne une fourchette : celle où seraient tombés 80 % des cas.{penchant}</p>
{bloc_table(["Pays", f"Croissance projetée {edition}-{f}", f"PIB {f} projeté", "Fourchette", "Écart à la projection"], corps)}{calibration}
    <p class="col note">PIB en volume, milliards de dollars constants de 2015. Fourchette : 10ᵉ à 90ᵉ
    centile des erreurs de niveau passées à {horizon} ans, parmi les projections de la même classe de
    croissance cumulée projetée (cinq classes de même effectif) et du même groupe de revenu. Ce n'est
    pas une prévision corrigée, mais la marge d'erreur qu'a connue le FMI ; en dollars courants, elle
    serait plus large. Détail pour tous les pays : <code>data/processed/gdp_projection_bands.csv</code>,
    onglet <code>Fourchettes_{f}</code> du classeur Excel, et test rétrospectif dans
    <code>gdp_projection_bands_calibration.csv</code>.</p>
  </section>
"""


def bloc_figure(uri: str, alt: str, legende: str) -> str:
    if not uri:
        return ""
    return (f'    <figure>\n      <div class="frame"><img src="{uri}" alt="{alt}"></div>\n'
            f'      <figcaption>{legende}</figcaption>\n    </figure>')


# ------------------------------------------------------------------ page

CSS = """
  :root {
    --ground: #FBFAFC; --surface: #F4F1F7; --ink: #1A1720; --muted: #6B6577;
    --accent: #7B52AB; --accent-soft: #EFE7F7; --rule: #E4E0EA;
    --figure: #FFFFFF;
    --up: #2F7D5B; --down: #A63D52; --down-soft: #FBEDF0;
    --shadow: 0 1px 2px rgba(26,23,32,.06), 0 8px 24px rgba(26,23,32,.05);
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
    --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #15131A; --surface: #1E1B26; --ink: #EBE8F0; --muted: #9B94A6;
      --accent: #B891E8; --accent-soft: #2A2136; --rule: #2E2A38;
      --figure: #FFFFFF;
      --up: #6FC79A; --down: #E1899C; --down-soft: #3A2028;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.3);
    }
  }
  :root[data-theme="dark"] {
    --ground: #15131A; --surface: #1E1B26; --ink: #EBE8F0; --muted: #9B94A6;
    --accent: #B891E8; --accent-soft: #2A2136; --rule: #2E2A38;
    --figure: #FFFFFF;
    --up: #6FC79A; --down: #E1899C; --down-soft: #3A2028;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.3);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--ground); color: var(--ink);
    font-family: var(--sans); font-size: 16px; line-height: 1.65;
    -webkit-font-smoothing: antialiased;
  }
  .page {
    max-width: 1120px; margin: 0 auto;
    padding: clamp(2rem, 5vw, 4.5rem) clamp(1rem, 4vw, 2.5rem) 5rem;
    display: flex; flex-direction: column; gap: 3.5rem;
  }
  .col { max-width: 68ch; }

  header { display: flex; flex-direction: column; gap: 1rem; }
  .eyebrow {
    font-family: var(--mono); font-size: .75rem; letter-spacing: .12em;
    text-transform: uppercase; color: var(--accent); margin: 0;
  }
  h1 {
    font-family: var(--serif); font-size: clamp(2rem, 5vw, 3rem); line-height: 1.1;
    font-weight: 600; margin: 0; text-wrap: balance; letter-spacing: -.01em;
  }
  .lede {
    font-family: var(--serif); font-size: 1.2rem; line-height: 1.55;
    color: var(--muted); margin: 0; max-width: 62ch;
  }

  .run {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px; background: var(--rule); border: 1px solid var(--rule);
    border-radius: 3px; overflow: hidden;
  }
  .stat { background: var(--surface); padding: 1rem 1.15rem; display: flex; flex-direction: column; gap: .2rem; }
  .stat dt {
    font-family: var(--mono); font-size: .7rem; letter-spacing: .08em;
    text-transform: uppercase; color: var(--muted); margin: 0;
  }
  .stat dd {
    margin: 0; font-family: var(--mono); font-size: 1.45rem;
    font-variant-numeric: tabular-nums; letter-spacing: -.02em;
  }

  section { display: flex; flex-direction: column; gap: 1.25rem; }
  h2 {
    font-family: var(--serif); font-size: 1.7rem; font-weight: 600; margin: 0;
    letter-spacing: -.01em; text-wrap: balance;
  }
  .sec-head { display: flex; flex-direction: column; gap: .3rem; border-top: 1px solid var(--rule); padding-top: 1.5rem; }
  p { margin: 0; }
  .note { color: var(--muted); font-size: .95rem; }
  code {
    font-family: var(--mono); font-size: .875em; background: var(--accent-soft);
    padding: .1em .35em; border-radius: 3px;
  }

  figure { margin: 0; display: flex; flex-direction: column; gap: .6rem; }
  .frame {
    border: 1px solid var(--rule); border-radius: 3px; background: var(--figure);
    padding: .75rem; box-shadow: var(--shadow); overflow-x: auto;
  }
  .frame img { display: block; width: 100%; height: auto; max-width: 100%; }
  figcaption { font-size: .85rem; color: var(--muted); max-width: 68ch; }

  .scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 3px; box-shadow: var(--shadow); }
  table { border-collapse: collapse; width: 100%; background: var(--surface); font-size: .9rem; }
  thead th {
    font-family: var(--mono); font-size: .68rem; letter-spacing: .07em;
    text-transform: uppercase; color: var(--muted); text-align: right; font-weight: 500;
    padding: .7rem .8rem; border-bottom: 1px solid var(--rule); white-space: nowrap;
  }
  thead th:nth-child(-n+2) { text-align: left; }
  tbody td { padding: .55rem .8rem; border-bottom: 1px solid var(--rule); white-space: nowrap; }
  tbody tr:last-child td { border-bottom: 0; }
  .num { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
  .mono { font-family: var(--mono); }
  .code { color: var(--accent); font-size: .82rem; letter-spacing: .04em; }
  .name { font-weight: 500; }
  .rank { color: var(--muted); font-size: .82rem; }
  .delta { font-size: .78rem; padding-left: .15rem; }
  .delta-up { color: var(--up); }
  .delta-down { color: var(--down); }
  .delta-flat { color: var(--muted); opacity: .6; }
  .wedge { font-family: var(--mono); font-size: .8rem; padding: .1rem .4rem; border-radius: 2px; font-variant-numeric: tabular-nums; }
  .wedge-pos { color: var(--muted); }
  .wedge-neg { color: var(--down); background: var(--down-soft); font-weight: 600; }
  .tag { font-family: var(--mono); font-size: .7rem; letter-spacing: .04em; padding: .12rem .45rem; border-radius: 2px; border: 1px solid var(--rule); }
  .tag-h { color: var(--muted); }
  .tag-f { color: var(--accent); background: var(--accent-soft); border-color: transparent; }

  footer {
    border-top: 1px solid var(--rule); padding-top: 1.5rem; color: var(--muted);
    font-size: .85rem; display: flex; flex-direction: column; gap: .4rem;
  }
  a { color: var(--accent); }
  a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""


def construire(data_dir: str, output_dir: str, pays_detail: str) -> str:
    unifie, synthese, annees = charger(data_dir)
    c = colonnes(annees)
    d, o, f = annees["debut"], annees["obs"], annees["fin"]

    manquantes = [nom for nom in c.values() if nom not in synthese.columns]
    if manquantes:
        raise KeyError(f"Colonnes absentes de la synthèse : {manquantes}. "
                       "La page et les données proviennent-elles du même run ?")

    # Repères d'exécution, tous lus dans les données
    agregats = int(unifie.loc[unifie.is_aggregate.astype(bool), "country_code"].nunique())
    couverture_ppa = int(synthese[c["ppa_obs"]].notna().sum())
    classes = int(synthese[c["rang"]].notna().sum())

    detail = unifie[unifie.country_code == pays_detail]
    nom_detail = detail["country_name"].iloc[0] if not detail.empty else pays_detail

    figures = {
        "exactitude": image(output_dir, "gdp_forecast_accuracy.png"),
        "niveaux": image(output_dir, "gdp_forecast_level_errors.png"),
        "sources": image(output_dir, f"gdp_source_discrepancy_{o}.png"),
        "traj": image(output_dir, f"gdp_top10_trajectories_{d}_{f}.png"),
        "cagr": image(output_dir, "gdp_cagr_comparison_top15.png"),
        "reel": image(output_dir, "gdp_nominal_vs_real_cagr_top15.png"),
        "panneaux": image(output_dir, "gdp_nominal_vs_real_trajectories.png"),
        "ppa": image(output_dir, f"gdp_ranking_nominal_vs_ppp_{o}.png"),
    }

    # Faits saillants recalculés, jamais recopiés — et tirés des lignes affichées,
    # pour que le commentaire et le tableau qu'il accompagne se répondent.
    volume_affiche = sous_ensemble_volume(synthese, c)
    ppa_affiche = sous_ensemble_ppa(synthese, c)

    ecart_min = volume_affiche.nsmallest(1, c["ecart"]).iloc[0]
    negatifs = int((synthese[c["ecart"]] < 0).sum())
    total_ecart = int(synthese[c["ecart"]].notna().sum())
    tete_ppa = synthese.nsmallest(1, c["rang_ppa"]).iloc[0]
    tete_nom = synthese.nsmallest(1, c["rang"]).iloc[0]
    grimpe = ppa_affiche.dropna(subset=[c["ecart_rang"]]).nlargest(1, c["ecart_rang"]).iloc[0]

    horodatage = datetime.now().astimezone().strftime("%d/%m/%Y")

    parts = [f"""<title>PIB mondial {d}–{f} — résultats</title>
<style>{CSS}</style>

<div class="page">

  <header>
    <p class="eyebrow">Pipeline PIB · régénéré le {horodatage}</p>
    <h1>PIB mondial, {d}–{f}</h1>
    <p class="lede">Historique Banque Mondiale jusqu'en {o}, prévisions FMI WEO jusqu'en {f},
    lus en prix courants, en volume et à parité de pouvoir d'achat.</p>
{note_rapport(data_dir, o)}  </header>

  <dl class="run">
    <div class="stat"><dt>Pays classés</dt><dd>{classes}</dd></div>
    <div class="stat"><dt>Lignes de série</dt><dd>{nb(len(unifie))}</dd></div>
    <div class="stat"><dt>Agrégats écartés</dt><dd>{agregats}</dd></div>
    <div class="stat"><dt>Couverture PPA</dt><dd>{couverture_ppa}</dd></div>
  </dl>

  <section>
    <div class="sec-head col"><h2>Les dix premières économies en {o}</h2></div>
    <p class="col note">Rangs calculés sur les seuls pays : les agrégats (<em>World</em>,
    <em>OECD members</em>, zone euro…) restent dans les séries mais sortent des classements.
    Tous les rangs portent sur les mêmes {classes} pays, renseignés en {o} et en {f} au taux de
    marché comme à parité, pour qu'un écart de rang traduise un mouvement et non l'entrée ou la
    sortie d'un pays du classement. PIB en milliards de dollars courants, CAGR en pourcentage annuel.</p>
{bloc_table(*table_top(synthese, c, annees))}
  </section>"""]

    if figures["sources"] and "Ecart_Sources_Pct" in unifie.columns:
        comparables = unifie[(unifie.year == o) & unifie.Ecart_Sources_Pct.notna()]
        divergents = int((comparables.Ecart_Sources_Pct.abs() > 5).sum())
        median = comparables.Ecart_Sources_Pct.abs().median()
        parts.append(f"""
  <section>
    <div class="sec-head col"><h2>Les deux sources, confrontées sur les mêmes années</h2></div>
    <p class="col">Le FMI publie ses propres estimations des années observées, jusqu'en {o}.
    Les confronter à celles de la Banque Mondiale montre que les deux institutions
    concordent presque partout — écart médian de {nb(median, 2)} % sur {len(comparables)} pays
    comparables — mais divergent nettement pour {divergents} d'entre eux.</p>
    <p class="col">Là où elles divergent, juxtaposer l'observation de l'une et la projection
    de l'autre fabriquerait une croissance qui n'existe pas. Les niveaux projetés sont donc
    raccordés au dernier niveau observé, ce qui conserve la dynamique du FMI et le niveau de
    la Banque Mondiale.</p>
{bloc_figure(figures["sources"], "Écart entre les deux sources et marche évitée à la jonction",
             f"À gauche l'écart de mesure en {o} ; à droite la croissance {o}→{o + 1} "
             "que produirait la juxtaposition, face à celle réellement projetée.")}
    <p class="col note">Cette confrontation mesure un écart entre institutions, pas la qualité
    des prévisions : l'API du FMI ne sert que son millésime courant, dont les valeurs passées
    sont des estimations d'aujourd'hui et non les projections d'alors.</p>
  </section>""")

    if figures["traj"]:
        parts.append(f"""
  <section>
    <div class="sec-head col"><h2>Trajectoires du PIB nominal</h2></div>
    <p class="col">Trait plein sur l'historique, pointillé sur la prévision, raccordés en {o}.</p>
{bloc_figure(figures["traj"], f"Trajectoires du PIB des dix premières économies de {d} à {f}",
             f"Top 10 mondial, {d}–{f}. La ligne rouge marque la frontière historique / prévision.")}
  </section>""")

    if figures["cagr"]:
        parts.append(f"""
  <section>
    <div class="sec-head col"><h2>Croissance passée contre croissance projetée</h2></div>
{bloc_figure(figures["cagr"], "Comparaison des CAGR historique et prévisionnel",
             f"CAGR historique ({d}–{o}) et prévisionnel ({o}–{f}), quinze premières économies.")}
  </section>""")

    parts.append(f"""
  <section>
    <div class="sec-head col"><h2>Nominal ou volume : ce que masque le taux de change</h2></div>
    <p class="col">Le PIB en dollars courants additionne la croissance réelle, l'inflation et
    le mouvement du taux de change. La série en volume — dollars constants de 2015 — neutralise
    les deux dernières. L'écart entre les deux mesures est la part qui ne doit rien à la production.</p>
{bloc_figure(figures["reel"], "Écart entre croissance nominale et croissance en volume",
             f"Les deux lectures d'un même pays sur {d}–{o}.")}
{bloc_table(*table_volume(synthese, c))}
    <p class="col">{nom_pays(ecart_min)} est le cas limite : {nb(ecart_min[c["cagr_h"]], 2)} % de
    croissance nominale annuelle contre {nb(ecart_min[c["cagr_rh"]], 2)} % en volume, soit un écart
    de {signe(ecart_min[c["ecart"]], 1)} point. {negatifs} pays sur {total_ecart} ont un écart négatif.</p>
{bloc_figure(figures["panneaux"], "Trajectoires en prix courants et en volume",
             "Les mêmes économies sur les deux bases de prix.")}
    <p class="col note">Les niveaux en volume de la période de prévision ne sont pas publiés par
    le FMI, qui ne diffuse qu'un taux de croissance réelle. Ils sont chaînés à partir du dernier
    point observé ; une année de croissance manquante interrompt le chaînage plutôt que d'extrapoler.</p>
  </section>

  <section>
    <div class="sec-head col"><h2>Comparer des niveaux : la parité de pouvoir d'achat</h2></div>
    <p class="col">Corriger le change sur la croissance ne rend pas les <em>niveaux</em> comparables :
    la série en volume reste convertie au taux de l'année de base. La parité de pouvoir d'achat
    mesure ce qu'une unité de production permet d'acheter sur place, et réordonne le classement.</p>
{bloc_figure(figures["ppa"], "Classement mondial au taux de marché et à parité de pouvoir d'achat",
             f"Déplacement des rangs entre les deux bases de conversion, {o}.")}
{bloc_table(*table_ppa(synthese, c))}
    <p class="col">{nom_pays(tete_ppa)} occupe le premier rang à parité, contre
    {nom_pays(tete_nom)} au taux de marché. Le mouvement le plus marqué revient à
    {nom_pays(grimpe)}, qui gagne {abs(int(grimpe[c["ecart_rang"]]))} rangs.</p>
    <p class="col note">Aucune des deux bases n'est « la bonne » : le taux de marché mesure le poids
    financier d'une économie dans les échanges internationaux, la parité le volume de production
    disponible sur place. Le rang PPA projeté en {f} suppose en outre les facteurs de conversion
    de 2021 inchangés, ce qui en élargit l'incertitude.</p>
  </section>

{section_previsions(data_dir, figures["exactitude"])}{section_niveaux(data_dir, figures["niveaux"])}{section_fourchettes(data_dir, synthese, c, f)}
  <section>
    <div class="sec-head col"><h2>Détail par pays — {nom_detail}</h2></div>
    <p class="col note">Dix dernières années de la série, prévisions comprises.</p>
{bloc_table(*table_pays(unifie, pays_detail))}
  </section>

  <footer>
    <p>Sources : Banque Mondiale (WDI) pour {d}–{o}, FMI (World Economic Outlook) pour {o + 1}–{f}.</p>
    <p>Page générée par <code>build_results_page.py</code> depuis <code>data/processed/</code>
    et <code>outputs/</code> — aucune valeur n'y est saisie à la main.</p>
  </footer>

</div>
""")

    html = "".join(parts)
    chemin = os.path.join(output_dir, "resultats_gdp.html")
    with open(chemin, "w", encoding="utf-8") as fichier:
        fichier.write(html)

    logging.info(f"Page de résultats générée : {chemin} ({len(html) // 1024} Ko)")
    return chemin


def nom_pays(ligne) -> str:
    return str(ligne["country_name"])


def main():
    parser = argparse.ArgumentParser(description="Page HTML de résultats du pipeline PIB.")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--output-dir", type=str, default="outputs")
    parser.add_argument("--pays", type=str, default="FRA",
                        help="Code ISO3 du pays détaillé en fin de page (par défaut: FRA)")
    args = parser.parse_args()
    construire(args.data_dir, args.output_dir, args.pays)


if __name__ == "__main__":
    main()
