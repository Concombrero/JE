import requests
import time
import random
import csv
import os
from tools import Address, Coords, Contact, Street, Data
from interface import Logger
from adr import AddressProcessor
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

address_processor = AddressProcessor()

class ScrapperPageJaune:
    
    def __init__(self):
            self.option = Options()
            self.option.add_argument('--no-sandbox')
            self.option.add_argument('--disable-dev-shm-usage')
            #self.option.add_argument('--headless')
            self.driver = webdriver.Chrome(options=self.option) # A voir ce qu'on prend comme driver
            
            self.page_jaune_url = "https://www.pagesjaunes.fr"


    def get_search_url(self, address: Address, logger: Logger) -> str:
        """
        Construit l'URL de recherche pour une adresse donnée.
        """
        logger.log(f"Construction de l'URL de recherche pour l'adresse: {address}", "DEBUG")
        voie_url_str = f"{address['numero']}+{address['voie'].replace(' ', '+')}"
        url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui=&ou={voie_url_str}%2C+{address['ville']}+%28{address['code_postal']}%29&univers=pagesjaunes&idOu="
        logger.log(f"URL de recherche construite: {url}", "DEBUG")
        return url


    def get_first_result_link(self, address: Address, logger: Logger) -> str:
        """
        Récupère le premier lien de résultat pour une adresse donnée.
        Utilise des requêtes HTTP avec des headers améliorés.
        """
        try:
            logger.log(f"Recherche de l'adresse dans pagejaune: {address}", "DEBUG")
            url = self.get_search_url(address, logger)
            
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))
            
            html = self.driver.page_source
                
            soup = BeautifulSoup(html, 'html.parser')
            
            first_result = soup.find('a', class_='bi-denomination pj-link')
            if first_result:
                logger.log(f"Premier résultat trouvé: {first_result.get('href')}", "DEBUG")
                return first_result.get('href')

            logger.log("Aucun résultat trouvé", "DEBUG")
            return None
        
        except Exception as e:
            return None


    def get_phone_number_from_html(self, html: str, logger: Logger) -> str:
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


    def get_address_from_html(self, html: str, logger: Logger) -> str:
        """
        Extrait l'adresse à partir du HTML dans le div address-container marg-btm-s.
        """
        logger.log("Extraction de l'adresse à partir du HTML", "DEBUG")
        soup = BeautifulSoup(html, 'html.parser')
        
        # Recherche du div avec la classe "address-container marg-btm-s"
        address_container = soup.find('div', class_='address-container marg-btm-s')
        
        if address_container:
            # Recherche du span avec la classe "noTrad" dans ce container
            address_span = address_container.find('span', class_='noTrad')
            if address_span:
                address_text = address_span.get_text(strip=True)
                logger.log(f"Adresse trouvée: {address_text}", "DEBUG")
                return address_text
        
        logger.log("Aucune adresse trouvée dans address-container marg-btm-s", "DEBUG")
        return None

    def get_title_from_html(self, html: str, logger: Logger) -> str:
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


    def get_contact_from_url(self, url: str, logger: Logger) -> Contact:
        """
        Récupère les informations de contact à partir de l'URL fournie.
        """
        try:
            logger.log(f"Récupération de la page HTML: {url}", "DEBUG")
            self.driver.get(url)
            time.sleep(random.uniform(2, 3))

            
            html = self.driver.page_source
            
            # sauvegarde le HTML pour analyse
            with open('pagejaune_contact.html', 'w', encoding='utf-8') as f:
                f.write(html)

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
            return None

    def is_str_address(self, string: str, address: Address, logger: Logger) -> bool:
        """
        Vérifie si la chaine de caractères correspond à l'adresse.
        """
        logger.log(f"Comparaison de l'adresse: {address} et {string}", "DEBUG")
        formatted_address = f"{address['numero']} {address['voie']}, {address['code_postal']} {address['ville']}"
        result = string.strip().lower() == formatted_address.strip().lower()
        logger.log(f"Résultat de la comparaison: {result}", "DEBUG")
        return result


    def process_address(self, address: Address, logger: Logger) -> Contact:
        """
        Traite une adresse pour récupérer les informations de contact.
        """
        logger.log(f"Traitement de l'adresse: {address}", "DEBUG")
        first_link = self.get_first_result_link(address, logger)
        first_link = self.page_jaune_url + first_link if first_link else None
        if first_link:
            contact = self.get_contact_from_url(first_link, logger)
            address_str = contact.get('address', '')
            if self.is_str_address(address_str, address, logger):
                return contact
            else:
                return None
    
    def save_data(self, data: Data, output_file_name: str, logger: Logger):
        """
        Enregistre les données dans un fichier CSV.
        """
        logger.log(f"Enregistrement des données dans le fichier: {output_file_name}", "DEBUG")
        
        if not output_file_name.endswith('.csv'):
            output_file_name += '.csv'
        
        with open(output_file_name, 'a', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not os.path.exists(output_file_name):
                logger.log("Création du fichier CSV et écriture de l'en-tête", "DEBUG")
                writer.writerow(['numero', 'voie', 'code_postal', 'ville', 'latitude', 'longitude', 'title', 'téléphone'])
            
            
            writer.writerow([
                data['address']['numero'],
                data['address']['voie'],
                data['address']['code_postal'],
                data['address']['ville'],
                data['coords']['latitude'],
                data['coords']['longitude'],
                data['contact']['title'],
                data['contact']['phone']
            ])
    
    def process_street(self, street: Street, logger: Logger, output_dir: os.path):
        """
        Traite une rue pour récupérer les informations de contact de chaque adresse.
        """
        logger.both(f"Traitement de la rue: {street['name']}")
        output_file_name = os.path.join(output_dir, "result.csv")

        for number in street['numbers']:
            logger.log(f"Traitement du numéro: {number}", "DEBUG")
            address = {
                'numero': number,
                'voie': street['name'],
                'code_postal': street['postal_code'],
                'ville': street['city']
            }
            contact = self.process_address(address, logger)
            if contact:
                coords = address_processor.address_to_coordinates(address, logger)

                data = {
                    'address': address,
                    'coords': coords,
                    'contact': contact
                }

                self.save_data(data, output_file_name, logger)
