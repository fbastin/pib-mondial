# Revue de littérature : incertitude des projections de PIB du FMI et prévision du trafic aérien

*30 septembre 2026.* Revue préparée en vue d'une publication qui s'appuierait sur les analyses de ce dépôt.

**Méthode.** Trois recherches, menées en parallèle :
- l'évaluation des prévisions du WEO ;
- l'incertitude tirée des erreurs passées ;
- le lien entre PIB et trafic aérien.

Chaque référence a été vérifiée en ligne : métadonnées Crossref, page de l'éditeur, IDEAS/RePEc, ou texte intégral pour les rapports. Les points non vérifiés sont signalés. Les références complètes sont dans `docs/references.bib` ; les clés BibTeX sont données entre crochets.

**En une phrase.** Le biais optimiste du FMI, son incapacité à prévoir les récessions, la perte de niveau après 2008 et l'idée de fourchettes tirées des erreurs passées sont établis. Trois choses ne le sont pas :
- nos fourchettes de niveau à 5 ans, conditionnées par la croissance projetée et le groupe de revenu, pour environ 190 pays ;
- nos probabilités de récession conditionnelles à la projection ;
- surtout, la propagation de l'erreur du FMI, ainsi calibrée, aux prévisions de trafic aérien.

---

## 1. Les prévisions du WEO : ce qui est établi

| Notre résultat | Déjà établi par | Statut |
|---|---|---|
| Biais optimiste, croissant avec l'horizon, plus fort pour les pays pauvres | Timmermann (2007), BIE du FMI (2014), de Resende (2014), Celasun et al. (2021), Ho et Mauro (2016), Aldenhoff (2007) | Établi |
| Le biais tient aux récessions non prévues | BIE (2014), Genberg et Martinez (2014), de Resende (2014), Dovern et Jannsen (2017) | Établi ; confirmé sur nos données |
| Récessions non annoncées un an à l'avance | Loungani (2001), Juhn et Loungani (2002), Genberg et Martinez (2014), An, Jalles et Loungani (2018) | Établi |
| Avantage sur une prévision naïve qui s'efface avec l'horizon | Timmermann (2007), Celasun et al. (2021) | Établi |
| Surestimation croissant avec la croissance projetée (pente < 1) | Ho et Mauro (2016), Carrière-Swallow et Marzluf (2023), Eicher et Rollinson (2023), Frankel (2011) | Partiel : l'idée existe, pas nos pentes par horizon |
| Correction tardive, révisions peu corrélées | Timmermann (2007), Hadzi-Vaskov et al. (2023) ; contra : An et al. (2018), Ashiya (2006), Aktuğ et Rezghi (2025) | Partiel, à discuter |
| Pas de retour à la trajectoire après 2008 | Fatás et Summers (2018), Ball (2014), Cerra et Saxena (2008) | Établi ; notre résultat l'étend |

### 1.1 Biais optimiste

**Évaluations du WEO.**
- **[Timmermann2007]** Les prévisions de croissance du WEO sont surestimées, surtout à un an et pour les pays sous programme du FMI. Les révisions d'avril à septembre de l'année en cours sont négatives en moyenne.
- **[IEO2014]** Le Bureau indépendant d'évaluation (BIE) du FMI juge les prévisions de bonne qualité et sans biais systématique hors récession, mais fortement optimistes autour des récessions : erreur médiane d'environ −6,3 points les années de récession, contre environ 0 les autres.
- **[deResende2014]** À 3-5 ans, l'erreur moyenne va de −0,44 à −0,76 point, avec la convention réalisé − prévu (l'inverse de la nôtre). L'effet cesse d'être significatif à 5 ans une fois exclues les grandes récessions.
- **[Celasun2021]** Pour les éditions 2004-2017, pas de biais sur l'année en cours et la suivante, sauf pour les pays à faible revenu. À 2-5 ans, le biais est de +0,3 à +0,5 point en médiane, plus fort pour les petites économies émergentes et à faible revenu.

**Économie politique et conséquences.**
- **[Aldenhoff2007]** et **[Dreher2008]** relient une partie du biais à des facteurs politiques, notamment les élections américaines, les crédits du FMI et les votes à l'ONU.
- **[BeaudryWillems2022]** en mesure les conséquences : surestimer la croissance d'un point la réduit d'environ un point trois ans plus tard, par l'endettement.
- **[Batchelor2001]** et **[Artis1996]** portent sur le G7 et comparent le FMI et l'OCDE à Consensus Economics.

**L'objection qu'un relecteur fera.** Le biais disparaît presque une fois exclues les années de récession [IEO2014 ; GenbergMartinez2014 ; deResende2014 ; DovernJannsen2017]. Nos données le confirment :

| Biais de croissance, en points | Ensemble | Hors années de recul de chaque pays | Hors 2009 et 2020 |
|---|---|---|---|
| À 1 an, moyenne / médiane / pondérée par le PIB | +1,00 / +0,34 / +0,58 | −0,11 / +0,01 / +0,02 | +0,62 (moyenne) |
| À 5 ans, moyenne / médiane / pondérée par le PIB | +0,93 / +0,62 / +0,81 | −0,14 / +0,25 / +0,17 | +0,52 (moyenne) |

- Les récessions mondiales n'en rendent pas compte ; les reculs propres à chaque pays, si. L'exclusion selon le résultat est en partie mécanique, puisqu'elle retire les grosses erreurs positives.
- **Cadrage proposé :** la trajectoire du FMI est à peu près juste hors récession, et l'erreur de niveau vient des reculs qu'elle omet. C'est précisément ce que nos probabilités de récession documentent.

### 1.2 Régression vers la moyenne

- **[HoMauro2016]** C'est le texte le plus proche : les éditions d'avril 1990-2012, pour 188 pays, jusqu'à 5 ans. Le biais croît avec l'horizon, jusqu'à environ 0,34 point par an. Il est plus fort quand la production est sous sa tendance et avant les programmes du FMI. Les projections de long terme sont plus optimistes qu'un retour à la moyenne ne le justifierait.
- **[PritchettSummers2014]** et **[Easterly1993]** en donnent le fondement : la croissance d'un pays persiste peu d'une décennie à l'autre (corrélation de 0,1 à 0,3).
- **[Frankel2011 ; FrankelSchreger2013]** Les prévisions officielles des gouvernements sont plus optimistes en haut de cycle et à 3 ans ou plus.
- **[CarriereSwallowMarzluf2023]** L'excès d'optimisme à deux ans se concentre dans les prévisions les plus fortes et suit l'expansion du crédit.
- **[EicherRollinson2023]** Les reprises à forte croissance sont surestimées dans les programmes du FMI.
- **Non trouvé :** des pentes de Mincer-Zarnowitz poolées par horizon, comme nos 0,74 puis 0,57. Timmermann les estime pays par pays.

### 1.3 Récessions non prévues

- **[Loungani2001]** À partir des prévisions privées de Consensus Economics : « the record of failure to predict recessions is virtually unblemished ».
- **[JuhnLoungani2002]** Sur 72 récessions (1989-1999), très peu sont prévues un an avant ; deux tiers restent inaperçues en avril de l'année même.
- **[GenbergMartinez2014]** Pour 185 pays (1991-2011), 13 % des observations sont des reculs. 12 % sont annoncés en avril de l'année précédente, contre 10 % dans nos données, et les pays à faible revenu sont les moins bien prévus.
- **[An2018]** Pour 63 pays (1992-2014), 5 récessions sur 153 sont annoncées en avril de l'année précédente, et les prévisions du FMI et de Consensus sont presque identiques. Les booms sont aussi manqués. Leur test de type Nordhaus donne un coefficient positif et significatif.
- **[DovernJannsen2017]** Les erreurs dépendent de l'état du cycle : fortement négatives en récession, légèrement positives en reprise.
- **Non trouvé :**
  - la fréquence des projections négatives au-delà de l'année en cours (Genberg et Martinez s'arrêtent à un an) ;
  - les fenêtres de 5 ans (3 % de reculs annoncés, 45 % survenus) ;
  - la probabilité de recul conditionnelle à la croissance projetée.

### 1.4 Révisions

- **[Nordhaus1987]** Une prévision efficace a des révisions non corrélées ; il trouve un lissage presque partout.
- **Revisions lissées, sur d'autres données :**
  - [LounganiStekler2013], sur les prévisions de Consensus ;
  - [Ashiya2006], sur le FMI et l'OCDE ;
  - [DovernWeisser2011], sur des prévisionnistes du G7 ;
  - [CoibionGorodnichenko2015], qui propose un test complémentaire (erreur régressée sur la révision).
- **[HadziVaskov2023]** Les révisions du WEO sont plus grandes et plus négatives près de l'année visée.
- **[AktugRezghi2025]** À l'inverse, ils concluent à une sur-réaction du WEO, croissante avec l'horizon.
- **Nos corrélations faibles, de −0,09 à +0,18, sont intermédiaires.** Il faudra les expliquer : fréquence semestrielle, choix des couples d'horizons, et contraste avec le coefficient positif d'An et al.

### 1.5 La crise de 2008 et les pertes durables

- **[FatasSummers2018]** C'est le plus proche de notre cas d'étude. À partir des projections à 5 ans du WEO d'avril 2007, rebasées sur 2006, ils calculent les erreurs de croissance cumulée pour 34 économies avancées. Elles croissent de 2009 à 2015, sans retour à la tendance. Notre résultat (6 à 18 % sous la trajectoire d'avant-crise) le confirme et l'étend à tous les pays et à toutes les éditions ; il n'est pas nouveau.
- **Perte de niveau durable après les crises :**
  - [Ball2014] : potentiel de 2014 inférieur de 8,4 % en moyenne au chemin de 2007 ;
  - [CerraSaxena2008] : pertes durables après les crises financières, et excès d'optimisme avant ;
  - [ReinhartRogoff2009 ; ReinhartRogoff2014] : durée des sorties de crise bancaire ;
  - [Blanchard2015], et le survol [CerraFatasSaxena2023] : hystérèse.
- **[Coibion2018]** Les estimations en temps réel du potentiel ne s'ajustent que graduellement. C'est le mécanisme des révisions successives du moyen terme.
- **[Pain2014]** Côté OCDE : prévisions trop hautes pendant toute la crise et la reprise.

---

## 2. Fourchettes tirées des erreurs passées

### 2.1 Le principe est ancien et répandu

- **[WilliamsGoodman1971]** C'est la référence fondatrice : limites de confiance empiriques tirées des erreurs de prévision passées.
- **Pratiques des banques centrales :**
  - Banque d'Angleterre [Britton1998] : de 1993 à 1996, l'erreur absolue moyenne des dix années précédentes, puis une loi normale à deux morceaux ;
  - BCE [ECB2009] : deux fois l'erreur absolue moyenne, valeurs extrêmes exclues ;
  - Réserve fédérale [ReifschneiderTulip2019] : écart quadratique moyen poolé sur plusieurs prévisionnistes ;
  - Banque de réserve d'Australie [TulipWallace2012].
- **Estimation et évaluation :**
  - [Knuppel2014] : estimation efficace entre horizons, utile quand les erreurs à 5 ans sont peu nombreuses et se chevauchent ;
  - [Clements2004 ; Clements2018] : les densités spécifiques au prévisionniste font rarement mieux qu'une incertitude historique poolée, ce qui éclaire l'échec de nos fourchettes par pays ;
  - [Fair1980] : l'approche par modèle, pour contraste.
- **Au FMI :**
  - [ElekdagKannan2009] : le graphique en éventail du WEO, pour la croissance mondiale seulement, à court terme, avec une loi paramétrique ajustée sur les marchés ;
  - [IMF2022] : dans le cadre de soutenabilité de la dette, les erreurs passées d'un pays à 1, 3 et 5 ans sont déjà comparées à celles de ses pairs par groupe de revenu, mais pour les déterminants de la dette, comme signal de réalisme ;
  - [EstefaniaFlores2023] : les erreurs de dette du WEO à 5 ans avoisinent 10 % du PIB.
- **[Kaack2017]** Le précédent le plus fort en dehors de l'économie : des intervalles empiriques pour les projections énergétiques officielles américaines, à des horizons de plusieurs années, évalués hors échantillon par le score probabiliste continu (CRPS), et destinés aux utilisateurs.

### 2.2 Appliqué au WEO : le travail le plus proche

**[Becker2025]** construit des intervalles autour des prévisions du WEO pour le PIB et l'inflation du G7, à partir de quantiles empiriques des erreurs absolues passées, par pays et sur fenêtre glissante, pour l'année en cours et la suivante. La couverture est proche de la cible. **À citer impérativement.** Notre travail s'en distingue sur plusieurs points :

| | Becker, Krüger et Schienle (2025) | Nos fourchettes |
|---|---|---|
| Grandeur | Croissance | Niveau du PIB |
| Horizon | 0 à 1 an | Jusqu'à 5 ans |
| Pays | G7 | Environ 190 |
| Conditionnement | Par pays | Classe de croissance projetée × groupe de revenu |
| Forme | Symétrique (erreurs absolues) | Asymétrique (quantiles des erreurs signées) |
| Fourchettes propres au pays | Réussies à court terme | Échouent à 5 ans (67 % de couverture pour une cible de 80 %) |

Voir aussi [KrugerPlett2024], des intervalles pour les prévisions à date fixe (Allemagne, États-Unis).

### 2.3 Conditionnement et cadre formel

- **Croissance conditionnelle :**
  - [Adrian2019 ; Adrian2022] (« croissance à risque ») : la distribution de la croissance dépend des conditions financières, surtout sa queue basse ;
  - [IsengildinaMassa2010] : régression quantile des erreurs d'une prévision officielle (USDA), selon le délai de prévision.
- **Cadre conforme.** Nos cellules forment une partition « de Mondrian » : une prédiction conforme conditionnelle par groupe [Vovk2013]. L'échangeabilité est violée par le chevauchement des fenêtres et la corrélation des pays en crise, ce que traitent [Barber2023], [GibbsCandes2021] et [Chernozhukov2021]. Notre test hors échantillon est la bonne vérification.
- **Probabilités de récession.**
  - [EstrellaMishkin1998] : modèles probit, à court terme et pour les États-Unis.
  - Notre probabilité à 5 ans, conditionnelle à la projection, n'a pas d'équivalent trouvé.
  - Son gain est modeste : score de Brier de 0,250 contre 0,279, soit une compétence d'environ 0,10. Il faut le dire.
  - Règles de score : [GneitingRaftery2007].

---

## 3. PIB et trafic aérien

### 3.1 Élasticité-revenu

- **[GalletDoucouliagos2014]** Méta-analyse : élasticité de base de 1,19, 1,55 pour l'international, 0,63 dans les spécifications dynamiques avec les prix. C'est la référence pour une distribution a priori de l'élasticité.
- **[InterVISTAS2007]** Pour l'IATA, des valeurs de jugement par type de marché et par distance : États-Unis, court-courrier 1,6 ; autres pays développés 1,3 ; pays en développement 1,8. Elles baissent aux revenus élevés, et les estimations propres ne sont pas robustes.
- **L'élasticité baisse avec la maturité du marché :**
  - [Graham2006] ;
  - EUROCONTROL [Eurocontrol2022] ;
  - le modèle de long terme de l'OACI [ICAO_LTF] ;
  - des modèles régionaux comme [Cheze2011].
- **[Valdes2015]** Dans les pays à revenu intermédiaire, la croissance du revenu, multipliée par une élasticité légèrement supérieure à 1, explique environ 75 % de la croissance des passagers. L'optimisme du FMI pour ces pays passe donc presque entièrement dans le trafic.
- **[Hanson2022]** L'élasticité dépend de l'état du cycle : plus faible pendant les reprises. Appliquée aux prévisions du FMI, le trafic retrouve son niveau de 2019 environ trois ans après le PIB. C'est le texte le plus proche de notre question sur les reprises.
- **Contexte :**
  - [Brons2002] : élasticité-prix ;
  - [Boonekamp2018] : compagnies à bas coûts, liens ethniques et emploi lié à l'aviation ;
  - [ChiBaek2013] : effets durables des chocs sur le niveau du trafic.

### 3.2 Des prévisions de trafic optimistes, et une erreur tracée jusqu'au PIB

- **[SuhRyerson2019]** Les erreurs des prévisions aéroportuaires viennent de l'incertitude économique et de l'optimisme des planificateurs. Les auteurs les corrigent par les erreurs passées d'aéroports comparables. C'est l'analogue méthodologique le plus proche, mais calibré sur les erreurs de trafic, pas sur celles du PIB.
- **[Flyvbjerg2005]** Biais d'optimisme des prévisions de trafic des grands projets de transport, et prévision par classe de référence.
- **[GAO2016]** Les prévisions de la FAA surestiment le trafic : +14,7 % à 5 ans pour les embarquements. « An important factor affecting forecast accuracy was the inaccuracy of the inputs … such as gross domestic product and fuel prices — resulting from events such as the 2007–2009 recession. » Le GAO recommande de publier l'incertitude.
- **[FAA2026]** Annexe sur l'exactitude : la variance des erreurs sur le PIB est semblable à celle des erreurs sur le trafic, « a substantial amount of the forecast variance for the traffic variables is attributable to the forecast error in the exogenous variables ». Même le scénario pessimiste de la FAA n'a pas de recul du PIB.
- **[DfT2017]** Paragraphe 4.28 : la prévision de 2009 « used economic inputs that pre-dated the recession, so it is unsurprising that its forecast was significantly too high ». Les données de PIB étranger viennent du WEO du FMI.

### 3.3 Le traitement de l'incertitude

- **Monte-Carlo sur le PIB autour de la trajectoire centrale :**
  - le guide des aéroports américains [ACRP76] ;
  - l'OCDE/FIT [ITF2016], qui demande aussi de tenir compte « des marges de risque des prévisions des facteurs clés » ;
  - l'Airports Commission britannique [AirportsCommission2014], autour du WEO d'avril 2014 ;
  - [DraySchafer2023].

  L'incertitude y est calibrée sur la variabilité historique de la croissance, symétrique, sans biais ni omission des récessions.
- **Le précédent le plus proche d'une incertitude calibrée sur des erreurs de prévision : [DfT2013].** Le Département des Transports britannique y adopte l'éventail de l'OBR, l'office britannique de responsabilité budgétaire, construit sur les erreurs officielles passées. Mais seulement pour le PIB britannique, en bornes à 20 % et 80 %, sans correction de biais ; le PIB étranger ne varie que de ±1 point.
- **Aéroports de Paris, berceau de la méthode de Kenza qu'utilise le projet trafic [Sallier2010Kenza], prévoit le trafic en probabilités depuis 2003** (Monte-Carlo et bootstrap) [ADP2011].
  - La note de 2011 demande des prévisions probabilistes des entrées, dont le PIB : « not a very common and ready to use type of forecast sold by economical data providers ». Les événements exceptionnels y forment une loi des résidus multimodale.
  - [Sallier2010PIB] construit donc la sienne, faute d'offre : une telle prévision « n'existe pas sur étagère à titre gracieux, ni même onéreux ». Modèles de tendance et de cycle, lois empiriques des erreurs relatives par horizon tirées de tests hors échantillon, et, pour les horizons lointains, extrapolation de l'écart-type de l'erreur avec l'horizon. La note rappelle une élasticité du trafic au PIB d'environ 2,3.
  - **Différence avec notre approche :** ces lois d'erreur sont celles des modèles d'ADP, pas celles de la projection qui alimente effectivement les prévisions. Nous calibrons sur les erreurs passées du FMI : son biais et ses récessions omises y entrent. En retour, l'extrapolation de Sallier répond à notre limite au-delà de l'horizon du WEO (`docs/scenarios_trafic.md`).
  - Deux notes internes, non publiées : à citer comme pratique d'un grand aéroport, pas comme littérature évaluée par les pairs. Une présentation de 2013 du même auteur, *LT probabilist GDP forecast*, figure dans le même dossier ; son format (.ppt) n'a pas permis de la lire.
- **Planification adaptative sous incertitude profonde :** [Kwakkel2010 ; Kwakkel2012].
- **La pratique industrielle injecte des trajectoires ponctuelles :**
  - [IATA2026] : « the single GDP forecasts from the IMF » jusqu'en 2030 ;
  - [Eurocontrol2024] : bandes symétriques autour des données d'Oxford Economics ;
  - Airbus et l'OACI : scénarios.

  Aucune ne donne de probabilité de récession calibrée sur l'historique.

### 3.4 La reprise après les chocs

- **[IATA2008]**, en décembre 2008 :
  - le trafic resterait sous sa tendance, « 9% lower by 2016 than pre-crisis industry forecasts » ;
  - « travel volumes rarely return to the previous trend » ;
  - le transport aérien varie « at roughly twice the rate of the overall economy ».
- **[Eurocontrol2010]** La prévision de long terme de 2010 a « environ 5 ans de retard » sur celle de 2008, à taux de croissance semblables : un déplacement de niveau, pendant de nos 6 à 18 % de PIB.
- **[Pearce2012]** Le trafic international et le fret retrouvent leur niveau d'avant la récession en moins de 18 mois ; le transport aérien reste élastique au revenu.
- **[DobruszkesVanHamme2011]** Les variations de l'offre de sièges en 2008-2010 dépendent fortement de la croissance du PIB de chaque pays. États-Unis, Europe et Japon sont plus touchés. C'est la meilleure étude reliant la reprise inégale au PIB réalisé, mais pas à l'écart entre PIB réalisé et projeté.
- **Autres :**
  - [FrankeJohn2011] : réponses de l'offre ;
  - [Smeral2010] : tourisme ;
  - [Gudmundsson2021] : durée de reprise après la COVID ;
  - [Sun2023] : reprise hétérogène après 2020.
- **Pour 2020, [IATA2026] parle d'un « structural gap » avec la tendance d'avant la COVID**, qu'aucun scénario ne comble. Mais les restrictions de voyage empêchent d'y lire le seul effet du revenu (voir `docs/cas_crise_2020.md`).

---

## 4. Positionnement

**Déjà établi — à citer, en présentant notre travail comme une extension :**
1. le biais optimiste du WEO, et son origine dans les récessions non prévues ;
2. l'échec à prévoir les récessions, et l'avantage sur une prévision naïve qui s'efface avec l'horizon ;
3. des fourchettes tirées des erreurs passées, y compris autour du WEO, mais pour le G7 et à court terme [Becker2025] ;
4. l'absence de retour à la trajectoire après 2008, mesurée sur les éditions du WEO [FatasSummers2018] ;
5. des erreurs de trafic attribuées aux erreurs de PIB, à titre de diagnostic [GAO2016 ; FAA2026 ; DfT2017], et des Monte-Carlo sur le PIB en planification aéroportuaire [ACRP76 ; AirportsCommission2014 ; ADP2011].

**Apparemment nouveau (aucun précédent trouvé) :**
1. **Des fourchettes calibrées du niveau du PIB à 5 ans autour des projections du WEO, pour environ 190 pays, éprouvées en temps réel** (`pib.calibration`). Chaque édition de 2000 à 2019 reçoit des fourchettes tirées des seules erreurs connues à sa date :
   - elles contiennent 79 % des erreurs (intervalle de confiance de 76 à 82 %, par bootstrap en blocs d'années visées), mais de 66 à 86 % selon l'édition ;
   - tirées de l'historique propre de chaque pays, elles n'en contiennent que 58 %, ce qui contraste avec la réussite des fenêtres par pays de Becker et al. à court terme.

   Le conditionnement n'améliore les scores que par le groupe de revenu et pondéré par le PIB : score d'intervalle de 33,5 contre 36,0 pour une fourchette unique, écart significatif. Sans pondération, méthode retenue, classe de croissance seule et fourchette unique se valent (score d'intervalle et CRPS). **L'article doit donc revendiquer des fourchettes poolées et calibrées en temps réel, pas un gain du conditionnement par la croissance projetée.**
2. **Une probabilité par pays d'au moins une année de recul à 5 ans**, conditionnelle à la projection : 3 % de reculs annoncés, 45 % survenus. En temps réel, compétence de 7,2 % sur une probabilité unique (score de Brier ; intervalle de 4,5 à 10,2 %), qui vient de la classe de croissance. Les probabilités sont bien ordonnées mais trop basses sur 2000-2019 (38 % en moyenne pour 49 % de périodes avec recul) : leur niveau dépend des crises de la période d'apprentissage. La trajectoire du FMI, prise comme une probabilité de 0 ou 1, fait bien pire (Brier supérieur de 79 %).
3. **La propagation de l'erreur du FMI, ainsi calibrée, aux prévisions de trafic aérien** : son biais, sa dépendance à la croissance projetée et au revenu, les récessions omises. Aucune étude, prévision officielle ou industrielle trouvée ne le fait ; l'IATA injecte la trajectoire ponctuelle du FMI. Aéroports de Paris propage bien un PIB probabiliste au trafic, mais calibré sur les erreurs de ses propres modèles, et dans des notes internes [Sallier2010PIB ; ADP2011].
4. **Pour 2008, décomposer l'écart du trafic aux prévisions d'avant-crise** en écart du PIB aux projections d'avant-crise, multiplié par l'élasticité. Les pièces existaient séparément [IATA2008 ; Eurocontrol2010 ; DobruszkesVanHamme2011 ; Hanson2022] ; c'est fait pour l'Europe et les États-Unis : 30 à 45 % du retard du trafic en 2013, mais rien des différences entre pays européens (`docs/cas_crise_2008.md`).

**Cadrage proposé.** Hors récession, la trajectoire du FMI est à peu près juste. L'erreur de niveau vient des reculs qu'elle omet, plus fréquents là où la croissance projetée est modeste. D'où deux compléments à la trajectoire médiane, à propager au trafic : une fourchette de niveau et une probabilité de récession.

## 5. À faire avant de soumettre

- **Fait** (`pib.calibration`) :
  - score d'intervalle et CRPS à côté de la couverture [Becker2025 ; Kaack2017] ;
  - fiabilité et compétence de Brier pour les probabilités ;
  - couverture par cellule et par édition ;
  - bootstrap par blocs d'années visées ;
  - calibration en temps réel, édition par édition, plutôt qu'une coupure unique en 2007.
- **Le niveau des probabilités de récession :** corrigé en traitant à part les crises mondiales (fréquence sur l'historique depuis 1961). La compétence passe de 7,2 à 11,8 %, mais les probabilités restent un peu basses (41 % pour 49 %) : avant 2009, le seul exemple de crise était 1991, modérée. À discuter dans l'article.
- **Le biais hors années de recul de chaque pays :** le publier, avec sa limite mécanique.
- **Nos corrélations de révisions :** les expliquer face à celles d'An et al. (2018) et d'Aktuğ et Rezghi (2025).
- **La propagation au trafic :**
  - des élasticités incertaines, dépendant de la maturité [GalletDoucouliagos2014 ; InterVISTAS2007] et de l'état du cycle [Hanson2022] ;
  - distinguer, pour 2020, le retard imputable aux restrictions de voyage.
- **Revues envisageables :**
  - *Journal of Air Transport Management* ou *Transport Policy*, pour l'angle appliqué ;
  - *Transportation Research Part E* (où a paru Suh et Ryerson) ou *Part A*, si la partie trafic est substantielle ;
  - *International Journal of Forecasting*, avec la partie méthode renforcée.

## Références écartées, faute de vérification

Barrionuevo (1993) ; Ahir et Loungani (2014, présentation seulement) ; Zhu et al. (2020) ; Niemeier (2013) ; Maldonado (1990) ; la méthode de Boeing (*Commercial Market Outlook*) ; une prépublication arXiv d'août 2026 sur la prédiction conforme selon le régime, non évaluée par les pairs.
