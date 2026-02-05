"""Module de scrapping des Pages Jaunes - NAVIGATEUR VISIBLE"""

import time
import random
import csv
import os
from typing import Optional, List, Dict, Any

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from tools import Address, Contact, Street, DataPJ
from logger import Logger
from address_processor import AddressProcessor
from address_comparator import AddressComparator
from bdnb import BDNB


class ScrapperPagesJaunes:
    """Scrapper Pages Jaunes avec navigateur visible"""
    
    def __init__(self):
        # Configuration Chrome - NAVIGATEUR VISIBLE
        self.options = Options()
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        # PAS de --headless pour voir le navigateur
        
        self.driver = None
        self.page_jaune_url = "https://www.pagesjaunes.fr"
        self.address_comparator = AddressComparator()
        self.address_processor = AddressProcessor()
        
    def start_browser(self):
        """Démarre le navigateur Chrome"""
        if self.driver is None:
            self.driver = webdriver.Chrome(options=self.options)
    
    def close_browser(self):
        """Ferme le navigateur"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_search_url(self, address: Address, logger: Logger) -> str:
        """Construit l'URL de recherche pour une adresse"""
        logger.log(f"Construction URL pour: {address}", "DEBUG")
        
        voie_url_str = f"{address['numero']}+{address['voie'].replace(' ', '+')}"
        url = (
            f"https://www.pagesjaunes.fr/annuaire/chercherlespros?"
            f"quoiqui=&ou={voie_url_str}%2C+{address['ville']}+%28{address['code_postal']}%29"
            f"&univers=pagesjaunes&idOu="
        )
        
        logger.log(f"URL: {url}", "DEBUG")
        return url

    def get_first_result_link(self, address: Address, logger: Logger) -> Optional[str]:
        """Récupère le premier lien de résultat"""
        try:
            self.start_browser()
            
            url = self.get_search_url(address, logger)
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))
            
            # Vérifier si on a été redirigé vers la page d'accueil (anti-bot)
            current_url = self.driver.current_url
            if current_url in ["https://www.pagesjaunes.fr/#", "https://www.pagesjaunes.fr/", "https://www.pagesjaunes.fr"]:
                logger.log("Redirection vers la page d'accueil détectée (possible blocage anti-bot)", "WARNING")
                return None
            
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            first_result = soup.find('div', class_='bi-content')
            if first_result:
                link = first_result.find('a', class_="bi-denomination")
                if link and link.get('href'):
                    href = link.get('href')
                    # Vérifier que le lien est valide (pas juste "#" ou vide)
                    if href and href not in ['#', '/#', ''] and href.startswith('/pros/'):
                        logger.log(f"Premier résultat trouvé: {href}", "DEBUG")
                        return href
                    else:
                        logger.log(f"Lien invalide ignoré: {href}", "DEBUG")
            
            logger.log("Aucun résultat trouvé sur Pages Jaunes", "DEBUG")
            return None
            
        except Exception as e:
            logger.log(f"Erreur lors de la recherche PJ: {e}", "ERROR")
            return None

    def get_phone_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """Extrait le numéro de téléphone du HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        bloc_coordonnees = soup.find('div', id='blocCoordonnees')
        
        if bloc_coordonnees:
            phone_elem = bloc_coordonnees.find('span', class_='coord-numero noTrad')
            if phone_elem:
                phone = phone_elem.get_text(strip=True)
                logger.log(f"Téléphone trouvé: {phone}", "DEBUG")
                return phone
        
        return None

    def get_address_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """Extrait l'adresse du HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        address_container = soup.find('div', class_='address-container marg-btm-s')
        if address_container:
            address_span = address_container.find('span', class_='noTrad')
            if address_span:
                address_text = address_span.get_text(strip=True)
                logger.log(f"Adresse trouvée: {address_text}", "DEBUG")
                return address_text
        
        return None

    def get_title_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """Extrait le titre de la page"""
        soup = BeautifulSoup(html, 'html.parser')
        title_elem = soup.find('title', id='metaTitle')
        
        if title_elem:
            title = title_elem.get_text(strip=True)
            logger.log(f"Titre trouvé: {title}", "DEBUG")
            return title
        
        return None

    def get_contact_from_url(self, url: str, logger: Logger) -> Optional[Contact]:
        """Récupère les informations de contact depuis une URL"""
        try:
            self.start_browser()
            
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))
            
            # Vérifier si on a été redirigé vers la page d'accueil
            current_url = self.driver.current_url
            if current_url in ["https://www.pagesjaunes.fr/#", "https://www.pagesjaunes.fr/", "https://www.pagesjaunes.fr"]:
                logger.log("Redirection vers la page d'accueil lors de la récupération du contact", "WARNING")
                return None
            
            html = self.driver.page_source
            
            phone = self.get_phone_from_html(html, logger)
            address = self.get_address_from_html(html, logger)
            title = self.get_title_from_html(html, logger)
            
            # Si aucune info n'a été trouvée, c'est probablement une page invalide
            if not phone and not address and not title:
                logger.log("Aucune information trouvée sur la page de contact", "DEBUG")
                return None
            
            return {
                'phone': phone or '',
                'title': title or '',
                'address': address or ''
            }
            
        except Exception as e:
            logger.log(f"Erreur récupération contact: {e}", "ERROR")
            return None

    def process_address(self, address: Address, logger: Logger) -> Optional[Contact]:
        """Traite une adresse pour récupérer les informations de contact"""
        logger.log(f"Traitement PJ de l'adresse: {address}", "DEBUG")
        
        first_link = self.get_first_result_link(address, logger)
        
        if not first_link:
            return None
        
        full_url = self.page_jaune_url + first_link
        time.sleep(random.uniform(2, 4))
        
        contact = self.get_contact_from_url(full_url, logger)
        
        if contact:
            address_str = contact.get('address', '')
            time.sleep(random.uniform(1, 2))
            
            # Vérifier que l'adresse correspond
            if self.address_comparator.is_address_match(address, address_str, logger):
                return contact
        
        return None

    def process_street(self, street: Street, logger: Logger, output_dir: str) -> List[DataPJ]:
        """Traite une rue complète"""
        bdnb = BDNB()
        
        logger.both(f"Traitement PJ de la rue: {street['name']}")
        results = []
        
        for number in street['numbers']:
            logger.log(f"Traitement du numéro: {number}", "DEBUG")
            
            address: Address = {
                'numero': number,
                'voie': street['name'],
                'code_postal': street['postal_code'],
                'ville': street['city']
            }
            
            contact = self.process_address(address, logger)
            coords = self.address_processor.address_to_coordinates(address, logger)
            
            data: DataPJ = {
                'address': address,
                'coords': coords,
                'contact': contact,
                'bdnb': None
            }
            
            # Récupérer les données BDNB si on a un contact
            if contact:
                logger.log(f"Récupération BDNB pour: {address}", "DEBUG")
                address_str = f"{address['numero']} {address['voie']} {address['code_postal']} {address['ville']}"
                bdnb_data = bdnb.get_building_info(address_str, logger)
                if bdnb_data:
                    data['bdnb'] = bdnb_data
            
            results.append(data)
        
        return results

    def save_results_csv(self, results: List[DataPJ], output_file: str, logger: Logger):
        """Sauvegarde les résultats en CSV"""
        logger.log(f"Sauvegarde des résultats PJ dans: {output_file}", "INFO")
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Numero', 'Voie', 'Code_Postal', 'Ville',
                'Latitude', 'Longitude',
                'PJ_Titre', 'PJ_Telephone',
                'BDNB_Annee_Construction', 'BDNB_Classe_DPE', 'BDNB_Consommation'
            ])
            
            for data in results:
                if data.get('contact'):
                    writer.writerow([
                        data['address']['numero'],
                        data['address']['voie'],
                        data['address']['code_postal'],
                        data['address']['ville'],
                        data['coords'].get('latitude', '') if data['coords'] else '',
                        data['coords'].get('longitude', '') if data['coords'] else '',
                        data['contact'].get('title', ''),
                        data['contact'].get('phone', ''),
                        data['bdnb'].get('annee_construction', '') if data['bdnb'] else '',
                        data['bdnb'].get('classe_bilan_dpe', '') if data['bdnb'] else '',
                        data['bdnb'].get('consommation_energie', '') if data['bdnb'] else ''
                    ])
        
        logger.both(f"Résultats PJ sauvegardés: {output_file}", "SUCCESS")
