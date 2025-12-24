#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py
Point d'entrée principal de l'application de prospection fusionnée.

Lance l'interface graphique qui combine les données de deux sources:
- Source 1: Pages Jaunes + BDNB
- Source 2: OSM + API Recherche Entreprises

Usage:
    python main.py
"""

import sys
from ui_merged import main

if __name__ == "__main__":
    print("=" * 60)
    print("Prospection Fusionnée - Sources 1 + 2")
    print("=" * 60)
    print()
    print("Lancement de l'interface graphique...")
    print()
    main()
