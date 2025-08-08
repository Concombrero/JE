import os
import sys
from tools import Address
from adr import AddressProcessor
from scrapper import ScrapperPageJaune


def main():
    address_processor = AddressProcessor()
    scraper = ScrapperPageJaune()
    # Adresse d'exemple basée sur votre HTML
    test_address: Address = {
        'numero': 103,
        'voie': 'Rue Alger',
        'code_postal': 81600,
        'ville': 'Gaillac'
    }
    
    contact = scraper.get_contact_from_url("https://www.pagesjaunes.fr/pros/04185788")
    print(contact)

if __name__ == "__main__":
    main()