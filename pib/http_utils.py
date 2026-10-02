#!/usr/bin/env python3
"""
http_utils.py
-------------
Accès HTTP commun aux deux collecteurs (Banque Mondiale, FMI).

Une API injoignable ne doit jamais se traduire par un jeu de données partiel livré
comme complet : après quelques tentatives espacées, l'échec remonte sous forme
d'exception, à charge pour l'appelant d'interrompre le traitement.
"""

import time
import logging
from typing import Any, Dict, Optional

import requests

# Le site du FMI refuse certaines requêtes sans agent de navigateur.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def get_json(url: str, params: Optional[Dict[str, Any]] = None,
             tentatives: int = 3, pause: float = 2.0, timeout: int = 30,
             headers: Optional[Dict[str, str]] = None) -> Any:
    """
    Interroge `url` et retourne la réponse JSON décodée.

    Les erreurs réseau, HTTP et de décodage sont retentées `tentatives` fois, avec une
    pause croissante ; la dernière est levée en `RuntimeError`. `headers` complète les
    en-têtes par défaut (l'API SDMX du FMI ne répond en JSON que sur demande).
    """
    return _interroger(url, params, tentatives, pause, timeout, headers, lambda r: r.json())


def get_texte(url: str, params: Optional[Dict[str, Any]] = None,
              tentatives: int = 3, pause: float = 2.0, timeout: int = 30,
              headers: Optional[Dict[str, str]] = None) -> str:
    """Comme `get_json`, mais retourne le texte de la réponse (CSV de l'API SDMX du FMI)."""
    return _interroger(url, params, tentatives, pause, timeout, headers, lambda r: r.text)


def _interroger(url, params, tentatives, pause, timeout, headers, lire) -> Any:
    """Requête GET retentée (voir `get_json`) ; `lire` extrait le contenu de la réponse."""
    derniere = None
    for essai in range(1, tentatives + 1):
        try:
            response = requests.get(url, params=params, headers={**HEADERS, **(headers or {})},
                                    timeout=timeout)
            response.raise_for_status()
            return lire(response)
        except (requests.RequestException, ValueError) as e:
            derniere = e
            if essai < tentatives:
                attente = pause * essai
                logging.warning(f"{url} : échec {essai}/{tentatives} ({e}), "
                                f"nouvel essai dans {attente:.0f} s.")
                time.sleep(attente)

    raise RuntimeError(f"{url} injoignable après {tentatives} tentatives : {derniere}")
