"""Types et Variables communs à tous les modules"""

from typing import TypedDict, List, Optional, Any, Dict


class Address(TypedDict):
    """Type Adresse"""
    numero: Optional[int]
    voie: str
    code_postal: int
    ville: str

class Coords(TypedDict):
    """Type Coordonnées"""
    latitude: float
    longitude: float

class Street(TypedDict):
    """Type Rue"""
    name: str
    city: str
    postal_code: str
    numbers: list[str]

class Contact(TypedDict):
    """Type Contact"""
    phone: str
    title: str
    address: str

class Data(TypedDict):
    """Type Data"""
    address: Address
    coords: Coords
    contact: Contact

class EnrichedData(TypedDict):
    """Type de données enrichies avec les deux sources"""
    # Infos de base
    name: str
    address: str
    distance_m: float
    lat: float
    lon: float
    
    # Données source 1 (Pages Jaunes + BDNB)
    pagesjaunes_phone: Optional[str]
    pagesjaunes_title: Optional[str]
    bdnb_annee_construction: Optional[str]
    bdnb_classe_dpe: Optional[str]
    
    # Données source 2 (OSM + API entreprises)
    osm_category: Optional[str]
    osm_phones: List[str]
    osm_emails: List[str]
    osm_websites: List[str]
    osm_socials: List[str]
    company_siren: Optional[str]
    company_siret: Optional[str]
    company_nom: Optional[str]
    company_naf: Optional[str]
    company_libelle_naf: Optional[str]
    dirigeants: List[Dict[str, Any]]
    building_year: Optional[int]
    roof_area_m2: Optional[float]
    parking_area_m2: Optional[float]
