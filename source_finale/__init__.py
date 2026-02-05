"""
Package src - Prospection immobilière

Modules principaux:
- address_processor: Traitement des adresses (BAN, OSM)
- address_comparator: Comparaison d'adresses avec tolérance
- scrapper_pj: Scrapping des Pages Jaunes
- entreprises: Recherche et enrichissement des entreprises
- fusion: Fusion des résultats PJ et Entreprises
- map_generator: Génération de cartes Leaflet
- bdnb: Accès à la Base Nationale des Bâtiments
- logger: Système de logging
- tools: Types et utilitaires communs
- ui: Interface graphique PySide6

Point d'entrée:
- main.py: Lance l'application (GUI par défaut, CLI avec --cli)
"""

__version__ = "1.0.0"
__author__ = "JE Project"

# Exports principaux
from .tools import (
    Address, Coords, Street, Contact,
    EntrepriseData, DataPJ, FusedData,
    sanitize, listify, safe_float, safe_int
)
from .logger import Logger
