"""Module de comparaison d'adresses - Copié depuis src_1"""

import re
import os
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional
from tools import Address
from interface import Logger

class AddressComparator:
    def __init__(self):
        # Dictionnaire des abréviations courantes
        self.abbreviations = {
            'rue': ['r', 'rue', 'r.', 'r°'],
            'avenue': ['av', 'ave', 'avenue', 'av.', 'ave.'],
            'boulevard': ['bd', 'blvd', 'boulevard', 'bd.', 'blvd.'],
            'place': ['pl', 'place', 'pl.'],
            'impasse': ['imp', 'impasse', 'imp.'],
            'chemin': ['ch', 'chemin', 'ch.'],
            'route': ['rt', 'route', 'rt.'],
            'allée': ['all', 'allée', 'allee', 'all.', 'alle'],
            'square': ['sq', 'square', 'sq.'],
            'passage': ['pass', 'passage', 'pass.'],
            'cours': ['cours', 'crs', 'crs.'],
            'quai': ['quai', 'q', 'q.'],
            'faubourg': ['fbg', 'faubourg', 'fbg.'],
            'esplanade': ['esp', 'esplanade', 'esp.'],
            'lotissement': ['lot', 'lotissement', 'lot.'],
            'residence': ['res', 'residence', 'résidence', 'res.']
        }
        
        # Mots à ignorer dans la comparaison
        self.stop_words = {'de', 'du', 'des', 'le', 'la', 'les', 'et', 'ou', 'd', 'l'}
        
        # Seuils de similarité
        self.similarity_thresholds = {
            'numero': 1.0,  # Numéro doit être exactement identique
            'voie': 0.75,   # Seul le nom de rue peut être approximatif
            'code_postal': 1.0,  # Code postal doit être exacte
            'ville': 1.0    # Ville doit être exactement identique
        }

    def normalize_string(self, text: str) -> str:
        """
        Normalise une chaîne de caractères pour la comparaison
        """
        if not text:
            return ""
        
        # Convertir en minuscules
        text = text.lower().strip()
        
        # Supprimer les accents
        replacements = {
            'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
            'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
            'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
            'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
            'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n'
        }
        
        for accent, replacement in replacements.items():
            text = text.replace(accent, replacement)
        
        # Supprimer la ponctuation et les caractères spéciaux
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Supprimer les espaces multiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def normalize_street_type(self, street: str) -> str:
        """
        Normalise le type de voie (rue, avenue, etc.)
        """
        street = self.normalize_string(street)
        words = street.split()
        
        normalized_words = []
        for word in words:
            # Chercher si le mot correspond à une abréviation
            found_replacement = False
            for full_form, abbreviations in self.abbreviations.items():
                if word in abbreviations:
                    normalized_words.append(full_form)
                    found_replacement = True
                    break
            
            if not found_replacement:
                normalized_words.append(word)
        
        return ' '.join(normalized_words)

    def extract_numbers(self, text: str) -> List[str]:
        """
        Extrait tous les nombres d'une chaîne
        """
        return re.findall(r'\d+', str(text))

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calcule la similarité entre deux chaînes
        """
        if not str1 and not str2:
            return 1.0
        if not str1 or not str2:
            return 0.0
        
        return SequenceMatcher(None, str1, str2).ratio()

    def compare_numbers(self, num1: str, num2: str) -> float:
        """
        Compare les numéros d'adresse - doit être exactement identique
        """
        if not num1 and not num2:
            return 1.0
        if not num1 or not num2:
            return 0.0
        
        # Extraire tous les nombres
        numbers1 = self.extract_numbers(str(num1))
        numbers2 = self.extract_numbers(str(num2))
        
        if not numbers1 and not numbers2:
            return 1.0
        if not numbers1 or not numbers2:
            return 0.0
        
        # Le numéro doit être exactement identique
        if numbers1[0] == numbers2[0]:
            return 1.0
        else:
            return 0.0  # Aucune tolérance pour les numéros

    def compare_streets(self, street1: str, street2: str) -> float:
        """
        Compare les noms de voies
        """
        if not street1 and not street2:
            return 1.0
        if not street1 or not street2:
            return 0.0
        
        # Normaliser les types de voies
        norm_street1 = self.normalize_street_type(street1)
        norm_street2 = self.normalize_street_type(street2)
        
        # Calculer la similarité directe
        direct_similarity = self.calculate_similarity(norm_street1, norm_street2)
        
        # Comparer mot par mot (pour gérer les réorganisations)
        words1 = set(norm_street1.split()) - self.stop_words
        words2 = set(norm_street2.split()) - self.stop_words
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        # Calculer la similarité des mots
        word_similarities = []
        for word1 in words1:
            best_match = max([self.calculate_similarity(word1, word2) for word2 in words2], default=0)
            word_similarities.append(best_match)
        
        word_similarity = sum(word_similarities) / len(word_similarities) if word_similarities else 0
        
        # Retourner la meilleure similarité
        return max(direct_similarity, word_similarity)

    def compare_postal_codes(self, code1: str, code2: str) -> float:
        """
        Compare les codes postaux - doivent être exactement identiques
        """
        if not code1 and not code2:
            return 1.0
        if not code1 or not code2:
            return 0.0
        
        # Les codes postaux doivent être identiques
        norm_code1 = re.sub(r'\D', '', str(code1))
        norm_code2 = re.sub(r'\D', '', str(code2))
        
        if norm_code1 == norm_code2:
            return 1.0
        else:
            return 0.0  # Aucune tolérance pour les codes postaux

    def compare_cities(self, city1: str, city2: str) -> float:
        """
        Compare les noms de villes - doivent être exactement identiques
        """
        if not city1 and not city2:
            return 1.0
        if not city1 or not city2:
            return 0.0
        
        norm_city1 = self.normalize_string(city1)
        norm_city2 = self.normalize_string(city2)
        
        # Les villes doivent être exactement identiques après normalisation
        if norm_city1 == norm_city2:
            return 1.0
        else:
            return 0.0  # Aucune tolérance pour les villes

    def parse_address_string(self, address_str: str) -> Optional[Dict]:
        """
        Parse une adresse sous forme de chaîne
        Format attendu: "numero voie code_postal ville"
        """
        if not address_str:
            return None
        
        address_str = address_str.strip()
        
        # Pattern pour extraire numero, voie, code postal et ville
        # Ex: "58 rue Alger 81600 Gaillac"
        pattern = r'^(\d+)\s+(.+?)\s+(\d{5})\s+(.+)$'
        match = re.match(pattern, address_str)
        
        if match:
            return {
                'numero': match.group(1),
                'voie': match.group(2).strip(),
                'code_postal': match.group(3),
                'ville': match.group(4).strip()
            }
        
        # Essayer un pattern plus flexible
        parts = address_str.split()
        if len(parts) >= 4:
            # Trouver le code postal (5 chiffres)
            code_postal_idx = None
            for i, part in enumerate(parts):
                if re.match(r'^\d{5}$', part):
                    code_postal_idx = i
                    break
            
            if code_postal_idx is not None and code_postal_idx > 0:
                return {
                    'numero': parts[0],
                    'voie': ' '.join(parts[1:code_postal_idx]),
                    'code_postal': parts[code_postal_idx],
                    'ville': ' '.join(parts[code_postal_idx + 1:])
                }
        
        return None

    def compare_addresses(self, address1: Address, address2: str, logger: Logger = None) -> Dict:
        """
        Compare une adresse structurée avec une adresse en chaîne
        
        Args:
            address1: Dict avec keys 'numero', 'voie', 'code_postal', 'ville'
            address2: String de l'adresse complète
            logger: Logger optionnel
            
        Returns:
            Dict avec les résultats de comparaison
        """
        if logger:
            logger.log(f"{address1['numero']} {address1['voie']}, {address1['code_postal']} {address1['ville']} VS {address2}", "INFO")
        
        parsed_address2 = self.parse_address_string(address2)
        
        if not parsed_address2:
            result = {
                'is_match': False,
                'overall_similarity': 0.0,
                'details': {
                    'numero': 0.0,
                    'voie': 0.0,
                    'code_postal': 0.0,
                    'ville': 0.0
                },
                'reason': 'Impossible de parser l\'adresse',
                'parsed_address2': None
            }
            if logger:
                logger.log(f"Impossible de parser l'adresse: '{address2}'", "DEBUG")
            return result
        
        # Comparer chaque composant
        similarities = {
            'numero': self.compare_numbers(
                str(address1.get('numero', '')), 
                str(parsed_address2.get('numero', ''))
            ),
            'voie': self.compare_streets(
                address1.get('voie', ''), 
                parsed_address2.get('voie', '')
            ),
            'code_postal': self.compare_postal_codes(
                address1.get('code_postal', ''), 
                parsed_address2.get('code_postal', '')
            ),
            'ville': self.compare_cities(
                address1.get('ville', ''), 
                parsed_address2.get('ville', '')
            )
        }
        
        # Calculer la similarité globale
        weights = {'numero': 0.2, 'voie': 0.4, 'code_postal': 0.2, 'ville': 0.2}
        overall_similarity = sum(similarities[key] * weights[key] for key in similarities)
        
        # Déterminer si c'est un match
        # TOUTES les conditions doivent être remplies :
        # - Numéro identique (seuil = 1.0)
        # - Code postal identique (seuil = 1.0) 
        # - Ville identique (seuil = 1.0)
        # - Rue approximativement similaire (seuil = 0.75)
        is_match = all(
            similarities[key] >= self.similarity_thresholds[key] 
            for key in similarities
        )
        
        # Si le numéro, code postal ou ville ne correspond pas exactement, pas de match
        strict_fields = ['numero', 'code_postal', 'ville']
        strict_match = all(similarities[field] == 1.0 for field in strict_fields)
        
        # Override: si les champs stricts ne matchent pas, forcer is_match à False
        if not strict_match:
            is_match = False
        
        result = {
            'is_match': is_match,
            'overall_similarity': overall_similarity,
            'details': similarities,
            'parsed_address2': parsed_address2,
            'strict_fields_match': strict_match,
            'reason': 'Comparaison réussie'
        }
        
        if logger:
            status = "MATCH" if is_match else "NO MATCH"
            logger.log(f"Résultat: {status}", "INFO")
        
        return result

    def is_address_match(self, address1: Address, address2: str, logger: Logger = None, threshold: float = 0.8) -> bool:
        """
        Méthode simplifiée pour vérifier si deux adresses correspondent
        
        Args:
            address1: Adresse structurée
            address2: Adresse en chaîne
            logger: Logger optionnel
            threshold: Seuil de similarité pour la rue uniquement (défaut: 0.75)
            
        Returns:
            bool: True si les adresses correspondent
        """
        comparison = self.compare_addresses(address1, address2, logger)
        
        # Match uniquement si les champs stricts sont identiques
        # ET que la rue est suffisamment similaire
        is_match = comparison['is_match']
        
        if logger:
            # Ne pas log dans is_address_match car déjà fait dans compare_addresses
            pass
        
        return is_match
