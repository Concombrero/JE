import requests
import time
import random
import csv
import os
from tools import Address, Coords, Contact, Street, Data
from interface import Logger


class BDNB:
    
    def __init__(self):
        self.base_url = 'https://api.bdnb.io/v1/bdnb/'
        self.last_request_time = time.time()
        self.minute_per_requests = 1/120 # 120 requests per minute
        
    
    def get_id(self, address_str, logger: Logger) -> str:
        """
        Récupère l'ID BDNB pour une adresse donnée.
        """
        params = {
            'q': address_str,
            'limit': '1'
        }
        
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        wait_time = self.minute_per_requests - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        
        try:
            response = requests.get(self.base_url + 'geocodage', params=params)
            self.last_request_time = time.time()
            response.raise_for_status()
            data = response.json()
            
            if data['features']:
                return data['features'][0]['properties']['id']
            else:
                logger.log(f"Pas d'ID trouvé pour l'adresse: {address_str}")
                return None
        except Exception as e:
            logger.log(f"Erreur lors de la récupération de l'ID pour l'adresse {address_str}: {e}")
            return None
    
    
    def get_data(self, bdnb_id, logger: Logger):
        """
        Récupère les données pour un ID BDNB donné.
        """
        
        params = {
            'cle_interop_adr': f"eq.{bdnb_id}",
            'limit': '1'
        }
        
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        wait_time = self.minute_per_requests - elapsed
        if wait_time > 0:
            time.sleep(wait_time)

        try:
            response = requests.get(f"{self.base_url}/donnees/batiment_groupe_complet/adresse", params=params)
            response.raise_for_status()
            data = response.json()

            if data:
                return self.extract_data(data[0], bdnb_id,logger)

        except Exception as e:
            logger.log(f"Erreur lors de la récupération des données pour l'ID {bdnb_id}: {e}")
            return None
        
    def conso_elec(self, bdnb_id, logger: Logger):
        """
        Récupère la consommation électrique pour un ID BDNB donné.
        """
        
        params = {
            'cle_interop_adr': f"eq.{bdnb_id}",
            'limit': '1'
        }
        
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        wait_time = self.minute_per_requests - elapsed
        if wait_time > 0:
            time.sleep(wait_time)

        try:
            response = requests.get(f"{self.base_url}/donnees/batiment_groupe_dle_elec_multimillesime/adresse", params=params)
            response.raise_for_status()
            data = response.json()

            if data:
                return data[0].get("consomation_energie", None)

        except Exception as e:
            logger.log(f"Erreur lors de la récupération des données (consommation électrique) pour l'ID {bdnb_id}: {e}")
            return None


    def extract_data(self, data_json, bdnb_id, logger: Logger) -> Data:
        """
        Extrait les informations pertinentes du JSON de données BDNB.
        """
        data = {
            "annee_construction": data_json.get("annee_construction", None),
            "classe_bilan_dpe": data_json.get("classe_bilan_dpe", None),
            "consomation_energie": self.conso_elec(bdnb_id, logger)
            }

        return data