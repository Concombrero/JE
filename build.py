#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de build pour créer l'exécutable (.exe) de l'application
Utilise PyInstaller

Usage:
    python build.py              # Build standard (dossier)
    python build.py --onefile    # Build en un seul fichier .exe
    python build.py --clean      # Nettoyer les fichiers de build
"""

import os
import sys
import shutil
import subprocess
import platform


# Configuration
APP_NAME = "ProspectionImmobiliere"
MAIN_SCRIPT = "source_finale/main.py"


def clean_build():
    """Nettoie les dossiers de build"""
    to_remove = ["build", "dist", f"{APP_NAME}.spec"]
    for item in to_remove:
        if os.path.exists(item):
            if os.path.isdir(item):
                shutil.rmtree(item)
            else:
                os.remove(item)
            print(f"✓ Supprimé: {item}")
    print("Nettoyage terminé.")


def install_pyinstaller():
    """Installe PyInstaller si nécessaire"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} disponible")
    except ImportError:
        print("Installation de PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installé")


def build(onefile=False):
    """Build l'application"""
    install_pyinstaller()
    
    # Commande PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",      # Application GUI (pas de console)
        "--noconfirm",     # Écrase sans demander
    ]
    
    # Mode un seul fichier ou dossier
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")
    
    # Ajouter le dossier source_finale comme données
    sep = ";" if platform.system() == "Windows" else ":"
    cmd.extend(["--add-data", f"source_finale{sep}source_finale"])
    
    # Imports cachés pour PySide6 et dépendances
    hidden_imports = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "selenium",
        "selenium.webdriver",
        "selenium.webdriver.chrome.service",
        "selenium.webdriver.chrome.options",
        "selenium.webdriver.common.by",
        "selenium.webdriver.support.ui",
        "selenium.webdriver.support.expected_conditions",
        "bs4",
        "requests",
        "geopy",
        "geopy.geocoders",
        "pyproj",
        "overpy",
    ]
    
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
    
    # Collecter PySide6
    cmd.extend(["--collect-all", "PySide6"])
    
    # Chemin du script principal
    cmd.append(MAIN_SCRIPT)
    
    print("\n" + "=" * 50)
    print(f"Build de {APP_NAME}")
    print("=" * 50)
    print(f"Mode: {'Fichier unique' if onefile else 'Dossier'}")
    print()
    
    # Lancer le build
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✓ BUILD RÉUSSI!")
        print("=" * 50)
        if onefile:
            exe = f"dist/{APP_NAME}.exe" if platform.system() == "Windows" else f"dist/{APP_NAME}"
        else:
            exe = f"dist/{APP_NAME}/{APP_NAME}.exe" if platform.system() == "Windows" else f"dist/{APP_NAME}/{APP_NAME}"
        print(f"\nExécutable: {exe}")
        print("\n→ Double-cliquez dessus pour lancer l'application!")
    else:
        print("\n✗ Erreur lors du build")


def main():
    args = sys.argv[1:]
    
    if "--clean" in args:
        clean_build()
        return
    
    if not os.path.exists(MAIN_SCRIPT):
        print(f"Erreur: {MAIN_SCRIPT} non trouvé!")
        print("Lancez ce script depuis le dossier racine du projet.")
        sys.exit(1)
    
    onefile = "--onefile" in args
    build(onefile=onefile)


if __name__ == "__main__":
    main()
