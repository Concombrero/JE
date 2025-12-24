"""Module de traitement des adresses - Copié depuis src_1"""

import math
import time
import requests
import json
import os
from tools import Coords, Address, Street
from interface import Logger
from typing import Dict, List


class AddressProcessor:
    def __init__(self):
        #self.ban_url = "https://api-adresse.data.gouv.fr/"
        self.ban_url = "https://data.geopf.fr/geocodage/"
        self.ban_last_request = 0
        self.ban_request_seconds = 1/50
        
    def address_to_coordinates(self, address: Address, logger: Logger) -> Coords:
        """
        Convertit une adresse en coordonnées latitude/longitude
        """
        logger.log(f'Reccupération des coordonnées de l\'adresse {address}')
        
        if not address:
            logger.log(f'Echec du reccupération de l\'adresse. Adresse vide', level="ERROR")
            return None
        
        # Rate limiting to avoid hitting the API too frequently
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
            
            logger.log(f'Requête au près de la BAN')
            response = requests.get(f"{self.ban_url}search/", params={"q": adr_str}, timeout=10)
            
            self.ban_last_request = time.time()
            
            logger.log(f'Traitement de la réponse')
            coords = response.json()['features'][0]['geometry']['coordinates']
            coords: Coords = {"longitude": coords[0],
                              "latitude": coords[1]}
            return coords
        
        except Exception as e:
            logger.log(f"Erreur lors de la recherche des coordonnées pour l'adresse '{address}': {e}", level="ERROR")
            return None

    def coordinates_to_address(self, coords: Coords, logger: Logger) -> Address:
        """
        Convertit des coordonnées latitude/longitude en adresse
        """
        logger.log(f'Récupération de l\'adresse correspondante aux coordonnées {coords}')
        
        if not coords or len(coords) != 2:
            logger.log(f'Les coordonnées ne sont pas au bon format')
            return None
        
        
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            logger.log(f'Requête au près de la BAN')
            response = requests.get(f"{self.ban_url}reverse/", params={"lon": coords['longitude'], "lat": coords['latitude'], "limit": 1})
            self.ban_last_request = time.time()
            
            logger.log(f'Traitement de la réponse')
            properties = response.json()['features'][0]['properties']
            adress: Address = {"numero": properties['housenumber'],
                            "voie": properties['street'],
                            "code_postal": properties['postcode'],
                            "ville": properties['city']}
            return adress
        except Exception as e:
            logger.log(f"Erreur lors de la recherche de l'adresse pour les coordonnées {coords}: {e}", level="ERROR")
            return None


    def calculate_bounding_box(self, coords: Coords, radius_km: float, logger: Logger) -> Dict:
        """
        Calcule la boîte englobante pour une zone circulaire autour des coordonnées
        """
        logger.log(f'Calcul de la boîte englobante pour les coordonnées {coords} avec un rayon de {radius_km} km')
        
        if not coords or len(coords) != 2:
            logger.log(f'Les coordonnées ne sont pas au bon format', level="ERROR")
            return None
        
        latitude = coords['latitude']
        longitude = coords['longitude']
        
        lat_offset = radius_km / 111.32  # 1 degré de latitude ≈ 111.32 km
        lon_offset = radius_km / (111.32 * math.cos(math.radians(latitude)))
        
        return {
            'south': latitude - lat_offset,
            'north': latitude + lat_offset,
            'west': longitude - lon_offset,
            'east': longitude + lon_offset
        }


    def is_valid_adress(self, address: Address, logger: Logger) -> bool:
        """
        Vérifie si l'adresse est valide
        """
        
        logger.log(f'Vérification de l\'adresse {address}')
        if not address:
            logger.log(f'Adresse vide', level="ERROR")
            return False
        
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"

            logger.log(f'Requête au près de la BAN pour vérifier l\'adresse {address}')
            response = requests.get(f"{self.ban_url}search/", params={"q": adr_str}, timeout=10)
            
            self.ban_last_request = time.time()
            
            detail = response.json()['features'][0]
            if "housenumber" in detail['properties']:
                logger.log(f"L'adresse {address} est valide")
                return True
            else:
                logger.log(f"L'adresse {address} n'est pas valide")
                return False
            
        except Exception as e:
            logger.log(f"Erreur lors de la vérification de l'adresse '{address}': {e}", level="ERROR")
            return False


    def get_street_number(self, street: Street, logger: Logger) -> None:
        """
        Récupère les numéros d'une rue donnée et actualise le dictionnaire de la rue
        """
        logger.log(f'Récupération des numéros pour la rue {street["name"]}')
        numbers = []
        centaine = 0
        number_finded = True
        while number_finded:
            logger.log(f'Verification des nombres de {centaine*50 + 1} à {(centaine + 1) * 50}')
            number_finded = False
            for i in range(centaine * 50 + 1, (centaine + 1) * 50 + 1):
                address = {
                    "numero": i,
                    "voie": street["name"],
                    "code_postal": street["postal_code"],
                    "ville": street["city"]
                }
                if self.is_valid_adress(address, logger):
                    logger.log(f'Numéro trouvé: {i}')
                    numbers.append(str(i))
                    number_finded = True
                else:
                    logger.log(f'Numéro non trouvé: {i}')
            
            centaine += 1
        street["numbers"] = numbers


    def save_street_to_json(self, street: Street, output_file: os.path) -> None:
        """
        Convertit le dictionnaire des rues en une chaîne JSON
        """
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(street, f, ensure_ascii=False, indent=4)
    
    def get_city_and_postal_code_from_coords(self, coords: Coords, logger: Logger):
        """
        Récupère la ville et le code postal à partir des coordonnées
        """
        address = self.coordinates_to_address(coords, logger)
        if address:
            return address['ville'], str(address['code_postal'])
        return "", ""


    def get_streets_in_area(self, center_lat: float, center_lon: float, radius_km: float, logger: Logger, dir_street: os.path):
        street_names = self.get_street_names(center_lat, center_lon, radius_km)
        logger.both(f"{len(street_names)} rues trouvées", "SUCCESS")
        city, postal_code = self.get_city_and_postal_code_from_coords({"latitude": center_lat, "longitude": center_lon}, logger)
        compteur = 0
        for name in street_names:
            logger.both(f"Traitement de la rue {compteur+1}/{len(street_names)}: {name}", "PROGRESS")
            compteur += 1
            street: Street = {
                "name": name,
                "city": city,
                "postal_code": postal_code,
                "numbers": []
            }
            self.get_street_number(street, logger)
            save = os.path.join(dir_street, f"{street['name'].replace('/', '_').replace(' ', '_')}.json")
            self.save_street_to_json(street, save)

    def get_street_names(self, lat, lon, distance_km):
        distance_m = int(distance_km * 1000)
        query = f"""
        [out:json];
        way(around:{distance_m},{lat},{lon})["highway"]["name"];
        out tags;
        """
        url = "https://overpass-api.de/api/interpreter"
        response = requests.get(url, params={"data": query})
        response.raise_for_status()
        data = response.json()

        # Extraire les noms uniques
        streets = {el["tags"]["name"] for el in data.get("elements", []) if "tags" in el and "name" in el["tags"]}
        return streets
