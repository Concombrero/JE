"""Module de traitement des adresses"""

import math
import time
import requests
import json
import os
from tools import Coords, Address
from typing import Dict


class AddressProcessor:
    def __init__(self):
        #self.ban_url = "https://api-adresse.data.gouv.fr/"
        self.ban_url = "https://data.geopf.fr/geocodage/"
        self.ban_last_request = 0
        self.ban_request_seconds = 1/50
        
    def address_to_coordinates(self, address: Address) -> Coords:
        """
        Convertit une adresse en coordonnées latitude/longitude
        """
        if not address:
            return None
        
        # Rate limiting to avoid hitting the API too frequently
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
            response = requests.get(f"{self.ban_url}search/", params={"q": adr_str}, timeout=10)
            
            self.ban_last_request = time.time()
            
            coords = response.json()['features'][0]['geometry']['coordinates']
            coords: Coords = {"longitude": coords[0],
                              "latitude": coords[1]}
            return coords
        except Exception as e:
            print(f"Erreur lors de la recherche des coordonnées pour l'adresse '{address}': {e}")
            return None

    def coordinates_to_address(self, coords: Coords) -> Address:
        """
        Convertit des coordonnées latitude/longitude en adresse
        """
        if not coords or len(coords) != 2:
            return None
        
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            response = requests.get(f"{self.ban_url}reverse/", params={"lon": coords['longitude'], "lat": coords['latitude'], "limit": 1})
            self.ban_last_request = time.time()
            
            properties = response.json()['features'][0]['properties']
            adress: Address = {"numero": properties['housenumber'],
                            "voie": properties['street'],
                            "code_postal": properties['postcode'],
                            "ville": properties['city']}
            return adress
        except Exception as e:
            print(f"Erreur lors de la recherche de l'adresse pour les coordonnées {coords}: {e}")
            return None
    
    
    def calculate_bounding_box(self, coords: Coords, radius_km: float) -> tuple:
        """
        Calcule la boîte englobante pour une zone circulaire autour des coordonnées
        """
        if not coords or len(coords) != 2:
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
        
    def get_streets_in_area(self, center_lat: float, center_lon: float, radius_km: float) -> Dict:
        """
        Récupère les rues dans un rayon spécifié autour d'un point central
        """
        bounding_box = self.calculate_bounding_box({'latitude': center_lat, 'longitude': center_lon}, radius_km)
        
        if not bounding_box:
            return []
        
        streets_name = set()  # Utilise un set pour éviter les doublons
        streets = {}
        step = 0.0001
        
        # Calcul du nombre total d'itérations pour le pourcentage
        lat_steps = int((bounding_box['north'] - bounding_box['south']) / step) + 1
        lon_steps = int((bounding_box['east'] - bounding_box['west']) / step) + 1
        total_iterations = lat_steps * lon_steps
        
        print(f"Total d'itérations: {total_iterations}")
        
        
        current_iteration = 0
        last_percentage = -1
        
        lat = bounding_box['south']
        while lat <= bounding_box['north']:
            lon = bounding_box['west']
            while lon <= bounding_box['east']:
                # Affichage du pourcentage tous les 10%
                percentage = int((current_iteration / total_iterations) * 100)
                if percentage >= last_percentage + 10:
                    print(f"Progression: {percentage}%")
                    last_percentage = percentage
                
                # Récupération de l'adresse pour ces coordonnées
                coords = {'latitude': lat, 'longitude': lon}
                address = self.coordinates_to_address(coords)
                
                if address and address.get('voie'):
                    if address['voie'] not in streets_name:
                        streets_name.add(address['voie'])
                        streets[address['voie']] = {"Ville ": address['ville'], "Code Postal": address['code_postal']}
                
                current_iteration += 1
                lon += step
            lat += step
            
        print("Progression: 100%")
        return streets
   
    def is_valid_adress(self, address: Address) -> bool:
        """
        Vérifie si l'adresse est valide
        """
        if not address:
            return None
        
        # Rate limiting to avoid hitting the API too frequently
        current_time = time.time()
        if current_time - self.ban_last_request < self.ban_request_seconds:
            time.sleep(self.ban_request_seconds - (current_time - self.ban_last_request))
        try:
            adr_str = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
            response = requests.get(f"{self.ban_url}search/", params={"q": adr_str}, timeout=10)
            
            self.ban_last_request = time.time()
            
            detail = response.json()['features'][0]
            if "housenumber" in detail['properties']:
                return True
            else:
                return False
            
        except Exception as e:
            print(f"Erreur lors de la recherche des coordonnées pour l'adresse '{address}': {e}")
            return False
        
    
    def get_streets_number(self, streets: Dict) -> Dict:
        """
        Récupère les numéros de rue pour chaque rue dans le dictionnaire
        """        
        for street, details in streets.items():
            print(f"Récupération des numéros pour la rue '{street}'")
            numbers = []
            centaine = 0
            number_finded = True
            while number_finded:
                print(centaine)
                number_finded = False
                for i in range(centaine*100 +1 , (centaine+1)*100 +1 ):
                    address = {
                        "numero": i,
                        "voie": street,
                        "code_postal": details.get("Code Postal"),
                        "ville": details.get("Ville ")
                    }
                    if self.is_valid_adress(address):
                        numbers.append(i)
                        number_finded = True
                centaine += 1

            streets[street]["Numéros"] = numbers
            streets[street]["Nombre de numéros"] = len(numbers)
            streets[street]["Maximum numéro"] = max(numbers) if numbers else 0
            streets[street]["Minimum numéro"] = min(numbers) if numbers else 0
            
        return streets

    def save_streets_to_json(self, streets: Dict, output_file: str) -> None:
        """
        Convertit le dictionnaire des rues en une chaîne JSON
        """
        
        if output_file and not output_file.endswith('.json'):
            output_file += '.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(streets, f, ensure_ascii=False, indent=4)
        
        
        
        