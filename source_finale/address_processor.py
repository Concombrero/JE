"""Module de traitement des adresses - BAN et OSM"""

import math
import time
import json
import os
import requests
from typing import Dict, List, Optional, Set

from tools import Coords, Address, Street
from logger import Logger


class AddressProcessor:
    """Classe pour le traitement des adresses via la BAN et Overpass/OSM"""
    
    def __init__(self):
        self.ban_url = "https://data.geopf.fr/geocodage/"
        self.ban_last_request = 0
        self.ban_request_seconds = 1/50  # 50 req/sec max
        
    def _rate_limit(self):
        """Applique le rate limiting pour la BAN"""
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        self.ban_last_request = time.time()
        
    def address_to_coordinates(self, address: Address, logger: Logger) -> Optional[Coords]:
        """Convertit une adresse en coordonnées latitude/longitude"""
        logger.log(f'Récupération des coordonnées de l\'adresse {address}')
        
        if not address:
            logger.log('Échec: adresse vide', level="ERROR")
            return None
        
        self._rate_limit()
        
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
            response = requests.get(
                f"{self.ban_url}search/", 
                params={"q": adr_str}, 
                timeout=10
            )
            response.raise_for_status()
            
            coords = response.json()['features'][0]['geometry']['coordinates']
            return {"longitude": coords[0], "latitude": coords[1]}
            
        except Exception as e:
            logger.log(f"Erreur lors de la recherche des coordonnées: {e}", level="ERROR")
            return None

    def coordinates_to_address(self, coords: Coords, logger: Logger) -> Optional[Address]:
        """Convertit des coordonnées latitude/longitude en adresse"""
        logger.log(f'Récupération de l\'adresse pour les coordonnées {coords}')
        
        if not coords:
            logger.log('Coordonnées invalides', level="ERROR")
            return None
        
        self._rate_limit()
        
        try:
            response = requests.get(
                f"{self.ban_url}reverse/", 
                params={"lon": coords['longitude'], "lat": coords['latitude'], "limit": 1},
                timeout=10
            )
            response.raise_for_status()
            
            properties = response.json()['features'][0]['properties']
            return {
                "numero": properties.get('housenumber', ''),
                "voie": properties.get('street', ''),
                "code_postal": properties.get('postcode', ''),
                "ville": properties.get('city', '')
            }
            
        except Exception as e:
            logger.log(f"Erreur lors de la recherche de l'adresse: {e}", level="ERROR")
            return None

    def calculate_bounding_box(self, coords: Coords, radius_km: float) -> Optional[Dict]:
        """Calcule la boîte englobante pour une zone circulaire"""
        if not coords:
            return None
        
        latitude = coords['latitude']
        longitude = coords['longitude']
        
        lat_offset = radius_km / 111.32
        lon_offset = radius_km / (111.32 * math.cos(math.radians(latitude)))
        
        return {
            'south': latitude - lat_offset,
            'north': latitude + lat_offset,
            'west': longitude - lon_offset,
            'east': longitude + lon_offset
        }

    def is_valid_address(self, address: Address, logger: Logger) -> bool:
        """Vérifie si l'adresse est valide via la BAN"""
        logger.log(f'Vérification de l\'adresse {address}')
        
        if not address:
            return False
        
        self._rate_limit()
        
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
            response = requests.get(
                f"{self.ban_url}search/", 
                params={"q": adr_str}, 
                timeout=10
            )
            response.raise_for_status()
            
            detail = response.json()['features'][0]
            return "housenumber" in detail.get('properties', {})
            
        except Exception as e:
            logger.log(f"Erreur lors de la vérification de l'adresse: {e}", level="ERROR")
            return False

    def get_street_numbers(self, street: Street, logger: Logger) -> None:
        """Récupère les numéros valides d'une rue et met à jour le dict street"""
        logger.log(f'Récupération des numéros pour la rue {street["name"]}')
        numbers = []
        centaine = 0
        number_found = True
        
        while number_found:
            logger.log(f'Vérification des nombres de {centaine*50 + 1} à {(centaine + 1) * 50}')
            number_found = False
            
            for i in range(centaine * 50 + 1, (centaine + 1) * 50 + 1):
                address = {
                    "numero": str(i),
                    "voie": street["name"],
                    "code_postal": street["postal_code"],
                    "ville": street["city"]
                }
                if self.is_valid_address(address, logger):
                    logger.log(f'Numéro trouvé: {i}')
                    numbers.append(str(i))
                    number_found = True
            
            centaine += 1
        
        street["numbers"] = numbers

    def save_street_to_json(self, street: Street, output_file: str) -> None:
        """Sauvegarde une rue en JSON"""
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(street, f, ensure_ascii=False, indent=4)
    
    def load_street_from_json(self, file_path: str, logger: Logger) -> Optional[Street]:
        """Charge une rue depuis un fichier JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.log(f"Erreur lors du chargement de {file_path}: {e}", level="ERROR")
            return None

    def get_city_and_postal_code_from_coords(self, coords: Coords, logger: Logger) -> tuple:
        """Récupère la ville et le code postal à partir des coordonnées"""
        address = self.coordinates_to_address(coords, logger)
        if address:
            return address['ville'], str(address['code_postal'])
        return "", ""

    def get_street_names_in_area(self, lat: float, lon: float, radius_km: float, logger: Optional['Logger'] = None, max_retries: int = 3) -> Set[str]:
        """Récupère les noms de rues dans une zone via Overpass avec retry et fallback"""
        distance_m = int(radius_km * 1000)
        query = f"""
        [out:json];
        way(around:{distance_m},{lat},{lon})["highway"]["name"];
        out tags;
        """
        
        # Liste des serveurs Overpass avec fallback
        overpass_urls = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        ]
        
        last_error = None
        
        for url in overpass_urls:
            for attempt in range(max_retries):
                try:
                    if logger:
                        logger.log(f"Requête Overpass (tentative {attempt + 1}/{max_retries}) sur {url.split('/')[2]}")
                    
                    response = requests.get(url, params={"data": query}, timeout=60)
                    response.raise_for_status()
                    data = response.json()
                    
                    streets = {
                        el["tags"]["name"] 
                        for el in data.get("elements", []) 
                        if "tags" in el and "name" in el["tags"]
                    }
                    
                    if streets:
                        return streets
                    
                    # Si aucune rue trouvée, on continue avec un autre serveur
                    if logger:
                        logger.log(f"Aucune rue trouvée sur {url.split('/')[2]}, essai d'un autre serveur...")
                    break  # Passer au serveur suivant
                    
                except requests.exceptions.Timeout:
                    last_error = "Timeout"
                    if logger:
                        logger.log(f"Timeout sur {url.split('/')[2]}, tentative {attempt + 1}/{max_retries}", level="WARNING")
                    time.sleep(2 * (attempt + 1))  # Attente exponentielle
                    
                except requests.exceptions.RequestException as e:
                    last_error = str(e)
                    if logger:
                        logger.log(f"Erreur requête sur {url.split('/')[2]}: {e}", level="WARNING")
                    time.sleep(2 * (attempt + 1))
                    
                except Exception as e:
                    last_error = str(e)
                    if logger:
                        logger.log(f"Erreur inattendue sur {url.split('/')[2]}: {e}", level="WARNING")
                    time.sleep(1)
        
        if logger:
            logger.log(f"Échec de récupération des rues après tous les essais. Dernière erreur: {last_error}", level="ERROR")
        
        return set()

    def get_streets_in_area(
        self, 
        center_lat: float, 
        center_lon: float, 
        radius_km: float, 
        logger: Logger, 
        dir_street: str
    ) -> List[str]:
        """
        Récupère toutes les rues dans une zone et sauvegarde leurs numéros.
        Retourne la liste des fichiers JSON créés.
        """
        street_names = self.get_street_names_in_area(center_lat, center_lon, radius_km, logger=logger)
        
        if not street_names:
            logger.both("Aucune rue trouvée via Overpass. Vérifiez votre connexion ou réessayez.", "ERROR")
            return []
        
        logger.both(f"{len(street_names)} rues trouvées", "SUCCESS")
        
        city, postal_code = self.get_city_and_postal_code_from_coords(
            {"latitude": center_lat, "longitude": center_lon}, 
            logger
        )
        
        os.makedirs(dir_street, exist_ok=True)
        saved_files = []
        
        for idx, name in enumerate(street_names, 1):
            logger.both(f"Traitement de la rue {idx}/{len(street_names)}: {name}", "PROGRESS")
            
            street: Street = {
                "name": name,
                "city": city,
                "postal_code": postal_code,
                "numbers": []
            }
            
            self.get_street_numbers(street, logger)
            
            safe_name = name.replace('/', '_').replace(' ', '_')
            save_path = os.path.join(dir_street, f"{safe_name}.json")
            self.save_street_to_json(street, save_path)
            saved_files.append(save_path)
        
        return saved_files

    def load_all_streets_from_dir(self, dir_street: str, logger: Logger) -> List[Street]:
        """Charge toutes les rues depuis un dossier"""
        streets = []
        
        if not os.path.isdir(dir_street):
            logger.log(f"Le dossier {dir_street} n'existe pas", level="ERROR")
            return streets
        
        for file in os.listdir(dir_street):
            if file.endswith('.json'):
                file_path = os.path.join(dir_street, file)
                street = self.load_street_from_json(file_path, logger)
                if street:
                    streets.append(street)
        
        logger.log(f"{len(streets)} rues chargées depuis {dir_street}")
        return streets
