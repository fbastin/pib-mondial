import pandas as pd
import os

# Emplacements possibles du classeur, dans l'ordre de recherche :
# le dossier du script (usage autonome), puis data/raw/ du pipeline principal,
# qui l'utilise aussi via evaluate_forecasts.py. Une seule copie suffit.
DOSSIER = os.path.dirname(os.path.abspath(__file__))
EMPLACEMENTS = [
    os.path.join(DOSSIER, "WEOhistorical.xlsx"),
    os.path.join(DOSSIER, "..", "data", "raw", "WEOhistorical.xlsx"),
]


def trouver_classeur():
    """Retourne le premier emplacement où le classeur est présent, sinon None."""
    for chemin in EMPLACEMENTS:
        if os.path.exists(chemin):
            return chemin
    return None


def get_all_weo_historical_gdp(file_path):
    """
    Charge et transforme l'historique complet des prédictions de croissance du PIB 
    pour tous les pays depuis le fichier WEOhistorical.xlsx.
    """
    if not os.path.exists(file_path):
        print(f"Erreur : Le fichier '{file_path}' est introuvable dans le dossier actuel.")
        return None

    print(f"Chargement du fichier '{file_path}'...")
    print("(Cela peut prendre quelques secondes vu le volume de données)")
    
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
    NOM_FICHIER_EXCEL = trouver_classeur()

    if NOM_FICHIER_EXCEL is None:
        print("Erreur : 'WEOhistorical.xlsx' introuvable. Cherché dans :")
        for chemin in EMPLACEMENTS:
            print(f"  - {os.path.normpath(chemin)}")
        print("Téléchargement : voir Documentation_WEO_FMI.md")
        raise SystemExit(1)

    print(f"Classeur trouvé : {os.path.normpath(NOM_FICHIER_EXCEL)}")

    # Exécution de la fonction
    df_all_countries = get_all_weo_historical_gdp(NOM_FICHIER_EXCEL)

    if df_all_countries is not None:
        print("\nAperçu des données :")
        print(df_all_countries.head(10))
        
        # Sauvegarde à côté du script, et non dans le répertoire courant :
        # le classeur d'entrée est lui aussi cherché relativement au script.
        filename = os.path.join(DOSSIER, "weo_forecasts_all_countries.csv")
        print(f"\nSauvegarde en cours vers '{filename}'...")
        
        df_all_countries.to_csv(filename, index=False)
        
        print("Sauvegarde réussie ! Vous pouvez maintenant utiliser ce CSV pour vos analyses.")
