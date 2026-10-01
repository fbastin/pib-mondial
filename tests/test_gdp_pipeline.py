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

    pytest -v                        # depuis la racine du dépôt (voir pytest.ini)
    pytest -m "not donnees"          # sans les fichiers produits
"""

import os
import re
import json

import numpy as np
import pandas as pd
import pytest

from pib import http_utils, gdp_pipeline, fetch_historical_gdp, fetch_forecast_gdp, update_weo_editions
from pib.gdp_pipeline import (
    calculate_cagr,
    reference_years,
    build_unified_dataset,
    splice_forecast_levels,
    extend_real_series,
    compute_country_summary,
    run_pipeline,
    unified_csv_path,
    latest_observed_year,
    latest_forecast_year,
    choose_reference_year,
)
from pib.visualize_gdp import detect_years

PROCESSED = os.path.join("data", "processed")


@pytest.fixture(autouse=True)
def sans_reseau_monde(monkeypatch):
    """
    Le pipeline collecte la croissance mondiale par habitant : les tests restent hors
    ligne avec une série simulée (reculs en 1975, 1982, 1991, 2009 et 2020).
    """
    serie = pd.Series({a: (-1.0 if a in (1975, 1982, 1991, 2009, 2020) else 2.0) for a in range(1961, 2026)},
                      name="croissance_pib_mondial_par_habitant")
    serie.index.name = "year"
    monkeypatch.setattr(gdp_pipeline, "fetch_world_per_capita_growth", lambda end_year=None: serie)


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
                 GDP_Real_USD=1e12 * (1.02 ** n), GDP_Real_PPP_Intl=1.5e12 * (1.02 ** n),
                 Population=50e6 * (1.01 ** n)),
            # Pays B : plus petit en nominal, plus grand en PPA (monnaie sous-évaluée)
            dict(country_code="BBB", country_name="Pays B", year=annee, is_aggregate=False,
                 GDP_Nominal_USD=5e11 * (1.05 ** n), GDP_Growth_Annual_Pct=4.0,
                 GDP_Per_Capita_USD=8000.0, GDP_PPP_USD=1.4e12 * (1.05 ** n),
                 GDP_Real_USD=5e11 * (1.04 ** n), GDP_Real_PPP_Intl=2.0e12 * (1.04 ** n),
                 Population=100e6 * (1.02 ** n)),
            dict(country_code="WLD", country_name="World", year=annee, is_aggregate=True,
                 GDP_Nominal_USD=9e13 * (1.03 ** n), GDP_Growth_Annual_Pct=3.0,
                 GDP_Per_Capita_USD=12000.0, GDP_PPP_USD=1e14 * (1.03 ** n),
                 GDP_Real_USD=9e13 * (1.02 ** n), GDP_Real_PPP_Intl=1e14 * (1.02 ** n),
                 Population=8e9),
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
                 GDP_Growth_Pct=2.0, GDP_PPP_Billions_USD=1200.0, GDP_Per_Capita_USD=32000.0,
                 Population_Millions=50 * (1.01 ** 24) * (1.01 ** n)),
            dict(country_code="BBB", country_name="BBB", year=annee, is_forecast=True,
                 is_aggregate=False, GDP_Nominal_Billions_USD=500 * (1.05 ** 24) * (1.05 ** n),
                 GDP_Growth_Pct=4.0, GDP_PPP_Billions_USD=1400.0, GDP_Per_Capita_USD=9000.0,
                 Population_Millions=100 * (1.02 ** 24) * (1.02 ** n)),
            dict(country_code="WLD", country_name="WLD", year=annee, is_forecast=True,
                 is_aggregate=True, GDP_Nominal_Billions_USD=90000 * (1.03 ** n),
                 GDP_Growth_Pct=3.0, GDP_PPP_Billions_USD=100000.0, GDP_Per_Capita_USD=13000.0),
        ]
    return pd.DataFrame(lignes)


def _fmi_avec_historique(desaccord: float = 1.60, desaccord_ppa: float = 0.50,
                         desaccord_hab: float = 2.0, desaccord_pop: float = 1.10) -> pd.DataFrame:
    """
    Extraction FMI incluant ses propres estimations des années observées.

    `desaccord` est le rapport entre le niveau FMI et le niveau Banque Mondiale pour
    Pays B, appliqué à **toute** sa série : le FMI mesure ce pays plus haut sans pour
    autant lui prêter une autre dynamique. C'est la configuration qui produit une marche
    à la jonction lorsque les deux séries sont juxtaposées. Pays A est mesuré à l'identique.

    La PPA courante (`desaccord_ppa`) et le PIB par habitant (`desaccord_hab`) divergent
    de rapports différents, comme sur données réelles : un facteur unique, calé sur le
    nominal, ne peut pas les raccorder. Le PIB par habitant de Pays B, stable sur
    l'historique, progresse de 4 %/an en projection. Sa population est comptée 10 % plus
    haut par le FMI (`desaccord_pop`), avec la même croissance de 2 %/an.
    """
    lignes = []
    for annee in range(2000, 2031):
        n = annee - 2000
        prevision = annee >= 2025
        lignes += [
            dict(country_code="AAA", country_name="AAA", year=annee, is_forecast=prevision,
                 is_aggregate=False, GDP_Nominal_Billions_USD=1000 * (1.03 ** n),
                 GDP_Growth_Pct=2.0, GDP_PPP_Billions_USD=1200 * (1.03 ** n),
                 GDP_Per_Capita_USD=30000.0, Population_Millions=50 * (1.01 ** n)),
            dict(country_code="BBB", country_name="BBB", year=annee, is_forecast=prevision,
                 is_aggregate=False, GDP_Nominal_Billions_USD=500 * desaccord * (1.05 ** n),
                 GDP_Growth_Pct=4.0, GDP_PPP_Billions_USD=1400 * desaccord_ppa * (1.05 ** n),
                 GDP_Per_Capita_USD=8000 * desaccord_hab * (1.04 ** max(annee - 2024, 0)),
                 Population_Millions=100 * desaccord_pop * (1.02 ** n)),
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
        from pib.build_results_page import note_rapport
        data, _ = self._run(tmp_path, monkeypatch, pays_c_publie=False)
        note_reference = note_rapport(str(data), 2024)
        note_recente = note_rapport(str(data / "plus_recent"), 2025)
        assert "Rapport de référence" in note_reference and "plus_recent/resultats_gdp.html" in note_reference
        assert "Pays C sort du classement" in note_recente and "../resultats_gdp.html" in note_recente


class TestHorizonAutomatique:
    """
    L'horizon de prévision suit l'édition du WEO (2031 pour avril 2026) au lieu d'être
    figé à 2030 : une année projetée par le FMI n'est plus téléchargée puis écartée.
    """

    @staticmethod
    def _fmi_jusqu_en_2031(annee_isolee: bool = False) -> pd.DataFrame:
        fmi = _fmi_avec_historique()
        horizon = fmi[fmi.year == 2030].copy()
        horizon["year"] = 2031
        horizon["GDP_Nominal_Billions_USD"] *= 1.03
        morceaux = [fmi, horizon]
        if annee_isolee:                          # une projection 2032 pour un seul pays
            isolee = horizon[horizon.country_code == "AAA"].copy()
            isolee["year"] = 2032
            morceaux.append(isolee)
        return pd.concat(morceaux, ignore_index=True)

    def test_horizon_de_l_edition(self):
        assert latest_forecast_year(_fmi_avec_historique()) == 2030
        assert latest_forecast_year(self._fmi_jusqu_en_2031()) == 2031

    def test_projection_isolee_ignoree(self):
        assert latest_forecast_year(self._fmi_jusqu_en_2031(annee_isolee=True)) == 2031

    def test_le_pipeline_suit_l_horizon(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gdp_pipeline, "fetch_all_historical_gdp", lambda start_year, end_year: _historique())
        monkeypatch.setattr(gdp_pipeline, "fetch_all_forecasts",
                            lambda **kwargs: (self._fmi_jusqu_en_2031(annee_isolee=True), {}))
        data = tmp_path / "data"
        run_pipeline(data_dir=str(data), output_dir=str(tmp_path / "outputs"))

        meta = json.loads((data / "extraction_metadata.json").read_text(encoding="utf-8"))
        assert meta["bornes"]["prevision"] == [2025, 2031]
        unifie = pd.read_csv(unified_csv_path(str(data)))
        assert unifie["year"].max() == 2031               # la projection isolée de 2032 est écartée
        synthese = pd.read_csv(data / "processed" / "gdp_country_summary.csv")
        assert synthese["CAGR_Prevision_2024_2031_Pct"].notna().all()
        assert synthese["Rank_2031_Forecast"].notna().all()


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
        from pib.evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert {"country_code", "year", "vintage", "horizon", "valeur"} <= set(table.columns)
        assert set(table["vintage"]) == {"S2018", "F2018", "F2020", "F2021"}

    def test_valeurs_manquantes_ecartees(self, tmp_path):
        """Le classeur note les trous « . » : ils ne doivent pas devenir des zéros."""
        from pib.evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        japon = table[(table.country_code == "JPN") & (table.vintage == "F2018")]
        assert japon.empty

    def test_horizon_compte_depuis_l_edition(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path))).set_index(
            ["country_code", "year", "vintage"])
        assert table.loc[("FRA", 2019, "S2018"), "horizon"] == 1     # projetée un an avant
        assert table.loc[("FRA", 2020, "S2018"), "horizon"] == 2
        assert table.loc[("FRA", 2019, "F2020"), "horizon"] == -1    # ré-estimation

    def test_reestimations_ne_sont_pas_des_previsions(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert not table.loc[table.horizon < 0, "est_projection"].any()
        assert table.loc[table.horizon >= 0, "est_projection"].all()

    def test_saison_extraite(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique
        table = lire_base_historique(str(self._classeur(tmp_path)))
        assert set(table["saison"]) == {"S", "F"}

    def test_agregats_ecartes_sans_liste_de_pays(self, tmp_path):
        """Sans série unifiée sous la main, le préfixe des codes d'agrégats sert de repli."""
        from pib.evaluate_forecasts import lire_base_historique, exclure_agregats
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
        from pib.evaluate_forecasts import lire_base_historique, realise_selon_fmi
        table = lire_base_historique(str(self._classeur(tmp_path)))
        reference = realise_selon_fmi(table).set_index(["country_code", "year"])
        assert reference.loc[("FRA", 2019), "realise_fmi"] == pytest.approx(1.8)
        assert reference.loc[("FRA", 2019), "realise_fmi"] != pytest.approx(1.5)
        assert reference.loc[("FRA", 2020), "realise_fmi"] == pytest.approx(-7.9)

    def test_erreur_de_prevision(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique, evaluer
        table = lire_base_historique(str(self._classeur(tmp_path)))
        evaluation = evaluer(table, data_dir=str(tmp_path / "absent"))

        ligne = evaluation[(evaluation.country_code == "FRA") & (evaluation.year == 2020)
                           & (evaluation.vintage == "S2018")].iloc[0]
        # +1,7 % projeté au printemps 2018 contre −7,9 % ré-estimé : 9,6 points
        assert ligne["erreur_vs_fmi"] == pytest.approx(9.6, abs=1e-9)

    def test_seules_les_projections_sont_evaluees(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique, evaluer
        table = lire_base_historique(str(self._classeur(tmp_path)))
        evaluation = evaluer(table, data_dir=str(tmp_path / "absent"))
        assert (evaluation["horizon"] >= 0).all()

    def test_code_kosovo_converti(self, tmp_path):
        """Régression : `KOS` était inconnu de la série du pipeline, le Kosovo était écarté."""
        from pib.evaluate_forecasts import lire_base_historique
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
        from pib.evaluate_forecasts import lire_base_historique, evaluer
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
        from pib.evaluate_forecasts import lire_base_historique, evaluer, synthese_par_horizon
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
        from pib.evaluate_forecasts import synthese_par_horizon, moyennes_dominees
        erreurs = [0.5, -0.3, 0.8, -1.1, 0.2, 1e7]
        evaluation = pd.DataFrame(dict(horizon=1, erreur_vs_fmi=erreurs, erreur_vs_bm=np.nan))
        synthese = synthese_par_horizon(evaluation)
        assert synthese.loc[0, "erreur_absolue_mediane"] == pytest.approx(0.65)
        assert moyennes_dominees(synthese)
        assert not moyennes_dominees(synthese_par_horizon(evaluation.iloc[:-1]))

    def test_classeur_absent_signale_clairement(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique
        with pytest.raises(FileNotFoundError, match="LISEZ-MOI"):
            lire_base_historique(str(tmp_path / "inexistant.xlsx"))

    def test_indicateur_inconnu_rejete(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique
        with pytest.raises(ValueError, match="Indicateur inconnu"):
            lire_base_historique(str(self._classeur(tmp_path)), indicateur="pib_magique")

    def test_synthese_couvre_les_deux_references(self, tmp_path):
        from pib.evaluate_forecasts import lire_base_historique, evaluer, synthese_par_horizon
        table = lire_base_historique(str(self._classeur(tmp_path)))
        synthese = synthese_par_horizon(evaluer(table, data_dir=str(tmp_path / "absent")))
        assert not synthese.empty
        assert {"horizon", "biais_moyen", "erreur_absolue_moyenne"} <= set(synthese.columns)


class TestEditionsAPI:
    """
    Éditions récentes du WEO lues dans l'API SDMX du FMI, en complément du classeur
    téléchargé à la main. Le flux courant ne dit pas quelle édition il porte : le nom est
    déduit des archives, et vérifié par l'horizon servi plutôt que deviné.
    """

    def test_edition_courante_apres_un_automne(self):
        from pib.update_weo_editions import nommer_editions
        assert nommer_editions(["WEO", "WEO_2025_OCT_VINTAGE"], horizon_courant=2031) == {
            "WEO": "S2026", "WEO_2025_OCT_VINTAGE": "F2025"}

    def test_edition_courante_apres_un_printemps(self):
        from pib.update_weo_editions import nommer_editions
        noms = nommer_editions(["WEO", "WEO_2025_OCT_VINTAGE", "WEO_2026_APR_VINTAGE"], horizon_courant=2031)
        assert noms["WEO"] == "F2026" and noms["WEO_2026_APR_VINTAGE"] == "S2026"

    def test_horizon_incoherent_refuse(self):
        from pib.update_weo_editions import nommer_editions
        with pytest.raises(RuntimeError, match="incohérente"):
            nommer_editions(["WEO", "WEO_2025_OCT_VINTAGE"], horizon_courant=2030)

    def test_sans_archive_rien_n_est_devine(self):
        from pib.update_weo_editions import nommer_editions
        with pytest.raises(RuntimeError, match="archivée"):
            nommer_editions(["WEO"], horizon_courant=2031)

    def test_lecture_de_la_reponse_sdmx(self, monkeypatch):
        """Années non ordonnées et valeurs textuelles, comme dans les réponses réelles."""
        from pib import update_weo_editions
        reponse = {
            "structure": {"dimensions": {
                "series": [{"id": "COUNTRY", "values": [{"id": "FRA", "name": "France"},
                                                        {"id": "KOS", "name": "Kosovo"}]},
                           {"id": "INDICATOR", "values": [{"id": "NGDP_RPCH"}]},
                           {"id": "FREQUENCY", "values": [{"id": "A"}]}],
                "observation": [{"id": "TIME_PERIOD", "values": [{"id": "2025"}, {"id": "2024"}]}]}},
            "dataSets": [{"series": {"0:0:0": {"observations": {"0": ["0.7"], "1": ["1.1"]}},
                                     "1:0:0": {"observations": {"1": ["4.0"], "0": [None]}}}}],
        }
        monkeypatch.setattr(update_weo_editions, "get_json", lambda url, **kwargs: reponse)
        table = update_weo_editions.lire_flux("WEO", "NGDP_RPCH").set_index(["country_code", "year"])
        assert table.loc[("FRA", 2025), "valeur"] == pytest.approx(0.7)
        assert table.loc[("FRA", 2024), "valeur"] == pytest.approx(1.1)
        assert table.loc[("KOS", 2024), "valeur"] == pytest.approx(4.0)
        assert len(table) == 3                               # la valeur nulle est écartée

    @staticmethod
    def _classeur(dossier, editions):
        """Classeur à trois onglets ne contenant que `editions`."""
        chemin = dossier / "WEOhistorical.xlsx"
        with pd.ExcelWriter(chemin) as writer:
            for feuille in ("ngdp_rpch", "pcpi_pch", "bca_gdp_bp6"):
                pd.DataFrame([dict(country="France", WEO_Country_Code=132, ISOAlpha_3Code="FRA", year=2024,
                                   **{f"{e}{feuille}": 1.0 for e in editions})]).to_excel(
                    writer, sheet_name=feuille, index=False)
        return chemin

    @staticmethod
    def _api(monkeypatch):
        from pib import update_weo_editions
        monkeypatch.setattr(update_weo_editions, "lister_flux", lambda: ["WEO", "WEO_2025_OCT_VINTAGE"])
        horizons = {"WEO": 2031, "WEO_2025_OCT_VINTAGE": 2030}
        monkeypatch.setattr(update_weo_editions, "lire_flux", lambda flux, ind: pd.DataFrame(
            [dict(country_code="FRA", country="France", year=a, valeur=float(a - 2000))
             for a in range(1980, horizons[flux] + 1)]))
        return update_weo_editions

    def test_ajout_des_editions_absentes_du_classeur(self, tmp_path, monkeypatch):
        module = self._api(monkeypatch)
        classeur = self._classeur(tmp_path, ["F2024", "F2025"])
        complement = tmp_path / "weo_editions_api.csv"
        module.mettre_a_jour(str(classeur), str(complement))

        ajout = pd.read_csv(complement)
        assert set(ajout["vintage"]) == {"S2026"}             # F2025 est déjà dans le classeur
        assert set(ajout["indicateur"]) == {"ngdp_rpch", "pcpi_pch", "bca_gdp_bp6"}
        assert sorted(ajout["year"].unique()) == list(range(2024, 2032))   # horizons −2 à +5

    def test_complement_cumulatif_et_classeur_prioritaire(self, tmp_path, monkeypatch):
        """
        Une édition que l'API ne sert plus reste dans le complément ; une édition arrivée
        entre-temps dans le classeur en sort.
        """
        module = self._api(monkeypatch)
        classeur = self._classeur(tmp_path, ["F2025"])
        complement = tmp_path / "weo_editions_api.csv"
        pd.DataFrame([
            dict(indicateur="ngdp_rpch", vintage="S2025", flux="WEO", country="France",
                 country_code="FRA", year=2025, valeur=1.2, extrait_le="2025-06-01"),
            dict(indicateur="ngdp_rpch", vintage="F2025", flux="WEO", country="France",
                 country_code="FRA", year=2025, valeur=0.9, extrait_le="2025-11-01"),
        ]).to_csv(complement, index=False)
        module.mettre_a_jour(str(classeur), str(complement))

        editions = set(pd.read_csv(complement).query("indicateur == 'ngdp_rpch'")["vintage"])
        assert editions == {"S2025", "S2026"}

    def test_lecture_du_classeur_completee(self, tmp_path):
        """Le complément ajoute ses éditions ; pour une édition commune, le classeur fait foi."""
        from pib.evaluate_forecasts import lire_base_historique
        classeur = TestBaseHistoriqueWEO._classeur(tmp_path)
        pd.DataFrame([
            dict(indicateur="ngdp_rpch", vintage="F2022", flux="WEO_2022_OCT_VINTAGE", country="France",
                 country_code="FRA", year=2020, valeur=-7.5, extrait_le="2026-09-29"),
            dict(indicateur="ngdp_rpch", vintage="F2021", flux="WEO_2021_OCT_VINTAGE", country="France",
                 country_code="FRA", year=2020, valeur=99.0, extrait_le="2026-09-29"),
        ]).to_csv(tmp_path / "weo_editions_api.csv", index=False)

        table = lire_base_historique(str(classeur)).set_index(["country_code", "year", "vintage"])
        assert table.loc[("FRA", 2020, "F2022"), "horizon"] == -2
        assert table.loc[("FRA", 2020, "F2021"), "valeur"] == pytest.approx(-7.9)


class TestArchiveDesEditions:
    """
    Chaque édition servie par l'API est archivée en entier, une fois pour toutes : c'est
    la publication d'époque qui compte, pas une version corrigée après coup.
    """

    @staticmethod
    def _reponse():
        return {
            "structure": {"dimensions": {
                "series": [{"id": "COUNTRY", "values": [{"id": "FRA"}, {"id": "G001"}]},
                           {"id": "INDICATOR", "values": [{"id": "NGDPD"}, {"id": "LP"}]},
                           {"id": "FREQUENCY", "values": [{"id": "A"}]}],
                "observation": [{"id": "TIME_PERIOD", "values": [{"id": "2025"}, {"id": "2024"}]}]}},
            "dataSets": [{"series": {"0:0:0": {"observations": {"0": ["3200.5"], "1": ["3160.4"]}},
                                     "0:1:0": {"observations": {"1": ["68.4"], "0": [None]}},
                                     "1:0:0": {"observations": {"0": ["117000"]}}}}],
        }

    def test_lecture_d_une_edition_complete(self, monkeypatch):
        monkeypatch.setattr(update_weo_editions, "get_json", lambda url, **kwargs: self._reponse())
        table = update_weo_editions.lire_edition_complete("WEO").set_index(["country_code", "indicator", "year"])
        assert table.loc[("FRA", "NGDPD", 2024), "value"] == pytest.approx(3160.4)
        assert table.loc[("FRA", "LP", 2024), "value"] == pytest.approx(68.4)
        assert table.loc[("G001", "NGDPD", 2025), "value"] == pytest.approx(117000)
        assert len(table) == 4                                  # la valeur nulle est écartée

    def test_archivage_unique_et_index(self, tmp_path, monkeypatch):
        appels = []

        def lire(flux):
            appels.append(flux)
            return pd.DataFrame(dict(country_code="FRA", indicator="NGDPD", year=[2024, 2025],
                                     value=[1.0, 2.0] if flux == "WEO" else [1.5, 2.5]))

        monkeypatch.setattr(update_weo_editions, "lire_edition_complete", lire)
        noms = {"WEO": "S2026", "WEO_2025_OCT_VINTAGE": "F2025"}
        assert update_weo_editions.archiver_editions(noms, str(tmp_path)) == ["F2025", "S2026"]
        assert update_weo_editions.archiver_editions(noms, str(tmp_path)) == []   # rien de nouveau
        assert len(appels) == 2                                                   # rien retéléchargé

        archive = pd.read_csv(tmp_path / "WEO_S2026.csv.gz")
        assert list(archive["value"]) == [1.0, 2.0]
        index = pd.read_csv(tmp_path / "index.csv")
        assert list(index["edition"]) == ["F2025", "S2026"]
        assert list(index["flux"]) == ["WEO_2025_OCT_VINTAGE", "WEO"]


class TestLecturesComplementaires:
    """Avril face à octobre, le FMI face à une prévision naïve, et la croissance mondiale."""

    def test_prevision_naive_sans_information_posterieure(self):
        """
        Pour une édition de 2016, la prévision naïve est la moyenne des croissances 2011 à
        2014 : la ré-estimation de 2015 ne paraît qu'à l'automne 2016.
        """
        from pib.evaluate_forecasts import ajouter_prevision_naive
        realise = pd.DataFrame(dict(country_code="FRA", year=range(2010, 2016),
                                    realise_fmi=[9.0, 1.0, 2.0, 3.0, 4.0, 50.0]))
        evaluation = pd.DataFrame(dict(country_code="FRA", annee_millesime=[2016, 2015, 2013],
                                       year=[2017, 2016, 2014], realise_fmi=[1.0, 1.0, 1.0]))
        naif = ajouter_prevision_naive(evaluation, realise).set_index("annee_millesime")
        assert naif.loc[2016, "naif"] == pytest.approx(2.5)                 # 2011 à 2014
        assert naif.loc[2015, "naif"] == pytest.approx((9 + 1 + 2 + 3) / 4)  # 2010 à 2013
        assert pd.isna(naif.loc[2013, "naif"])                              # moins de trois années
        assert naif.loc[2016, "erreur_naif"] == pytest.approx(1.5)

    def test_comparaison_avec_la_prevision_naive(self):
        from pib.evaluate_forecasts import comparaison_naive
        evaluation = pd.DataFrame(dict(horizon=1, erreur_vs_fmi=[1.0, -1.0, 3.0, np.nan],
                                       erreur_naif=[2.0, 2.0, -1.0, 5.0]))
        ligne = comparaison_naive(evaluation).iloc[0]
        assert ligne["observations"] == 3
        assert ligne["rapport_eam"] == pytest.approx((5 / 3) / (5 / 3))
        assert ligne["part_fmi_meilleur"] == pytest.approx(200 / 3, abs=1e-3)

    def test_avril_et_octobre_separes(self):
        from pib.evaluate_forecasts import synthese_par_saison
        evaluation = pd.DataFrame(dict(horizon=0, saison=["F", "S", "S"], erreur_vs_fmi=[0.0, 1.0, 2.0]))
        table = synthese_par_saison(evaluation)
        assert list(table["saison"]) == ["S", "F"]
        assert table.set_index("saison").loc["S", "biais_moyen"] == pytest.approx(1.5)

    def test_croissance_mondiale_contre_le_fmi_seulement(self, tmp_path):
        """
        L'agrégat World est évalué contre sa propre ré-estimation ; la croissance mondiale
        de la Banque Mondiale, pondérée aux taux de change, n'est pas comparable.
        """
        from pib.evaluate_forecasts import lire_base_historique, evaluer_monde
        table = lire_base_historique(str(TestBaseHistoriqueWEO._classeur(tmp_path)))
        monde = evaluer_monde(table)
        assert set(monde["country_code"]) == {"G001"}
        ligne = monde[monde.vintage == "S2018"].iloc[0]
        assert ligne["erreur_vs_fmi"] == pytest.approx(3.9 - 2.8)            # ré-estimation F2020
        assert monde["erreur_vs_bm"].isna().all()


class TestGroupesDeRevenu:
    """Le groupe de revenu de la Banque Mondiale suit chaque pays jusque dans la synthèse."""

    def test_groupe_lu_dans_les_metadonnees(self, monkeypatch):
        items = [{"id": "USA", "region": {"id": "NAC"}, "incomeLevel": {"id": "HIC"}},
                 {"id": "VEN", "region": {"id": "LCN"}, "incomeLevel": {"id": ""}},
                 {"id": "WLD", "region": {"id": "NA"}, "incomeLevel": {"id": "NA"}}]
        monkeypatch.setattr(fetch_historical_gdp, "fetch_worldbank_pages", lambda url, params: ({}, items))
        assert fetch_historical_gdp.fetch_worldbank_country_codes() == {"USA": "HIC", "VEN": "INX"}

    def test_groupe_propage_a_la_prevision_et_a_la_synthese(self):
        historique = _historique()
        historique["income_group"] = historique["country_code"].map({"AAA": "HIC", "BBB": "LMC"})
        unifie = build_unified_dataset(historique, _prevision())
        prevision = unifie[unifie.is_forecast.astype(bool) & (unifie.country_code == "BBB")]
        assert set(prevision["income_group"]) == {"LMC"}
        synthese = compute_country_summary(extend_real_series(unifie, 2024), reference_years(2000, 2024, 2030))
        assert synthese.set_index("country_code").loc["AAA", "income_group"] == "HIC"


class TestLecturesDuBiais:
    """
    Le biais moyen compte chaque pays pour un et suppose les erreurs indépendantes. La
    synthèse le complète d'un biais pondéré par le PIB, d'un intervalle de confiance
    groupé par année visée et d'un biais hors récessions mondiales.
    """

    def test_biais_pondere_par_le_pib(self):
        from pib.evaluate_forecasts import synthese_par_horizon
        evaluation = pd.DataFrame(dict(horizon=1, year=[2010, 2011], erreur_vs_fmi=[1.0, 3.0],
                                       erreur_vs_bm=np.nan, poids_pib=[3.0, 1.0]))
        ligne = synthese_par_horizon(evaluation).iloc[0]
        assert ligne["biais_moyen"] == pytest.approx(2.0)
        assert ligne["biais_pondere_pib"] == pytest.approx(1.5)

    def test_intervalle_groupe_par_annee(self):
        """
        Cent pays, deux années : +2 points pour tous en 2010, 0 en 2011. Supposées
        indépendantes, ces erreurs donneraient un intervalle étroit autour de +1 ; groupées
        par année, il n'y a que deux observations, et l'intervalle inclut zéro.
        """
        from pib.evaluate_forecasts import synthese_par_horizon
        evaluation = pd.DataFrame(dict(horizon=1, year=[2010] * 50 + [2011] * 50,
                                       erreur_vs_fmi=[2.0] * 50 + [0.0] * 50, erreur_vs_bm=np.nan))
        ligne = synthese_par_horizon(evaluation).iloc[0]
        assert ligne["ic95_bas"] == pytest.approx(1 - 1.96, abs=1e-3)
        assert ligne["ic95_haut"] == pytest.approx(1 + 1.96, abs=1e-3)
        assert ligne["annees_visees"] == 2

    def test_biais_hors_recessions_mondiales(self):
        from pib.evaluate_forecasts import synthese_par_horizon
        evaluation = pd.DataFrame(dict(horizon=1, year=[2009, 2019, 2020, 2021],
                                       erreur_vs_fmi=[8.0, 1.0, 9.0, 0.0], erreur_vs_bm=np.nan))
        assert synthese_par_horizon(evaluation).iloc[0]["biais_hors_recessions_mondiales"] == pytest.approx(0.5)

    def test_biais_par_groupe_de_revenu(self):
        from pib.evaluate_forecasts import synthese_par_revenu
        evaluation = pd.DataFrame(dict(horizon=1, year=2010, erreur_vs_fmi=[0.5, 1.5, 2.0],
                                       income_group=["HIC", "LIC", "INX"]))
        table = synthese_par_revenu(evaluation).set_index("income_group")
        assert set(table.index) == {"HIC", "LIC"}             # « non classé » n'est pas un groupe
        assert table.loc["LIC", "biais_moyen"] == pytest.approx(1.5)


class TestErreursDeNiveau:
    """
    PIB prévu et PIB réalisé : les croissances projetées par une édition, enchaînées,
    comparées aux croissances réalisées enchaînées de même.
    """

    @staticmethod
    def _evaluation(realise_h1=1.0, horizons=(0, 1, 2)):
        lignes = [dict(country="France", country_code="FRA", income_group="HIC", vintage="S2020", saison="S",
                       annee_millesime=2020, year=2020 + h, horizon=h, poids_pib=3000.0, valeur=2.0,
                       realise_fmi=(realise_h1 if h == 1 else 1.0), realise_bm=1.0) for h in horizons]
        return pd.DataFrame(lignes)

    def test_croissances_enchainees(self):
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(self._evaluation()).set_index("horizon")
        assert niveaux.loc[0, "erreur_niveau_vs_fmi_pct"] == pytest.approx((1.02 / 1.01 - 1) * 100)
        assert niveaux.loc[2, "erreur_niveau_vs_fmi_pct"] == pytest.approx((1.02 ** 3 / 1.01 ** 3 - 1) * 100)

    def test_realise_manquant_interrompt_l_enchainement(self):
        """Sans croissance réalisée à un an, les niveaux à un et deux ans restent inconnus."""
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(self._evaluation(realise_h1=np.nan)).set_index("horizon")
        assert pd.notna(niveaux.loc[0, "erreur_niveau_vs_fmi_pct"])
        assert niveaux.loc[[1, 2], "erreur_niveau_vs_fmi_pct"].isna().all()
        assert niveaux["erreur_niveau_vs_bm_pct"].notna().all()     # l'autre référence est complète

    def test_horizon_manquant_interrompt_l_enchainement(self):
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(self._evaluation(horizons=(0, 2))).set_index("horizon")
        assert pd.isna(niveaux.loc[2, "erreur_niveau_vs_fmi_pct"])

    def test_synthese_des_niveaux(self):
        from pib.evaluate_forecasts import synthese_niveau
        niveaux = pd.DataFrame(dict(horizon=5, year=2025, poids_pib=[1.0, 1.0, 2.0],
                                    erreur_niveau_vs_fmi_pct=[10.0, -8.0, 2.0], erreur_niveau_vs_bm_pct=np.nan))
        ligne = synthese_niveau(niveaux).iloc[0]
        assert ligne["mediane"] == pytest.approx(2.0)
        assert ligne["moyenne_ponderee_pib"] == pytest.approx(1.5)
        assert ligne["part_trop_haut_5pct"] == pytest.approx(100 / 3, abs=1e-3)   # sorties arrondies
        assert ligne["part_trop_bas_5pct"] == pytest.approx(100 / 3, abs=1e-3)


class TestFourchettesDesProjections:
    """
    Fourchette empirique autour du PIB projeté : erreurs de niveau passées au même
    horizon, parmi les projections de même classe de croissance projetée et de même
    groupe de revenu. Le biais propre à un pays ne se reproduisant pas d'une période à
    l'autre, l'historique du pays n'est plus utilisé.
    """

    @staticmethod
    def _niveaux(cas_par_cellule=120):
        """
        Projections passées à 5 ans : les faibles croissances projetées (10 %) se sont
        réalisées à peu près (erreurs de −5 à +5 %), les fortes (50 %) ont été surestimées
        (erreurs de +10 à +30 %). Tous pays à revenu élevé, éditions 1995 à 2014.
        """
        lignes = []
        for i in range(cas_par_cellule):
            annee = 1995 + i % 20
            lignes.append(dict(country_code=f"F{i}", income_group="HIC", horizon=5, annee_millesime=annee,
                               year=annee + 5, poids_pib=1.0, croissance_prevue_cumulee_pct=10.0,
                               erreur_niveau_vs_fmi_pct=-5.0 + 10.0 * i / (cas_par_cellule - 1)))
            lignes.append(dict(country_code=f"R{i}", income_group="HIC", horizon=5, annee_millesime=annee,
                               year=annee + 5, poids_pib=1.0, croissance_prevue_cumulee_pct=50.0,
                               erreur_niveau_vs_fmi_pct=10.0 + 20.0 * i / (cas_par_cellule - 1)))
        return pd.DataFrame(lignes)

    @staticmethod
    def _synthese():
        return pd.DataFrame(dict(country_code=["LEN", "VIF", "SAN", "TWN"],
                                 country_name=["Lente", "Vive", "Sans projection", "Taïwan"],
                                 income_group=["HIC", "HIC", "HIC", None], GDP_Reel_2031_Billion_USD_2015=100.0))

    @staticmethod
    def _croissance():
        return pd.Series({"LEN": 8.0, "VIF": 55.0, "TWN": 55.0})

    def test_classes_de_croissance(self):
        from pib.evaluate_forecasts import classes_de_croissance
        classes, bornes = classes_de_croissance(pd.Series(range(1, 11), dtype=float))
        assert list(classes) == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        nouvelles, _ = classes_de_croissance(pd.Series([0.0, 100.0, np.nan]), bornes)
        assert list(nouvelles[:2]) == [1, 5] and pd.isna(nouvelles.iloc[2])

    def test_fourchette_selon_la_croissance_projetee(self):
        """Une projection vive reçoit la marge des projections vives : entièrement vers le bas."""
        from pib.evaluate_forecasts import fourchettes_projections
        bandes = fourchettes_projections(self._niveaux(), self._croissance(), self._synthese(), 2031, 2026
                                         ).set_index("country_code")
        assert bandes.loc["VIF", "borne_haute_pct"] < 0
        assert bandes.loc["LEN", "borne_basse_pct"] < 0 < bandes.loc["LEN", "borne_haute_pct"]
        assert (bandes["horizon"] == 5).all()

    def test_replis(self):
        """Sans groupe : la classe seule ; sans croissance projetée : toutes les projections."""
        from pib.evaluate_forecasts import fourchettes_projections
        bandes = fourchettes_projections(self._niveaux(), self._croissance(), self._synthese(), 2031, 2026
                                         ).set_index("country_code")
        assert bandes.loc["VIF", "projections_de_reference"] == "classe × groupe de revenu"
        assert bandes.loc["TWN", "projections_de_reference"] == "classe de croissance"
        assert bandes.loc["SAN", "projections_de_reference"] == "ensemble des projections"

    def test_cellule_trop_petite_repliee_sur_la_classe(self):
        from pib.evaluate_forecasts import fourchettes_projections
        bandes = fourchettes_projections(self._niveaux(cas_par_cellule=40), self._croissance(), self._synthese(),
                                         2031, 2026).set_index("country_code")
        assert bandes.loc["VIF", "projections_de_reference"] == "classe de croissance"

    def test_bornes_tirees_des_erreurs_passees(self):
        """Un niveau passé trop haut de p % ramène le réalisé à 1 / (1 + p) de la projection."""
        from pib.evaluate_forecasts import fourchettes_projections
        vive = fourchettes_projections(self._niveaux(), self._croissance(), self._synthese(), 2031, 2026
                                       ).set_index("country_code").loc["VIF"]
        p10, p90 = vive["erreur_niveau_p10_pct"], vive["erreur_niveau_p90_pct"]
        assert vive["borne_basse_pct"] == pytest.approx((1 / (1 + p90 / 100) - 1) * 100, abs=1e-2)
        assert vive["borne_haute_pct"] == pytest.approx((1 / (1 + p10 / 100) - 1) * 100, abs=1e-2)
        assert vive["GDP_Reel_2031_Bas"] == pytest.approx(100 * (1 + vive["borne_basse_pct"] / 100), abs=1e-2)

    def test_variante_du_seul_groupe_de_revenu(self):
        """Publiée à côté : la même fourchette pour tout le groupe, quelle que soit la croissance projetée."""
        from pib.evaluate_forecasts import fourchettes_projections
        niveaux = self._niveaux()
        bandes = fourchettes_projections(niveaux, self._croissance(), self._synthese(), 2031, 2026
                                         ).set_index("country_code")
        p10, p90 = niveaux["erreur_niveau_vs_fmi_pct"].quantile([0.1, 0.9])
        for code in ("LEN", "VIF"):
            assert bandes.loc[code, "borne_basse_pct_groupe_seul"] == pytest.approx((1 / (1 + p90 / 100) - 1) * 100, abs=1e-2)
            assert bandes.loc[code, "borne_haute_pct_groupe_seul"] == pytest.approx((1 / (1 + p10 / 100) - 1) * 100, abs=1e-2)
        # La méthode retenue distingue, elle, la projection vive de la lente
        assert bandes.loc["VIF", "borne_haute_pct"] < bandes.loc["VIF", "borne_haute_pct_groupe_seul"]
        # Sans groupe : l'ensemble des projections
        assert bandes.loc["TWN", "borne_basse_pct_groupe_seul"] == pytest.approx((1 / (1 + p90 / 100) - 1) * 100, abs=1e-2)

    def test_horizon_sans_historique(self):
        from pib.evaluate_forecasts import fourchettes_projections
        assert fourchettes_projections(self._niveaux(), self._croissance(), self._synthese(), 2033, 2026).empty

    def test_croissance_projetee_par_la_derniere_edition(self):
        """Octobre si l'édition est parue, sinon avril ; un pays dont un horizon manque est écarté."""
        from pib.evaluate_forecasts import croissance_projetee_actuelle
        lignes = [dict(country_code="FRA", annee_millesime=2026, saison=s, horizon=h, valeur=v)
                  for s, v in (("S", 1.0), ("F", 2.0)) for h in range(0, 3)]
        lignes += [dict(country_code="ITA", annee_millesime=2026, saison="F", horizon=h, valeur=1.0) for h in (0, 1)]
        croissance = croissance_projetee_actuelle(pd.DataFrame(lignes), 2026, 2)
        assert croissance["FRA"] == pytest.approx((1.02 ** 3 - 1) * 100)
        assert "ITA" not in croissance.index

    def test_calibration_retrospective(self):
        """
        Les biais par pays s'inversent d'une période à l'autre : les fourchettes tirées de
        l'historique du pays manquent la cible, celles par classe de croissance l'atteignent.
        """
        from pib.evaluate_forecasts import calibration_fourchettes
        rng = np.random.default_rng(0)
        lignes = []
        for pays in range(40):
            biais = 5.0 if pays % 2 else -5.0
            for annee in range(1995, 2020):
                inverse = -biais if annee > 2007 else biais     # le biais du pays s'inverse
                lignes.append(dict(country_code=f"P{pays}", income_group="HIC", horizon=5,
                                   annee_millesime=annee, year=annee + 5, poids_pib=1.0,
                                   croissance_prevue_cumulee_pct=20.0 + pays % 5,
                                   erreur_niveau_vs_fmi_pct=inverse + rng.normal(0, 1)))
        table = calibration_fourchettes(pd.DataFrame(lignes), 5).set_index("methode")
        assert table.loc["historique du pays", "couverture_pct"] < 20
        assert table.loc["classe de croissance × groupe de revenu", "couverture_pct"] > 60
        assert table.loc["classe de croissance × groupe de revenu", "retenue"]


class TestEfficience:
    """Plus le FMI annonce de croissance, plus il surestime : pente de Mincer-Zarnowitz sous 1."""

    def test_pente_et_biais_par_quintile(self):
        from pib.evaluate_forecasts import efficience
        prevu = np.linspace(0, 8, 200)
        evaluation = pd.DataFrame(dict(horizon=1, valeur=prevu, realise_fmi=1.0 + 0.5 * prevu))
        ligne = efficience(evaluation).iloc[0]
        assert ligne["pente"] == pytest.approx(0.5, abs=1e-6)
        assert ligne["constante"] == pytest.approx(1.0, abs=1e-6)
        assert ligne["biais_median_q1"] < ligne["biais_median_q5"]

    def test_croissance_cumulee_projetee(self):
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(TestErreursDeNiveau._evaluation()).set_index("horizon")
        assert niveaux.loc[2, "croissance_prevue_cumulee_pct"] == pytest.approx((1.02 ** 3 - 1) * 100)

    def test_niveaux_par_classe_de_croissance(self):
        from pib.evaluate_forecasts import synthese_niveau_par_croissance
        niveaux = TestFourchettesDesProjections._niveaux()
        table = synthese_niveau_par_croissance(niveaux)
        assert table["mediane"].iloc[-1] > table["mediane"].iloc[0]


class TestPopulationEtParHabitant:
    """
    Population et PIB en volume par habitant, de l'historique à l'horizon : les modèles de
    trafic aérien raisonnent par habitant. La population projetée du FMI est raccordée au
    dernier niveau de la Banque Mondiale, comme les autres séries de niveau.
    """

    def test_population_en_millions(self, unifie):
        ligne = unifie[(unifie.country_code == "AAA") & (unifie.year == 2024)].iloc[0]
        assert ligne["Population_Millions"] == pytest.approx(50 * 1.01 ** 24)

    def test_population_projetee_raccordee(self, unifie_recouvrement):
        """Le FMI compte Pays B 10 % plus haut : le raccord garde sa dynamique, pas son niveau."""
        b = unifie_recouvrement[unifie_recouvrement.country_code == "BBB"].set_index("year")
        assert b.loc[2024, "Facteur_Raccord_Population"] == pytest.approx(1 / 1.10)
        assert b.loc[2030, "Population_Millions"] == pytest.approx(100 * 1.02 ** 30)
        assert b.loc[2030, "Population_FMI_Millions"] == pytest.approx(110 * 1.02 ** 30)

    def test_pib_reel_par_habitant(self, unifie_recouvrement):
        from pib.gdp_pipeline import add_per_capita
        d = add_per_capita(unifie_recouvrement).set_index(["country_code", "year"])
        for annee in (2010, 2030):     # observé, puis projeté (volume chaîné, population raccordée)
            ligne = d.loc[("BBB", annee)]
            assert ligne["GDP_Real_Per_Capita_USD_2015"] == pytest.approx(
                ligne["GDP_Real_Billions_USD"] * 1e9 / (ligne["Population_Millions"] * 1e6))
        assert d.loc[("BBB", 2030), "GDP_Real_Per_Capita_USD_2015"] == pytest.approx(5000 * (1.04 / 1.02) ** 30)

    def test_population_manquante_laisse_la_case_vide(self, unifie_recouvrement):
        from pib.gdp_pipeline import add_per_capita
        d = unifie_recouvrement.copy()
        d.loc[(d.country_code == "AAA") & (d.year == 2026), "Population_Millions"] = np.nan
        d = add_per_capita(d).set_index(["country_code", "year"])
        assert pd.isna(d.loc[("AAA", 2026), "GDP_Real_Per_Capita_USD_2015"])
        assert pd.notna(d.loc[("AAA", 2027), "GDP_Real_Per_Capita_USD_2015"])

    def test_synthese_par_habitant(self, unifie_recouvrement):
        from pib.gdp_pipeline import add_per_capita
        s = compute_country_summary(add_per_capita(unifie_recouvrement),
                                    reference_years(2000, 2024, 2030)).set_index("country_code")
        assert s.loc["BBB", "Population_2030_Millions"] == pytest.approx(100 * 1.02 ** 30)
        assert s.loc["BBB", "CAGR_Population_Prevision_2024_2030_Pct"] == pytest.approx(2.0)
        assert s.loc["BBB", "CAGR_Reel_Par_Habitant_Prevision_2024_2030_Pct"] == pytest.approx((1.04 / 1.02 - 1) * 100)
        assert s.loc["AAA", "GDP_Reel_Par_Habitant_2000_USD_2015"] == pytest.approx(20000.0)


class TestScenariosPourLeTrafic:
    """
    Scénarios de PIB par habitant et de population pour le projet trafic : fourchettes à
    chaque horizon jusqu'à celui du FMI, puis croissance de long terme de l'OCDE et
    population de l'ONU.
    """

    @staticmethod
    def _entrees():
        unifie = pd.DataFrame([dict(country_code="AAA", country_name="Pays A", income_group="HIC", is_aggregate=False,
                                    year=a, is_forecast=a > 2024, GDP_Real_Per_Capita_USD_2015=v, Population_Millions=10.0,
                                    GDP_Per_Capita_USD=v * 1.5)
                               for a, v in ((2023, 98.0), (2024, 100.0), (2025, 102.0), (2026, 104.0))])
        bandes = pd.DataFrame(dict(country_code="AAA", year=[2025, 2026], erreur_niveau_mediane_pct=[5.0, 10.0],
                                   borne_basse_pct=[-10.0, -20.0], borne_haute_pct=[5.0, 10.0],
                                   erreur_niveau_mediane_si_crise_mondiale_pct=[np.nan, 25.0]))
        ocde = pd.DataFrame([dict(zone="AAA", scenario=s, year=a, valeur=100 * (1 + g) ** (a - 2026))
                             for s, g in (("BAU1", 0.01), ("ET3", 0.005), ("BAU2", 0.02)) for a in range(2026, 2029)])
        wpp = pd.DataFrame([dict(country_code="AAA", year=a, variante=v, population=9.0 * 1.02 ** (a - 2024) * r)
                            for a in range(2023, 2029) for v, r in (("centrale", 1.0), ("basse", 0.9), ("haute", 1.1))])
        return unifie, bandes, ocde, wpp

    def test_zone_de_croissance(self):
        from pib.scenarios import zone_de_croissance
        zones = {"CAN", "A2", "F6", "W"}
        assert zone_de_croissance("CAN", "NAC", zones) == ("CAN", "pays")
        assert zone_de_croissance("NGA", "SSF", zones) == ("F6", "région")
        assert zone_de_croissance("XXX", None, zones) == ("W", "monde")

    def test_scenarios_jusqu_a_l_horizon_du_fmi(self):
        from pib.scenarios import construire_scenarios
        table, _ = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028)
        t = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert t[(2026, "central_fmi")] == pytest.approx(104.0)
        assert t[(2026, "central_corrige")] == pytest.approx(104.0 / 1.10)
        assert t[(2026, "bas")] == pytest.approx(104.0 * 0.8)
        assert t[(2026, "haut")] == pytest.approx(104.0 * 1.1)
        assert t[(2026, "crise_mondiale")] == pytest.approx(104.0 / 1.25)
        assert t[(2025, "crise_mondiale")] == pytest.approx(102.0 / 1.05)    # sans erreur de crise : médiane générale
        assert t.xs(2024, level="year").nunique() == 1                       # le passé observé est commun

    def test_croissance_de_long_terme_et_population(self):
        """Au-delà : croissance de l'OCDE (centrale, la plus faible, la plus forte) ; population de l'ONU."""
        from pib.scenarios import construire_scenarios
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028)
        t = table.set_index(["year", "scenario"])
        pib = t["pib_reel_par_habitant_usd_2015"]
        assert pib[(2028, "central_fmi")] == pytest.approx(104.0 * 1.01 ** 2)
        assert pib[(2028, "bas")] == pytest.approx(104.0 * 0.8 * 1.005 ** 2)
        assert pib[(2028, "haut")] == pytest.approx(104.0 * 1.1 * 1.02 ** 2)
        assert t.loc[(2028, "central_fmi"), "population_millions_centrale"] == pytest.approx(10.0 * 1.02 ** 2)
        assert t.loc[(2028, "central_fmi"), "population_millions_basse"] == pytest.approx(10.0 * 1.02 ** 2 * 0.9)
        assert t.loc[(2024, "central_fmi"), "population_millions_basse"] == pytest.approx(10.0)
        assert fiches.iloc[0]["bornes_long_terme"] == "scénarios de l'OCDE ET3 et BAU2"
        assert t.loc[(2028, "central_fmi"), "periode"] == "long terme"

    @staticmethod
    def _bandes_long_terme(groupe="HIC"):
        h = np.arange(0, 41)
        return pd.DataFrame({"groupe": groupe, "horizon": h, "p10_lisse": -1.0 * h, "p90_lisse": 2.0 * h})

    def test_bornes_de_long_terme_elargies(self):
        """Au-delà de l'horizon du FMI : fourchette du pays élargie comme les erreurs passées de son groupe."""
        from pib.scenarios import construire_scenarios
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028,
                                             bandes_long_terme=self._bandes_long_terme())
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        central = {2027: 104.0 * 1.01, 2028: 104.0 * 1.01 ** 2}
        # Horizon du FMI 2026 = horizon 5 ; 2027 = 6 ; 2028 = 7
        assert pib[(2027, "bas")] == pytest.approx(central[2027] * 0.8 * 1.10 / 1.12)
        assert pib[(2028, "bas")] == pytest.approx(central[2028] * 0.8 * 1.10 / 1.14)
        assert pib[(2028, "haut")] == pytest.approx(central[2028] * 1.1 * 0.95 / 0.93)
        assert pib[(2026, "bas")] == pytest.approx(104.0 * 0.8)                 # continuité à l'horizon du FMI
        assert pib[(2028, "central_fmi")] == pytest.approx(central[2028])        # centraux inchangés
        assert fiches.iloc[0]["bornes_long_terme"] == "erreurs passées du FMI prolongé (HIC)"

    def test_variante_du_seul_groupe_elargie_de_meme(self):
        """Les bornes du seul groupe de revenu suivent la même règle : continuité, puis élargissement."""
        from pib.scenarios import construire_scenarios
        unifie, bandes, ocde, wpp = self._entrees()
        bandes = bandes.assign(borne_basse_pct_groupe_seul=[-15.0, -25.0], borne_haute_pct_groupe_seul=[8.0, 12.0])
        table, _ = construire_scenarios(unifie, bandes, ocde, wpp, regions={}, annee_fin=2028,
                                        bandes_long_terme=self._bandes_long_terme())
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert pib[(2026, "bas_groupe_seul")] == pytest.approx(104.0 * 0.75)
        assert pib[(2026, "haut_groupe_seul")] == pytest.approx(104.0 * 1.12)
        assert pib[(2028, "bas_groupe_seul")] == pytest.approx(104.0 * 1.01 ** 2 * 0.75 * 1.10 / 1.14)
        assert pib[(2028, "haut_groupe_seul")] == pytest.approx(104.0 * 1.01 ** 2 * 1.12 * 0.95 / 0.93)

    def test_variante_absente_reprend_les_bornes_retenues(self):
        from pib.scenarios import construire_scenarios
        table, _ = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028)
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert pib[(2028, "bas_groupe_seul")] == pytest.approx(pib[(2028, "bas")])
        assert pib[(2028, "haut_groupe_seul")] == pytest.approx(pib[(2028, "haut")])

    def test_elargir_fige_le_milieu_et_impose_un_plancher(self):
        from pib.scenarios import elargir, Z80, ECART_TYPE_ANNUEL_MSW
        h = np.array([6, 7, 8, 9])
        lb, lh = np.array([-0.30, -0.40, -0.50, -0.60]), np.array([0.30, 0.30, 0.30, 0.30])
        bas, haut = elargir(lb, lh, h, h_ajuste=7)
        milieu, demi = (bas + haut) / 2, (haut - bas) / 2
        assert milieu.tolist() == pytest.approx([0.0, -0.05, -0.05, -0.05])     # figé au-delà de 7
        assert demi.tolist() == pytest.approx([0.30, 0.35, 0.40, 0.45])          # largeurs conservées
        # Fourchette étroite : le plancher l'emporte
        bas, haut = elargir(np.array([-0.01]), np.array([0.01]), np.array([20]), h_ajuste=None)
        assert ((haut - bas) / 2)[0] == pytest.approx(Z80 * ECART_TYPE_ANNUEL_MSW * 20)
        assert ECART_TYPE_ANNUEL_MSW == pytest.approx(0.0108, abs=1e-4)

    def test_variante_elargie_des_pays_riches(self):
        """Identique aux bornes retenues jusqu'à l'horizon du FMI, élargie ensuite pour un pays riche."""
        from pib.scenarios import construire_scenarios, elargir
        bandes_lt = self._bandes_long_terme().assign(annees_edition=lambda d: np.where(d["horizon"] <= 6, 12, 5))
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028, bandes_long_terme=bandes_lt)
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert pib[(2026, "bas_elargi")] == pytest.approx(pib[(2026, "bas")])
        assert pib[(2026, "haut_elargi")] == pytest.approx(pib[(2026, "haut")])
        central = np.array([pib[(a, "central_fmi")] for a in (2027, 2028)])
        bas, haut = elargir(np.log(np.array([pib[(a, "bas")] for a in (2027, 2028)]) / central),
                            np.log(np.array([pib[(a, "haut")] for a in (2027, 2028)]) / central), np.array([6, 7]), 6)
        assert [pib[(a, "bas_elargi")] for a in (2027, 2028)] == pytest.approx(list(central * np.exp(bas)))
        assert [pib[(a, "haut_elargi")] for a in (2027, 2028)] == pytest.approx(list(central * np.exp(haut)))
        # Le milieu de 2028 reprend celui de 2027, dernier horizon ajusté
        milieu = [np.log(pib[(a, "bas_elargi")] * pib[(a, "haut_elargi")]) / 2 - np.log(pib[(a, "central_fmi")]) for a in (2027, 2028)]
        assert milieu[1] == pytest.approx(milieu[0])
        assert bool(fiches.iloc[0]["bornes_elargies"])

    def test_variante_elargie_reprend_les_bornes_hors_pays_riches(self):
        from pib.scenarios import construire_scenarios
        unifie, bandes, ocde, wpp = self._entrees()
        table, fiches = construire_scenarios(unifie.assign(income_group="LIC"), bandes, ocde, wpp, regions={},
                                             annee_fin=2028, bandes_long_terme=self._bandes_long_terme("tous"))
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert pib[(2028, "bas_elargi")] == pytest.approx(pib[(2028, "bas")])
        assert pib[(2028, "haut_elargi")] == pytest.approx(pib[(2028, "haut")])
        assert not bool(fiches.iloc[0]["bornes_elargies"])

    def test_variantes_de_population_calibrees(self):
        """Bornes calibrées de `pib.population` appliquées à la centrale ; le passé observé n'en a pas."""
        from pib.scenarios import construire_scenarios
        calibrees = pd.DataFrame({"country_code": "AAA", "year": range(2024, 2029),
                                  "calibree_basse": 0.85, "calibree_haute": 1.2})
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028, bornes_population=calibrees)
        t = table[table["scenario"] == "central_fmi"].set_index("year")
        assert t.loc[2028, "population_millions_basse_calibree"] == pytest.approx(t.loc[2028, "population_millions_centrale"] * 0.85)
        assert t.loc[2028, "population_millions_haute_calibree"] == pytest.approx(t.loc[2028, "population_millions_centrale"] * 1.2)
        assert t.loc[2024, "population_millions_haute_calibree"] == pytest.approx(10.0)
        assert bool(fiches.iloc[0]["population_bornes_calibrees"])

    def test_sans_calibration_les_variantes_de_l_onu(self):
        from pib.scenarios import construire_scenarios
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028)
        t = table[table["scenario"] == "central_fmi"].set_index("year")
        assert t.loc[2028, "population_millions_basse_calibree"] == pytest.approx(t.loc[2028, "population_millions_basse"])
        assert t.loc[2028, "population_millions_haute_calibree"] == pytest.approx(t.loc[2028, "population_millions_haute"])
        assert not bool(fiches.iloc[0]["population_bornes_calibrees"])

    def test_groupe_inconnu_prend_tous_les_pays(self):
        from pib.scenarios import construire_scenarios
        table, fiches = construire_scenarios(*self._entrees(), regions={}, annee_fin=2028,
                                             bandes_long_terme=self._bandes_long_terme("tous"))
        assert fiches.iloc[0]["bornes_long_terme"] == "erreurs passées du FMI prolongé (tous)"
        pib = table.set_index(["year", "scenario"])["pib_reel_par_habitant_usd_2015"]
        assert pib[(2028, "bas")] == pytest.approx(104.0 * 1.01 ** 2 * 0.8 * 1.10 / 1.14)


class TestMiroir:
    """Copie vers un dossier partagé : seulement ce qui a changé, jamais de suppression."""

    def test_copie_ce_qui_change_et_ne_supprime_rien(self, tmp_path):
        import miroir
        src, dst = tmp_path / "depot", tmp_path / "partage"
        (src / "data" / "processed").mkdir(parents=True)
        (src / "a.txt").write_text("nouveau")
        (src / "b.txt").write_text("identique")
        (src / "data" / "processed" / "c.csv").write_text("modifié")
        (dst / "data" / "processed").mkdir(parents=True)
        (dst / "b.txt").write_text("identique")
        (dst / "data" / "processed" / "c.csv").write_text("ancien")
        (dst / "garde.csv").write_text("laissé exprès")
        bilan = miroir.copier(["a.txt", "b.txt", "data/processed/c.csv"], str(src), str(dst))
        assert sorted(bilan["copies"]) == ["a.txt", "data/processed/c.csv"]
        assert bilan["identiques"] == 1 and bilan["erreurs"] == []
        assert (dst / "data" / "processed" / "c.csv").read_text() == "modifié"
        assert (dst / "garde.csv").read_text() == "laissé exprès"

    def test_simulation_ne_copie_rien(self, tmp_path):
        import miroir
        src, dst = tmp_path / "depot", tmp_path / "partage"
        src.mkdir(), dst.mkdir()
        (src / "a.txt").write_text("x")
        assert miroir.copier(["a.txt"], str(src), str(dst), simulation=True)["copies"] == ["a.txt"]
        assert not (dst / "a.txt").exists()


class TestPopulationONU:
    """
    Erreurs passées des projections de population de l'ONU, et bornes calibrées pour
    contenir 80 % de ces erreurs.
    """

    @staticmethod
    def _actuelle():
        """Révision actuelle : deux pays, estimés jusqu'en 2023, projetés ensuite avec bornes."""
        lignes = []
        for code, loc, base in (("AAA", 1, 6000.0), ("BBB", 2, 100.0), ("CCC", 3, 5000.0)):
            for a in range(2000, 2027):
                med = base * (1.01 ** (a - 2000))
                lignes.append(dict(country_code=code, LocID=loc, year=a, mediane=med,
                                   basse=med * 0.95 if a > 2024 else med, haute=med * 1.04 if a > 2024 else med))
        return pd.DataFrame(lignes)

    def test_erreurs_horizon_signe_et_taille(self):
        from pib.population import erreurs, GRANDS, PETITS
        act = self._actuelle()
        estimee = act.set_index(["LocID", "year"])["mediane"]
        revision = pd.DataFrame([dict(LocID=loc, year=a, population=estimee[(loc, a)] * (1.10 if loc == 1 else 0.95))
                                 for loc in (1, 2) for a in range(2000, 2026)]
                                + [dict(LocID=3, year=a, population=5200.0 if a == 2000 else 4000.0) for a in range(2000, 2026)])
        e = erreurs({2000: revision}, act).set_index(["country_code", "year"])
        assert e.loc[("AAA", 2003), "erreur_pct"] == pytest.approx(10.0)      # projeté au-dessus : erreur positive
        assert e.loc[("BBB", 2003), "erreur_pct"] == pytest.approx(-5.0)
        assert e.loc[("AAA", 2003), "horizon"] == 3
        assert e.loc[("AAA", 2003), "classe_taille"] == GRANDS               # 6,6 millions donnés en 2000
        assert e.loc[("BBB", 2003), "classe_taille"] == PETITS
        assert e.loc[("CCC", 2010), "classe_taille"] == GRANDS               # taille de l'année de la révision
        assert e.index.get_level_values("year").min() == 2001                 # après la révision
        assert e.index.get_level_values("year").max() == 2023                 # jusqu'à la dernière année estimée

    def test_ecart_en_demi_largeurs(self):
        from pib.population import ecarts_normalises
        e = pd.DataFrame(dict(revision=2000, country_code=["AAA", "BBB"], year=2010, horizon=1, classe_taille="x",
                              erreur_pct=[-10.0, 2.0]))
        bornes = pd.DataFrame(dict(country_code=["AAA", "BBB"], horizon=1, onu_bas_pct=[-4.0, -4.0], onu_haut_pct=[5.0, 5.0]))
        m = ecarts_normalises(e, bornes).set_index("country_code")
        # Projeté 10 % sous le réalisé : réalisé au-dessus, côté haut
        assert m.loc["AAA", "z"] == pytest.approx(-np.log(0.9) / np.log(1.05))
        assert not m.loc["AAA", "dedans"]
        assert m.loc["BBB", "z"] == pytest.approx(-np.log(1.02) / -np.log(0.96))
        assert m.loc["BBB", "dedans"]

    @staticmethod
    def _z(valeurs):
        return pd.DataFrame([dict(classe_taille="c", tiers_largeur="moyenne", horizon=h, revision=r, z=z, dedans=abs(z) <= 1)
                             for h in range(1, 11) for r in range(2000, 2010, 2) for z in valeurs])

    def test_multiplicateurs_portent_la_couverture_a_80(self):
        from pib.population import multiplicateurs
        k = multiplicateurs(self._z(np.linspace(-2, 3, 101))).set_index("horizon")
        assert k.loc[5, "k_bas_observe"] == pytest.approx(1.5)
        assert k.loc[5, "k_haut_observe"] == pytest.approx(2.5)
        assert k.loc[30, "k_bas"] == pytest.approx(1.5, abs=1e-6)               # extrapolé, constant
        assert k.loc[30, "k_haut"] == pytest.approx(2.5, abs=1e-6)
        assert k.loc[5, "part_dans_bornes_calibrees"] == pytest.approx(81 / 101)

    def test_tiers_de_largeur_des_bornes_de_l_onu(self):
        from pib.population import bornes_actuelles
        def tiers(largeurs):
            act = pd.DataFrame([dict(country_code=c, LocID=i, year=2030, mediane=100.0, basse=100.0 - w, haute=100.0 + w)
                                for i, (c, w) in enumerate(largeurs.items())])
            return bornes_actuelles(act).set_index("country_code")["tiers_largeur"].to_dict()
        # Quatre largeurs : rangs centrés, (rang − ½) / n
        assert tiers({"AAA": 1.0, "BBB": 5.0, "CCC": 20.0, "DDD": 8.0}) == {
            "AAA": "étroite", "BBB": "moyenne", "DDD": "moyenne", "CCC": "large"}
        # Ex aequo : même tiers
        assert tiers({"AAA": 1.0, "BBB": 5.0, "CCC": 20.0, "DDD": 5.0}) == {
            "AAA": "étroite", "BBB": "moyenne", "DDD": "moyenne", "CCC": "large"}

    def test_multiplicateur_propre_a_chaque_tiers(self):
        from pib.population import multiplicateurs
        m = pd.concat([self._z(np.linspace(-2, 3, 101)).assign(tiers_largeur="étroite"),
                       self._z(np.linspace(-1.2, 1.5, 101)).assign(tiers_largeur="large")])
        k = multiplicateurs(m).set_index(["tiers_largeur", "horizon"])
        assert k.loc[("étroite", 5), "k_haut"] == pytest.approx(2.5, abs=1e-6)
        assert k.loc[("large", 5), "k_haut"] == pytest.approx(1.23, abs=1e-6)

    def test_jamais_plus_etroit_que_l_onu(self):
        from pib.population import multiplicateurs
        k = multiplicateurs(self._z(np.linspace(-0.5, 3, 101))).set_index("horizon")
        assert k.loc[5, "k_bas_observe"] < 1
        assert (k["k_bas"] >= 1).all() and k.loc[5, "k_bas"] == pytest.approx(1.0)

    def test_bornes_par_pays_selon_le_tiers_de_largeur(self):
        from pib.population import bornes_par_pays, GRANDS
        act = pd.DataFrame([dict(country_code=c, LocID=i, year=a, mediane=6000.0,
                                 basse=6000.0 * (1 - w) if a > 2024 else 6000.0, haute=6000.0 * (1 + w) if a > 2024 else 6000.0)
                            for i, (c, w) in enumerate((("AAA", 0.01), ("BBB", 0.05), ("CCC", 0.20))) for a in (2024, 2025)])
        calibration = pd.DataFrame(dict(classe_taille=GRANDS, tiers_largeur=["étroite", "moyenne", "large"], horizon=1,
                                        k_bas=1.0, k_haut=[3.0, 2.0, 1.5]))
        b = bornes_par_pays(act, calibration).set_index("country_code")
        assert b.loc["AAA", "calibree_haute"] == pytest.approx(1.01 ** 3.0)
        assert b.loc["BBB", "calibree_haute"] == pytest.approx(1.05 ** 2.0)
        assert b.loc["CCC", "calibree_haute"] == pytest.approx(1.20 ** 1.5)

    def test_bornes_par_pays(self):
        from pib.population import bornes_par_pays, GRANDS, PETITS
        calibration = pd.DataFrame(dict(classe_taille=[GRANDS, PETITS], tiers_largeur="moyenne", horizon=1,
                                        k_bas=[2.0, 1.0], k_haut=[3.0, 1.0]))     # bornes égales : tiers du milieu
        b = bornes_par_pays(self._actuelle(), calibration).set_index("country_code")
        assert b.loc["AAA", "year"] == 2025
        assert b.loc["AAA", "calibree_basse"] == pytest.approx(0.95 ** 2)
        assert b.loc["AAA", "calibree_haute"] == pytest.approx(1.04 ** 3)
        assert b.loc["BBB", "calibree_haute"] == pytest.approx(1.04)          # petit pays : k = 1


class TestTiragesConjoints:
    """
    Trajectoires conjointes de tous les pays : chaque tirage rejoue une édition passée,
    chaque pays garde exactement sa fourchette, la dépendance entre pays est celle des rangs.
    """

    EDITIONS = [f"{s}{a}" for a in range(2000, 2010) for s in ("S", "F")]
    PAYS = ["AAA", "BBB", "CCC", "DDD"]

    @classmethod
    def _entrees(cls, propre: dict = None):
        """
        Erreurs passées = choc commun de l'édition + écart propre au pays ; tous les cas dans
        une seule cellule (« ensemble »). Fourchettes aux horizons 0 et 1 (2026, 2027),
        scénarios jusqu'en 2029 avec une fourchette qui s'élargit.
        """
        rng = np.random.default_rng(0)
        choc = dict(zip(cls.EDITIONS, rng.normal(0, 5, len(cls.EDITIONS))))
        choc["F2008"] = 30.0                                  # la pire édition, pour tous
        propre = propre or {}
        niveaux = pd.DataFrame([dict(country_code=c, vintage=v, annee_millesime=int(v[1:]), horizon=h,
                                     income_group="HIC" if c < "C" else "LIC",
                                     croissance_prevue_cumulee_pct=2.0 + h,
                                     erreur_niveau_vs_fmi_pct=choc[v] + propre.get(c, 0.0) + rng.normal(0, 1))
                                for c in cls.PAYS for v in cls.EDITIONS for h in (0, 1)])
        bandes = pd.DataFrame([dict(country_code=c, income_group="HIC" if c < "C" else "LIC", horizon=h,
                                    year=2026 + h, classe_de_croissance=np.nan) for c in cls.PAYS for h in (0, 1)])
        central = {2026: 100.0, 2027: 102.0, 2028: 104.0, 2029: 106.0}
        largeur = {2026: 0.05, 2027: 0.10, 2028: 0.20, 2029: 0.30}
        scenarios = pd.DataFrame([dict(country_code=c, year=a, scenario=s, population_millions_centrale=10.0,
                                       pib_reel_par_habitant_usd_2015=central[a] * f)
                                  for c in cls.PAYS for a in central
                                  for s, f in (("central_fmi", 1.0), ("bas", np.exp(-largeur[a])),
                                               ("haut", np.exp(largeur[a] / 2)))])
        return niveaux, bandes, scenarios

    def test_niveaux_de_quantile(self):
        from pib.tirages import niveaux_de_quantile
        u = pd.DataFrame({"S2000": [0.9, 0.1], "F2000": [0.2, 0.5], "S2001": [0.5, 0.3]}, index=["AAA", "BBB"])
        n = niveaux_de_quantile(u)
        assert n.loc["AAA"].tolist() == pytest.approx([5 / 6, 1 / 6, 3 / 6])
        assert n.loc["BBB"].tolist() == pytest.approx([1 / 6, 5 / 6, 3 / 6])

    def test_chaque_pays_garde_sa_fourchette(self):
        from pib.tirages import tirages, niveaux_de_quantile
        niveaux, bandes, scenarios = self._entrees(propre={"AAA": 20.0})      # AAA toujours surestimé
        t = tirages(niveaux, bandes, scenarios, 2029, pays_min=1)
        passe = niveaux[niveaux["horizon"] == 1]["erreur_niveau_vs_fmi_pct"].to_numpy()
        n = len(self.EDITIONS)
        attendu = np.sort(100 / (1 + np.quantile(passe, (np.arange(1, n + 1) - 0.5) / n) / 100))
        for c in self.PAYS:
            tire = t[(t["country_code"] == c) & (t["year"] == 2027)].sort_values("pib_reel_par_habitant_usd_2015")
            # Le biais propre de AAA ne déplace pas sa fourchette : seuls les rangs comptent
            assert np.sort(tire["pib_reel_par_habitant_usd_2015"].to_numpy() / 102.0 * 100) == pytest.approx(attendu)

    def test_le_choc_commun_est_conserve(self):
        from pib.tirages import tirages
        niveaux, bandes, scenarios = self._entrees()
        t = tirages(niveaux, bandes, scenarios, 2029, pays_min=1)
        pire = t[t["year"] == 2027].loc[lambda d: d.groupby("country_code")["pib_reel_par_habitant_usd_2015"].idxmin()]
        assert set(pire["tirage"]) == {"F2008"}

    def test_position_constante_au_dela_de_l_horizon(self):
        from pib.tirages import tirages
        niveaux, bandes, scenarios = self._entrees()
        t = tirages(niveaux, bandes, scenarios, 2029, pays_min=1).set_index(["tirage", "country_code", "year"])
        largeur = {2027: 0.10, 2029: 0.30}
        central = {2027: 102.0, 2029: 106.0}
        for tirage in ("F2008", "S2003"):
            z = {a: (np.log(t.loc[(tirage, "CCC", a), "pib_reel_par_habitant_usd_2015"] / central[a]) + largeur[a] / 4)
                    / (largeur[a] * 3 / 4) for a in (2027, 2029)}
            assert z[2029] == pytest.approx(z[2027])

    def test_pays_absent_prend_la_mediane_de_son_groupe(self):
        from pib.tirages import positions
        passe = pd.DataFrame(dict(vintage=["S2000"] * 3 + ["F2000"] * 3, country_code=["AAA", "BBB", "CCC"] * 2,
                                  u=[0.9, 0.7, 0.2, 0.1, 0.3, np.nan]))
        groupes = pd.Series({"AAA": "HIC", "BBB": "HIC", "CCC": "LIC", "DDD": "HIC", "EEE": "UMC"})
        u = positions(passe.dropna(), ["S2000", "F2000"], groupes)
        assert u.loc["DDD", "S2000"] == pytest.approx(0.8)            # médiane de AAA et BBB
        assert u.loc["CCC", "F2000"] == pytest.approx(0.2)            # seul LIC absent : médiane de tous
        assert u.loc["EEE", "S2000"] == pytest.approx(0.7)            # groupe sans membre : médiane de tous

    @staticmethod
    def _population(revisions=(1998, 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2015, 2017)):
        """Positions passées : un choc commun par révision, plus un écart propre ; scénarios avec bornes calibrées."""
        rng = np.random.default_rng(1)
        choc = dict(zip(revisions, rng.normal(0, 1, len(revisions))))
        choc[2008] = 5.0                                          # la révision la plus basse pour tous
        positions = pd.DataFrame([dict(revision=r, country_code=c, classe_taille="x", z=choc[r] + 0.1 * rng.normal())
                                  for r in revisions for c in ("AAA", "BBB", "CCC")])
        scenarios = pd.DataFrame([dict(country_code=c, year=a, scenario="central_fmi", population_millions_centrale=10.0,
                                       population_millions_basse_calibree=10.0 * np.exp(-0.01 * (a - 2025)),
                                       population_millions_haute_calibree=10.0 * np.exp(0.02 * (a - 2025)))
                                  for c in ("AAA", "BBB", "CCC") for a in (2026, 2030, 2050)])
        return positions, scenarios

    def test_affectation_des_revisions_par_blocs(self):
        from pib.tirages import affecter_revisions
        a = affecter_revisions(self.EDITIONS, [1998, 2000])
        assert [a[e] for e in ("S2000", "F2004", "S2005", "F2009")] == [1998, 1998, 2000, 2000]
        assert pd.Series(a).value_counts().tolist() == [10, 10]

    def test_population_garde_les_bornes_calibrees_et_le_choc_commun(self):
        from pib.tirages import niveaux_population, affecter_revisions, population_tirages
        positions, scenarios = self._population()
        niveaux = niveaux_population(positions, pd.Index(["AAA", "BBB", "CCC", "DDD"]))
        # Absent partout : position médiane, ex aequo départagés dans l'ordre ; la fourchette reste exacte
        assert sorted(niveaux.loc["DDD"]) == pytest.approx([(k - 0.5) / 10 for k in range(1, 11)])
        editions = [f"{s}{a}" for a in range(1990, 2020) for s in ("S", "F")]
        p = population_tirages(niveaux.drop(index="DDD"), affecter_revisions(editions, list(niveaux.columns)),
                               scenarios, [2026, 2030, 2050])
        p = p.merge(scenarios, on=["country_code", "year"])
        assert (p["population_millions"] < p["population_millions_basse_calibree"] * (1 - 1e-9)).groupby(p["country_code"]).mean().tolist() == pytest.approx([0.1] * 3)
        assert (p["population_millions"] > p["population_millions_haute_calibree"] * (1 + 1e-9)).groupby(p["country_code"]).mean().tolist() == pytest.approx([0.1] * 3)
        # La révision au choc commun le plus fort donne à tous la population la plus haute
        haut = p[p["year"] == 2050].loc[lambda d: d.groupby("country_code")["population_millions"].idxmax()]
        assert set(haut["revision_onu"]) == {2008}
        # Position relative constante d'une année à l'autre
        x = p[(p["tirage"] == "S2000") & (p["country_code"] == "AAA")].set_index("year")
        rel = lambda a: np.log(x.loc[a, "population_millions"] / 10.0) / np.log(x.loc[a, "population_millions_haute_calibree"] / 10.0
                                                                               if x.loc[a, "population_millions"] >= 10.0 else
                                                                               10.0 / x.loc[a, "population_millions_basse_calibree"])
        assert abs(rel(2030)) == pytest.approx(abs(rel(2050)))

    def test_pib_par_habitant_suit_la_population_tiree(self):
        """Le PIB total du tirage ne dépend pas de la population : le PIB par habitant, si."""
        from pib.tirages import par_habitant
        scenarios = pd.DataFrame(dict(country_code="AAA", year=[2030, 2050], scenario="central_fmi",
                                      population_millions_centrale=[10.0, 12.0]))
        t = pd.DataFrame(dict(tirage="S2000", country_code="AAA", year=[2030, 2050],
                              pib_reel_par_habitant_usd_2015=[50_000.0, 60_000.0], population_millions=[11.0, 9.0]))
        r = par_habitant(t, scenarios).set_index("year")
        assert r.loc[2030, "pib_reel_milliards_usd_2015"] == pytest.approx(50_000.0 * 10.0 / 1000)
        assert r.loc[2030, "pib_reel_par_habitant_usd_2015"] == pytest.approx(50_000.0 * 10.0 / 11.0)
        assert r.loc[2050, "pib_reel_par_habitant_usd_2015"] == pytest.approx(60_000.0 * 12.0 / 9.0)

    def test_intervalle_tire_les_annees_d_edition(self):
        from pib.tirages import intervalle_des_quantiles
        constant = pd.Series(95.0, index=self.EDITIONS)
        assert intervalle_des_quantiles(constant, 0.1, tirages=50) == pytest.approx((95.0, 95.0))
        # Avril et octobre d'une même année tirés ensemble : autant de 110 que de 90, médiane 100
        total = pd.Series([110.0 if e.startswith("S") else 90.0 for e in self.EDITIONS], index=self.EDITIONS)
        assert intervalle_des_quantiles(total, 0.5, tirages=200) == pytest.approx((100.0, 100.0))


class TestGroupesDeRevenuALEdition:
    """
    Groupe de revenu connu à la date de l'édition : le groupe actuel rangerait parmi les pays
    riches ceux qui le sont devenus en dépassant les prévisions.
    """

    def test_lecture_du_classement_historique(self, tmp_path):
        from pib.groupes_revenu import lire, FEUILLE
        lignes = [[None] * 5 for _ in range(11)]
        lignes[4] = [None, "Bank's fiscal year:", "FY89", "FY99", "FY12"]
        lignes += [["POL", "Poland", "LM", "UM", "H"], ["YEM", "Yemen", "L", "LM*", ".."], ["xx", None, "H", "H", "H"]]
        chemin = tmp_path / "oghist.xlsx"
        pd.DataFrame(lignes).to_excel(chemin, sheet_name=FEUILLE, header=False, index=False)
        g = lire(str(chemin)).set_index(["country_code", "exercice"])["groupe"]
        assert g[("POL", 1989)] == "LMC" and g[("POL", 1999)] == "UMC" and g[("POL", 2012)] == "HIC"
        assert g[("YEM", 1999)] == "LMC"                    # astérisque retiré
        assert ("YEM", 2012) not in g.index                 # « .. » : pas de classement
        assert "xx" not in g.index.get_level_values(0)

    def test_groupe_a_l_edition(self):
        from pib.groupes_revenu import a_l_edition
        groupes = pd.DataFrame({"country_code": "POL", "exercice": [2011, 2012, 2013],
                                "groupe": ["UMC", "UMC", "HIC"]})
        cas = pd.DataFrame({"country_code": ["POL", "POL", "POL", "ZZZ"], "income_group": "HIC",
                            "vintage": ["S2012", "F2012", "S2013", "S2012"], "annee_millesime": [2012, 2012, 2013, 2012]})
        r = a_l_edition(cas, groupes)
        # Avril 2012 : exercice 2012 ; octobre 2012 : exercice 2013 ; pays sans historique : groupe actuel
        assert r["income_group"].tolist() == ["UMC", "HIC", "HIC", "HIC"]
        assert cas["income_group"].tolist() == ["HIC"] * 4          # l'original est intact
        assert a_l_edition(cas, None) is cas                        # sans classement : inchangé


class TestEcartParSousEchantillon:
    """L'écart entre méthodes se vérifie sur des sous-échantillons : sans la Chine et l'Inde, par période."""

    def test_ecart_et_sous_echantillons(self):
        from pib import calibration as c
        lignes = []
        riches = ("FRA", "DEU", "USA", "JPN", "GBR", "ITA", "CAN", "ESP")
        for code in ("CHN", "IND") + riches:
            for annee in range(1990, 2020):
                for methode, score in ((c.METHODE_RETENUE, 10.0 if code in ("CHN", "IND") else 5.0), ("groupe de revenu", 5.0)):
                    lignes.append(dict(country_code=code, annee_millesime=annee, year=annee + 5, methode=methode,
                                       income_group="HIC" if code in riches else "UMC",
                                       poids_pib=10.0 if code in ("CHN", "IND") else 1.0,
                                       score_intervalle=score, couvert=True, bas=-1.0, haut=1.0))
        # Les autres méthodes sont présentes aussi, pour que les cas soient communs
        p = pd.DataFrame(lignes)
        autres = [m for m in c.METHODES if m not in (c.METHODE_RETENUE, "groupe de revenu")]
        p = pd.concat([p] + [p[p["methode"] == "groupe de revenu"].assign(methode=m) for m in autres], ignore_index=True)
        e = c.ecart_par_sous_echantillon(p, tirages=20).set_index("sous_echantillon")
        assert e.loc["tous les cas", "ecart"] == pytest.approx(1.0, abs=1e-3)          # 5 points pour 2 pays sur 10
        assert e.loc["sans la Chine ni l'Inde", "ecart"] == pytest.approx(0.0, abs=1e-3)
        assert e.loc["tous les cas", "ecart_pondere_pib"] == pytest.approx(5 * 20 / 28, abs=1e-3)
        assert e.loc["revenu élevé", "ecart_pondere_pib"] == pytest.approx(0.0, abs=1e-3)


class TestFourchettesDeLongTerme:
    """
    Au-delà de l'horizon du FMI : erreurs des trajectoires du FMI prolongées, en temps réel ;
    quantiles par groupe de revenu lissés par une loi de puissance ; élargissement des bornes.
    """

    def test_derive_ne_voit_que_le_passe_connu(self):
        from pib.long_terme import derive
        reel = pd.Series(2.0, index=range(1990, 2030))
        reel.loc[2009:] = 50.0                         # l'avenir et l'année v − 1 ne doivent pas compter
        assert derive(reel, 2010) == pytest.approx(2.0)
        lacunaire = pd.Series(2.0, index=range(2001, 2004))
        assert np.isnan(derive(lacunaire, 2010))       # 3 années sur 10 : trop peu

    def test_prolongements(self):
        from pib.long_terme import croissances_prevues
        fmi = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 297.0])
        p = croissances_prevues(fmi, 2.5, h_max=7)
        assert np.allclose(p["fmi_puis_derive"], [1, 2, 3, 4, 5, 297, 2.5, 2.5])
        assert np.allclose(p["fmi_prolonge"], [1, 2, 3, 4, 5, 297, 5, 5])   # médiane des horizons 3 à 5
        assert np.allclose(p["derive"], 2.5)

    def test_erreurs_prolongees_enchainees(self):
        from pib.long_terme import erreurs_prolongees
        lignes = [dict(country_code="AAA", income_group="HIC", vintage="F2010", annee_millesime=2010, horizon=h,
                       year=2010 + h, valeur=3.0, realise_fmi=1.0) for h in range(6)]
        lignes += [dict(country_code="AAA", income_group="HIC", vintage="X", annee_millesime=1900, horizon=9,
                        year=a, valeur=np.nan, realise_fmi=1.0) for a in range(1995, 2010)]
        lignes += [dict(country_code="AAA", income_group="HIC", vintage="X", annee_millesime=1900, horizon=9,
                        year=a, valeur=np.nan, realise_fmi=1.0) for a in range(2016, 2020)]
        e = erreurs_prolongees(pd.DataFrame(lignes), h_max=9).set_index("horizon")
        assert list(e.index) == list(range(10))
        # Dérive : 1 % ; FMI : 3 % jusqu'à 5 ans, puis 1 % ; réalisé : 1 %
        assert e.loc[9, "erreur_derive"] == pytest.approx(0.0, abs=1e-9)
        assert e.loc[9, "erreur_fmi_puis_derive"] == pytest.approx(100 * ((1.03 / 1.01) ** 6 - 1))
        assert e.loc[9, "erreur_fmi_prolonge"] == pytest.approx(100 * ((1.03 / 1.01) ** 10 - 1))

    def test_derive_negative_ecartee_des_fourchettes(self):
        """Une dérive négative extrapole un effondrement : la trajectoire sort des fourchettes."""
        from pib.long_terme import erreurs_prolongees, cas_pour_les_fourchettes
        lignes = []
        for code, passe in (("AAA", 1.0), ("BBB", -3.0)):
            lignes += [dict(country_code=code, income_group="LMC", vintage="F2010", annee_millesime=2010, horizon=h,
                            year=2010 + h, valeur=3.0, realise_fmi=1.0) for h in range(6)]
            lignes += [dict(country_code=code, income_group="LMC", vintage="X", annee_millesime=1900, horizon=9,
                            year=a, valeur=np.nan, realise_fmi=passe) for a in range(1995, 2010)]
        e = erreurs_prolongees(pd.DataFrame(lignes), h_max=5)
        assert e.groupby("country_code")["derive_pct"].first().to_dict() == pytest.approx({"AAA": 1.0, "BBB": -3.0})
        assert set(cas_pour_les_fourchettes(e)["country_code"]) == {"AAA"}

    def test_loi_lissee_retrouvee_et_lissage(self):
        from pib.long_terme import ajuster_loi, lisser
        h = np.arange(1, 17)
        p90 = 100 * np.expm1(0.03 * (h + 1) ** 0.9)
        p10 = 100 * np.expm1(-0.015 * (h + 1) ** 1.1)
        assert ajuster_loi(h, p90) == pytest.approx((0.0, 0.03, 0.9), abs=1e-9)
        assert ajuster_loi(h, p10) == pytest.approx((0.0, -0.015, 1.1), abs=1e-9)
        q = pd.DataFrame({"groupe": "HIC", "horizon": np.r_[0, h, 30], "annees_edition": np.r_[25, [12] * 16, 2],
                          "p10": np.r_[-1, p10, -90], "p90": np.r_[1, p90, 500], "p50": 0.0, "cas": 100})
        bandes, lois = lisser(q)
        assert lois.iloc[0]["horizon_max_ajuste"] == 16          # l'horizon 30 (2 années d'édition) est écarté
        b30 = bandes.set_index("horizon").loc[30]
        assert b30["p90_lisse"] == pytest.approx(100 * np.expm1(0.03 * 31 ** 0.9))
        assert np.all(np.diff(bandes["p90_lisse"]) > 0) and np.all(np.diff(bandes["p10_lisse"]) < 0)

    def test_loi_lissee_qui_change_de_signe(self):
        """10e centile négatif à court terme, positif au-delà : la loi le suit."""
        from pib.long_terme import ajuster_loi
        h = np.arange(1, 17)
        q = 100 * np.expm1(-0.05 + 0.01 * (h + 1))
        alpha, beta, b = ajuster_loi(h, q)
        assert (alpha, beta, b) == pytest.approx((-0.05, 0.01, 1.0), abs=1e-9)

    def test_elargissement(self):
        from pib.long_terme import elargissement
        h = np.arange(0, 41)
        b = pd.DataFrame({"groupe": ["HIC"] * 41 + ["tous"] * 41, "horizon": np.r_[h, h],
                          "p10_lisse": np.r_[-1.0 * h, -2.0 * h], "p90_lisse": np.r_[2.0 * h, 3.0 * h]})
        assert elargissement(b, "HIC", 5, 5) == pytest.approx((1.0, 1.0))
        bas, haut = elargissement(b, "HIC", 5, 10)
        assert bas == pytest.approx(1.10 / 1.20) and haut == pytest.approx(0.95 / 0.90)
        assert elargissement(b, "XYZ", 5, 10) == pytest.approx((1.15 / 1.30, 0.90 / 0.80))   # groupe inconnu : tous
        assert elargissement(b, "HIC", 5, 99) == elargissement(b, "HIC", 5, 40)               # au-delà : dernier horizon

    @pytest.mark.donnees
    def test_fourchettes_de_long_terme_produites(self):
        chemin = os.path.join("data", "processed", "gdp_long_horizon_bands.csv")
        if not os.path.exists(chemin):
            pytest.skip("pib.long_terme n'a pas tourné")
        b = pd.read_csv(chemin)
        assert (b["p90_lisse"] > b["p10_lisse"]).all()
        assert (b.loc[b["horizon"] >= 1, "p90_lisse"] > 0).all()
        for _, g in b.groupby("groupe"):
            assert np.all(np.diff(g.sort_values("horizon")["p90_lisse"]) > 0)


class TestCalibrationEnTempsReel:
    """
    Évaluation probabiliste des fourchettes et des probabilités de récession : chaque
    édition n'utilise que les erreurs connues à sa date ; scores propres (intervalle, CRPS,
    Brier) comparés entre méthodes sur les mêmes cas.
    """

    def test_score_d_intervalle(self):
        from pib.calibration import score_intervalle
        s = score_intervalle([-10, -10, -10], [10, 10, 10], [0, -15, 12], alpha=0.2)
        assert list(s) == pytest.approx([20.0, 20 + 10 * 5, 20 + 10 * 2])

    def test_crps_de_la_distribution_empirique(self):
        """Formule en O(log n) = définition : E|X − y| − E|X − X'| / 2."""
        from pib.calibration import Distribution
        x = np.array([3.0, -1.0, 4.0, 1.0, 5.0, 9.0])
        for y in (-2.0, 2.5, 4.0, 12.0):
            attendu = np.abs(x - y).mean() - np.abs(x[:, None] - x[None, :]).mean() / 2
            assert Distribution(x).crps(y)[0] == pytest.approx(attendu)

    @staticmethod
    def _niveaux():
        """
        Projections à 5 ans de 30 pays à revenu élevé, éditions 1990 à 2006. Erreurs des
        éditions jusqu'à 1998 : de −10 à +10 ; ensuite : +50. Un recul survient une fois sur deux.
        """
        lignes = []
        for m in range(1990, 2007):
            for i in range(30):
                lignes.append(dict(country_code=f"P{i}", income_group="HIC", horizon=5, annee_millesime=m, year=m + 5,
                                   poids_pib=1.0, croissance_prevue_cumulee_pct=10.0 + i,
                                   erreur_niveau_vs_fmi_pct=-10 + 20 * i / 29 if m <= 1998 else 50.0,
                                   pire_croissance_realisee=-1.0 if i % 2 else 1.0, pire_croissance_prevue=1.0))
        return pd.DataFrame(lignes)

    def test_aucune_erreur_encore_inconnue(self):
        """
        Pour l'édition 2005 à 5 ans, seules les erreurs des éditions jusqu'à 1998 sont connues :
        les +50 des éditions 1999 à 2004 ne doivent pas élargir sa fourchette.
        """
        from pib.calibration import previsions_en_temps_reel
        p = previsions_en_temps_reel(self._niveaux(), horizon=5, premiere=2005)
        e2005 = p[(p["annee_millesime"] == 2005) & (p["methode"] == "inconditionnelle")]
        assert (e2005["haut"] <= 10).all()
        assert set(p["annee_millesime"]) == {2005, 2006}

    def test_cas_communs_et_historique_du_pays(self):
        """Moins de `MIN_CAS_PAYS` erreurs connues : pas de fourchette tirée de l'historique du pays."""
        from pib.calibration import previsions_en_temps_reel, cas_communs, MIN_CAS_PAYS
        assert MIN_CAS_PAYS == 8
        p = previsions_en_temps_reel(self._niveaux(), horizon=5, premiere=2003)
        pays = p[p["methode"] == "historique du pays"]
        assert pays[pays["annee_millesime"] == 2003].empty        # 7 éditions connues (1990 à 1996)
        assert len(pays[pays["annee_millesime"] == 2004]) == 30   # 8 éditions connues (1990 à 1997)
        commun = cas_communs(p)
        assert set(commun["annee_millesime"]) == {2004, 2005, 2006}
        assert commun.groupby(["country_code", "annee_millesime", "year"])["methode"].nunique().eq(5).all()

    def test_recessions_mondiales_et_leur_frequence(self):
        """Reculs en 1975, 1982, 1991 : sur 1961-1998, part des périodes de 5 ans qui en contiennent un."""
        from pib.evaluate_forecasts import recessions_mondiales, probabilite_crise_mondiale, periodes_en_crise
        monde = pd.Series({a: (-1.0 if a in (1975, 1982, 1991, 2009) else 2.0) for a in range(1961, 2011)})
        assert recessions_mondiales(monde, jusqu_a=1998) == [1975, 1982, 1991]
        periodes = [any(a <= r <= a + 4 for r in (1975, 1982, 1991)) for a in range(1961, 1995)]
        assert probabilite_crise_mondiale(monde, 5, jusqu_a=1998) == pytest.approx(np.mean(periodes))
        assert list(periodes_en_crise(pd.Series([2003, 2004, 2009]), 5, [2009])) == [False, True, False]

    def test_probabilite_avec_crises_mondiales_a_part(self):
        """
        Périodes passées en crise mondiale : recul toujours ; hors crise : jamais. La
        probabilité vaut alors la part des périodes de 5 ans en crise sur l'historique long.
        """
        from pib.evaluate_forecasts import fourchettes_projections, probabilite_crise_mondiale
        monde = pd.Series({a: (-1.0 if a in (1982, 1991, 2009) else 2.0) for a in range(1961, 2026)})
        niveaux = TestFourchettesDesProjections._niveaux()
        crise = [any(m + 1 <= r <= m + 5 for r in (1982, 1991, 2009)) for m in niveaux["annee_millesime"]]
        niveaux["pire_croissance_realisee"] = np.where(crise, -2.0, 1.0)
        bandes = fourchettes_projections(niveaux, pd.Series({"LEN": 10.0, "VIF": 55.0}),
                                         TestFourchettesDesProjections._synthese(), 2031, 2026, monde).set_index("country_code")
        pi = probabilite_crise_mondiale(monde, 5) * 100
        assert bandes.loc["LEN", "probabilite_crise_mondiale_pct"] == pytest.approx(pi, abs=1e-2)
        assert bandes.loc["LEN", "probabilite_recul_si_crise_mondiale_pct"] == pytest.approx(100.0)
        assert bandes.loc["LEN", "probabilite_recul_hors_crise_mondiale_pct"] == pytest.approx(0.0)
        assert bandes.loc["LEN", "probabilite_recul_pct"] == pytest.approx(pi, abs=1e-2)

    def test_crises_mondiales_connues_a_la_date_de_l_edition(self):
        """
        Édition 2005 : une récession mondiale de 2003 n'est connue qu'à partir de l'édition
        2005 (v − 2), celle de 2004 pas encore ; elle ne peut peser sur sa probabilité.
        """
        from pib.calibration import previsions_en_temps_reel, METHODE_MELANGE
        niveaux = self._niveaux()
        niveaux.loc[niveaux["annee_millesime"] == 1999, "pire_croissance_realisee"] = -1.0   # période 2000-2004 : recul partout
        sans = pd.Series({a: 2.0 for a in range(1961, 2010)})
        avec_2004 = sans.copy(); avec_2004[2004] = -1.0
        p1 = previsions_en_temps_reel(niveaux, horizon=5, premiere=2005, monde=sans)
        p2 = previsions_en_temps_reel(niveaux, horizon=5, premiere=2005, monde=avec_2004)
        m1 = p1[(p1["methode"] == METHODE_MELANGE) & (p1["annee_millesime"] == 2005)]["proba_recul"]
        m2 = p2[(p2["methode"] == METHODE_MELANGE) & (p2["annee_millesime"] == 2005)]["proba_recul"]
        assert list(m1) == pytest.approx(list(m2))
        # Édition 2006 : récession de 2004 connue ; probabilité de crise tirée de l'historique jusqu'en 2004
        # seulement ; recul toujours dans la période en crise (édition 1999), une fois sur deux ailleurs
        from pib.evaluate_forecasts import probabilite_crise_mondiale
        pi = probabilite_crise_mondiale(avec_2004, 5, jusqu_a=2004)
        m6 = p2[(p2["methode"] == METHODE_MELANGE) & (p2["annee_millesime"] == 2006)]["proba_recul"]
        assert np.allclose(m6, pi * 1.0 + (1 - pi) * 0.5)

    def test_brier_et_competence(self):
        """Une probabilité juste (1 ou 0 selon le recul) a une compétence de 1 face à la fréquence moyenne."""
        from pib.calibration import scores_recession, METHODES, METHODE_FMI
        lignes = []
        for i in range(40):
            recul = float(i % 2)
            for methode in (*METHODES, METHODE_FMI):
                proba = recul if methode == "classe de croissance" else 0.5
                lignes.append(dict(country_code=f"P{i}", annee_millesime=2000, year=2000 + i % 10, methode=methode,
                                   proba_recul=proba, recul=recul, brier=(proba - recul) ** 2))
        s = scores_recession(pd.DataFrame(lignes), tirages=20).set_index("methode")
        assert s.loc["classe de croissance", "competence"] == pytest.approx(1.0)
        assert s.loc["inconditionnelle", "brier"] == pytest.approx(0.25)
        assert s.loc["classe × groupe de revenu", "competence"] == pytest.approx(0.0)

    def test_fiabilite_par_tranche(self):
        from pib.calibration import fiabilite_recession, METHODE_RETENUE
        p = pd.DataFrame(dict(methode=METHODE_RETENUE, proba_recul=[0.15, 0.15, 0.35, 0.35], recul=[0.0, 1.0, 1.0, 1.0]))
        f = fiabilite_recession(p).set_index("tranche")
        assert f.loc["(0.1, 0.2]", "frequence_observee"] == pytest.approx(0.5)
        assert f.loc["(0.3, 0.4]", "frequence_observee"] == pytest.approx(1.0)


class TestMillesimesBanqueMondiale:
    """
    Le réalisé se révise aussi : éditions archivées des WDI, révisions depuis la première
    publication, et croissance telle que publiée à la fin de l'année suivante.
    """

    @staticmethod
    def _archive():
        """
        Croissance 2000 de Pays A : publiée 2,0 en juillet 2001, révisée 2,5 en juillet 2002,
        3,0 en juillet 2006. Pays B, année 2000 : 1,0 puis inchangée.
        """
        return pd.DataFrame(dict(
            version=[200107, 200207, 200607, 200107, 200607],
            country_code=["AAA", "AAA", "AAA", "BBB", "BBB"], year=2000,
            value=[2.0, 2.5, 3.0, 1.0, 1.0]))

    def test_lecture_d_une_edition(self, monkeypatch):
        """Champs lus par nom (leur ordre varie), valeurs nulles écartées, pages suivies."""
        from pib import millesimes_bm
        pages = {1: [({"Country": "USA", "Time": "YR2008", "Series": "S", "Version": "202607"}, -0.1),
                     ({"Time": "YR2009", "Country": "USA", "Series": "S", "Version": "202607"}, None)],
                 2: [({"Series": "S", "Country": "FRA", "Time": "YR2008", "Version": "202607"}, 0.2)]}

        def faux_get_json(url, params=None, **kw):
            p = params["page"]
            return {"pages": 2, "source": {"data": [
                {"variable": [{"concept": k, "id": v} for k, v in champs.items()], "value": valeur}
                for champs, valeur in pages[p]]}}
        monkeypatch.setattr(millesimes_bm, "get_json", faux_get_json)
        t = millesimes_bm.lire_millesime("202607", "S")
        assert list(zip(t["country_code"], t["year"], t["value"])) == [("USA", 2008, -0.1), ("FRA", 2008, 0.2)]

    def test_archivage_unique(self, tmp_path, monkeypatch):
        from pib import millesimes_bm
        appels = []
        monkeypatch.setattr(millesimes_bm, "lire_millesime", lambda v, s: appels.append((v, s)) or
                            pd.DataFrame(dict(country_code=["USA"], year=[2008], value=[1.0])))
        assert millesimes_bm.archiver_millesimes(str(tmp_path), ["200107", "200207"]) == ["200107", "200207"]
        assert millesimes_bm.archiver_millesimes(str(tmp_path), ["200107", "200207", "200607"]) == ["200607"]
        assert len(appels) == 3 * len(millesimes_bm.SERIES)
        assert len(pd.read_csv(tmp_path / "index.csv")) == 3
        assert set(millesimes_bm.charger_archive(str(tmp_path))["version"]) == {200107, 200207, 200607}

    def test_revisions_depuis_la_premiere_publication(self):
        from pib.millesimes_bm import revisions_depuis_publication
        r = revisions_depuis_publication(self._archive(), delais=(1, 5, 10)).set_index(["country_code", "delai"])
        assert r.loc[("AAA", "1"), "premiere"] == 2.0 and r.loc[("AAA", "1"), "valeur"] == 2.5
        assert r.loc[("AAA", "5"), "valeur"] == 3.0
        assert r.loc[("AAA", "actuelle"), "valeur"] == 3.0
        assert ("AAA", "10") not in r.index        # au-delà de la dernière édition
        assert r.loc[("BBB", "1"), "valeur"] == 1.0

    def test_annees_anterieures_a_l_archive_ecartees(self):
        """1990, déjà ancienne à la première édition archivée (2001), n'a pas de vraie première publication."""
        from pib.millesimes_bm import revisions_depuis_publication
        archive = pd.concat([self._archive(), pd.DataFrame(dict(version=[200107, 200607], country_code="AAA",
                                                                year=1990, value=[1.0, 4.0]))])
        r = revisions_depuis_publication(archive, delais=(5,))
        assert set(r["year"]) == {2000}

    def test_synthese_des_revisions(self):
        from pib.millesimes_bm import revisions_depuis_publication, synthese_croissance
        t = synthese_croissance(revisions_depuis_publication(self._archive(), delais=(5,))).set_index("delai")
        assert t.loc["5", "revision_moyenne"] == pytest.approx(0.5)       # (1,0 + 0) / 2
        assert t.loc["5", "part_au_dela_du_seuil_pct"] == pytest.approx(0.0)

    def test_croissance_en_temps_reel(self):
        """Pour 2000 : dernière édition parue au plus tard en décembre 2001."""
        from pib.millesimes_bm import croissance_en_temps_reel
        t = croissance_en_temps_reel(self._archive()).set_index("country_code")
        assert t.loc["AAA", "realise_bm_temps_reel"] == 2.0

    def test_biais_selon_la_reference(self):
        from pib.millesimes_bm import biais_selon_la_reference
        evaluation = pd.DataFrame(dict(country_code="AAA", year=2000, horizon=1, valeur=4.0,
                                       realise_fmi=2.2, realise_bm=3.0, poids_pib=1.0), index=[0])
        temps_reel = pd.DataFrame(dict(country_code=["AAA"], year=[2000], realise_bm_temps_reel=[2.0]))
        ligne = biais_selon_la_reference(evaluation, temps_reel).iloc[0]
        assert ligne["biais_moyen_fmi_un_an"] == pytest.approx(1.8)
        assert ligne["biais_moyen_bm_temps_reel"] == pytest.approx(2.0)
        assert ligne["biais_moyen_bm_actuelle"] == pytest.approx(1.0)


class TestRisqueDeRecession:
    """
    La trajectoire du FMI est lisse : elle n'annonce presque jamais le recul qui survient
    pourtant, sur cinq ans, pour un pays sur deux. Pire année des horizons 1 à h, projetée
    et réalisée ; fréquence des reculs par groupe et dans les fourchettes.
    """

    @staticmethod
    def _evaluation(realise=(-5.0, 1.0, 2.0, -0.5)):
        return pd.DataFrame([dict(country="France", country_code="FRA", income_group="HIC", vintage="S2020", saison="S",
                                  annee_millesime=2020, year=2020 + h, horizon=h, poids_pib=1.0, valeur=v,
                                  realise_fmi=r, realise_bm=1.0)
                             for h, (v, r) in enumerate(zip((2.0, 2.0, -1.0, 2.0), realise))])

    def test_pire_annee_des_horizons_suivants(self):
        """L'année de l'édition ne compte pas : son recul de −5 % n'entre dans aucune période."""
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(self._evaluation()).set_index("horizon")
        assert niveaux[["pire_croissance_prevue", "pire_croissance_realisee"]].loc[0].isna().all()
        assert list(niveaux.loc[[1, 2, 3], "pire_croissance_prevue"]) == [2.0, -1.0, -1.0]
        assert list(niveaux.loc[[1, 2, 3], "pire_croissance_realisee"]) == [1.0, 1.0, -0.5]

    def test_realise_manquant_rompt_la_periode(self):
        from pib.evaluate_forecasts import erreurs_de_niveau
        niveaux = erreurs_de_niveau(self._evaluation(realise=(1.0, np.nan, -2.0, -3.0))).set_index("horizon")
        assert niveaux.loc[[1, 2, 3], "pire_croissance_realisee"].isna().all()

    def test_reculs_par_horizon(self):
        from pib.evaluate_forecasts import reculs_par_horizon
        evaluation = pd.DataFrame(dict(horizon=1, valeur=[1.0, -1.0, 1.0, 1.0], realise_fmi=[-1.0, -1.0, -2.0, 1.0]))
        ligne = reculs_par_horizon(evaluation).iloc[0]
        assert ligne["recul_annonce_pct"] == pytest.approx(25.0)
        assert ligne["recul_survenu_pct"] == pytest.approx(75.0)
        assert ligne["reculs_survenus_annonces_pct"] == pytest.approx(100 / 3, abs=1e-3)
        assert ligne["reculs_annonces_survenus_pct"] == pytest.approx(100.0)

    def test_risque_par_groupe_et_par_periode(self):
        """
        Quatre périodes de deux ans : A recule, B annonce un recul qui ne vient pas, C recule
        pendant la crise de 2009 (édition 2008), D ne recule pas. Hors crises : A, B, D.
        """
        from pib.evaluate_forecasts import risque_de_recession
        niveaux = pd.DataFrame(dict(
            country_code=["A", "B", "C", "D"], horizon=2, vintage=["S2000", "S2000", "S2008", "S2003"],
            annee_millesime=[2000, 2000, 2008, 2003], year=[2002, 2002, 2010, 2005],
            income_group=["HIC", "LIC", "HIC", "LIC"], poids_pib=[10.0, 1.0, 10.0, 1.0],
            pire_croissance_prevue=[1.0, -1.0, 1.0, 1.0], pire_croissance_realisee=[-2.0, 1.0, -4.0, 2.0]))
        table = risque_de_recession(niveaux).set_index("groupe")
        tous = table.loc["Tous les pays"]
        assert tous["recul_annonce_pct"] == pytest.approx(25.0)
        assert tous["recul_survenu_pct"] == pytest.approx(50.0)
        assert tous["recul_survenu_pondere_pib_pct"] == pytest.approx(2000 / 22, abs=1e-3)
        assert tous["recul_survenu_hors_crises_mondiales_pct"] == pytest.approx(100 / 3, abs=1e-3)
        assert tous["recul_survenu_avant_coupure_pct"] == pytest.approx(100 / 3, abs=1e-3)
        assert tous["recul_survenu_apres_coupure_pct"] == pytest.approx(100.0)
        assert tous["pire_annee_mediane_pct"] == pytest.approx(-3.0)
        assert table.loc["Revenu élevé", "recul_survenu_pct"] == pytest.approx(100.0)
        assert table.loc["Faible revenu", "recul_survenu_pct"] == pytest.approx(0.0)

    def test_grandes_economies_comptees_par_edition(self):
        """Avril et octobre visent la même année : par année visée, dix pays seulement seraient retenus."""
        from pib.evaluate_forecasts import _grandes_economies, GRANDES_ECONOMIES
        cas = pd.DataFrame([dict(country_code=f"P{i}", vintage=v, annee_millesime=2000, year=2005, horizon=5,
                                 poids_pib=float(100 - i)) for i in range(30) for v in ("S2000", "F2000")])
        grandes = cas[_grandes_economies(cas)]
        assert grandes["country_code"].nunique() == GRANDES_ECONOMIES
        assert (grandes.groupby("vintage").size() == GRANDES_ECONOMIES).all()

    @staticmethod
    def _niveaux_avec_reculs():
        """Projections modestes : un recul une fois sur deux ; projections vives : jamais."""
        niveaux = TestFourchettesDesProjections._niveaux()
        lente = niveaux["croissance_prevue_cumulee_pct"] < 20
        niveaux["pire_croissance_realisee"] = np.where(lente, np.where(niveaux.index % 4 == 0, -1.0, 1.0), 2.0)
        return niveaux

    def test_probabilite_de_recul_dans_les_fourchettes(self):
        from pib.evaluate_forecasts import fourchettes_projections
        croissance = pd.Series({"LEN": 10.0, "VIF": 55.0})     # dans les classes des projections passées
        bandes = fourchettes_projections(self._niveaux_avec_reculs(), croissance,
                                         TestFourchettesDesProjections._synthese(), 2031, 2026).set_index("country_code")
        assert bandes.loc["LEN", "projections_de_reference"] == "classe × groupe de revenu"
        assert bandes.loc["LEN", "probabilite_recul_pct"] == pytest.approx(50.0)
        assert bandes.loc["LEN", "pire_annee_mediane_pct"] == pytest.approx(-1.0)
        assert bandes.loc["VIF", "probabilite_recul_pct"] == pytest.approx(0.0)
        assert pd.isna(bandes.loc["VIF", "pire_annee_mediane_pct"])
        # Repli sur l'ensemble des projections : un recul dans un quart des cas
        assert bandes.loc["SAN", "probabilite_recul_pct"] == pytest.approx(25.0)

    def test_recul_par_classe_de_croissance(self):
        from pib.evaluate_forecasts import synthese_niveau_par_croissance
        table = synthese_niveau_par_croissance(self._niveaux_avec_reculs())
        assert table["recul_survenu_pct"].iloc[0] == pytest.approx(50.0)
        assert table["recul_survenu_pct"].iloc[-1] == pytest.approx(0.0)

    def test_phrase_selon_le_poids_des_crises_mondiales(self, tmp_path):
        """Le commentaire suit les données : les crises mondiales expliquent l'essentiel ou non."""
        from pib.build_results_page import section_recessions
        processed = tmp_path / "processed"
        processed.mkdir()
        pd.DataFrame(dict(horizon=[0, 1], projections=100, recul_annonce_pct=[10.0, 2.0], recul_survenu_pct=14.0,
                          reculs_survenus=14, reculs_survenus_annonces_pct=[60.0, 10.0], reculs_annonces_survenus_pct=50.0)
                     ).to_csv(processed / "weo_recession_by_horizon_ngdp_rpch.csv", index=False)

        def phrase(hors_crises):
            pd.DataFrame(dict(horizon=[5], groupe=["Tous les pays"], income_group=[None], periodes=[100],
                              recul_annonce_pct=[3.0], recul_survenu_pct=[45.0], recul_survenu_pondere_pib_pct=[48.0],
                              recul_survenu_hors_crises_mondiales_pct=[hors_crises], recul_survenu_avant_coupure_pct=[38.0],
                              recul_survenu_apres_coupure_pct=[56.0], pire_annee_mediane_pct=[-3.4])
                         ).to_csv(processed / "weo_recession_risk_ngdp_rpch.csv", index=False)
            return section_recessions(str(tmp_path))

        assert "n'en expliquent pas l'essentiel" in phrase(32.0)
        assert "en expliquent l'essentiel" in phrase(10.0)


class TestRevisionsDesEditions:
    """
    Révisions d'une édition à la suivante : leur sens, leur enchaînement (test de
    Nordhaus), et ce que change la dernière édition archivée.
    """

    def test_revisions_entre_editions_consecutives(self):
        """Octobre 2022 manque : la révision d'avril 2023 n'est pas calculée."""
        from pib.revisions_weo import revisions_successives
        base = pd.DataFrame(dict(country_code="FRA", year=2022, vintage=["S2021", "F2021", "S2022", "S2023"],
                                 saison=["S", "F", "S", "S"], annee_millesime=[2021, 2021, 2022, 2023],
                                 horizon=[1, 1, 0, -1], valeur=[2.0, 1.5, 1.0, 0.8]))
        r = revisions_successives(base).set_index("vintage")
        assert pd.isna(r.loc["S2021", "revision"])
        assert r.loc["F2021", "revision"] == pytest.approx(-0.5)
        assert r.loc["S2022", "revision"] == pytest.approx(-0.5)
        assert r.loc["S2022", "revision_precedente"] == pytest.approx(-0.5)
        assert pd.isna(r.loc["S2023", "revision"]) and pd.isna(r.loc["S2023", "revision_precedente"])

    def test_test_de_nordhaus(self):
        """Chaque révision prolonge la moitié de la précédente : pente 0,5, toutes de même sens."""
        from pib.revisions_weo import synthese_des_revisions
        precedente = np.linspace(-2, 2, 101)
        precedente = precedente[precedente != 0]
        revisions = pd.DataFrame(dict(year=2000 + np.arange(len(precedente)) % 20, horizon=0, saison="S",
                                      revision_precedente=precedente, revision=0.5 * precedente))
        ligne = synthese_des_revisions(revisions).iloc[0]
        assert ligne["pente_nordhaus"] == pytest.approx(0.5, abs=1e-6)
        assert ligne["correlation"] == pytest.approx(1.0, abs=1e-6)
        assert ligne["part_meme_sens_pct"] == pytest.approx(100.0)
        assert ligne["part_a_la_baisse_pct"] == pytest.approx(50.0)

    def test_etapes_dans_l_ordre_chronologique(self):
        from pib.revisions_weo import synthese_des_revisions
        revisions = pd.DataFrame(dict(year=2020, horizon=[1, 0, 1, -1], saison=["F", "S", "S", "F"],
                                      revision=-0.1, revision_precedente=np.nan))
        assert list(synthese_des_revisions(revisions)["etape"]) == [
            "avril, horizon 1", "octobre, horizon 1", "avril, horizon 0", "octobre, ré-estimation"]

    @staticmethod
    def _niveaux(pays: dict) -> pd.DataFrame:
        """Format de `lire_niveaux` : une ligne par pays, une colonne par (indicateur, année)."""
        lignes = [dict(country_code=code, indicator=ind, year=annee, value=v)
                  for code, valeurs in pays.items() for (ind, annee), v in valeurs.items()]
        return pd.DataFrame(lignes).pivot_table(index="country_code", columns=["indicator", "year"], values="value")

    def test_revisions_de_niveau(self):
        """
        L'Inde change d'année de base (volume ×1,6, rien d'autre) ; la Bulgarie change de
        monnaie (monnaie nationale ÷ 1,95583) ; le Japon révise sa projection en dollars de
        5 % et en volume de 2 % ; le Nigeria révise tout son PIB en dollars de 20 %.
        """
        from pib.revisions_weo import revisions_de_niveau
        ancien = {("NGDP", 2024): 100.0, ("NGDP_R", 2024): 100.0, ("NGDP_R", 2030): 150.0,
                  ("NGDPD", 2024): 10.0, ("NGDPD", 2030): 15.0}
        nouveau = {
            "IND": {**ancien, ("NGDP_R", 2024): 160.0, ("NGDP_R", 2030): 240.0},
            "BGR": {**ancien, ("NGDP", 2024): 100 / 1.95583, ("NGDP_R", 2024): 100 / 1.95583,
                    ("NGDP_R", 2030): 150 / 1.95583},
            "JPN": {**ancien, ("NGDP_R", 2030): 153.0, ("NGDPD", 2030): 15.75},
            "NGA": {**ancien, ("NGDPD", 2024): 12.0, ("NGDPD", 2030): 18.0},
        }
        table = revisions_de_niveau(self._niveaux({code: ancien for code in nouveau}), self._niveaux(nouveau),
                                    2024, 2030).set_index("country_code")
        assert table.loc["IND", "revision_croissance_reelle_pct"] == pytest.approx(0.0)
        assert table.loc["IND", "changement_annee_de_base"] and not table.loc["IND", "revision_de_l_historique"]
        assert not table.loc["BGR", ["changement_annee_de_base", "revision_de_l_historique"]].any()
        assert table.loc["JPN", "revision_croissance_usd_pct"] == pytest.approx(5.0)
        assert table.loc["JPN", "revision_croissance_reelle_pct"] == pytest.approx(2.0)
        assert table.loc["NGA", "revision_de_l_historique"] and not table.loc["NGA", "changement_annee_de_base"]
        assert table.loc["NGA", "revision_croissance_usd_pct"] == pytest.approx(0.0)
        assert table.loc["NGA", "revision_pib_usd_cible_pct"] == pytest.approx(20.0)

    def test_historique_controle_sur_une_annee_observee(self):
        """
        Le raccord du rapport le plus récent se fait sur une année encore estimée par
        l'ancienne édition : sa révision (ici l'inflation 2025, +10 %) n'est pas un
        changement d'année de base. Le contrôle porte sur une année observée des deux côtés.
        """
        from pib.revisions_weo import revisions_de_niveau
        ancien = {(ind, annee): 100.0 for ind in ("NGDP", "NGDP_R", "NGDPD") for annee in (2023, 2025, 2030)}
        nouveau = {**ancien, ("NGDP", 2025): 110.0}
        a, n = self._niveaux({"EST": ancien}), self._niveaux({"EST": nouveau})
        assert revisions_de_niveau(a, n, 2025, 2030)["changement_annee_de_base"].iloc[0]
        assert not revisions_de_niveau(a, n, 2025, 2030, annee_controle=2023)["changement_annee_de_base"].iloc[0]

    def test_editions_archivees_dans_l_ordre(self, tmp_path):
        from pib.revisions_weo import editions_archivees
        for nom in ("WEO_S2026.csv.gz", "WEO_F2025.csv.gz", "WEO_F2024.csv.gz", "index.csv", "LISEZ-MOI.md"):
            (tmp_path / nom).write_text("")
        assert editions_archivees(str(tmp_path)) == ["F2024", "F2025", "S2026"]
        assert editions_archivees(str(tmp_path / "absent")) == []

    def test_niveaux_archives_lus_aux_codes_de_la_banque_mondiale(self, tmp_path):
        from pib.revisions_weo import lire_niveaux
        pd.DataFrame(dict(country_code=["KOS", "KOS", "FRA"], indicator=["NGDPD", "LP", "NGDPD"],
                          year=2024, value=[10.0, 1.8, 3000.0])).to_csv(tmp_path / "WEO_S2026.csv.gz", index=False)
        niveaux = lire_niveaux(str(tmp_path), "S2026")
        assert niveaux.loc["XKX", ("NGDPD", 2024)] == pytest.approx(10.0)
        assert "LP" not in niveaux.columns.get_level_values("indicator")

    def test_zero_arrondi_sans_signe_negatif(self):
        from pib.build_results_page import signe
        assert signe(-0.001) == "+0,00"
        assert signe(-0.5) == "−0,50"


class TestCasDeCrise:
    """
    Une récession mondiale dans les prévisions du FMI (2009, 2020) : recul annoncé ou non,
    rebond sous-estimé ou non, niveau projeté contre niveau réalisé.
    """

    @staticmethod
    def _base():
        """
        Trois pays, recul de 2009 : A annoncé et survenu, B survenu sans être annoncé, C ni
        l'un ni l'autre. Réalisé : ré-estimation d'octobre 2010 (horizon −1).
        """
        lignes = []
        for code, prevu, reel in (("AAA", -1.0, -2.0), ("BBB", 1.0, -1.0), ("CCC", 1.0, 1.0)):
            lignes += [dict(country=code, country_code=code, year=2009, vintage="S2009", saison="S",
                            annee_millesime=2009, horizon=0, valeur=prevu),
                       dict(country=code, country_code=code, year=2009, vintage="F2010", saison="F",
                            annee_millesime=2010, horizon=-1, valeur=reel),
                       dict(country=code, country_code=code, year=2010, vintage="S2009", saison="S",
                            annee_millesime=2009, horizon=1, valeur=1.0),
                       dict(country=code, country_code=code, year=2010, vintage="F2011", saison="F",
                            annee_millesime=2011, horizon=-1, valeur=4.0)]
        return pd.DataFrame(lignes).assign(est_projection=lambda d: d["horizon"] >= 0)

    def test_editions_autour_du_choc(self):
        from pib.cas_de_crise import editions_autour
        assert editions_autour(2009) == ["S2008", "F2008", "S2009", "F2009", "S2010", "F2010"]

    def test_reculs_annonces_et_survenus(self):
        from pib.cas_de_crise import reculs_annonces
        poids = pd.Series({"AAA": 1.0, "BBB": 3.0, "CCC": 6.0})
        ligne = reculs_annonces(self._base(), 2009, poids).set_index("edition").loc["S2009"]
        assert (ligne["recul_annonce"], ligne["recul_survenu"]) == (1, 2)
        assert ligne["recul_annonce_part_pib_pct"] == pytest.approx(10.0)
        assert ligne["recul_survenu_part_pib_pct"] == pytest.approx(40.0)
        assert ligne["reculs_survenus_annonces_pct"] == pytest.approx(50.0)

    def test_rebond_sous_estime(self):
        """Prévu +1 %, réalisé +4 % : erreur de −3 points, rebond sous-estimé partout."""
        from pib.cas_de_crise import erreurs_du_rebond
        ligne = erreurs_du_rebond(self._base(), 2009, pd.Series({"AAA": 1.0, "BBB": 1.0, "CCC": 1.0})).iloc[0]
        assert ligne["erreur_mediane"] == pytest.approx(-3.0)
        assert ligne["rebond_sous_estime_pct"] == pytest.approx(100.0)

    def test_indice_de_niveau(self):
        from pib.cas_de_crise import indice_de_niveau
        niveau = indice_de_niveau(pd.Series({2008: 10.0, 2009: -10.0}), 2008, 2009)
        assert list(niveau.round(6)) == [110.0, 99.0]

    def test_lecture_jsonstat_eurostat(self):
        """Indice linéaire du JSON-stat : la dernière dimension (le temps) varie le plus vite ; valeurs absentes omises."""
        from pib.cas_de_crise import decoder_jsonstat
        donnees = {"id": ["unit", "geo", "time"], "size": [1, 2, 3],
                   "dimension": {"unit": {"category": {"index": {"PAS": 0}}},
                                 "geo": {"category": {"index": {"DE": 0, "FR": 1}}},
                                 "time": {"category": {"index": {"2007": 0, "2008": 1, "2009": 2}}}},
                   "value": {"0": 10.0, "2": 12.0, "4": 21.0}}
        t = decoder_jsonstat(donnees).set_index(["geo", "year"])["value"]
        assert t[("DE", 2007)] == 10.0 and t[("DE", 2009)] == 12.0 and t[("FR", 2008)] == 21.0
        assert ("DE", 2008) not in t.index

    @staticmethod
    def _trafic_et_pib():
        """
        Choc de 2009, base 2007, tendance 2004-2007. Pays E (Eurostat) : trafic +10 %/an
        avant (log), puis +20 % de 2007 à 2013 ; PIB réalisé +1 %/an, projeté en octobre
        2008 à +3 %/an. Les États-Unis : trafic et PIB plats, projeté à +2 %/an.
        """
        trafic = pd.DataFrame([dict(country_code=c, year=a, passagers=v, source=s)
                               for c, s, serie in (("EEE", "Eurostat", {2004: 100.0, 2007: 100 * np.exp(0.3),
                                                                       2010: 100 * np.exp(0.3), 2013: 100 * np.exp(0.5)}),
                                                   ("USA", "Banque Mondiale (OACI)", {2004: 50.0, 2007: 50.0, 2010: 50.0, 2013: 50.0}))
                               for a, v in serie.items()])
        base = pd.DataFrame([dict(country_code=c, vintage="F2008", year=a, valeur=g)
                             for c, g in (("EEE", 3.0), ("USA", 2.0)) for a in range(2008, 2014)])
        actuel = pd.Series({(c, a): g for c, g in (("EEE", 1.0), ("USA", 0.0)) for a in range(2003, 2014)})
        return trafic, base, actuel

    def test_trafic_et_pib(self):
        from pib.cas_de_crise import trafic_et_pib
        t = trafic_et_pib(*self._trafic_et_pib(), 2009).set_index("country_code")
        assert t.loc["EEE", "croissance_trafic_avant"] == pytest.approx(0.3)
        assert t.loc["EEE", "croissance_trafic_2013"] == pytest.approx(0.2)
        assert t.loc["EEE", "croissance_pib_2013"] == pytest.approx(6 * np.log(1.01))
        assert t.loc["EEE", "ecart_pib_2013"] == pytest.approx(6 * (np.log(1.01) - np.log(1.03)))

    def test_part_du_retard_du_trafic_expliquee_par_le_pib(self):
        """Retard du trafic sur sa tendance : 0,2 − 6 × 0,1 = −0,4 ; part expliquée : ε × écart de PIB / −0,4."""
        from pib.cas_de_crise import trafic_et_pib, synthese_trafic
        table = trafic_et_pib(*self._trafic_et_pib(), 2009)
        s = synthese_trafic(table, pd.Series({"EEE": 1.0, "USA": 1.0}), 2009).set_index(["groupe", "annee"])
        europe = s.loc[("Europe (Eurostat)", 2013)]
        ecart_pib = 6 * (np.log(1.01) - np.log(1.03)) * 100
        assert europe["ecart_trafic"] == pytest.approx(-40.0, abs=1e-2)
        assert europe["ecart_pib"] == pytest.approx(ecart_pib, abs=1e-2)
        assert europe["part_expliquee_1.5_pct"] == pytest.approx(1.5 * ecart_pib / -40.0 * 100, abs=1e-1)
        assert s.loc[("États-Unis", 2013), "ecart_trafic"] == pytest.approx(0.0, abs=1e-2)
        assert pd.isna(s.loc[("États-Unis", 2013), "part_expliquee_1_pct"])    # pas de retard à expliquer

    def test_regression_du_trafic_sur_le_pib(self):
        from pib.cas_de_crise import regressions_trafic
        pib = np.linspace(-0.1, 0.2, 8)
        table = pd.DataFrame(dict(country_code=[f"P{i}" for i in range(8)], source="Eurostat",
                                  croissance_pib_avant=pib, croissance_trafic_avant=0.05 + 2 * pib,
                                  croissance_pib_2010=pib, croissance_trafic_2010=0.05 + 2 * pib,
                                  croissance_pib_2013=pib, croissance_trafic_2013=0.05 + 2 * pib))
        r = regressions_trafic(table, 2009).set_index("periode")
        assert r.loc["2007-2013", "pente"] == pytest.approx(2.0)
        assert r.loc["2004-2007", "r2"] == pytest.approx(1.0)

    def test_estimation_actuelle_tiree_de_la_derniere_edition(self, tmp_path):
        """Le classeur ne ré-estime que deux ans en arrière : l'estimation actuelle vient de l'archive."""
        from pib.cas_de_crise import estimation_actuelle
        for edition, valeur in (("F2025", -3.0), ("S2026", -2.5)):
            pd.DataFrame(dict(country_code=["KOS", "USA"], indicator="NGDP_RPCH", year=2009, value=valeur)
                         ).to_csv(tmp_path / f"WEO_{edition}.csv.gz", index=False)
        actuel = estimation_actuelle(str(tmp_path))
        assert actuel[("USA", 2009)] == pytest.approx(-2.5)
        assert ("XKX", 2009) in actuel.index
        assert estimation_actuelle(str(tmp_path / "absent")).empty



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
            pytest.skip("Aucune donnée produite : lancez `python produire_rapports.py`")
        if not os.path.exists(synthese):
            pytest.skip("Aucune donnée produite : lancez `python produire_rapports.py`")
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
        # Les colonnes portent les bornes du run : on les retrouve plutôt que de les figer
        obs = int(next(c for c in synthese.columns if re.fullmatch(r"Rank_\d{4}", c))[5:])
        fin = int(next(c for c in synthese.columns if re.fullmatch(r"Rank_\d{4}_Forecast", c))[5:9])
        classes = synthese.dropna(subset=[f"Rank_{obs}"])
        assert (classes["Rank_Change"] == classes[f"Rank_{obs}"] - classes[f"Rank_{fin}_Forecast"]).all()
        assert classes[[f"Rank_{fin}_Forecast", f"Rank_PPA_{obs}", f"Rank_PPA_{fin}"]].notna().all().all()

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

    def test_pib_par_habitant_coherent(self, fichiers):
        """PIB en volume par habitant = volume / population, observé comme projeté ; ordres de grandeur."""
        unifie, _ = fichiers
        if "GDP_Real_Per_Capita_USD_2015" not in unifie.columns:
            pytest.skip("série produite avant l'ajout de la population")
        d = unifie.dropna(subset=["GDP_Real_Per_Capita_USD_2015"])
        attendu = d["GDP_Real_Billions_USD"] / d["Population_Millions"] * 1000
        assert np.allclose(d["GDP_Real_Per_Capita_USD_2015"], attendu, rtol=1e-9)
        assert d["is_forecast"].astype(bool).any()
        derniere = d[~d["is_forecast"].astype(bool)]["year"].max()
        hab = d[d["year"] == derniere].set_index("country_code")["GDP_Real_Per_Capita_USD_2015"]
        assert 40_000 < hab["USA"] < 90_000 and 1_000 < hab["IND"] < 5_000
