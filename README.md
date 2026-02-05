# Prospection Immobilière - Fusion de src_1 et src_2

## 📖 Vue d'ensemble

Ce projet est une application de prospection immobilière qui permet de récupérer et d'enrichir des données sur les entreprises et bâtiments à partir d'une adresse et d'un rayon de recherche.

**La version finale (`src/`) a été créée en fusionnant deux projets distincts :**
- **`src_1/`** : Scrapping des Pages Jaunes + données BDNB
- **`src_2/`** : Recherche d'entreprises via OSM/Overpass + API Recherche Entreprises

---

## 🔄 Comment la fusion a été réalisée

### Structure des projets sources

#### `src_1/` - Pages Jaunes + BDNB
| Fichier | Fonction |
|---------|----------|
| `main.py` | Interface CLI pour lancer la recherche |
| `scrapper.py` | Scrapping Selenium des Pages Jaunes |
| `adr.py` | Traitement et validation des adresses |
| `address_comparator.py` | Comparaison d'adresses |
| `bdnb.py` | Récupération données BDNB (DPE, construction) |
| `interface.py` | Logger et affichage console |
| `tools.py` | Types de base (Address, Contact, Street) |

#### `src_2/` - Entreprises OSM + API Gouvernementales
| Fichier | Fonction |
|---------|----------|
| `trouve_entreprise.py` | Géocodage + recherche entreprises OSM/Overpass |
| `recup_donnees_entreprises.py` | Enrichissement via API Recherche Entreprises, contacts OSM, surfaces |
| `ui_prospection.py` | Interface Qt (PySide6) avec carte Leaflet |

---

### Fichiers de la version fusionnée (`src/`)

| Fichier final | Origine | Description |
|---------------|---------|-------------|
| `main.py` | **Nouveau** | Interface CLI unifiée combinant les deux workflows |
| `ui.py` | Basé sur `src_2/ui_prospection.py` | Interface Qt améliorée avec modes multiples |
| `scrapper_pj.py` | Basé sur `src_1/scrapper.py` | Scrapping Pages Jaunes refactoré |
| `entreprises.py` | Fusion de `src_2/trouve_entreprise.py` + `src_2/recup_donnees_entreprises.py` | Module unifié de recherche entreprises |
| `fusion.py` | **Nouveau** | Fusion des résultats PJ et Entreprises + filtrage |
| `map_generator.py` | Extrait de `src_2/ui_prospection.py` | Génération de carte Leaflet autonome |
| `address_processor.py` | Basé sur `src_1/adr.py` | Traitement des adresses (renommé) |
| `address_comparator.py` | `src_1/address_comparator.py` | Inchangé |
| `bdnb.py` | `src_1/bdnb.py` | Inchangé |
| `logger.py` | Basé sur `src_1/interface.py` | Logger amélioré (renommé) |
| `tools.py` | Fusion des deux `tools.py` | Types étendus (FusedData, EntrepriseData, etc.) |

---

## 🔀 Détail des transformations

### 1. Fusion des types (`tools.py`)

**Avant (src_1/tools.py)** :
```python
class Address(TypedDict):
    numero: int
    voie: str
    code_postal: int
    ville: str

class Data(TypedDict):
    address: Address
    coords: Coords
    contact: Contact
```

**Après (src/tools.py)** :
```python
class Address(TypedDict):
    numero: str       # Changé en str pour flexibilité
    voie: str
    code_postal: str  # Changé en str
    ville: str

# Nouveaux types ajoutés
class EntrepriseData(TypedDict):
    """Données enrichies d'une entreprise (anciennement src_2)"""
    name: str
    category: Optional[str]
    phones: List[str]
    emails: List[str]
    websites: List[str]
    company_info: Optional[Dict[str, Any]]
    # ...

class FusedData(TypedDict):
    """Données fusionnées PJ + Entreprises"""
    # Identifiant
    numero: str
    voie: str
    # Pages Jaunes
    pj_title: Optional[str]
    pj_phone: Optional[str]
    # BDNB
    classe_bilan_dpe: Optional[str]
    # Entreprises
    entreprise_nom: Optional[str]
    entreprise_siret: Optional[str]
    # ...
```

### 2. Fusion de la recherche entreprises (`entreprises.py`)

Les deux fichiers `trouve_entreprise.py` (géocodage + recherche OSM) et `recup_donnees_entreprises.py` (enrichissement API) ont été fusionnés dans une seule classe `EntrepriseSearcher` :

```python
class EntrepriseSearcher:
    """Classe combinant:
    - Géocodage BAN (anciennement dans recup_donnees_entreprises.py)
    - Recherche OSM/Overpass (anciennement dans trouve_entreprise.py)
    - Enrichissement API Recherche Entreprises
    - Récupération contacts OSM
    - Calcul surfaces toiture/parking
    """
    
    def geocode_ban(self, address): ...
    def search_businesses_osm(self, lat, lon, radius): ...
    def search_companies_api(self, name, address): ...
    def get_osm_contacts(self, lat, lon): ...
    def get_building_info(self, lat, lon): ...
    def enrich_address(self, address, logger): ...  # Méthode principale
```

### 3. Module de fusion des résultats (`fusion.py`)

**Nouveau fichier** qui combine les résultats des deux sources :

```python
def fuse_results(pj_results: List[DataPJ], ent_results: List[EntrepriseData]) -> List[FusedData]:
    """
    Fusionne les données Pages Jaunes et Entreprises par adresse.
    - Matching par proximité géographique (< 50m)
    - Matching par similarité de nom
    - Déduplication
    """

def is_interesting_result(entry: FusedData) -> Tuple[bool, List[str]]:
    """
    Filtre les résultats "intéressants" :
    - Au moins un contact (téléphone/email)
    - SIRET identifié
    - Grande surface de toiture (> 100m²)
    - etc.
    """
```

### 4. Interface unifiée (`ui.py`)

L'interface Qt de `src_2/ui_prospection.py` a été étendue pour supporter :

| Mode | Description |
|------|-------------|
| **Workflow complet** | Adresse → Rues → PJ + Entreprises → Fusion → Carte |
| **Depuis un dossier** | Charger des rues existantes → Reprendre le traitement |
| **Afficher carte** | Ouvrir un fichier CSV ou carte existante |

La génération de carte a été extraite dans `map_generator.py` pour être réutilisable par le CLI.

### 5. CLI unifié (`main.py`)

Le nouveau `main.py` combine les workflows des deux projets :

```python
"""
Usage:
    python main.py          # Lance l'interface graphique Qt
    python main.py --cli    # Lance l'interface terminal

Modes d'exécution:
1. COMPLET: Adresse + rayon → rues → scrapping PJ → recherche entreprises → fusion → carte
2. DEPUIS DOSSIER: Charger un dossier de rues existant
3. CARTE SEULE: Afficher une carte existante
"""
```

---

## 📊 Schéma du workflow fusionné

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ENTRÉE UTILISATEUR                           │
│              Adresse de départ + Rayon (km)                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RÉCUPÉRATION DES RUES                            │
│    (AddressProcessor - géocodage + recherche des rues autour)       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────┴─────────────────────────┐
        │                                                   │
        ▼                                                   ▼
┌───────────────────────┐                     ┌───────────────────────┐
│     WORKFLOW SRC_1    │                     │     WORKFLOW SRC_2    │
│    (ScrapperPagesJaunes)                    │   (EntrepriseSearcher)│
│                       │                     │                       │
│ • Scrapping PJ        │                     │ • Recherche OSM       │
│ • Téléphone           │                     │ • API Entreprises     │
│ • Données BDNB        │                     │ • Contacts OSM        │
│                       │                     │ • Surfaces bâtiment   │
└───────────────────────┘                     └───────────────────────┘
        │                                                   │
        └─────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FUSION                                       │
│    (fusion.py - fuse_results + is_interesting_result)               │
│                                                                     │
│    • Matching par adresse/coordonnées                               │
│    • Déduplication                                                  │
│    • Filtrage des résultats intéressants                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          SORTIE                                      │
│                                                                     │
│    • resultats_fusionnes.csv                                        │
│    • carte.html (Leaflet interactive)                               │
│    • Fichiers JSON par rue                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation et utilisation

### Prérequis
```bash
pip install -r requirements.txt
```

### Dépendances principales
- `PySide6` - Interface graphique Qt
- `selenium` + `beautifulsoup4` - Scrapping web
- `geopy` + `pyproj` + `overpy` - Géocodage et recherche OSM
- `requests` - Appels API

### Lancement
```bash
# Interface graphique (recommandé)
cd src
python main.py

# Interface ligne de commande
cd src
python main.py --cli
```

---

## 📁 Structure des sorties

```
output/
└── <nom_recherche>/
    ├── log.txt                    # Logs de l'exécution
    ├── resultats_fusionnes.csv    # Données fusionnées
    ├── carte.html                 # Carte interactive Leaflet
    └── streets/                   # Données brutes par rue
        ├── Rue_Example.json
        └── ...
```

---

## 🔧 Différences clés entre les versions

| Aspect | src_1 | src_2 | src (fusionné) |
|--------|-------|-------|----------------|
| **Interface** | CLI simple | Qt + WebEngine | CLI + Qt unifié |
| **Sources de données** | Pages Jaunes, BDNB | OSM, API Entreprises | Toutes combinées |
| **Contacts** | Téléphone uniquement | Email, téléphone, site web, réseaux sociaux | Tous |
| **Données entreprise** | Non | SIRET, dirigeants | Oui |
| **Données bâtiment** | DPE (BDNB) | Surface toiture, année construction | Toutes |
| **Visualisation** | Aucune | Carte Leaflet intégrée | Carte Leaflet exportable |
| **Filtrage** | Non | Critère de contact | Multi-critères configurable |

---

## � Créer un exécutable (.exe)

L'application peut être packagée en un exécutable autonome grâce à PyInstaller. Cela permet de la distribuer et de l'utiliser sans avoir Python installé.

### Prérequis

```bash
pip install pyinstaller
```

### Build de l'exécutable

```bash
# Build en dossier (démarrage plus rapide)
python build.py

# Build en un seul fichier .exe (plus facile à distribuer)
python build.py --onefile

# Nettoyer les fichiers de build
python build.py --clean
```

### Résultat

| Mode | Emplacement de l'exécutable |
|------|----------------------------|
| Dossier | `dist/ProspectionImmobiliere/ProspectionImmobiliere.exe` |
| Fichier unique | `dist/ProspectionImmobiliere.exe` |


---

## 📝 Notes de développement

- Les fichiers `source_rendu_intervenant1/` et `source_rendu_intervenant_2/` ont été conservés pour référence historique
- La version finale dans `source_finale/` est la seule à utiliser
- Le module `fusion.py` est le cœur de l'intégration, gérant le matching et la déduplication
- L'architecture a été pensée pour permettre l'ajout futur de nouvelles sources de données
