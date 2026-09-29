#!/usr/bin/env python3
"""
test_gdp_pipeline.py
--------------------
Tests des invariants du pipeline PIB.

Chaque test correspond à une propriété qu'un défaut réel a violée sans lever
d'erreur : c'est le mode de défaillance de ce projet — des colonnes vides ou des
classements faux, jamais une exception. Les tests unitaires travaillent sur des
données synthétiques (aucun appel réseau) ; les tests marqués `donnees` vérifient
les fichiers réellement produits et se sautent d'eux-mêmes s'ils sont absents.

    pytest test_gdp_pipeline.py -v
    pytest test_gdp_pipeline.py -m "not donnees"    # sans les fichiers produits
"""

import os
import json

import numpy as np
import pandas as pd
import pytest

import http_utils
import gdp_pipeline
import fetch_historical_gdp
import fetch_forecast_gdp
from gdp_pipeline import (
    calculate_cagr,
    reference_years,
    build_unified_dataset,
    splice_forecast_levels,
    extend_real_series,
    compute_country_summary,
    run_pipeline,
    unified_csv_path,
    latest_observed_year,
    choose_reference_year,
)
from visualize_gdp import detect_years

PROCESSED = os.path.join("data", "processed")


# ---------------------------------------------------------------- fixtures

def _historique() -> pd.DataFrame:
    """
    Extraction Banque Mondiale simulée : deux pays et un agrégat, 2000-2024.

    L'agrégat porte volontairement un code ISO3 (`WLD`) et le plus gros PIB :
    c'est la configuration qui plaçait *World* en tête du classement mondial.
    Les libellés sont ceux de la Banque Mondiale, différents de ceux du FMI.
    """
    lignes = []
    for annee in range(2000, 2025):
        n = annee - 2000
        lignes += [
            # PIB nominal ×2 sur la période, volume ×1,5 : l'écart est l'effet prix/change
            dict(country_code="AAA", country_name="Pays A", year=annee, is_aggregate=False,
                 GDP_Nominal_USD=1e12 * (1.03 ** n), GDP_Growth_Annual_Pct=2.0,
                 GDP_Per_Capita_USD=30000.0, GDP_PPP_USD=1.2e12 * (1.03 ** n),
                 GDP_Real_USD=1e12 * (1.02 ** n), GDP_Real_PPP_Intl=1.5e12 * (1.02 ** n)),
            # Pays B : plus petit en nominal, plus grand en PPA (monnaie sous-évaluée)
            dict(country_code="BBB", country_name="Pays B", year=annee, is_aggregate=False,
                 GDP_Nominal_USD=5e11 * (1.05 ** n), GDP_Growth_Annual_Pct=4.0,
                 GDP_Per_Capita_USD=8000.0, GDP_PPP_USD=1.4e12 * (1.05 ** n),
                 GDP_Real_USD=5e11 * (1.04 ** n), GDP_Real_PPP_Intl=2.0e12 * (1.04 ** n)),
            dict(country_code="WLD", country_name="World", year=annee, is_aggregate=True,
                 GDP_Nominal_USD=9e13 * (1.03 ** n), GDP_Growth_Annual_Pct=3.0,
                 GDP_Per_Capita_USD=12000.0, GDP_PPP_USD=1e14 * (1.03 ** n),
                 GDP_Real_USD=9e13 * (1.02 ** n), GDP_Real_PPP_Intl=1e14 * (1.02 ** n)),
        ]
    return pd.DataFrame(lignes)


def _prevision() -> pd.DataFrame:
    """
    Extraction FMI simulée : 2025-2030, sans niveau en volume (le FMI n'en publie pas).

    Les libellés valent le code brut, comme dans les payloads réels d'indicateurs :
    c'est ce qui scindait chaque pays en deux séries lors de la fusion.
    """
    lignes = []
    for annee in range(2025, 2031):
        n = annee - 2024
        lignes += [
            dict(country_code="AAA", country_name="AAA", year=annee, is_forecast=True,
                 is_aggregate=False, GDP_Nominal_Billions_USD=1000 * (1.03 ** 24) * (1.03 ** n),
                 GDP_Growth_Pct=2.0, GDP_PPP_Billions_USD=1200.0, GDP_Per_Capita_USD=32000.0),
            dict(country_code="BBB", country_name="BBB", year=annee, is_forecast=True,
                 is_aggregate=False, GDP_Nominal_Billions_USD=500 * (1.05 ** 24) * (1.05 ** n),
                 GDP_Growth_Pct=4.0, GDP_PPP_Billions_USD=1400.0, GDP_Per_Capita_USD=9000.0),
            dict(country_code="WLD", country_name="WLD", year=annee, is_forecast=True,
                 is_aggregate=True, GDP_Nominal_Billions_USD=90000 * (1.03 ** n),
                 GDP_Growth_Pct=3.0, GDP_PPP_Billions_USD=100000.0, GDP_Per_Capita_USD=13000.0),
        ]
    return pd.DataFrame(lignes)


def _fmi_avec_historique(desaccord: float = 1.60, desaccord_ppa: float = 0.50,
                         desaccord_hab: float = 2.0) -> pd.DataFrame:
    """
    Extraction FMI incluant ses propres estimations des années observées.

    `desaccord` est le rapport entre le niveau FMI et le niveau Banque Mondiale pour
    Pays B, appliqué à **toute** sa série : le FMI mesure ce pays plus haut sans pour
    autant lui prêter une autre dynamique. C'est la configuration qui produit une marche
    à la jonction lorsque les deux séries sont juxtaposées. Pays A est mesuré à l'identique.

    La PPA courante (`desaccord_ppa`) et le PIB par habitant (`desaccord_hab`) divergent
    de rapports différents, comme sur données réelles : un facteur unique, calé sur le
    nominal, ne peut pas les raccorder. Le PIB par habitant de Pays B, stable sur
    l'historique, progresse de 4 %/an en projection.
    """
    lignes = []
    for annee in range(2000, 2031):
        n = annee - 2000
        prevision = annee >= 2025
        lignes += [
            dict(country_code="AAA", country_name="AAA", year=annee, is_forecast=prevision,
                 is_aggregate=False, GDP_Nominal_Billions_USD=1000 * (1.03 ** n),
                 GDP_Growth_Pct=2.0, GDP_PPP_Billions_USD=1200 * (1.03 ** n),
                 GDP_Per_Capita_USD=30000.0),
            dict(country_code="BBB", country_name="BBB", year=annee, is_forecast=prevision,
                 is_aggregate=False, GDP_Nominal_Billions_USD=500 * desaccord * (1.05 ** n),
                 GDP_Growth_Pct=4.0, GDP_PPP_Billions_USD=1400 * desaccord_ppa * (1.05 ** n),
                 GDP_Per_Capita_USD=8000 * desaccord_hab * (1.04 ** max(annee - 2024, 0))),
            dict(country_code="WLD", country_name="WLD", year=annee, is_forecast=prevision,
                 is_aggregate=True, GDP_Nominal_Billions_USD=90000 * (1.03 ** n),
                 GDP_Growth_Pct=3.0, GDP_PPP_Billions_USD=100000.0, GDP_Per_Capita_USD=12000.0),
        ]
    return pd.DataFrame(lignes)


@pytest.fixture
def unifie() -> pd.DataFrame:
    """Série unifiée 2000-2030, volumes de prévision chaînés."""
    return extend_real_series(build_unified_dataset(_historique(), _prevision()), base_year=2024)


@pytest.fixture
def unifie_recouvrement() -> pd.DataFrame:
    """Série unifiée avec estimations FMI en regard des années observées, puis raccordée."""
    unifie = build_unified_dataset(_historique(), _fmi_avec_historique())
    return extend_real_series(splice_forecast_levels(unifie, base_year=2024), base_year=2024)


@pytest.fixture
def synthese(unifie) -> pd.DataFrame:
    return compute_country_summary(unifie, reference_years(2000, 2024, 2030))


# ------------------------------------------------------------------- CAGR

class TestCagr:
    def test_croissance_composee_exacte(self):
        # 100 → 200 en 10 ans : 2^(1/10) - 1 ≈ 7,177 %
        assert calculate_cagr(100.0, 200.0, 10) == pytest.approx(7.17734625, abs=1e-6)

    def test_serie_plate_donne_zero(self):
        assert calculate_cagr(500.0, 500.0, 24) == pytest.approx(0.0)

    @pytest.mark.parametrize("debut, fin, annees", [
        (np.nan, 200.0, 10),    # valeur de départ manquante
        (100.0, np.nan, 10),    # valeur d'arrivée manquante
        (0.0, 200.0, 10),       # départ nul : taux non défini
        (-50.0, 200.0, 10),     # PIB négatif : aberrant
        (100.0, 200.0, 0),      # durée nulle
    ])
    def test_cas_degeneres_donnent_nan(self, debut, fin, annees):
        """Un CAGR non calculable doit valoir NaN, jamais une valeur inventée."""
        assert pd.isna(calculate_cagr(debut, fin, annees))


# -------------------------------------------------- années de référence

class TestAnneesReference:
    def test_valeurs_par_defaut(self):
        assert reference_years(2000, 2024, 2030) == {
            "start": 2000, "mid": 2010, "end": 2024, "fcst": 2030}

    def test_annee_intermediaire_suit_le_debut(self):
        assert reference_years(1995, 2023, 2028)["mid"] == 2005

    def test_historique_court_replie_sur_le_milieu(self):
        """Avec moins de dix ans d'historique, début + 10 dépasserait la période."""
        annees = reference_years(2018, 2024, 2028)
        assert annees["start"] < annees["mid"] < annees["end"]


# ------------------------------------------------------------- unification

class TestUnification:
    def test_un_seul_libelle_par_code(self, unifie):
        """
        Régression : les payloads FMI ne portent pas les libellés, `parse_imf_data`
        retombait sur le code brut. Le pivot sur (code, nom) scindait alors chaque
        pays en deux séries — l'une sans prévision, l'autre sans historique.
        """
        assert unifie.groupby("country_code")["country_name"].nunique().max() == 1

    def test_libelle_banque_mondiale_retenu(self, unifie):
        assert set(unifie.loc[unifie.country_code == "AAA", "country_name"]) == {"Pays A"}

    def test_serie_continue_sans_doublon(self, unifie):
        for code in ("AAA", "BBB"):
            annees = sorted(unifie.loc[unifie.country_code == code, "year"])
            assert annees == list(range(2000, 2031))
        assert not unifie.duplicated(subset=["country_code", "year"]).any()

    def test_drapeau_agregat_constant_sur_la_serie(self, unifie):
        assert unifie.groupby("country_code")["is_aggregate"].nunique().max() == 1

    def test_unites_harmonisees_en_milliards(self, unifie):
        """La Banque Mondiale publie en USD bruts, le FMI en milliards."""
        valeur_2000 = unifie.loc[(unifie.country_code == "AAA") & (unifie.year == 2000),
                                 "GDP_Nominal_Billions_USD"].iloc[0]
        assert valeur_2000 == pytest.approx(1000.0)


# ------------------------------------------------- chaînage des volumes

class TestChainageVolume:
    def test_croissance_implicite_egale_au_taux_fmi(self, unifie):
        """
        Le FMI ne publie qu'un taux de croissance réelle : les niveaux de prévision
        sont reconstitués par chaînage. Recalculer la croissance de ces niveaux doit
        redonner le taux de départ, sinon le chaînage dérive.
        """
        serie = unifie[unifie.country_code == "AAA"].sort_values("year")
        implicite = serie["GDP_Real_Billions_USD"].pct_change() * 100
        attendu = serie["GDP_Growth_Pct"]
        prevision = serie["is_forecast"].astype(bool)
        assert implicite[prevision].values == pytest.approx(attendu[prevision].values, abs=1e-9)

    def test_ppa_chainee_au_meme_rythme(self, unifie):
        """Les deux mesures en volume ne diffèrent que par une constante de conversion."""
        serie = unifie[unifie.country_code == "BBB"].sort_values("year")
        prevision = serie["is_forecast"].astype(bool)
        ratio = (serie.loc[prevision, "GDP_Real_PPP_Billions_Intl"].values
                 / serie.loc[prevision, "GDP_Real_Billions_USD"].values)
        assert ratio == pytest.approx(np.full(len(ratio), ratio[0]))

    def test_base_du_chainage_reste_la_valeur_observee(self, unifie):
        """L'année frontière garde la valeur de la Banque Mondiale, non une valeur chaînée."""
        base = unifie.loc[(unifie.country_code == "AAA") & (unifie.year == 2024),
                          "GDP_Real_Billions_USD"].iloc[0]
        assert base == pytest.approx(1000.0 * (1.02 ** 24))

    def test_annee_manquante_interrompt_le_chainage(self):
        """Une croissance absente ne doit pas être franchie : mieux vaut vide qu'inventé."""
        prevision = _prevision()
        trou = (prevision.country_code == "AAA") & (prevision.year == 2027)
        prevision.loc[trou, "GDP_Growth_Pct"] = np.nan

        unifie = extend_real_series(
            build_unified_dataset(_historique(), prevision), base_year=2024)
        serie = unifie[unifie.country_code == "AAA"].set_index("year")["GDP_Real_Billions_USD"]

        assert serie.loc[2026] == pytest.approx(1000.0 * (1.02 ** 24) * 1.02 ** 2)
        assert serie.loc[[2027, 2028, 2029, 2030]].isna().all()

    def test_annee_absente_interrompt_le_chainage(self):
        """
        Régression : une année sans ligne (prévision démarrant deux ans après la fin de
        l'historique) était franchie, le taux de 2026 s'appliquant au niveau de 2024.
        """
        prevision = _prevision()
        prevision = prevision[prevision.year != 2025]

        unifie = extend_real_series(
            build_unified_dataset(_historique(), prevision), base_year=2024)
        serie = unifie[unifie.country_code == "AAA"].set_index("year")["GDP_Real_Billions_USD"]

        assert 2025 not in serie.index
        assert serie.loc[[2026, 2027, 2028, 2029, 2030]].isna().all()


# ------------------------------------------------------- synthèse et rangs

class TestSynthese:
    def test_agregats_absents_du_classement(self, synthese):
        """
        Régression : `WB_AGGREGATES` n'était pas appliqué et le filtre `len(code) == 3`
        ne rejetait ni WLD ni OED. *World* et *OECD members* occupaient les deux
        premiers rangs mondiaux, les États-Unis n'arrivaient que douzièmes.
        """
        assert "WLD" not in set(synthese.country_code)
        assert set(synthese.country_code) == {"AAA", "BBB"}

    def test_une_ligne_par_pays(self, synthese):
        assert len(synthese) == synthese.country_code.nunique()

    def test_colonnes_portent_les_annees_du_run(self, synthese):
        for colonne in ("GDP_2000_Billion_USD", "GDP_2024_Billion_USD",
                        "GDP_2030_Forecast_Billion_USD", "CAGR_Historique_2000_2024_Pct",
                        "CAGR_Reel_Historique_2000_2024_Pct", "Rank_PPA_2024"):
            assert colonne in synthese.columns

    def test_aucune_colonne_de_reference_vide(self, synthese):
        """
        Régression : les pays scindés en deux séries laissaient le PIB 2030, le CAGR
        prévisionnel et le rang projeté vides pour toutes les grandes économies.
        """
        for colonne in ("GDP_2024_Billion_USD", "GDP_2030_Forecast_Billion_USD",
                        "CAGR_Prevision_2024_2030_Pct", "Rank_2030_Forecast"):
            assert synthese[colonne].notna().all(), f"{colonne} est vide"

    def test_cagr_nominal_superieur_au_reel_si_inflation(self, synthese):
        """Nominal 3 %/an contre volume 2 %/an : l'écart doit valoir ~1 point."""
        ligne = synthese[synthese.country_code == "AAA"].iloc[0]
        assert ligne["CAGR_Historique_2000_2024_Pct"] == pytest.approx(3.0, abs=1e-6)
        assert ligne["CAGR_Reel_Historique_2000_2024_Pct"] == pytest.approx(2.0, abs=1e-6)
        assert ligne["Ecart_Nominal_Reel_2000_2024_Pts"] == pytest.approx(1.0, abs=1e-6)

    def test_rangs_coherents_avec_les_niveaux(self, synthese):
        ordonnee = synthese.sort_values("GDP_2024_Billion_USD", ascending=False)
        assert list(ordonnee["Rank_2024"]) == sorted(ordonnee["Rank_2024"])

    def test_rangs_ppa_coherents_avec_les_niveaux_ppa(self, synthese):
        ordonnee = synthese.sort_values("GDP_PPA_2024_Billion_Intl_2021", ascending=False)
        assert list(ordonnee["Rank_PPA_2024"]) == sorted(ordonnee["Rank_PPA_2024"])

    def test_classement_ppa_distinct_du_nominal(self, synthese):
        """
        Pays B est plus petit au taux de marché mais plus grand à parité :
        les deux bases doivent donner des premiers différents.
        """
        premier_nominal = synthese.loc[synthese["Rank_2024"] == 1, "country_code"].iloc[0]
        premier_ppa = synthese.loc[synthese["Rank_PPA_2024"] == 1, "country_code"].iloc[0]
        assert premier_nominal == "AAA"
        assert premier_ppa == "BBB"
        assert synthese.loc[synthese.country_code == "BBB",
                            "Ecart_Rang_Nominal_PPA_2024"].iloc[0] > 0


class TestPanelClassement:
    """
    Régression : chaque colonne de rang était calculée sur les pays qu'elle couvrait.
    Taïwan, absent de la Banque Mondiale, entrait 22ᵉ au classement 2030 ; le Pakistan,
    sans projection FMI, en sortait. Les écarts de rang de 140 pays sur 183 mêlaient ainsi
    leur mouvement propre à ces entrées et sorties.
    """

    @pytest.fixture
    def synthese_mouvante(self):
        # Entre Pays A et Pays B : présent en 2024 seulement (type Pakistan)...
        historique = _historique()
        seulement_2024 = historique[historique.country_code == "BBB"].copy()
        seulement_2024["country_code"], seulement_2024["country_name"] = "HHH", "Historique seul"
        seulement_2024["GDP_Nominal_USD"] = 1.8e12
        # ... et présent en 2030 seulement (type Taïwan)
        prevision = _prevision()
        seulement_2030 = prevision[prevision.country_code == "BBB"].copy()
        seulement_2030["country_code"], seulement_2030["country_name"] = "FFF", "Prévision seule"
        seulement_2030["GDP_Nominal_Billions_USD"] = 2300.0

        unifie = extend_real_series(build_unified_dataset(
            pd.concat([historique, seulement_2024]), pd.concat([prevision, seulement_2030])),
            base_year=2024)
        return compute_country_summary(unifie, reference_years(2000, 2024, 2030)).set_index("country_code")

    def test_entrees_et_sorties_sans_effet_sur_les_rangs(self, synthese_mouvante):
        """Pays B est deuxième aux deux dates : il ne doit afficher aucun mouvement."""
        b = synthese_mouvante.loc["BBB"]
        assert (b["Rank_2024"], b["Rank_2030_Forecast"], b["Rank_Change"]) == (2, 2, 0)

    def test_pays_hors_panel_gardent_leurs_niveaux_sans_rang(self, synthese_mouvante):
        for code, niveau in (("HHH", "GDP_2024_Billion_USD"), ("FFF", "GDP_2030_Forecast_Billion_USD")):
            ligne = synthese_mouvante.loc[code]
            assert pd.notna(ligne[niveau])
            assert ligne[["Rank_2024", "Rank_2030_Forecast", "Rank_PPA_2024"]].isna().all()

    def test_ecarts_de_rang_egaux_a_la_difference_affichee(self, synthese_mouvante):
        classes = synthese_mouvante.dropna(subset=["Rank_2024"])
        assert (classes["Rank_Change"]
                == classes["Rank_2024"] - classes["Rank_2030_Forecast"]).all()
        assert (classes["Ecart_Rang_Nominal_PPA_2024"]
                == classes["Rank_2024"] - classes["Rank_PPA_2024"]).all()


class TestBornesPersonnalisees:
    """
    Régression : les années de référence étaient figées à 2000/2010/2024/2030.
    Un run sur d'autres bornes produisait une synthèse entièrement vide, sans erreur.
    """

    @pytest.fixture
    def synthese_1995(self):
        historique = _historique()
        historique["year"] = historique["year"] - 5          # 1995-2019
        prevision = _prevision()
        prevision["year"] = prevision["year"] - 5            # 2020-2025
        unifie = extend_real_series(
            build_unified_dataset(historique, prevision), base_year=2019)
        return compute_country_summary(unifie, reference_years(1995, 2019, 2025))

    def test_colonnes_suivent_les_bornes(self, synthese_1995):
        assert "GDP_1995_Billion_USD" in synthese_1995.columns
        assert "CAGR_Historique_1995_2019_Pct" in synthese_1995.columns
        assert "Rank_PPA_2019" in synthese_1995.columns
        assert "GDP_2024_Billion_USD" not in synthese_1995.columns

    def test_metriques_renseignees(self, synthese_1995):
        for colonne in ("GDP_2019_Billion_USD", "GDP_2025_Forecast_Billion_USD",
                        "CAGR_Historique_1995_2019_Pct", "Rank_2019"):
            assert synthese_1995[colonne].notna().all(), f"{colonne} est vide"

    def test_duree_du_cagr_suit_la_periode(self, synthese_1995):
        """24 ans d'historique quelles que soient les bornes : le taux reste 3 %."""
        ligne = synthese_1995[synthese_1995.country_code == "AAA"].iloc[0]
        assert ligne["CAGR_Historique_1995_2019_Pct"] == pytest.approx(3.0, abs=1e-6)


class TestBornesDuPipeline:
    """Des bornes incohérentes sont refusées avant toute requête réseau."""

    @pytest.mark.parametrize("fcst_start", [2024, 2026])
    def test_prevision_contigue_a_l_historique(self, fcst_start, tmp_path):
        with pytest.raises(ValueError, match="2025"):
            run_pipeline(end_year=2024, fcst_start=fcst_start,
                         data_dir=str(tmp_path / "data"), output_dir=str(tmp_path / "out"))
        assert not (tmp_path / "data").exists()

    def test_bornes_ordonnees(self, tmp_path):
        with pytest.raises(ValueError, match="incohérentes"):
            run_pipeline(start_year=2024, end_year=2024, fcst_end=2030,
                         data_dir=str(tmp_path / "data"), output_dir=str(tmp_path / "out"))


def _avec_pays_c(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute Pays C, grande économie calquée sur Pays A."""
    c = df[df.country_code == "AAA"].copy()
    c["country_code"], c["country_name"] = "CCC", "Pays C"
    return pd.concat([df, c], ignore_index=True)


def _historique_jusqu_en_2025(pays_c_publie: bool) -> pd.DataFrame:
    """
    Extraction Banque Mondiale 2000-2025. L'année 2025 est publiée pour Pays A et B mais,
    si `pays_c_publie` est faux, pas encore pour Pays C — le cas des Émirats arabes unis
    (27ᵉ économie) en septembre 2026.
    """
    historique = _avec_pays_c(_historique())
    derniere = historique[historique.year == 2024].copy()
    derniere["year"] = 2025
    if not pays_c_publie:
        derniere = derniere[derniere.country_code != "CCC"]
    return pd.concat([historique, derniere], ignore_index=True)


class TestDeuxRapports:
    """
    La dernière année publiée arrive pays par pays. Le rapport de référence retient la plus
    récente dont le classement est quasi complet ; la dernière année publiée, si elle est
    plus récente, fait l'objet d'un second rapport, sans jamais remplacer le premier.
    """

    def test_derniere_annee_observee(self):
        historique = _historique_jusqu_en_2025(pays_c_publie=False)
        assert latest_observed_year(historique) == 2025          # 2 pays sur 3
        precoce = historique[(historique.year < 2025) | (historique.country_code == "AAA")]
        assert latest_observed_year(precoce) == 2024             # 1 pays sur 3 : valeur précoce

    def test_seuil_en_pib_et_non_en_nombre_de_pays(self):
        """
        Saint-Marin, absent de 2024, ne doit pas renvoyer la référence en 2023 ; une grande
        économie absente de 2025 doit, elle, la maintenir en 2024.
        """
        poids = pd.Series({"USA": 30000.0, "ARE": 550.0, "FRA": 3000.0, "SMR": 2.0})
        classes = {2023: {"USA", "ARE", "FRA", "SMR"},
                   2024: {"USA", "ARE", "FRA"},
                   2025: {"USA", "FRA"}}
        annee, pertes = choose_reference_year(classes, poids, seuil_pct=0.1)
        assert annee == 2024
        assert pertes[2024] < 0.1 < pertes[2025]

    def test_derniere_annee_retenue_si_complete(self):
        poids = pd.Series({"USA": 30000.0, "FRA": 3000.0})
        annee, _ = choose_reference_year({2024: {"USA", "FRA"}, 2025: {"USA", "FRA"}}, poids)
        assert annee == 2025

    @staticmethod
    def _run(tmp_path, monkeypatch, pays_c_publie):
        monkeypatch.setattr(gdp_pipeline, "fetch_all_historical_gdp",
                            lambda start_year, end_year: _historique_jusqu_en_2025(pays_c_publie))
        monkeypatch.setattr(gdp_pipeline, "fetch_all_forecasts",
                            lambda **kwargs: (_avec_pays_c(_fmi_avec_historique()), {}))
        data, sorties = tmp_path / "data", tmp_path / "outputs"
        run_pipeline(data_dir=str(data), output_dir=str(sorties))
        return data, sorties

    @staticmethod
    def _meta(dossier):
        return json.loads((dossier / "extraction_metadata.json").read_text(encoding="utf-8"))

    def test_reference_en_place_et_plus_recent_a_part(self, tmp_path, monkeypatch):
        data, sorties = self._run(tmp_path, monkeypatch, pays_c_publie=False)

        reference, recent = self._meta(data), self._meta(data / "plus_recent")
        assert reference["bornes"]["historique"] == [2000, 2024]
        assert reference["rapport"]["type"] == "reference"
        assert reference["rapport"]["autre_rapport"] == "plus_recent"
        assert recent["bornes"]["historique"] == [2000, 2025]
        assert recent["rapport"]["pays_sans_rang_par_rapport_a_la_reference"] == ["Pays C"]

        synthese = pd.read_csv(data / "processed" / "gdp_country_summary.csv").set_index("country_code")
        synthese_recente = pd.read_csv(unified_csv_path(str(data / "plus_recent")).replace(
            "gdp_unified_2000_2030.csv", "gdp_country_summary.csv")).set_index("country_code")
        assert synthese.loc["CCC", "Rank_2024"] == synthese.loc["AAA", "Rank_2024"]
        assert pd.isna(synthese_recente.loc["CCC", "Rank_2025"])
        assert synthese_recente["Rank_2025"].notna().sum() == 2

        assert (sorties / "gdp_master_dataset.xlsx").exists()
        assert (sorties / "plus_recent" / "gdp_master_dataset.xlsx").exists()

    def test_un_seul_rapport_quand_la_derniere_annee_est_complete(self, tmp_path, monkeypatch):
        """Un rapport plus récent périmé, laissé par un run précédent, doit disparaître."""
        (tmp_path / "data" / "plus_recent").mkdir(parents=True)
        (tmp_path / "outputs" / "plus_recent").mkdir(parents=True)
        data, sorties = self._run(tmp_path, monkeypatch, pays_c_publie=True)

        assert self._meta(data)["bornes"]["historique"] == [2000, 2025]
        assert self._meta(data)["rapport"]["autre_rapport"] is None
        assert not (data / "plus_recent").exists()
        assert not (sorties / "plus_recent").exists()

    def test_note_de_la_page_de_resultats(self, tmp_path, monkeypatch):
        """Chaque page dit quel rapport elle présente et renvoie vers l'autre."""
        from build_results_page import note_rapport
        data, _ = self._run(tmp_path, monkeypatch, pays_c_publie=False)
        note_reference = note_rapport(str(data), 2024)
        note_recente = note_rapport(str(data / "plus_recent"), 2025)
        assert "Rapport de référence" in note_reference and "plus_recent/resultats_gdp.html" in note_reference
        assert "Pays C sort du classement" in note_recente and "../resultats_gdp.html" in note_recente


class TestRecouvrementSources:
    """
    Le WEO couvre aussi les années observées. Les conserver permet de confronter les
    deux sources ; encore faut-il que la Banque Mondiale reste la référence sur ces
    années, et que la comparaison ne contamine pas la série livrée.
    """

    def test_banque_mondiale_fait_autorite_sur_l_observe(self, unifie_recouvrement):
        """Le FMI mesure Pays B 60 % plus haut : sa valeur ne doit pas écraser l'historique."""
        observe = unifie_recouvrement[(unifie_recouvrement.country_code == "BBB")
                                      & (unifie_recouvrement.year == 2010)].iloc[0]
        assert observe["GDP_Nominal_Billions_USD"] == pytest.approx(500 * (1.05 ** 10))
        assert observe["GDP_Nominal_FMI_Billions_USD"] == pytest.approx(500 * 1.60 * (1.05 ** 10))

    def test_ecart_entre_sources_mesure(self, unifie_recouvrement):
        ecart = unifie_recouvrement.loc[(unifie_recouvrement.country_code == "BBB")
                                        & (unifie_recouvrement.year == 2015), "Ecart_Sources_Pct"].iloc[0]
        assert ecart == pytest.approx(60.0, abs=1e-6)

    def test_ecart_nul_quand_les_sources_concordent(self, unifie_recouvrement):
        ecart = unifie_recouvrement.loc[(unifie_recouvrement.country_code == "AAA")
                                        & (unifie_recouvrement.year == 2015), "Ecart_Sources_Pct"].iloc[0]
        assert ecart == pytest.approx(0.0, abs=1e-9)

    def test_ecart_non_renseigne_sur_la_prevision(self, unifie_recouvrement):
        """Comparer deux sources n'a de sens que là où les deux observent."""
        prevision = unifie_recouvrement[unifie_recouvrement.is_forecast.astype(bool)]
        assert prevision["Ecart_Sources_Pct"].isna().all()

    def test_serie_toujours_continue_et_sans_doublon(self, unifie_recouvrement):
        for code in ("AAA", "BBB"):
            annees = sorted(unifie_recouvrement.loc[
                unifie_recouvrement.country_code == code, "year"])
            assert annees == list(range(2000, 2031))
        assert not unifie_recouvrement.duplicated(subset=["country_code", "year"]).any()


class TestRaccord:
    """
    Régression : juxtaposer les deux sources créait une marche à la jonction qui ne
    devait rien à l'économie. Sur données réelles, seize pays sautaient de plus de cinq
    points de croissance apparente, le Soudan changeant même de signe.
    """

    def test_niveau_raccorde_sur_la_derniere_observation(self, unifie_recouvrement):
        serie = unifie_recouvrement[unifie_recouvrement.country_code == "BBB"].set_index("year")
        observe = serie.loc[2024, "GDP_Nominal_Billions_USD"]
        premier_projete = serie.loc[2025, "GDP_Nominal_Billions_USD"]
        # Le FMI projette +5 % : le niveau raccordé doit suivre ce rythme, pas bondir de 60 %
        assert premier_projete == pytest.approx(observe * 1.05, rel=1e-9)

    def test_dynamique_du_fmi_preservee(self, unifie_recouvrement):
        """Le raccord change le niveau, jamais les taux de croissance projetés."""
        serie = unifie_recouvrement[unifie_recouvrement.country_code == "BBB"].sort_values("year")
        prevision = serie["is_forecast"].astype(bool)
        livree = serie.loc[prevision, "GDP_Nominal_Billions_USD"].pct_change()
        brute = serie.loc[prevision, "GDP_Nominal_FMI_Billions_USD"].pct_change()
        assert livree.dropna().values == pytest.approx(brute.dropna().values, rel=1e-9)

    def test_facteur_constant_sur_la_serie(self, unifie_recouvrement):
        facteurs = unifie_recouvrement.groupby("country_code")["Facteur_Raccord"].nunique()
        assert facteurs.max() == 1

    def test_facteur_neutre_si_les_sources_concordent(self, unifie_recouvrement):
        facteur = unifie_recouvrement.loc[unifie_recouvrement.country_code == "AAA",
                                          "Facteur_Raccord"].iloc[0]
        assert facteur == pytest.approx(1.0, abs=1e-9)

    def test_annees_observees_intactes(self, unifie_recouvrement):
        """Le raccord ne touche qu'à la prévision."""
        sans_raccord = build_unified_dataset(_historique(), _fmi_avec_historique())
        avant = sans_raccord[~sans_raccord.is_forecast.astype(bool)].sort_values(
            ["country_code", "year"])["GDP_Nominal_Billions_USD"].values
        apres = unifie_recouvrement[~unifie_recouvrement.is_forecast.astype(bool)].sort_values(
            ["country_code", "year"])["GDP_Nominal_Billions_USD"].values
        assert avant == pytest.approx(apres)

    def test_ppa_raccordee_sur_son_propre_ecart(self, unifie_recouvrement):
        """
        Régression : le facteur du nominal était appliqué à la PPA courante. Sur données
        réelles, le Burundi y chutait de 46 % en 2025, le Soudan y bondissait de 95 %,
        quand le FMI leur projetait +7 % et +6 %.
        """
        serie = unifie_recouvrement[unifie_recouvrement.country_code == "BBB"].set_index("year")
        croissance = serie.loc[2025, "GDP_PPP_Billions_USD"] / serie.loc[2024, "GDP_PPP_Billions_USD"]
        assert croissance == pytest.approx(1.05, rel=1e-9)
        assert serie["Facteur_Raccord_PPA"].iloc[0] == pytest.approx(1 / 0.50)
        assert serie["Facteur_Raccord"].iloc[0] == pytest.approx(1 / 1.60)

    def test_pib_par_habitant_raccorde(self, unifie_recouvrement):
        """
        Régression : le PIB par habitant n'était pas raccordé du tout. La marche que le
        raccord supprime sur le nominal y subsistait : +121 % pour le Burundi en 2025.
        """
        serie = unifie_recouvrement[unifie_recouvrement.country_code == "BBB"].set_index("year")
        assert serie.loc[2025, "GDP_Per_Capita_USD"] == pytest.approx(8000 * 1.04, rel=1e-9)
        assert serie.loc[2030, "GDP_Per_Capita_USD"] == pytest.approx(8000 * 1.04 ** 6, rel=1e-9)

    def test_valeurs_fmi_brutes_conservees_en_regard(self, unifie_recouvrement):
        """Le niveau FMI d'origine reste lisible à côté de la série raccordée."""
        ligne = unifie_recouvrement[(unifie_recouvrement.country_code == "BBB")
                                    & (unifie_recouvrement.year == 2025)].iloc[0]
        assert ligne["GDP_PPP_FMI_Billions_USD"] == pytest.approx(1400 * 0.50 * 1.05 ** 25)
        assert ligne["GDP_Per_Capita_FMI_USD"] == pytest.approx(8000 * 2.0 * 1.04)

    def test_absence_de_valeurs_fmi_laisse_la_serie_intacte(self):
        """Sans recouvrement, le raccord doit se contenter d'un avertissement."""
        unifie = build_unified_dataset(_historique(), _prevision())
        assert "GDP_Nominal_FMI_Billions_USD" not in unifie.columns
        inchange = splice_forecast_levels(unifie, base_year=2024)
        assert inchange["GDP_Nominal_Billions_USD"].equals(unifie["GDP_Nominal_Billions_USD"])


class TestCollecte:
    """
    Une source injoignable doit interrompre la collecte : un indicateur manquant vidait
    silencieusement les colonnes qui en dépendent, une liste de pays manquante laissait
    les agrégats entrer dans les classements.
    """

    def test_nouvelles_tentatives_puis_echec_explicite(self, monkeypatch):
        appels = []

        def en_panne(*args, **kwargs):
            appels.append(args)
            raise http_utils.requests.ConnectionError("réseau coupé")

        monkeypatch.setattr(http_utils.requests, "get", en_panne)
        monkeypatch.setattr(http_utils.time, "sleep", lambda s: None)
        with pytest.raises(RuntimeError, match="3 tentatives"):
            http_utils.get_json("https://exemple.invalid", tentatives=3)
        assert len(appels) == 3

    def test_liste_des_pays_fmi_indispensable(self, monkeypatch):
        def injoignable(url, **kwargs):
            raise RuntimeError(f"{url} injoignable")

        monkeypatch.setattr(fetch_forecast_gdp, "get_json", injoignable)
        with pytest.raises(RuntimeError):
            fetch_forecast_gdp.fetch_imf_countries()

    def test_toutes_les_pages_banque_mondiale_lues(self, monkeypatch):
        """Une réponse sur plusieurs pages ne doit pas être tronquée à la première."""
        def page(numero):
            return [{"page": numero, "pages": 2, "lastupdated": "2026-07-13"},
                    [{"countryiso3code": code, "country": {"value": code}, "date": "2024",
                      "value": 1.0} for code in (("AAA",) if numero == 1 else ("BBB", "WLD"))]]

        monkeypatch.setattr(fetch_historical_gdp, "get_json",
                            lambda url, params=None: page(params["page"]))
        df = fetch_historical_gdp.fetch_worldbank_indicator(
            "NY.GDP.MKTP.CD", 2024, 2024, country_codes={"AAA", "BBB"})
        assert set(df.country_code) == {"AAA", "BBB", "WLD"}
        assert df.set_index("country_code").loc["WLD", "is_aggregate"]

    def test_indicateur_vide_refuse(self, monkeypatch):
        monkeypatch.setattr(fetch_historical_gdp, "get_json",
                            lambda url, params=None: [{"page": 1, "pages": 1}, None])
        with pytest.raises(RuntimeError, match="Aucune donnée"):
            fetch_historical_gdp.fetch_worldbank_indicator("NY.GDP.MKTP.CD", 2024, 2024, {"AAA"})

    def test_codes_fmi_convertis_vers_la_banque_mondiale(self):
        """
        Régression : le Kosovo (`UVK` au FMI, `XKX` à la Banque Mondiale) formait deux
        entités classées séparément, l'une sans prévision, l'autre sans historique.
        """
        brut = {"values": {"NGDPD": {"UVK": {"2024": 11.0, "2030": 18.0},
                                     "WBG": {"2024": 16.0}}}}
        df = fetch_forecast_gdp.parse_imf_data(
            brut, "NGDPD", countries={"UVK": "Kosovo", "WBG": "West Bank and Gaza"})
        assert set(df.country_code) == {"XKX", "PSE"}
        assert not df.is_aggregate.any()


class TestSerieDuDernierRun:
    """
    Plusieurs séries unifiées peuvent coexister (runs sur d'autres bornes). Celle retenue
    doit être celle du dernier run, désignée par ses métadonnées — ni la dernière par
    ordre alphabétique, ni la plus récemment modifiée.
    """

    @staticmethod
    def _run(dossier, debut, fin):
        processed = dossier / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        (processed / f"gdp_unified_{debut}_{fin}.csv").write_text("country_code\n")
        (dossier / "extraction_metadata.json").write_text(
            f'{{"bornes": {{"historique": [{debut}, 2024], "prevision": [2025, {fin}]}}}}')

    def test_metadonnees_designent_la_serie(self, tmp_path):
        self._run(tmp_path, 2000, 2030)
        self._run(tmp_path, 1995, 2028)                      # dernier run
        plus_recente = tmp_path / "processed" / "gdp_unified_2000_2030.csv"
        os.utime(plus_recente)                               # retouchée après coup
        assert unified_csv_path(str(tmp_path)).endswith("gdp_unified_1995_2028.csv")

    def test_ambiguite_sans_metadonnees_refusee(self, tmp_path):
        self._run(tmp_path, 2000, 2030)
        self._run(tmp_path, 1995, 2028)
        (tmp_path / "extraction_metadata.json").unlink()
        with pytest.raises(FileNotFoundError, match="Plusieurs"):
            unified_csv_path(str(tmp_path))

    def test_serie_unique_sans_metadonnees_acceptee(self, tmp_path):
        self._run(tmp_path, 2000, 2030)
        (tmp_path / "extraction_metadata.json").unlink()
        assert unified_csv_path(str(tmp_path)).endswith("gdp_unified_2000_2030.csv")


class TestDetectionAnnees:
    def test_frontiere_est_la_derniere_annee_observee(self, unifie):
        assert detect_years(unifie) == {"start": 2000, "boundary": 2024, "end": 2030}


# ------------------------------------ évaluation des prévisions d'époque

class TestBaseHistoriqueWEO:
    """
    Lecture de la WEO Historical Forecasts Database : un onglet par indicateur, une ligne
    par (pays, année visée), une colonne par édition nommée `S2019ngdp_rpch`.

    L'invariant central est l'horizon : sans lui, une ré-estimation d'une année écoulée
    serait comptée comme une prévision, et l'évaluation mesurerait la capacité du FMI à
    se souvenir du passé plutôt qu'à anticiper l'avenir.
    """

    @staticmethod
    def _classeur(dossier, onglet="ngdp_rpch"):
        """Reproduit le format du classeur, valeurs manquantes en « . » comprises."""
        lignes = pd.DataFrame([
            # World est un agrégat du FMI, publié dans le même onglet
            dict(country="World", WEO_Country_Code=1, ISOAlpha_3Code="G001", year=2019,
                 **{f"S2018{onglet}": 3.9, f"F2018{onglet}": 3.7, f"F2020{onglet}": 2.8}),
            # France 2019 porte deux ré-estimations : à un an (F2020) et à deux ans (F2021),
            # de valeurs différentes, pour que le choix de la référence soit vérifiable
            dict(country="France", WEO_Country_Code=132, ISOAlpha_3Code="FRA", year=2019,
                 **{f"S2018{onglet}": 2.1, f"F2018{onglet}": 1.9,
                    f"F2020{onglet}": 1.8, f"F2021{onglet}": 1.5}),
            dict(country="France", WEO_Country_Code=132, ISOAlpha_3Code="FRA", year=2020,
                 **{f"S2018{onglet}": 1.7, f"F2018{onglet}": 1.6, f"F2021{onglet}": -7.9}),
            dict(country="Japan", WEO_Country_Code=158, ISOAlpha_3Code="JPN", year=2020,
                 **{f"S2018{onglet}": 0.8, f"F2018{onglet}": ".", f"F2021{onglet}": -4.5}),
            # Le classeur code le Kosovo `KOS`, la Banque Mondiale `XKX`
            dict(country="Kosovo", WEO_Country_Code=967, ISOAlpha_3Code="KOS", year=2019,
                 **{f"S2018{onglet}": 4.0, f"F2020{onglet}": 4.8}),
        ])
        chemin = dossier / "WEOhistorical.xlsx"
        lignes.to_excel(chemin, sheet_name=onglet, index=False)
        return chemin

    def test_mise_au_format_long(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert {"country_code", "year", "vintage", "horizon", "valeur"} <= set(table.columns)
        assert set(table["vintage"]) == {"S2018", "F2018", "F2020", "F2021"}

    def test_valeurs_manquantes_ecartees(self, tmp_path):
        """Le classeur note les trous « . » : ils ne doivent pas devenir des zéros."""
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        japon = table[(table.country_code == "JPN") & (table.vintage == "F2018")]
        assert japon.empty

    def test_horizon_compte_depuis_l_edition(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path))).set_index(
            ["country_code", "year", "vintage"])
        assert table.loc[("FRA", 2019, "S2018"), "horizon"] == 1     # projetée un an avant
        assert table.loc[("FRA", 2020, "S2018"), "horizon"] == 2
        assert table.loc[("FRA", 2019, "F2020"), "horizon"] == -1    # ré-estimation

    def test_reestimations_ne_sont_pas_des_previsions(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert not table.loc[table.horizon < 0, "est_projection"].any()
        assert table.loc[table.horizon >= 0, "est_projection"].all()

    def test_saison_extraite(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert set(table["saison"]) == {"S", "F"}

    def test_agregats_ecartes_sans_liste_de_pays(self, tmp_path):
        """Sans série unifiée sous la main, le préfixe des codes d'agrégats sert de repli."""
        from evaluate_forecasts import lire_base_historique, exclure_agregats
        table = lire_base_historique(str(self._classeur(tmp_path)))
        pays = exclure_agregats(table, data_dir=str(tmp_path / "absent"))
        assert "G001" not in set(pays["country_code"])
        assert {"FRA", "JPN"} <= set(pays["country_code"])

    def test_reference_prise_a_un_an_et_pas_plus_tard(self, tmp_path):
        """
        La référence est la ré-estimation de l'automne suivant, pas une révision ultérieure.

        France 2019 vaut 1,8 dans l'édition d'automne 2020 et 1,5 dans celle de 2021 :
        retenir la seconde jugerait la prévision sur des révisions statistiques
        postérieures, hors de portée du prévisionniste.
        """
        from evaluate_forecasts import lire_base_historique, realise_selon_fmi
        table = lire_base_historique(str(self._classeur(tmp_path)))
        reference = realise_selon_fmi(table).set_index(["country_code", "year"])
        assert reference.loc[("FRA", 2019), "realise_fmi"] == pytest.approx(1.8)
        assert reference.loc[("FRA", 2019), "realise_fmi"] != pytest.approx(1.5)
        assert reference.loc[("FRA", 2020), "realise_fmi"] == pytest.approx(-7.9)

    def test_erreur_de_prevision(self, tmp_path):
        from evaluate_forecasts import lire_base_historique, evaluer
        table = lire_base_historique(str(self._classeur(tmp_path)))
        evaluation = evaluer(table, data_dir=str(tmp_path / "absent"))

        ligne = evaluation[(evaluation.country_code == "FRA") & (evaluation.year == 2020)
                           & (evaluation.vintage == "S2018")].iloc[0]
        # +1,7 % projeté au printemps 2018 contre −7,9 % ré-estimé : 9,6 points
        assert ligne["erreur_vs_fmi"] == pytest.approx(9.6, abs=1e-9)

    def test_seules_les_projections_sont_evaluees(self, tmp_path):
        from evaluate_forecasts import lire_base_historique, evaluer
        table = lire_base_historique(str(self._classeur(tmp_path)))
        evaluation = evaluer(table, data_dir=str(tmp_path / "absent"))
        assert (evaluation["horizon"] >= 0).all()

    def test_code_kosovo_converti(self, tmp_path):
        """Régression : `KOS` était inconnu de la série du pipeline, le Kosovo était écarté."""
        from evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert "XKX" in set(table.country_code)
        assert "KOS" not in set(table.country_code)

    @staticmethod
    def _pipeline(dossier):
        """Série unifiée minimale : la croissance observée par la Banque Mondiale."""
        (dossier / "processed").mkdir(parents=True)
        pd.DataFrame([
            dict(country_code="FRA", year=2019, is_forecast=False, is_aggregate=False, GDP_Growth_Pct=1.9),
            dict(country_code="FRA", year=2020, is_forecast=False, is_aggregate=False, GDP_Growth_Pct=-7.5),
            dict(country_code="JPN", year=2020, is_forecast=False, is_aggregate=False, GDP_Growth_Pct=-4.2),
        ]).to_csv(dossier / "processed" / "gdp_unified_2000_2030.csv", index=False)
        return str(dossier)

    def test_reference_banque_mondiale_pour_la_croissance(self, tmp_path):
        from evaluate_forecasts import lire_base_historique, evaluer
        table = lire_base_historique(str(self._classeur(tmp_path)))
        evaluation = evaluer(table, data_dir=self._pipeline(tmp_path / "data"))
        ligne = evaluation[(evaluation.country_code == "FRA") & (evaluation.year == 2020)
                           & (evaluation.vintage == "S2018")].iloc[0]
        assert ligne["erreur_vs_bm"] == pytest.approx(1.7 - (-7.5))

    def test_pas_de_reference_banque_mondiale_hors_croissance(self, tmp_path):
        """
        Régression : la référence Banque Mondiale était toujours la croissance du PIB,
        y compris pour `--indicateur pcpi_pch` — l'inflation projetée était comparée
        à la croissance observée.
        """
        from evaluate_forecasts import lire_base_historique, evaluer, synthese_par_horizon
        table = lire_base_historique(str(self._classeur(tmp_path, onglet="pcpi_pch")),
                                     indicateur="pcpi_pch")
        evaluation = evaluer(table, data_dir=self._pipeline(tmp_path / "data"),
                             indicateur="pcpi_pch")
        assert evaluation["erreur_vs_bm"].isna().all()
        assert not synthese_par_horizon(evaluation)["reference"].str.startswith("Banque").any()

    def test_valeurs_extremes_signalees(self):
        """
        Une projection d'hyperinflation (le Venezuela à 10 000 000 %) porte la moyenne
        à des milliers de points : la synthèse doit fournir des médianes et le signaler.
        """
        from evaluate_forecasts import synthese_par_horizon, moyennes_dominees
        erreurs = [0.5, -0.3, 0.8, -1.1, 0.2, 1e7]
        evaluation = pd.DataFrame(dict(horizon=1, erreur_vs_fmi=erreurs, erreur_vs_bm=np.nan))
        synthese = synthese_par_horizon(evaluation)
        assert synthese.loc[0, "erreur_absolue_mediane"] == pytest.approx(0.65)
        assert moyennes_dominees(synthese)
        assert not moyennes_dominees(synthese_par_horizon(evaluation.iloc[:-1]))

    def test_classeur_absent_signale_clairement(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        with pytest.raises(FileNotFoundError, match="LISEZ-MOI"):
            lire_base_historique(str(tmp_path / "inexistant.xlsx"))

    def test_indicateur_inconnu_rejete(self, tmp_path):
        from evaluate_forecasts import lire_base_historique
        with pytest.raises(ValueError, match="Indicateur inconnu"):
            lire_base_historique(str(self._classeur(tmp_path)), indicateur="pib_magique")

    def test_synthese_couvre_les_deux_references(self, tmp_path):
        from evaluate_forecasts import lire_base_historique, evaluer, synthese_par_horizon
        table = lire_base_historique(str(self._classeur(tmp_path)))
        synthese = synthese_par_horizon(evaluer(table, data_dir=str(tmp_path / "absent")))
        assert not synthese.empty
        assert {"horizon", "biais_moyen", "erreur_absolue_moyenne"} <= set(synthese.columns)


# ------------------------------------------- fichiers réellement produits

@pytest.mark.donnees
class TestFichiersProduits:
    """
    Contrôles sur les données du dépôt. Sautés si le pipeline n'a pas encore tourné.
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def fichiers():
        synthese = os.path.join(PROCESSED, "gdp_country_summary.csv")
        try:
            serie = unified_csv_path("data")
        except FileNotFoundError:
            pytest.skip("Aucune donnée produite : lancez `python gdp_pipeline.py`")
        if not os.path.exists(synthese):
            pytest.skip("Aucune donnée produite : lancez `python gdp_pipeline.py`")
        return pd.read_csv(serie), pd.read_csv(synthese)

    def test_un_seul_libelle_par_code(self, fichiers):
        unifie, _ = fichiers
        multiples = unifie.groupby("country_code")["country_name"].nunique()
        assert multiples.max() == 1, f"codes ambigus : {list(multiples[multiples > 1].index)}"

    def test_aucun_agregat_dans_la_synthese(self, fichiers):
        unifie, synthese = fichiers
        agregats = set(unifie.loc[unifie.is_aggregate.astype(bool), "country_code"])
        intrus = agregats & set(synthese.country_code)
        assert not intrus, f"agrégats classés comme pays : {sorted(intrus)}"

    def test_agregats_notoires_ecartes(self, fichiers):
        _, synthese = fichiers
        assert not {"WLD", "OED", "EUU", "HIC", "MIC"} & set(synthese.country_code)

    def test_pas_de_doublon_pays_annee(self, fichiers):
        unifie, _ = fichiers
        assert not unifie.duplicated(subset=["country_code", "year"]).any()

    def test_chainage_reel_coherent(self, fichiers):
        """Sur données réelles : la croissance implicite des volumes chaînés."""
        unifie, _ = fichiers
        verifies = 0
        for code in ("USA", "CHN", "IND", "FRA"):
            serie = unifie[unifie.country_code == code].sort_values("year")
            if serie.empty:
                continue
            prevision = serie["is_forecast"].astype(bool)
            implicite = (serie["GDP_Real_Billions_USD"].pct_change() * 100)[prevision]
            attendu = serie["GDP_Growth_Pct"][prevision]
            valides = implicite.notna() & attendu.notna()
            if valides.any():
                assert implicite[valides].values == pytest.approx(
                    attendu[valides].values, abs=1e-6), f"chaînage incohérent pour {code}"
                verifies += 1
        assert verifies > 0, "aucun pays vérifiable"

    def test_rangs_coherents_avec_les_niveaux(self, fichiers):
        _, synthese = fichiers
        for niveau, rang in (("GDP_2024_Billion_USD", "Rank_2024"),
                             ("GDP_PPA_2024_Billion_Intl_2021", "Rank_PPA_2024")):
            if niveau not in synthese.columns:
                continue
            ordonnee = synthese.dropna(subset=[niveau, rang]).sort_values(niveau, ascending=False)
            assert list(ordonnee[rang]) == sorted(ordonnee[rang]), f"{rang} incohérent"

    def test_ecarts_de_rang_sur_un_meme_panel(self, fichiers):
        _, synthese = fichiers
        if "Rank_2024" not in synthese.columns:
            pytest.skip("run sur d'autres bornes")
        classes = synthese.dropna(subset=["Rank_2024"])
        assert (classes["Rank_Change"] == classes["Rank_2024"] - classes["Rank_2030_Forecast"]).all()
        assert classes[["Rank_2030_Forecast", "Rank_PPA_2024", "Rank_PPA_2030"]].notna().all().all()

    def test_codes_propres_au_fmi_convertis(self, fichiers):
        unifie, _ = fichiers
        assert not {"UVK", "WBG"} & set(unifie.country_code)

    def test_premieres_economies_plausibles(self, fichiers):
        """Garde-fou de bon sens : le Top 3 nominal ne change pas d'un run à l'autre."""
        _, synthese = fichiers
        if "Rank_2024" not in synthese.columns:
            pytest.skip("run sur d'autres bornes")
        tete = synthese.nsmallest(3, "Rank_2024")["country_code"].tolist()
        assert tete == ["USA", "CHN", "DEU"]
