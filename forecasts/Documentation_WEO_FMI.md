# Documentation : Extraction des Prévisions Historiques du WEO (FMI)

Ce document explique comment télécharger les données du Fonds Monétaire International (FMI) et utiliser le script Python permettant de structurer l'historique complet des prévisions de croissance du Produit Intérieur Brut (PIB) pour l'ensemble des pays.

## 1. Téléchargement de la base de données

Le FMI met régulièrement à jour la structure de ses serveurs, ce qui rend difficile le téléchargement automatisé via des scripts. Il est recommandé de télécharger le fichier source (Excel) manuellement.

* **Lien de téléchargement direct (fichier utilisé) :** 
  [WEOhistorical.xlsx](https://data.imf.org/-/media/iData/External-Storage/Documents/977574FA66914EAD900D3FEC55C7316A/en/WEOhistorical.xlsx)

* **Page de recherche officielle (source) :**
  [Résultats de recherche IMF - WEO Historical Forecasts Database](https://data.imf.org/en/Search-Results#q=WEO%20Historical%20Forecasts%20Database&t=coveob02de888&sort=relevancy&f:idata_dataset_name=[World%20Economic%20Outlook%20(WEO)])

⚠️ **Avertissement de péremption :** Le FMI publie de nouvelles éditions du *World Economic Outlook* chaque printemps et automne. **Il est très probable que ces liens changent ou deviennent inactifs d'ici 2027.**
Si le lien direct est rompu, utilisez la page de recherche pour retrouver la dernière version du document `"WEOhistorical.xlsx"`.

---

## 2. Prérequis techniques

Le script nécessite Python 3 et les bibliothèques `pandas` et `openpyxl`.

> **Depuis le projet GDP**, inutile de créer quoi que ce soit : l'environnement du pipeline contient déjà ces deux bibliothèques.
>
> ```bash
> ~/.venvs/gdp/bin/python forecasts/fetch_forecasts.py
> ```
>
> La section ci-dessous ne concerne que l'usage de ce dossier **isolé du reste du projet**.

Si vous utilisez un système Linux (comme Ubuntu) avec des restrictions sur les paquets système (PEP 668), il est conseillé de créer un environnement virtuel — **en dehors de ce dossier** s'il est synchronisé (Nextcloud, Dropbox…) : un venv pèse une centaine de mégaoctets pour plusieurs milliers de fichiers, et ne se déplace pas une fois créé, ses chemins internes étant absolus.

```bash
# Création et activation de l'environnement virtuel
python3 -m venv ~/.venvs/weo
source ~/.venvs/weo/bin/activate

# Installation des dépendances
pip install pandas openpyxl
```

---

## 3. Le script Python (`fetch_forecasts.py`)

Le script cherche `WEOhistorical.xlsx` à deux emplacements, dans cet ordre :

1. le dossier du script — usage autonome, si vous ne voulez que les prévisions ;
2. `../data/raw/` — emplacement utilisé par le pipeline principal du projet.

Une seule copie du classeur suffit donc, où qu'elle soit. Les chemins sont résolus par rapport au script et non au répertoire courant : il s'exécute depuis n'importe où, et écrit toujours son CSV à côté de lui.

> Ce dossier est **indépendant du pipeline principal**. Celui-ci exploite le même classeur via `evaluate_forecasts.py`, qui confronte en plus chaque prévision à ce qui s'est réellement produit. Le script ci-dessous se limite à l'extraction, pour qui ne veut que les prévisions brutes.

```python
import pandas as pd
import os

def get_all_weo_historical_gdp(file_path):
    """
    Charge et transforme l'historique complet des prédictions de croissance du PIB 
    pour tous les pays depuis le fichier WEOhistorical.xlsx.
    """
    if not os.path.exists(file_path):
        print(f"Erreur : Le fichier '{file_path}' est introuvable dans le dossier actuel.")
        return None

    print(f"Chargement du fichier '{file_path}'...")
    
    # 1. Lire l'onglet de la croissance du PIB réel
    df = pd.read_excel(file_path, sheet_name='ngdp_rpch')
    
    # 2. Identifier les colonnes de base (identifiants) et les colonnes de prévisions
    id_vars = ['country', 'WEO_Country_Code', 'ISOAlpha_3Code', 'year']
    value_vars = [col for col in df.columns if col not in id_vars]
    
    print("Restructuration des données au format long (melt)...")
    
    # 3. Transformer de format "large" à format "long" (tidy data)
    df_long = pd.melt(df, id_vars=id_vars, value_vars=value_vars, 
                      var_name='vintage', value_name='value')
    
    # 4. Nettoyer la colonne vintage (ex: 'S1990ngdp_rpch' -> 'S1990')
    df_long['vintage'] = df_long['vintage'].str.replace('ngdp_rpch', '')
    
    print("Nettoyage des valeurs manquantes et conversion numérique...")
    
    # 5. Filtrer les valeurs manquantes brutes (les points '.')
    df_long = df_long[df_long['value'] != '.']
    
    # 6. Forcer la conversion en nombre (les erreurs deviennent NaN, puis on supprime les NaN)
    df_long['value'] = pd.to_numeric(df_long['value'], errors='coerce')
    df_long = df_long.dropna(subset=['value'])
    
    # 7. Trier les données logiquement
    print("Tri final des données...")
    df_long = df_long.sort_values(by=['ISOAlpha_3Code', 'year', 'vintage'])
    
    print(f"Terminé ! {len(df_long):,} prévisions ont été récupérées.")
    
    return df_long

if __name__ == "__main__":
    NOM_FICHIER_EXCEL = "WEOhistorical.xlsx" 
    
    df_all_countries = get_all_weo_historical_gdp(NOM_FICHIER_EXCEL)

    if df_all_countries is not None:
        filename = "weo_forecasts_all_countries.csv"
        df_all_countries.to_csv(filename, index=False)
        print(f"Sauvegarde réussie sous '{filename}'.")
```

---

## 4. Exécution et résultats

Pour lancer l'extraction :
```bash
python3 fetch_forecasts.py
```

### Structure du fichier de sortie (`weo_forecasts_all_countries.csv`)

Le script génère un fichier CSV d'environ 100 000 lignes, formaté de manière standard pour faciliter l'analyse (Tidy Data) :

| Colonne | Type | Description | Exemple |
| :--- | :--- | :--- | :--- |
| **country** | `Texte` | Nom du pays ou du groupe géographique | `France` |
| **WEO_Country_Code** | `Entier` | Identifiant interne du FMI | `132` |
| **ISOAlpha_3Code** | `Texte` | Code pays au format ISO-3 | `FRA` |
| **year** | `Entier` | L'année ciblée par la prévision | `2024` |
| **vintage** | `Texte` | La date à laquelle la prévision a été faite (S = Spring, F = Fall) | `S2023` |
| **value** | `Flottant` | La valeur de la croissance du PIB réel prévue (en %) | `1.34` |
