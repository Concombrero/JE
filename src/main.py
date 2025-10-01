import os
import sys
import json
import csv
import time
from interface import Logger
from adr import AddressProcessor
from scrapper import ScrapperPageJaune

address_processor = AddressProcessor()
scraper_pj = ScrapperPageJaune()

def clear_terminal():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')
    
def print_header():
    print("="*60)
    print("Logiciel")
    print("="*60)
    
def get_user_address(logger: Logger):
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
    if address_processor.is_valid_adress(adress, logger):
        return adress
    else:
        logger.console("Adresse invalide, veuillez réessayer.")
        return get_user_address(logger)

def get_user_radius(logger: Logger):
    """Prompt the user for a radius in kilometers."""
    while True:
        try:
            radius = float(input("Entrez un rayon en kilomètres: "))
            if radius > 0:
                return radius
            else:
                logger.console("Le rayon doit être supérieur à 0.")
        except ValueError:
            logger.console("Veuillez entrer un nombre valide.")

def get_output_dirname():
    """
    Demande le nom du dossier de sortie

    Returns:
        str: Chemin du fichier de sortie
    """
    while True:
        dirname = input("Quel est le nom de la recherche ? ").strip()

        if not dirname:
            print("Le nom du dossier ne peut pas être vide.")

        
        dirname = os.path.join('output', dirname)
        # Vérifier si le dossier existe déjà
        if os.path.exists(dirname):
            print(f"Le dossier '{dirname}' existe déjà. Veuillez choisir un autre nom.")
        
        else:
            os.makedirs(dirname, exist_ok=True)
            return dirname


def start_logiciel():
    """
    MISE EN PLACE
    """
    clear_terminal()
    print_header()

    output_dirpath = get_output_dirname()

    logger = Logger(os.path.join(output_dirpath, 'log.txt'))
    logger.both("Démarrage du programme", "INFO")
    
    
    address = get_user_address(logger)
    logger.log(f"Adresse saisie: {address}", "DEBUG")

    radius = get_user_radius(logger)
    logger.log(f"Rayon saisi: {radius} km", "DEBUG")
    
    return address, radius, output_dirpath, logger


def get_streets(address, radius, output_dirpath, logger):
    """
    RÉCUPÉRATION DES RUES
    """
    logger.console(f"Passage à la récupération des coordonnées de l'adresse.", "PROGRESS")
    coords = address_processor.address_to_coordinates(address, logger)
    
    logger.log(f"Coordonnées récupérées: {coords}", "DEBUG")
    
    logger.console(f"Coordonnées récupérées: {coords}", "SUCCESS")
    
    logger.console(f"Passage à la récupération des rues dans un rayon de {radius} km autour des coordonnées.", "PROGRESS")

    
    dir_street = os.path.join(output_dirpath, 'streets')
    os.makedirs(dir_street, exist_ok=True)
    address_processor.get_streets_in_area(
        center_lat=coords['latitude'],
        center_lon=coords['longitude'],
        radius_km=radius,
        logger=logger,
        dir_street=dir_street
    )

    return dir_street


def process_street_pj(dir_street, output_dirpath, logger):
    """
    Traitement des rues
    """
    for file in os.listdir(dir_street):
        if file.endswith('.json'):
            file_path = os.path.join(dir_street, file)
            with open(file_path, 'r', encoding='utf-8') as f:
                street = json.load(f)
                logger.log(f"Traitement de la rue: {street}", "DEBUG")
                
                # Traitement de la rue
                scraper_pj.process_street(
                    street=street,
                    logger=logger,
                    output_dir=output_dirpath
                )

def main():
    try:
        
        address, radius, output_dirpath, logger = start_logiciel()
        
        # Démarer un timer
        start_time = time.time()

        dir_street = get_streets(address, radius, output_dirpath, logger)
        
        address_time = time.time()
        
        process_street_pj(dir_street, output_dirpath, logger)
        
        end_time = time.time()
        
        logger.both(f"Temps pour récupérer les rues: {address_time - start_time:.2f} secondes", "INFO")
        logger.both(f"Temps total d'exécution: {end_time - start_time:.2f} secondes", "INFO")
        logger.both("Programme terminé avec succès.", "SUCCESS")
        
        
    
    except Exception as e:
        logger.both(f"Une erreur s'est produite: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
