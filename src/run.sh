#!/bin/bash
# Script de démarrage rapide pour l'application de prospection fusionnée

echo "========================================"
echo "Prospection Fusionnée - Sources 1 + 2"
echo "========================================"
echo ""

# Vérifier que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

echo "✅ Python 3 détecté: $(python3 --version)"

# Vérifier que ChromeDriver est installé (pour Selenium)
if ! command -v chromedriver &> /dev/null; then
    echo "⚠️  ChromeDriver n'est pas installé ou pas dans le PATH"
    echo "   Installation recommandée:"
    echo "   - Ubuntu/Debian: sudo apt-get install chromium-chromedriver"
    echo "   - macOS: brew install chromedriver"
    echo ""
fi

# Créer le dossier output s'il n'existe pas
mkdir -p ../output

# Vérifier les dépendances
echo ""
echo "Vérification des dépendances Python..."

MISSING_DEPS=0

for pkg in requests beautifulsoup4 selenium PySide6 overpy geopy pyproj; do
    if python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        echo "  ✅ $pkg"
    else
        echo "  ❌ $pkg (manquant)"
        MISSING_DEPS=1
    fi
done

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "⚠️  Certaines dépendances sont manquantes"
    echo "   Installez-les avec: pip install -r requirements.txt"
    echo ""
    read -p "Voulez-vous installer les dépendances maintenant ? (o/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Oo]$ ]]; then
        pip install -r requirements.txt
    else
        echo "Installation annulée"
        exit 1
    fi
fi

# Lancer l'application
echo ""
echo "🚀 Lancement de l'application..."
echo ""

python3 main.py
