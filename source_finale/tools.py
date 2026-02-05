"""Types et Variables communs à tous les modules"""

from typing import TypedDict, Optional, List, Dict, Any


class Address(TypedDict):
    """Type Adresse"""
    numero: str
    voie: str
    code_postal: str
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
    numbers: List[str]


class Contact(TypedDict):
    """Type Contact (Pages Jaunes)"""
    phone: str
    title: str
    address: str


class EntrepriseData(TypedDict):
    """Type données enrichies d'une entreprise (src_2)"""
    name: str
    category: Optional[str]
    address: str
    distance_m: Optional[float]
    phones: List[str]
    emails: List[str]
    websites: List[str]
    socials: List[str]
    company_info: Optional[Dict[str, Any]]
    owner_first_name: Optional[str]
    owner_last_name: Optional[str]
    owner_role: Optional[str]
    building_year: Optional[int]
    roof_area_m2: Optional[float]
    parking_area_m2: Optional[float]


class DataPJ(TypedDict):
    """Type Data pour Pages Jaunes (src_1)"""
    address: Address
    coords: Coords
    contact: Optional[Contact]
    bdnb: Optional[Dict[str, Any]]


class FusedData(TypedDict):
    """Type pour les données fusionnées"""
    # Identifiant
    numero: str
    voie: str
    code_postal: str
    ville: str
    latitude: Optional[float]
    longitude: Optional[float]
    
    # Pages Jaunes
    pj_title: Optional[str]
    pj_phone: Optional[str]
    
    # BDNB
    annee_construction: Optional[int]
    classe_bilan_dpe: Optional[str]
    
    # Entreprises (src_2)
    entreprise_nom: Optional[str]
    entreprise_category: Optional[str]
    entreprise_phones: Optional[List[str]]
    entreprise_emails: Optional[List[str]]
    entreprise_websites: Optional[List[str]]
    entreprise_siren: Optional[str]
    entreprise_siret: Optional[str]
    entreprise_naf: Optional[str]
    owner_name: Optional[str]
    owner_role: Optional[str]
    
    # OSM données batiment
    roof_area_m2: Optional[float]
    parking_area_m2: Optional[float]
    building_year: Optional[int]


# Utilitaires
def sanitize(s, default=""):
    """Nettoie une valeur pour affichage"""
    try:
        if s is None:
            return default
        return str(s)
    except Exception:
        return default


def listify(x):
    """Convertit en liste si ce n'est pas déjà une liste"""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def safe_float(x, default=None):
    """Conversion sécurisée en float"""
    try:
        return float(x)
    except Exception:
        return default


def safe_int(x, default=None):
    """Conversion sécurisée en int"""
    try:
        return int(x)
    except Exception:
        return default
