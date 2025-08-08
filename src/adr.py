"""Module de traitement des adresses"""

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
            logger.log(f'Verification des nombres de {centaine*100 + 1} à {(centaine + 1) * 100}')
            number_finded = False
            for i in range(centaine * 100 + 1, (centaine + 1) * 100 + 1):
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
        
    def get_streets_in_area(self, center_lat: float, center_lon: float, radius_km: float, logger: Logger, dir_street: os.path):
        """
        Récupère les rues dans un rayon spécifié autour d'un point central
        Sauvegarde chaque rue au format JSON dans le répertoire spécifié
        """
        
        logger.log(f'Récupération des rues dans un rayon de {radius_km} km autour du point ({center_lat}, {center_lon})')
        bounding_box = self.calculate_bounding_box({'latitude': center_lat, 'longitude': center_lon}, radius_km, logger)
        
        if not bounding_box:
            logger.log(f'Erreur lors du calcul de la boîte englobante', level="ERROR")
            return []
        
        streets_name = set()  # Utilise un set pour éviter les doublons
        step = 0.0001
        
        logger.log(f'Calcul du nombre total d\'itérations pour le pourcentage')
        # Calcul du nombre total d'itérations pour le pourcentage
        lat_steps = int((bounding_box['north'] - bounding_box['south']) / step) + 1
        lon_steps = int((bounding_box['east'] - bounding_box['west']) / step) + 1
        total_iterations = lat_steps * lon_steps
        
        logger.log(f"Total d'itérations: {total_iterations}")
        
        
        current_iteration = 0
        last_percentage = -1
        
        logger.log(f'Début de la récupération des rues')
        lat = bounding_box['south']
        while lat <= bounding_box['north']:
            lon = bounding_box['west']
            while lon <= bounding_box['east']:
                # Affichage du pourcentage tous les 10%
                percentage = int((current_iteration / total_iterations) * 100)
                if percentage >= last_percentage + 10:
                    logger.console(f"Progression: {percentage}%")
                    last_percentage = percentage
                
                # Récupération de l'adresse pour ces coordonnées
                coords = {'latitude': lat, 'longitude': lon}
                logger.log(f'Récupération de l\'adresse pour les coordonnées {coords}')
                address = self.coordinates_to_address(coords, logger)
                
                
                if address and address.get('voie'):
                    if address['voie'] not in streets_name:
                        logger.log(f"Rue trouvée: {address['voie']}")
                        streets_name.add(address['voie'])
                        street= {
                            "name": address['voie'],
                            "city": address['ville'],
                            "postal_code": address['code_postal'],
                            "numbers": []
                        }
                        self.get_street_number(street, logger)
                        output_file = os.path.join(dir_street, f"{street['name']}.json")
                        self.save_street_to_json(street, output_file)
                        logger.both(f"Rue enregistrée dans {output_file}", "SUCCESS")                 
                current_iteration += 1
                lon += step
            lat += step
        print("Progression: 100%")
