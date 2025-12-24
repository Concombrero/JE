# Prospection Fusionnée - Sources 1 + 2

Ce dossier `src` contient une application qui fusionne les fonctionnalités des deux sources originales (`src_1` et `src_2`) pour enrichir les données d'entreprises avec un maximum d'informations.

## 🎯 Fonctionnalités

L'application combine les données de **deux sources** :

### Source 1 : Pages Jaunes + BDNB
- **Pages Jaunes** : Scraping pour récupérer téléphone et titre de l'entreprise
- **BDNB** : Données du bâtiment (année de construction, classe DPE)

### Source 2 : OSM + API Recherche Entreprises
- **OpenStreetMap (OSM)** : Contacts (téléphones, emails, sites web, réseaux sociaux) et catégories
- **API Recherche Entreprises** : SIREN, SIRET, NAF, dirigeants
- **Données bâtiment OSM** : Année plausible, surface toiture, surface parking

## 📦 Structure des fichiers

```
src/
├── main.py                           # Point d'entrée principal
├── ui_merged.py                      # Interface graphique Qt
├── enrichment.py                     # Module d'enrichissement fusionné
├── export_data.py                    # Export CSV et carte HTML
├── trouve_entreprise.py              # Recherche entreprises OSM (source 2)
├── recup_donnees_entreprises.py      # Récupération données API (source 2)
├── scrapper.py                       # Scraping Pages Jaunes (source 1)
├── bdnb.py                          # API BDNB (source 1)
├── adr.py                           # Traitement adresses (source 1)
├── address_comparator.py            # Comparaison d'adresses (source 1)
├── interface.py                     # Logger
└── tools.py                         # Types et structures de données
```

## 🚀 Installation

### Prérequis

- Python 3.8+
- ChromeDriver (pour Selenium)

### Dépendances

Installez les dépendances requises :

```bash
pip install requests beautifulsoup4 selenium PySide6 overpy geopy pyproj
```

### Configuration ChromeDriver

Pour le scraping Pages Jaunes, ChromeDriver doit être installé :

```bash
# Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# macOS (avec Homebrew)
brew install chromedriver

# Ou téléchargez depuis: https://chromedriver.chromium.org/
```

## 📖 Utilisation

### Lancer l'application

```bash
cd /home/tim/Documents/Projet/JE/src
python main.py
```

### Interface graphique

1. **Adresse** : Saisissez l'adresse du centre de recherche (ex: `10 Rue de la Paix, 75002 Paris`)
2. **Rayon** : Définissez le rayon de recherche en kilomètres (ex: `0.5` pour 500 mètres)
3. **Dossier** : Nom du dossier de sortie (les résultats seront dans `output/[nom]`)
4. Cliquez sur **Lancer**

### Résultats

Les résultats sont sauvegardés dans `output/[nom_dossier]/` :

- **`resultats.csv`** : Tableur avec toutes les données enrichies des deux sources
- **`carte.html`** : Carte interactive Leaflet avec marqueurs clusterisés
- **`log.txt`** : Journal d'exécution détaillé

## 📊 Données exportées

### Dans le CSV

Chaque ligne contient :

#### Informations générales
- Nom, Adresse, Latitude, Longitude, Distance

#### Source 1 : Pages Jaunes + BDNB
- PJ - Téléphone
- PJ - Titre
- BDNB - Année Construction
- BDNB - Classe DPE

#### Source 2 : OSM + API Entreprises
- OSM - Catégorie, Téléphones, Emails, Sites Web, Réseaux Sociaux
- Entreprise - SIREN, SIRET, Nom, NAF, Libellé NAF
- Dirigeants (noms, prénoms, rôles)
- Bâtiment - Année, Surface Toiture, Surface Parking

### Sur la carte

La carte HTML interactive affiche :
- **Fond de carte** : Satellite (Esri) ou Plan (OSM) au choix
- **Cercle de recherche** : Rayon défini autour du centre
- **Marqueurs clusterisés** : Chaque entreprise avec popup détaillée
- **Badges colorés** : Identification visuelle des sources de données

## 🔧 Architecture

### Flux de traitement

1. **Géocodage** : L'adresse initiale est géocodée via Nominatim
2. **Recherche OSM** : Les entreprises sont trouvées via Overpass (programme 1)
3. **Enrichissement parallèle** : Pour chaque entreprise :
   - Géocodage BAN de son adresse
   - Enrichissement Source 2 (API + OSM) : rapide
   - Enrichissement Source 1 (PJ + BDNB) : plus lent, avec scraping
4. **Filtrage de qualité** : Élimination des entreprises :
   - Hors de la zone de recherche (distance > rayon + 10%)
   - Avec informations insuffisantes (score qualité < 3/15)
5. **Export** : Sauvegarde CSV + génération carte HTML

> 📖 Pour plus de détails sur le filtrage, consultez [FILTRAGE_QUALITE.md](./FILTRAGE_QUALITE.md)

### Parallélisation

- 2 workers en parallèle pour éviter de surcharger les APIs et le scraping
- Gestion des erreurs robuste : si une source échoue, les autres continuent

## ⚠️ Limitations

- **Pages Jaunes** : Le scraping peut être détecté et bloqué en cas d'usage intensif
- **BDNB** : Rate limit de 120 requêtes/minute
- **Overpass** : Peut être lent ou indisponible temporairement
- **Selenium** : Nécessite ChromeDriver installé et peut être gourmand en ressources

## 🛠️ Développement

### Modules clés

- **`enrichment.py`** : Gère l'enrichissement avec les deux sources
- **`ui_merged.py`** : Interface Qt6 avec thread worker
- **`export_data.py`** : Export CSV et génération carte Leaflet
- **`scrapper.py`** : Scraping Pages Jaunes avec Selenium + BeautifulSoup
- **`recup_donnees_entreprises.py`** : Appels API et Overpass

### Logger

Tous les modules utilisent le `Logger` de `interface.py` qui :
- Écrit dans un fichier log
- Affiche dans la console avec émojis
- Conserve uniquement les 100 dernières lignes

## 📝 Notes

- **Pas de clé API requise** : Toutes les APIs utilisées sont publiques et gratuites
- **Scraping éthique** : Délais aléatoires entre les requêtes Pages Jaunes
- **Thread-safe** : L'enrichissement parallèle est géré par ThreadPoolExecutor
- **Cancellable** : L'utilisateur peut annuler la prospection en cours

## 📄 Licence

Ce projet est destiné à un usage interne. Respectez les conditions d'utilisation des APIs et sites web utilisés.

## 🤝 Contribution

Pour toute amélioration ou correction, modifiez les fichiers dans ce dossier `src` sans toucher aux sources originales `src_1` et `src_2`.
