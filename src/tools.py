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
    