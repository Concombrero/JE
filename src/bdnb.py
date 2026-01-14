"""Module d'accès à la Base de Données Nationales des Bâtiments (BDNB)"""

import time
import requests
from typing import Dict, Any, Optional

from logger import Logger


class BDNB:
    """Classe pour interroger l'API BDNB"""
    
    def __init__(self):
        self.base_url = 'https://api.bdnb.io/v1/bdnb/'
        self.last_request_time = time.time()
        self.min_request_interval = 1/120  # 120 req/min max
        
    def _rate_limit(self):
        """Applique le rate limiting"""
        elapsed = time.time() - self.last_request_time
        wait_time = self.min_request_interval - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_request_time = time.time()
    
    def get_id(self, address_str: str, logger: Logger) -> Optional[str]:
        """Récupère l'ID BDNB pour une adresse donnée"""
        params = {
            'q': address_str,
            'limit': '1'
        }
        
        self._rate_limit()
        
        try:
            response = requests.get(
                self.base_url + 'geocodage', 
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('features'):
                return data['features'][0]['properties']['id']
            else:
                logger.log(f"Pas d'ID BDNB trouvé pour: {address_str}", "DEBUG")
                return None
                
        except Exception as e:
            logger.log(f"Erreur BDNB get_id: {e}", "ERROR")
            return None
    
    def get_data(self, bdnb_id: str, logger: Logger) -> Optional[Dict[str, Any]]:
        """Récupère les données BDNB pour un ID donné"""
        params = {
            'cle_interop_adr': f"eq.{bdnb_id}",
            'limit': '1'
        }
        
        self._rate_limit()
        
        try:
            response = requests.get(
                f"{self.base_url}donnees/batiment_groupe_complet/adresse", 
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data:
                return self._extract_data(data[0], logger)
            return None
            
        except Exception as e:
            logger.log(f"Erreur BDNB get_data: {e}", "ERROR")
            return None

    def _extract_data(self, data_json: Dict, logger: Logger) -> Dict[str, Any]:
        """Extrait les informations pertinentes du JSON BDNB"""
        return {
            "annee_construction": data_json.get("annee_construction"),
            "classe_bilan_dpe": data_json.get("classe_bilan_dpe"),
            "consommation_energie": data_json.get("consommation_energie")
        }
    
    def get_building_info(self, address_str: str, logger: Logger) -> Optional[Dict[str, Any]]:
        """Méthode combinée: récupère les infos BDNB pour une adresse"""
        bdnb_id = self.get_id(address_str, logger)
        if bdnb_id:
            return self.get_data(bdnb_id, logger)
        return None
