"""Module de scraping Pages Jaunes - Adapté depuis src_1"""

import requests
import time
import random
from tools import Address, Contact
from interface import Logger
from address_comparator import AddressComparator
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from typing import Optional


class ScrapperPageJaune:
    
    def __init__(self):
        self.option = Options()
        self.option.add_argument('--no-sandbox')
        self.option.add_argument('--disable-dev-shm-usage')
        self.option.add_argument('--disable-gpu')
        self.option.add_argument('--disable-software-rasterizer')
        self.option.add_argument('--disable-extensions')
        self.option.add_argument('--disable-setuid-sandbox')
        self.option.add_argument('--remote-debugging-port=9222')
        self.option.add_argument('--window-size=1920,1080')
        self.option.add_argument('--start-maximized')
        self.option.add_argument('--disable-blink-features=AutomationControlled')
        # Ajout de user-agent pour éviter la détection
        self.option.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        # Mode headless désactivé pour afficher le navigateur
        # self.option.add_argument('--headless=new')
        self.driver = webdriver.Chrome(options=self.option)
        
        self.page_jaune_url = "https://www.pagesjaunes.fr"
        self.address_comparator = AddressComparator()


    def get_search_url(self, address: Address, business_name: Optional[str], logger: Logger) -> str:
        """
        Construit l'URL de recherche pour une adresse et un nom de commerce.
        Gère les adresses avec et sans numéro.
        
        Args:
            address: Adresse structurée
            business_name: Nom du commerce à chercher (optionnel)
            logger: Logger
        """
        logger.log(f"Construction de l'URL de recherche pour '{business_name}' à l'adresse: {address}", "DEBUG")
        
        # Construire la partie adresse
        if address['numero'] and address['numero'] > 0:
            voie_url_str = f"{address['numero']}+{address['voie'].replace(' ', '+')}"
        else:
            # Adresse sans numéro (ex: Place des Tuileaux)
            voie_url_str = address['voie'].replace(' ', '+')
        
        # Construire la partie "quoi/qui" (nom du commerce)
        quoiqui = ""
        if business_name:
            # Nettoyer et encoder le nom du commerce
            quoiqui = business_name.strip().replace(' ', '+')
        
        url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={quoiqui}&ou={voie_url_str}%2C+{address['ville']}+%28{address['code_postal']}%29&univers=pagesjaunes&idOu="
        logger.log(f"URL de recherche construite: {url}", "DEBUG")
        return url

    def get_first_result_link(self, address: Address, business_name: Optional[str], logger: Logger) -> Optional[str]:
        """
        Récupère le premier lien de résultat pour une adresse et un nom de commerce.
        
        Args:
            address: Adresse structurée
            business_name: Nom du commerce
            logger: Logger
        """
        try:
            logger.log(f"Recherche de '{business_name}' à l'adresse {address} dans Pages Jaunes", "DEBUG")
            url = self.get_search_url(address, business_name, logger)
            
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))

            html = self.driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            first_result = soup.find('div', class_='bi-content')
            if first_result:
                link = first_result.find('a', class_="bi-denomination")
                if link and link.get('href'):
                    href = link.get('href')
                    logger.log(f"Premier résultat trouvé: {href}", "DEBUG")
                    return href
            logger.log("Aucun résultat trouvé", "DEBUG")
            return None
        
        except Exception as e:
            logger.log(f"Erreur lors de la récupération du premier lien: {e}", "ERROR")
            return None


    def get_phone_number_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """
        Extrait le numéro de téléphone à partir du HTML.
        """
        logger.log("Extraction du numéro de téléphone à partir du HTML", "DEBUG")
        soup = BeautifulSoup(html, 'html.parser')
        bloc_coordonnees = soup.find('div', id='blocCoordonnees')
        
        if bloc_coordonnees:
            phone_elem = bloc_coordonnees.find('span', class_='coord-numero noTrad')
            if phone_elem:
                logger.log(f"Numéro de téléphone trouvé: {phone_elem.get_text(strip=True)}", "DEBUG")
                return phone_elem.get_text(strip=True)

        logger.log("Aucun numéro de téléphone trouvé", "DEBUG")
        return None


    def get_address_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """
        Extrait l'adresse à partir du HTML dans le div address-container marg-btm-s.
        """
        logger.log("Extraction de l'adresse à partir du HTML", "DEBUG")
        soup = BeautifulSoup(html, 'html.parser')
        
        address_container = soup.find('div', class_='address-container marg-btm-s')
        
        if address_container:
            address_span = address_container.find('span', class_='noTrad')
            if address_span:
                address_text = address_span.get_text(strip=True)
                logger.log(f"Adresse trouvée: {address_text}", "DEBUG")
                return address_text
        
        logger.log("Aucune adresse trouvée dans address-container marg-btm-s", "DEBUG")
        return None

    def get_title_from_html(self, html: str, logger: Logger) -> Optional[str]:
        """
        Extrait le titre de la page à partir du HTML.
        """
        logger.log("Extraction du titre à partir du HTML", "DEBUG")
        soup = BeautifulSoup(html, 'html.parser')
        title_elem = soup.find('title', id='metaTitle')
        
        if title_elem:
            logger.log(f"Titre trouvé: {title_elem.get_text(strip=True)}", "DEBUG")
            return title_elem.get_text(strip=True)
        
        logger.log("Aucun titre trouvé", "DEBUG")
        return None


    def get_contact_from_url(self, url: str, logger: Logger) -> Optional[Contact]:
        """
        Récupère les informations de contact à partir de l'URL fournie.
        """
        try:
            logger.log(f"Récupération de la page HTML: {url}", "DEBUG")
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))

            html = self.driver.page_source

            phone = self.get_phone_number_from_html(html, logger)
            address = self.get_address_from_html(html, logger)
            title = self.get_title_from_html(html, logger)

            contact: Contact = {
                'phone': phone or '',
                'title': title or '',
                'address': address or ''
            }
            return contact
        
        except Exception as e:
            logger.log(f"Erreur lors de la récupération du contact: {e}", "ERROR")
            return None

    def is_str_address(self, string: str, address: Address, logger: Logger) -> bool:
        """
        Vérifie si la chaine de caractères correspond à l'adresse en tenant compte des fautes de frappe.
        """
        logger.log(f"Comparaison avancée de l'adresse: {address} et '{string}'", "DEBUG")
        
        is_match = self.address_comparator.is_address_match(address, string, logger, threshold=0.8)
        
        logger.log(f"Résultat de la comparaison: {'MATCH' if is_match else 'NO MATCH'}", "DEBUG")
        
        return is_match


    def process_address(self, address: Address, business_name: Optional[str], logger: Logger) -> Optional[Contact]:
        """
        Traite une adresse et un nom de commerce pour récupérer les informations de contact.
        
        Args:
            address: Adresse structurée
            business_name: Nom du commerce à chercher
            logger: Logger
            
        Returns:
            Contact avec phone, title, address ou None si pas de match.
        """
        logger.log(f"Traitement de '{business_name}' à l'adresse: {address}", "DEBUG")
        first_link = self.get_first_result_link(address, business_name, logger)
        first_link = self.page_jaune_url + first_link if first_link else None
        if first_link:
            time.sleep(random.uniform(2, 4))
            contact = self.get_contact_from_url(first_link, logger)
            if contact:
                address_str = contact.get('address', '')
                time.sleep(random.uniform(2, 4))
                if self.is_str_address(address_str, address, logger):
                    return contact
                else:
                    logger.log("Adresse ne correspond pas", "DEBUG")
                    return None
        return None

    def close(self):
        """Ferme le driver Selenium"""
        if self.driver:
            self.driver.quit()
