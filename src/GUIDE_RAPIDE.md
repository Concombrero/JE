# 🎯 GUIDE RAPIDE - Application de Prospection Fusionnée

## ✨ Ce qui a été créé

Un **nouveau dossier `src`** qui fusionne les deux sources existantes :
- ✅ **src_1** (Pages Jaunes + BDNB) 
- ✅ **src_2** (OSM + API Entreprises)

**Aucun code des sources originales n'a été modifié ou supprimé.**

## 📁 Structure du projet

```
JE/
├── src_1/              # Source originale 1 (inchangée)
├── src_2/              # Source originale 2 (inchangée)
└── src/                # 🆕 NOUVEAU - Fusion des deux sources
    ├── main.py         # 🚀 Lancez ceci !
    ├── ui_merged.py    # Interface graphique
    ├── enrichment.py   # Fusion des données
    ├── export_data.py  # Export CSV + Carte
    ├── README.md       # Documentation complète
    ├── requirements.txt
    └── run.sh          # Script de démarrage
```

## 🚀 Démarrage rapide

### Option 1 : Script automatique (recommandé)

```bash
cd /home/tim/Documents/Projet/JE/src
./run.sh
```

### Option 2 : Manuel

```bash
cd /home/tim/Documents/Projet/JE/src

# Installer les dépendances (première fois)
pip install -r requirements.txt

# Lancer l'application
python main.py
```

## 🎨 Interface utilisateur

L'application s'ouvre avec une interface graphique moderne basée sur **src_2** :

1. **Adresse** : Point de départ de la recherche  
   Exemple : `10 Rue de la Paix, 75002 Paris`

2. **Rayon** : Distance de recherche en km  
   Exemple : `0.5` (500 mètres)

3. **Dossier** : Nom pour sauvegarder les résultats  
   Exemple : `ma_prospection`

4. **Lancer** : Démarre la prospection

## 📊 Résultats générés

Les résultats sont sauvegardés dans `output/[nom_dossier]/` :

### 📄 resultats.csv
Tableur Excel/CSV avec **toutes les données enrichies** :
- Informations générales (nom, adresse, coordonnées, distance)
- **Source 1 (Pages Jaunes)** : téléphone, titre
- **Source 1 (BDNB)** : année construction, classe DPE
- **Source 2 (OSM)** : catégorie, téléphones, emails, sites web
- **Source 2 (API)** : SIREN, SIRET, NAF, dirigeants
- **Source 2 (Bâtiment)** : surface toiture, parking

### 🗺️ carte.html
Carte interactive Leaflet avec :
- Fond satellite ou plan au choix
- Cercle de recherche visible
- Marqueurs clusterisés
- Popups détaillées avec badges colorés par source
- **Double-cliquez** pour ouvrir dans votre navigateur

### 📝 log.txt
Journal d'exécution avec tous les détails

## 🔄 Workflow de l'application

```
1. 📍 Géocodage de l'adresse initiale
   └─> Obtention des coordonnées GPS

2. 🔍 Recherche des entreprises (Overpass OSM)
   └─> Liste des entreprises dans le rayon

3. 🔄 Pour chaque entreprise :
   ├─> Géocodage de son adresse (BAN)
   ├─> Enrichissement Source 2 (API + OSM) ⚡ Rapide
   └─> Enrichissement Source 1 (PJ + BDNB) 🐢 Plus lent

4. 💾 Export des résultats
   ├─> CSV avec toutes les colonnes
   └─> Carte HTML interactive
```

## 💡 Avantages de cette fusion

| Source 1 (src_1) | Source 2 (src_2) | 🆕 Fusion (src) |
|------------------|------------------|-----------------|
| Téléphone PJ ✅ | Téléphones OSM ✅ | **LES DEUX** ✅✅ |
| Titre PJ ✅ | - | **Titre PJ** ✅ |
| Année construction ✅ | Année bâtiment ✅ | **LES DEUX** ✅✅ |
| Classe DPE ✅ | - | **DPE** ✅ |
| - | Emails ✅ | **Emails** ✅ |
| - | Sites web ✅ | **Sites web** ✅ |
| - | SIREN/SIRET ✅ | **SIREN/SIRET** ✅ |
| - | Dirigeants ✅ | **Dirigeants** ✅ |
| - | Surface toiture ✅ | **Surface toiture** ✅ |

**Résultat : Maximum d'informations pour chaque entreprise !**

## ⚙️ Prérequis système

### Obligatoire
- Python 3.8+
- ChromeDriver (pour le scraping Pages Jaunes)

### Installation ChromeDriver

**Ubuntu/Debian :**
```bash
sudo apt-get update
sudo apt-get install chromium-chromedriver
```

**macOS :**
```bash
brew install chromedriver
```

**Windows :**
Téléchargez depuis https://chromedriver.chromium.org/

## 📦 Dépendances Python

Toutes listées dans `requirements.txt` :
- `requests` : Appels HTTP
- `beautifulsoup4` : Parsing HTML
- `selenium` : Scraping dynamique
- `PySide6` : Interface graphique
- `overpy` : API Overpass OSM
- `geopy` : Géocodage
- `pyproj` : Calculs géographiques

## ⚠️ Notes importantes

1. **Scraping Pages Jaunes** : Peut être lent (délais anti-détection)
2. **Rate limits** : BDNB limité à 120 req/min
3. **Parallélisation** : 2 workers maximum pour ne pas surcharger
4. **Temps d'exécution** : ~2-3 min pour 20 entreprises

## 🐛 Dépannage

### Erreur "ChromeDriver not found"
```bash
# Vérifiez l'installation
which chromedriver

# Si manquant, installez-le
sudo apt-get install chromium-chromedriver
```

### Erreur "Module not found"
```bash
# Réinstallez les dépendances
pip install -r requirements.txt
```

### Scraping PJ bloqué
- Réduisez le nombre d'entreprises
- Augmentez les délais dans `scrapper.py`
- Utilisez uniquement la source 2 temporairement

## 📞 Support

Pour toute question ou amélioration :
1. Consultez `src/README.md` (documentation complète)
2. Vérifiez les logs dans `output/[dossier]/log.txt`
3. Les sources originales `src_1` et `src_2` restent intactes et utilisables

## 🎓 Pour aller plus loin

- Modifiez `enrichment.py` pour ajouter d'autres sources
- Personnalisez `export_data.py` pour changer le format CSV
- Adaptez `ui_merged.py` pour modifier l'interface
- Consultez les logs pour comprendre le comportement

---

**Bon courage avec votre prospection ! 🚀**
