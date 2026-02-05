"""Types et Variables communs à tous les modules"""

from typing import TypedDict


class Address(TypedDict):
    """Type Adresse"""
    numero: int
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