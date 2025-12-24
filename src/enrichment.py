#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrichment.py
Module qui fusionne les données des deux sources:
- Source 1: Pages Jaunes (scraping) + BDNB (bâtiment)
- Source 2: OSM/Overpass + API Recherche Entreprises + géocodage BAN

Pour chaque entreprise trouvée, on enrichit avec les deux sources.
"""

import sys
import time
from typing import Any, Dict, List, Optional
from tools import Address, EnrichedData
from interface import Logger

# Imports source 1
from bdnb import BDNB
from scrapper import ScrapperPageJaune
from adr import AddressProcessor

# Imports source 2
import recup_donnees_entreprises as rde


class EnrichmentManager:
    """
    Gère l'enrichissement des données entreprises avec les deux sources.
    """
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.bdnb = BDNB()
        self.scrapper_pj = ScrapperPageJaune()
        self.address_processor = AddressProcessor()
    
    def _init_scrapper(self):
        """Initialise le scrapper Pages Jaunes si nécessaire"""
        if self.scrapper_pj is None:
            self.logger.log("Initialisation du scrapper Pages Jaunes", "DEBUG")
            self.scrapper_pj = ScrapperPageJaune()
    
    def enrich_with_source1(self, name: str, address_str: str, lat: float, lon: float) -> Dict[str, Any]:
        """
        Enrichit avec la source 1 (Pages Jaunes + BDNB).
        
        Args:
            name: Nom de l'entreprise
            address_str: Adresse complète en string
            lat, lon: Coordonnées géographiques
            
        Returns:
            Dict avec les données PJ et BDNB
        """
        result = {
            'pagesjaunes_phone': None,
            'pagesjaunes_title': None,
            'bdnb_annee_construction': None,
            'bdnb_classe_dpe': None,
        }
        
        try:
            # Essayer de parser l'adresse pour le format attendu par Pages Jaunes
            parsed = self._parse_address_for_pj(address_str)
            if not parsed:
                self.logger.log(f"Impossible de parser l'adresse pour PJ: {address_str}", "DEBUG")
                return result
            
            # Scraping Pages Jaunes
            self._init_scrapper()
            self.logger.log(f"Scraping Pages Jaunes pour {name} à {address_str}", "DEBUG")
            contact = self.scrapper_pj.process_address(parsed, name, self.logger)
            
            if contact:
                result['pagesjaunes_phone'] = contact.get('phone')
                result['pagesjaunes_title'] = contact.get('title')
                self.logger.log(f"Contact PJ trouvé: {contact.get('phone')}", "DEBUG")
            else:
                self.logger.log(f"Aucun contact PJ trouvé pour {name}", "DEBUG")
            
            # Enrichissement BDNB
            self.logger.log(f"Enrichissement BDNB pour {address_str}", "DEBUG")
            bdnb_id = self.bdnb.get_id(address_str, self.logger)
            if bdnb_id:
                bdnb_data = self.bdnb.get_data(bdnb_id, self.logger)
                if bdnb_data:
                    result['bdnb_annee_construction'] = bdnb_data.get('annee_construction')
                    result['bdnb_classe_dpe'] = bdnb_data.get('classe_bilan_dpe')
                    self.logger.log(f"Données BDNB: année={bdnb_data.get('annee_construction')}, DPE={bdnb_data.get('classe_bilan_dpe')}", "DEBUG")
            
        except Exception as e:
            self.logger.log(f"Erreur enrichissement source 1: {e}", "ERROR")
        
        return result
    
    def enrich_with_source2(self, name: str, address_str: str) -> Dict[str, Any]:
        """
        Enrichit avec la source 2 (API entreprises + OSM).
        
        Args:
            name: Nom de l'entreprise
            address_str: Adresse complète en string
            
        Returns:
            Dict avec les données de l'API entreprises et OSM
        """
        result = {
            'osm_phones': [],
            'osm_emails': [],
            'osm_websites': [],
            'osm_socials': [],
            'osm_category': None,
            'company_siren': None,
            'company_siret': None,
            'company_nom': None,
            'company_naf': None,
            'company_libelle_naf': None,
            'dirigeants': [],
            'building_year': None,
            'roof_area_m2': None,
            'parking_area_m2': None,
            'owner_first_name': None,
            'owner_last_name': None,
            'owner_role': None,
        }
        
        try:
            self.logger.log(f"Enrichissement source 2 pour {name} à {address_str}", "DEBUG")
            data = rde.run_test(name, address_str)
            
            if not data:
                self.logger.log(f"Aucune donnée source 2 pour {name}", "DEBUG")
                return result
            
            # Contacts OSM
            contacts_osm = data.get('contacts_osm', {})
            result['osm_phones'] = contacts_osm.get('phones', [])
            result['osm_emails'] = contacts_osm.get('emails', [])
            result['osm_websites'] = contacts_osm.get('websites', [])
            result['osm_socials'] = contacts_osm.get('socials', [])
            
            # Catégories OSM
            osm_cats = contacts_osm.get('osm_categories', [])
            result['osm_category'] = ', '.join(osm_cats) if osm_cats else None
            
            # Données entreprise
            companies = data.get('companies', [])
            if companies:
                comp = companies[0]
                result['company_siren'] = comp.get('siren')
                result['company_siret'] = comp.get('siret_siege')
                result['company_nom'] = comp.get('nom_complet')
                result['company_naf'] = comp.get('naf')
                result['company_libelle_naf'] = comp.get('naf_libelle')
                result['dirigeants'] = comp.get('dirigeants', [])
            
            # Données bâtiment OSM
            result['building_year'] = data.get('building_year')
            result['roof_area_m2'] = data.get('roof_area_m2')
            result['parking_area_m2'] = data.get('parking_area_m2')
            
            # Owner (dirigeant principal)
            owner = data.get('owner', {})
            if owner:
                result['owner_first_name'] = owner.get('first_name')
                result['owner_last_name'] = owner.get('last_name')
                result['owner_role'] = owner.get('role')
            
            self.logger.log(f"Enrichissement source 2 réussi pour {name}", "DEBUG")
            
        except Exception as e:
            self.logger.log(f"Erreur enrichissement source 2 pour {name}: {e}", "ERROR")
        
        return result
    
    def enrich_business(self, name: str, address_str: str, category: str, 
                       distance_m: float, lat: float, lon: float) -> Optional[EnrichedData]:
        """
        Enrichit une entreprise avec les données des deux sources.
        
        Args:
            name: Nom de l'entreprise
            address_str: Adresse complète
            category: Catégorie OSM
            distance_m: Distance du centre de recherche
            lat, lon: Coordonnées
            
        Returns:
            EnrichedData ou None si échec
        """
        self.logger.log(f"Enrichissement complet pour {name}", "DEBUG")
        
        # Enrichissement source 2 (plus rapide, on le fait d'abord)
        source2_data = self.enrich_with_source2(name, address_str)
        
        # Enrichissement source 1 (scraping, plus lent)
        source1_data = self.enrich_with_source1(name, address_str, lat, lon)
        
        # Fusion des données
        enriched: EnrichedData = {
            'name': name,
            'address': address_str,
            'distance_m': distance_m,
            'lat': lat,
            'lon': lon,
            # Source 1
            'pagesjaunes_phone': source1_data.get('pagesjaunes_phone'),
            'pagesjaunes_title': source1_data.get('pagesjaunes_title'),
            'bdnb_annee_construction': source1_data.get('bdnb_annee_construction'),
            'bdnb_classe_dpe': source1_data.get('bdnb_classe_dpe'),
            # Source 2
            'osm_category': source2_data.get('osm_category'),
            'osm_phones': source2_data.get('osm_phones', []),
            'osm_emails': source2_data.get('osm_emails', []),
            'osm_websites': source2_data.get('osm_websites', []),
            'osm_socials': source2_data.get('osm_socials', []),
            'company_siren': source2_data.get('company_siren'),
            'company_siret': source2_data.get('company_siret'),
            'company_nom': source2_data.get('company_nom'),
            'company_naf': source2_data.get('company_naf'),
            'company_libelle_naf': source2_data.get('company_libelle_naf'),
            'dirigeants': source2_data.get('dirigeants', []),
            'building_year': source2_data.get('building_year'),
            'roof_area_m2': source2_data.get('roof_area_m2'),
            'parking_area_m2': source2_data.get('parking_area_m2'),
        }
        
        return enriched
    
    def _parse_address_for_pj(self, address_str: str) -> Optional[Address]:
        """
        Parse une adresse string pour le format attendu par Pages Jaunes.
        Formats acceptés:
        - "16, Chemin du Vieux Chêne, 38240, Meylan"
        - "16 Chemin du Vieux Chêne, 38240 Meylan"
        - "16 Chemin du Vieux Chêne 38240 Meylan"
        """
        try:
            import re
            
            # Nettoyer l'adresse en supprimant les virgules multiples et espaces superflus
            clean_addr = re.sub(r'\s*,\s*', ', ', address_str.strip())
            
            # Pattern 1: "numero, voie, code_postal, ville" (avec virgules)
            pattern1 = r'^(\d+),?\s+(.+?),\s*(\d{5}),?\s+(.+)$'
            match = re.match(pattern1, clean_addr)
            
            if match:
                return {
                    'numero': int(match.group(1)),
                    'voie': match.group(2).strip().rstrip(','),
                    'code_postal': int(match.group(3)),
                    'ville': match.group(4).strip()
                }
            
            # Pattern 2: "numero voie, code_postal ville" (une virgule)
            pattern2 = r'^(\d+)\s+(.+?),\s*(\d{5})\s+(.+)$'
            match = re.match(pattern2, clean_addr)
            
            if match:
                return {
                    'numero': int(match.group(1)),
                    'voie': match.group(2).strip(),
                    'code_postal': int(match.group(3)),
                    'ville': match.group(4).strip()
                }
            
            # Pattern 3: Sans virgule, rechercher le code postal
            parts = clean_addr.replace(',', ' ').split()
            if len(parts) >= 4:
                for i, part in enumerate(parts):
                    if re.match(r'^\d{5}$', part):
                        # Vérifier que le premier élément est bien un numéro
                        if parts[0].isdigit():
                            return {
                                'numero': int(parts[0]),
                                'voie': ' '.join(parts[1:i]),
                                'code_postal': int(part),
                                'ville': ' '.join(parts[i+1:])
                            }
            
            # Pattern 4: Adresse sans numéro (ex: "Place des Tuileaux, 38240, Meylan")
            pattern4 = r'^([^,\d]+),\s*(\d{5}),?\s+(.+)$'
            match = re.match(pattern4, clean_addr)
            
            if match:
                self.logger.log(f"Adresse sans numéro détectée: {address_str}", "DEBUG")
                return {
                    'numero': 0,  # Pas de numéro
                    'voie': match.group(1).strip(),
                    'code_postal': int(match.group(2)),
                    'ville': match.group(3).strip()
                }
                
        except Exception as e:
            self.logger.log(f"Erreur parsing adresse '{address_str}': {e}", "ERROR")
        
        return None
    
    def close(self):
        """Ferme les ressources (notamment Selenium)"""
        if self.scrapper_pj:
            self.scrapper_pj.close()
