"""Fichier logiciel du projet."""

from adr import get_adrs


def main():
    """
    Fonction principale du programme.
    """
    
    ### Récupération du point d'origine
    org = {"longitude": 1.906557, "latitude": 43.898288}  # Exemple: 103 Rue d'Alger Gaillac
    
    ### Récupération rayon de recherche
    n_km = 1
    
    ### Récupération des adresses
    print("Récupération des adresses...")
    adrs = get_adrs(org, n_km)
    print(f"{len(adrs)} adresses trouvées.")
    



if __name__ == "__main__":
    main()
