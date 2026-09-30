"""
pib — collecte, unification, évaluation et livrables du PIB mondial.

Collecte
    http_utils             requêtes HTTP communes : nouvelles tentatives, échec explicite
    fetch_historical_gdp   historique Banque Mondiale (API WDI)
    fetch_forecast_gdp     prévisions FMI (API DataMapper)

Calcul
    gdp_pipeline           unification, raccord, volumes, synthèse, rapports

Évaluation des prévisions
    update_weo_editions    éditions récentes du WEO (API SDMX du FMI)
    evaluate_forecasts     prévisions d'époque confrontées au réalisé, risque de récession
    revisions_weo          révisions d'une édition du WEO à la suivante
    calibration            fourchettes et probabilités de récession éprouvées en temps réel

Export
    scenarios              scénarios de PIB par habitant et de population jusqu'en 2050, pour le trafic
    cas_de_crise           une récession mondiale dans les prévisions (hors chaîne)
    millesimes_bm          éditions archivées des WDI : révisions du réalisé

Livrables
    visualize_gdp          graphiques et tableau de bord
    build_results_page     page de résultats HTML

Chaque module se lance depuis la racine du dépôt (`python -m pib.gdp_pipeline`) ;
`produire_rapports.py` enchaîne le tout.
"""
