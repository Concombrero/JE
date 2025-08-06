
import os
import sys
from adr import AddressProcessor


AddressProcessor = AddressProcessor()

def clear_terminal():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')
    
def print_header():
    print("="*60)
    print("Logiciel")
    print("="*60)
    
def get_user_address():
    """Prompt the user for an address."""
    numero = input("Entrez le numéro de la maison: ").strip()
    voie = input("Entrez le nom de la voie: ").strip()
    code_postal = input("Entrez le code postal: ").strip()
    ville = input("Entrez le nom de la ville: ").strip()
    adress = {
        "numero": numero,
        "voie": voie,
        "code_postal": code_postal,
        "ville": ville
    }
    if AddressProcessor.address_to_coordinates(adress):
        return adress
    else:
        print("Adresse invalide, veuillez réessayer.")
        return get_user_address()
    
def get_user_radius():
    """Prompt the user for a radius in kilometers."""
    while True:
        try:
            radius = float(input("Entrez un rayon en kilomètres: "))
            if radius > 0:
                return radius
            else:
                print("Le rayon doit être supérieur à 0.")
        except ValueError:
            print("Veuillez entrer un nombre valide.")
    
def get_output_filename():
    """
    Demande le nom du fichier de sortie
    
    Returns:
        str: Chemin du fichier de sortie
    """
    while True:
        filename = input("Nom du fichier de sortie (sans extension, défaut: 'streets'): ").strip()
        
        if not filename:
            filename = "streets"
        
        # Ajouter l'extension .json si nécessaire
        if not filename.endswith('.json'):
            filename += '.json'
        
        # Ajouter le chemin vers le dossier output
        output_path = os.path.join('output', filename)
        
        # Vérifier si le fichier existe déjà
        if os.path.exists(output_path):
            overwrite = input(f"Le fichier '{output_path}' existe déjà. L'écraser? (o/N): ")
            if overwrite.lower() not in ['o', 'oui', 'y', 'yes']:
                continue
        
        return output_path
    
def display_progress(message: str):
    """Affiche un message de progression"""
    print(f"\n ⏳ {message}...")
    
def display_success(message):
    """Affiche un message de succès"""
    print(f"✅ {message}")

def display_error(message):
    """Affiche un message d'erreur"""
    print(f"❌ Erreur: {message}")

def main():
    try:
        clear_terminal()
        print_header()
        
        address = get_user_address()
        radius = get_user_radius()
        
        display_progress("Récupération des coordonnées de l'adresse")
        coords = AddressProcessor.address_to_coordinates(address)
        
        if not coords:
            display_error("Impossible de récupérer les coordonnées de l'adresse.")
            sys.exit(1)
        
        display_success(f"Coordonnées récupérées avec succès. Latitude: {coords['latitude']}, Longitude: {coords['longitude']}")

        center_lat, center_lon = coords["latitude"], coords["longitude"]
        display_progress("Récupération des rues dans le rayon spécifié")
        
        streets = AddressProcessor.get_streets_in_area(center_lat, center_lon, radius)

        if not streets:
            display_error("Aucune rue trouvée dans le rayon spécifié.")
            sys.exit(1)
        
        display_success(f"{len(streets)} rues trouvées.")
        street_numbers = AddressProcessor.get_streets_number(streets)
        
        output_filename = get_output_filename()
        AddressProcessor.save_streets_to_json(street_numbers, output_filename)
        
        display_success(f"Les rues ont été enregistrées dans '{output_filename}'")
        print("Fin du programme.")
        
    except Exception as e:
        display_error(f"Une erreur s'est produite: {e}")
        sys.exit(1)
        

def test():
    """
    Fonction principale du programme.
    """
    
    ### Récupération du point d'origine
    coord =AddressProcessor.address_to_coordinates({
        "numero": 103,
        "voie": "Rue D'Alger",
        "code_postal": 81600,
        "ville": "Gaillac"
    })

    print(coord)

    adress = AddressProcessor.coordinates_to_address(coord)
    print(adress)
    
    """
    ### Récupération rayon de recherche
    n_km = 0.1
    
    streets = AddressProcessor.get_streets_in_area(org['latitude'], org['longitude'], n_km)
    print(f"Rues trouvées dans un rayon de {n_km} km autour de l'origine:")
    for street in streets:
        print(f" - {street}")"""

if __name__ == "__main__":
    main()
