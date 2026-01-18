#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Programme principal de prospection immobilière
Combine les workflows src_1 (Pages Jaunes) et src_2 (Entreprises)

Usage:
    python main.py          # Lance l'interface graphique Qt
    python main.py --cli    # Lance l'interface terminal

Modes d'exécution:
1. COMPLET: Adresse + rayon -> récupération rues -> scrapping PJ -> recherche entreprises -> fusion -> carte
2. DEPUIS DOSSIER: Charger un dossier de rues existant -> scrapping PJ -> recherche entreprises -> fusion -> carte  
3. CARTE SEULE: Afficher une carte existante
"""

import os
import sys
import webbrowser
from typing import List, Optional

from logger import Logger
from tools import Address, Street
from address_processor import AddressProcessor
from scrapper_pj import ScrapperPagesJaunes
from entreprises import EntrepriseSearcher
from fusion import fuse_results, save_fused_csv, load_fused_csv, fused_to_map_features
from map_generator import save_map_html


def clear_terminal():
    """Efface le terminal"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Affiche l'en-tête du programme"""
    print("=" * 60)
    print("    PROSPECTION IMMOBILIÈRE - Récupération de données")
    print("=" * 60)
    print()


def print_menu():
    """Affiche le menu principal"""
    print("Choisissez un mode d'exécution:")
    print()
    print("  1. WORKFLOW COMPLET")
    print("     Nouvelle recherche depuis une adresse")
    print()
    print("  2. REPRENDRE DEPUIS UN DOSSIER")
    print("     Charger un dossier de rues existant et lancer le scrapping")
    print()
    print("  3. AFFICHER UNE CARTE")
    print("     Ouvrir une carte existante ou un fichier CSV")
    print()
    print("  0. QUITTER")
    print()


def get_choice(prompt: str, valid_choices: List[str]) -> str:
    """Demande un choix à l'utilisateur"""
    while True:
        choice = input(prompt).strip()
        if choice in valid_choices:
            return choice
        print(f"Choix invalide. Options: {', '.join(valid_choices)}")


def get_user_address(logger: Logger) -> Address:
    """Demande l'adresse à l'utilisateur"""
    address_processor = AddressProcessor()
    
    print("\n--- Saisie de l'adresse de départ ---")
    
    while True:
        numero = input("Numéro de la voie: ").strip()
        voie = input("Nom de la voie: ").strip()
        code_postal = input("Code postal: ").strip()
        ville = input("Ville: ").strip()
        
        address: Address = {
            "numero": numero,
            "voie": voie,
            "code_postal": code_postal,
            "ville": ville
        }
        
        print("\nVérification de l'adresse...")
        if address_processor.is_valid_address(address, logger):
            logger.log(f"Adresse validee: {address}", "INFO")
            return address
        else:
            logger.console("Adresse invalide, veuillez reessayer.", "ERROR")


def get_radius(logger: Logger) -> float:
    """Demande le rayon de recherche"""
    while True:
        try:
            radius = float(input("Rayon de recherche en km: ").strip())
            if radius > 0:
                return radius
            print("Le rayon doit être supérieur à 0.")
        except ValueError:
            print("Veuillez entrer un nombre valide.")


def get_output_dirname() -> str:
    """Demande le nom du dossier de sortie"""
    while True:
        dirname = input("Nom de la recherche (dossier de sauvegarde): ").strip()
        
        if not dirname:
            print("Le nom ne peut pas être vide.")
            continue
        
        dirpath = os.path.join('output', dirname)
        
        if os.path.exists(dirpath):
            print(f"[ATTENTION] Le dossier '{dirpath}' existe deja.")
            overwrite = input("Voulez-vous l'utiliser quand meme ? (o/n): ").strip().lower()
            if overwrite == 'o':
                return dirpath
        else:
            os.makedirs(dirpath, exist_ok=True)
            return dirpath


def select_existing_folder() -> Optional[str]:
    """Permet de sélectionner un dossier existant"""
    output_dir = 'output'
    
    if not os.path.exists(output_dir):
        print("[ERREUR] Aucun dossier 'output' trouve.")
        return None
    
    folders = [f for f in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, f))]
    
    if not folders:
        print("[ERREUR] Aucun dossier de recherche trouve dans 'output'.")
        return None
    
    print("\nDossiers disponibles:")
    for i, folder in enumerate(folders, 1):
        streets_dir = os.path.join(output_dir, folder, 'streets')
        has_streets = os.path.exists(streets_dir) and any(f.endswith('.json') for f in os.listdir(streets_dir)) if os.path.exists(streets_dir) else False
        status = "✓ rues" if has_streets else "○ vide"
        print(f"  {i}. {folder} [{status}]")
    
    print(f"  0. Retour")
    
    choice = input("\nVotre choix: ").strip()
    
    try:
        idx = int(choice)
        if idx == 0:
            return None
        if 1 <= idx <= len(folders):
            return os.path.join(output_dir, folders[idx - 1])
    except ValueError:
        pass
    
    print("Choix invalide.")
    return None


def select_existing_file(extension: str = ".html") -> Optional[str]:
    """Permet de sélectionner un fichier existant"""
    output_dir = 'output'
    
    if not os.path.exists(output_dir):
        print("[ERREUR] Aucun dossier 'output' trouve.")
        return None
    
    # Chercher tous les fichiers avec l'extension donnée
    files = []
    for root, dirs, filenames in os.walk(output_dir):
        for filename in filenames:
            if filename.endswith(extension):
                files.append(os.path.join(root, filename))
    
    if not files:
        print(f"[ERREUR] Aucun fichier {extension} trouve.")
        return None
    
    print(f"\nFichiers {extension} disponibles:")
    for i, filepath in enumerate(files, 1):
        relpath = os.path.relpath(filepath, output_dir)
        print(f"  {i}. {relpath}")
    
    print(f"  0. Retour")
    
    choice = input("\nVotre choix: ").strip()
    
    try:
        idx = int(choice)
        if idx == 0:
            return None
        if 1 <= idx <= len(files):
            return files[idx - 1]
    except ValueError:
        pass
    
    print("Choix invalide.")
    return None


# ==================== WORKFLOW COMPLET ====================

def run_complete_workflow():
    """Exécute le workflow complet"""
    clear_terminal()
    print_header()
    print("MODE: WORKFLOW COMPLET\n")
    
    # Étape 0: Saisie des paramètres
    output_dirpath = get_output_dirname()
    logger = Logger(os.path.join(output_dirpath, 'log.txt'))
    logger.both("Démarrage du workflow complet", "INFO")
    
    address = get_user_address(logger)
    radius = get_radius(logger)
    
    logger.log(f"Adresse: {address}", "DEBUG")
    logger.log(f"Rayon: {radius} km", "DEBUG")
    
    # Étape 1: Récupération des rues
    logger.both("\nEtape 1: Recuperation des adresses...", "PROGRESS")
    
    address_processor = AddressProcessor()
    coords = address_processor.address_to_coordinates(address, logger)
    
    if not coords:
        logger.both("Impossible de géocoder l'adresse.", "ERROR")
        return
    
    logger.both(f"Coordonnées: {coords['latitude']:.6f}, {coords['longitude']:.6f}", "SUCCESS")
    
    dir_street = os.path.join(output_dirpath, 'streets')
    address_processor.get_streets_in_area(
        center_lat=coords['latitude'],
        center_lon=coords['longitude'],
        radius_km=radius,
        logger=logger,
        dir_street=dir_street
    )
    
    # Charger les rues
    streets = address_processor.load_all_streets_from_dir(dir_street, logger)
    
    if not streets:
        logger.both("Aucune rue trouvée.", "ERROR")
        return
    
    # Étape 2: Scrapping Pages Jaunes
    logger.both("\nEtape 2: Scrapping Pages Jaunes (navigateur visible)...", "PROGRESS")
    
    scrapper = ScrapperPagesJaunes()
    pj_results = []
    
    try:
        for i, street in enumerate(streets, 1):
            logger.both(f"Rue {i}/{len(streets)}: {street['name']}", "PROGRESS")
            results = scrapper.process_street(street, logger, output_dirpath)
            pj_results.extend(results)
    finally:
        scrapper.close_browser()
    
    # Étape 3: Recherche entreprises
    logger.both("\nEtape 3: Enrichissement entreprises...", "PROGRESS")
    
    entreprise_searcher = EntrepriseSearcher()
    entreprise_results = []
    
    # Enrichir les résultats PJ avec données entreprises
    if pj_results:
        logger.both(f"Enrichissement de {len(pj_results)} resultats PJ...", "INFO")
        pj_enriched = entreprise_searcher.process_pj_results(pj_results, logger)
        entreprise_results.extend(pj_enriched)
        logger.both(f"{len(pj_enriched)} entreprises enrichies depuis PJ", "SUCCESS")
    
    # Étape 4: Fusion des résultats
    logger.both("\nEtape 4: Fusion des resultats...", "PROGRESS")
    
    fused_data = fuse_results(pj_results, entreprise_results, logger)
    
    # Sauvegarder CSV fusionné
    fused_csv = os.path.join(output_dirpath, 'resultats_fusionnes.csv')
    save_fused_csv(fused_data, fused_csv, logger)
    
    # Étape 5: Génération de la carte
    logger.both("\nEtape 5: Generation de la carte interactive...", "PROGRESS")
    
    features = fused_to_map_features(fused_data)
    
    if features:
        map_file = os.path.join(output_dirpath, 'carte.html')
        radius_m = int(radius * 1000)
        
        save_map_html(
            center_lat=coords['latitude'],
            center_lon=coords['longitude'],
            radius_m=radius_m,
            features=features,
            output_file=map_file,
            title=f"Prospection - {address['ville']}"
        )
        
        logger.both(f"\nWorkflow termine!", "SUCCESS")
        logger.both(f"   Dossier: {output_dirpath}", "INFO")
        logger.both(f"   CSV fusionne: {fused_csv}", "INFO")
        logger.both(f"   Carte: {map_file}", "INFO")
        
        # Ouvrir la carte
        open_map = input("\nOuvrir la carte dans le navigateur ? (o/n): ").strip().lower()
        if open_map == 'o':
            webbrowser.open('file://' + os.path.abspath(map_file))
    else:
        logger.both("Aucune donnée avec coordonnées pour la carte.", "WARNING")


# ==================== DEPUIS DOSSIER ====================

def run_from_folder():
    """Lance le scrapping depuis un dossier de rues existant"""
    clear_terminal()
    print_header()
    print("MODE: REPRENDRE DEPUIS UN DOSSIER\n")
    
    folder = select_existing_folder()
    if not folder:
        return
    
    logger = Logger(os.path.join(folder, 'log.txt'))
    logger.both(f"Reprise depuis le dossier: {folder}", "INFO")
    
    # Charger les rues
    dir_street = os.path.join(folder, 'streets')
    
    if not os.path.exists(dir_street):
        logger.both(f"Pas de dossier 'streets' dans {folder}", "ERROR")
        return
    
    address_processor = AddressProcessor()
    streets = address_processor.load_all_streets_from_dir(dir_street, logger)
    
    if not streets:
        logger.both("Aucune rue trouvée dans le dossier.", "ERROR")
        return
    
    logger.both(f"{len(streets)} rues chargées", "SUCCESS")
    
    # Calculer le centre approximatif
    center_lat, center_lon = None, None
    for street in streets:
        if street.get("numbers"):
            addr_str = f"{street['numbers'][0]} {street['name']}, {street['postal_code']} {street['city']}"
            geo = address_processor.address_to_coordinates({
                "numero": street['numbers'][0],
                "voie": street['name'],
                "code_postal": street['postal_code'],
                "ville": street['city']
            }, logger)
            if geo:
                center_lat = geo['latitude']
                center_lon = geo['longitude']
                break
    
    # Étape 2: Scrapping Pages Jaunes
    logger.both("\nScrapping Pages Jaunes (navigateur visible)...", "PROGRESS")
    
    scrapper = ScrapperPagesJaunes()
    pj_results = []
    
    try:
        for i, street in enumerate(streets, 1):
            logger.both(f"Rue {i}/{len(streets)}: {street['name']}", "PROGRESS")
            results = scrapper.process_street(street, logger, folder)
            pj_results.extend(results)
    finally:
        scrapper.close_browser()
    
    # Recherche entreprises
    logger.both("\nEnrichissement entreprises...", "PROGRESS")
    
    entreprise_searcher = EntrepriseSearcher()
    entreprise_results = []
    
    # Enrichir les résultats PJ
    if pj_results:
        logger.both(f"Enrichissement de {len(pj_results)} resultats PJ...", "INFO")
        pj_enriched = entreprise_searcher.process_pj_results(pj_results, logger)
        entreprise_results.extend(pj_enriched)
        logger.both(f"{len(pj_enriched)} entreprises enrichies depuis PJ", "SUCCESS")
    
    # Fusion
    logger.both("\nFusion des resultats...", "PROGRESS")
    
    fused_data = fuse_results(pj_results, entreprise_results, logger)
    
    fused_csv = os.path.join(folder, 'resultats_fusionnes.csv')
    save_fused_csv(fused_data, fused_csv, logger)
    
    # Carte
    if center_lat and center_lon:
        logger.both("\nGeneration de la carte...", "PROGRESS")
        
        features = fused_to_map_features(fused_data)
        
        if features:
            map_file = os.path.join(folder, 'carte.html')
            
            # Estimer le rayon
            radius_m = 500  # Par défaut
            
            save_map_html(
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=radius_m,
                features=features,
                output_file=map_file,
                title="Prospection"
            )
            
            logger.both(f"\nTermine!", "SUCCESS")
            logger.both(f"   Carte: {map_file}", "INFO")
            
            open_map = input("\nOuvrir la carte ? (o/n): ").strip().lower()
            if open_map == 'o':
                webbrowser.open('file://' + os.path.abspath(map_file))
    else:
        logger.both("\nTermine! (pas de carte generee - coordonnees manquantes)", "SUCCESS")


# ==================== CARTE SEULE ====================

def run_map_only():
    """Affiche une carte existante"""
    clear_terminal()
    print_header()
    print("MODE: AFFICHER UNE CARTE\n")
    
    print("Que voulez-vous ouvrir ?")
    print("  1. Une carte HTML existante")
    print("  2. Générer une carte depuis un CSV")
    print("  0. Retour")
    
    choice = input("\nVotre choix: ").strip()
    
    if choice == "1":
        html_file = select_existing_file(".html")
        if html_file:
            print(f"\nOuverture de: {html_file}")
            webbrowser.open('file://' + os.path.abspath(html_file))
    
    elif choice == "2":
        csv_file = select_existing_file(".csv")
        if csv_file:
            logger = Logger(os.path.join(os.path.dirname(csv_file), 'log_carte.txt'))
            
            # Charger le CSV
            data = load_fused_csv(csv_file, logger)
            
            if not data:
                print("[ERREUR] Aucune donnee dans le CSV.")
                return
            
            # Trouver le centre
            valid_coords = [(d["latitude"], d["longitude"]) for d in data if d.get("latitude") and d.get("longitude")]
            
            if not valid_coords:
                print("[ERREUR] Aucune coordonnee valide dans les donnees.")
                return
            
            center_lat = sum(c[0] for c in valid_coords) / len(valid_coords)
            center_lon = sum(c[1] for c in valid_coords) / len(valid_coords)
            
            # Générer la carte
            map_file = csv_file.replace('.csv', '_carte.html')
            
            features = [d for d in data if d.get("latitude") and d.get("longitude")]
            
            save_map_html(
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=500,
                features=features,
                output_file=map_file,
                title="Carte depuis CSV"
            )
            
            print(f"\n[OK] Carte generee: {map_file}")
            
            open_map = input("Ouvrir la carte ? (o/n): ").strip().lower()
            if open_map == 'o':
                webbrowser.open('file://' + os.path.abspath(map_file))


# ==================== MAIN ====================

def main_cli():
    """Point d'entrée pour le mode terminal"""
    while True:
        clear_terminal()
        print_header()
        print_menu()
        
        choice = input("Votre choix: ").strip()
        
        if choice == "1":
            run_complete_workflow()
            input("\nAppuyez sur Entrée pour continuer...")
        
        elif choice == "2":
            run_from_folder()
            input("\nAppuyez sur Entrée pour continuer...")
        
        elif choice == "3":
            run_map_only()
            input("\nAppuyez sur Entrée pour continuer...")
        
        elif choice == "0":
            print("\nAu revoir!")
            sys.exit(0)
        
        else:
            print("Choix invalide.")
            input("\nAppuyez sur Entrée pour continuer...")


def main():
    """Point d'entrée principal - lance l'interface graphique par défaut"""
    # Vérifier si on veut le mode CLI
    if "--cli" in sys.argv or "-c" in sys.argv:
        main_cli()
    else:
        # Lancer l'interface graphique
        try:
            from ui import main as ui_main
            ui_main()
        except ImportError as e:
            print(f"Erreur: Impossible de charger l'interface graphique: {e}")
            print("Assurez-vous que PySide6 est installé: pip install PySide6 PySide6-WebEngine")
            print("\nLancement du mode terminal à la place...")
            main_cli()


if __name__ == "__main__":
    main()
