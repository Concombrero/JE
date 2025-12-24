# 🔍 Système de Filtrage de Qualité

## Objectif

Le système de filtrage de qualité élimine automatiquement les entreprises qui :
1. **Ne sont pas dans la zone de recherche** (hors rayon spécifié)
2. **Ont trop peu d'informations** exploitables

## Critères de Filtrage

### 1. Vérification de la Zone Géographique

- ✅ **Conservé** : Distance réelle ≤ rayon + 10% de marge
- ❌ **Éliminé** : Distance réelle > rayon + 10% de marge
- ❌ **Éliminé** : Coordonnées GPS manquantes

### 2. Score de Qualité des Informations

Le système calcule un **score de qualité** sur 15 points :

#### Informations de Contact (5 points max)
- 📞 **+2 points** : Téléphone (Pages Jaunes ou OSM)
- 📧 **+1 point** : Email(s) trouvé(s)
- 🌐 **+2 points** : Site web trouvé

#### Informations sur l'Entreprise (5 points max)
- 🏢 **+3 points** : SIREN/SIRET trouvé
- 📊 **+1 point** : Code NAF trouvé
- 👤 **+1 point** : Dirigeant(s) identifié(s)

#### Informations sur le Bâtiment (3 points max)
- 🏗️ **+1 point** : Année de construction (BDNB ou OSM)
- ⚡ **+1 point** : Classe DPE (BDNB)
- 📐 **+1 point** : Surface toiture ou parking (OSM)

#### Informations sur l'Adresse (2 points max)
- 🏠 **+1 point** : Adresse contient un numéro de rue
- 📍 **+1 point** : Adresse détaillée (avec ville, code postal)

### Seuil Minimum

**⚠️ Score minimum requis : 3 points sur 15**

Les entreprises avec un score < 3 sont automatiquement éliminées.

## Exemples

### ✅ Entreprise Conservée (Score : 8/15)
```
- Nom : "SARL Dupont & Fils"
- Téléphone : +33 1 23 45 67 89        → +2 points
- Email : contact@dupont.fr            → +1 point
- SIREN : 123456789                    → +3 points
- Code NAF : 4520A                     → +1 point
- Adresse : "15 Rue Victor Hugo"       → +1 point
TOTAL : 8 points ✅ CONSERVÉ
```

### ❌ Entreprise Éliminée (Score : 2/15)
```
- Nom : "Commerce Inconnu"
- Adresse : "Rue quelque part"         → +1 point
- Année construction : 1980            → +1 point
TOTAL : 2 points ❌ ÉLIMINÉ (< 3 points)
```

### ❌ Entreprise Éliminée (Hors Zone)
```
- Nom : "Entreprise Test"
- Distance : 650m (rayon recherche : 500m)
- Score qualité : 6 points
❌ ÉLIMINÉ (hors zone malgré bon score)
```

## Logs

Le filtrage génère des logs détaillés dans `log.txt` :

```
[INFO] Application du filtre de qualité
[DEBUG] Entreprise 'Commerce ABC' filtrée: hors zone (650m > 500m)
[DEBUG] Entreprise 'Société XYZ' filtrée: qualité insuffisante (score: 2/3)
[DEBUG] Entreprise 'SARL Dupont' retenue (score qualité: 8/15)
[INFO] 12 entreprise(s) filtrée(s) (qualité insuffisante)
[SUCCESS] 38 entreprises retenues après filtrage
```

## Configuration

Pour modifier les critères, éditez la méthode `_filter_by_quality()` dans `ui_merged.py` :

- **Marge de tolérance** : Ligne `if distance > radius_m * 1.1:` (actuellement 10%)
- **Seuil minimum** : Variable `MIN_QUALITY_SCORE = 3` (actuellement 3/15)
- **Points par critère** : Ajustez les `quality_score +=` dans le code

## Avantages

✅ Élimine les données incomplètes ou inexploitables  
✅ Garantit que les résultats sont dans la zone recherchée  
✅ Améliore la qualité globale des prospects  
✅ Réduit le bruit dans les exports CSV et cartes  
✅ Logs détaillés pour comprendre les rejets  

## Impact

Avant filtrage : Toutes les entreprises trouvées par OSM  
Après filtrage : Uniquement les entreprises avec données exploitables et dans la zone

**Résultat** : Des prospects de meilleure qualité pour votre prospection ! 🎯
