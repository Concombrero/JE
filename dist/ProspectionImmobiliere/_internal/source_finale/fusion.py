"""Module de fusion des résultats PJ et Entreprises"""

import csv
import os
import math
from typing import List, Dict, Any, Optional, Tuple

from tools import DataPJ, EntrepriseData, FusedData
from logger import Logger


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance en mètres entre deux points GPS (formule de Haversine).
    """
    R = 6371000  # Rayon de la Terre en mètres
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def is_interesting_result(entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Détermine si un résultat est "intéressant" à conserver.
    
    Critères d'intérêt (au moins 2 doivent être satisfaits):
    - A un numéro de téléphone (PJ ou entreprise)
    - A un email
    - A un site web
    - A un SIRET/SIREN (entreprise identifiée)
    - A un nom d'entreprise ou titre PJ
    - A des informations DPE/BDNB
    - A une surface de toiture > 100m² (potentiel photovoltaïque)
    
    Returns:
        Tuple (is_interesting: bool, reasons: List[str])
    """
    reasons = []
    score = 0
    
    # Téléphone
    has_phone = bool(entry.get("pj_phone"))
    ent_phones = entry.get("entreprise_phones") or []
    if has_phone or (ent_phones and len(ent_phones) > 0 and ent_phones[0]):
        score += 2  # Contact direct = très important
        reasons.append("telephone")
    
    # Email
    ent_emails = entry.get("entreprise_emails") or []
    if ent_emails and len(ent_emails) > 0 and ent_emails[0]:
        score += 2  # Contact direct = très important
        reasons.append("email")
    
    # Site web
    ent_websites = entry.get("entreprise_websites") or []
    if ent_websites and len(ent_websites) > 0 and ent_websites[0]:
        score += 1
        reasons.append("site_web")
    
    # SIRET/SIREN (entreprise officielle)
    if entry.get("entreprise_siret") or entry.get("entreprise_siren"):
        score += 2  # Entreprise identifiée = important
        reasons.append("siret_siren")
    
    # Nom identifié
    if entry.get("entreprise_nom") or entry.get("pj_title"):
        score += 1
        reasons.append("nom_identifie")
    
    # Informations DPE (bâtiment caractérisé)
    if entry.get("classe_bilan_dpe"):
        score += 1
        reasons.append("dpe")
    
    # Surface de toiture significative (potentiel photovoltaïque)
    roof_area = entry.get("roof_area_m2")
    if roof_area:
        try:
            if float(roof_area) >= 100:
                score += 2  # Grande surface = potentiel important
                reasons.append("grande_surface_toiture")
        except (ValueError, TypeError):
            pass
    
    # Surface parking (potentiel ombrières)
    parking_area = entry.get("parking_area_m2")
    if parking_area:
        try:
            if float(parking_area) >= 200:
                score += 1
                reasons.append("parking")
        except (ValueError, TypeError):
            pass
    
    # Propriétaire identifié
    if entry.get("owner_name"):
        score += 1
        reasons.append("proprietaire_identifie")
    
    # Un résultat est intéressant si score >= 3
    # (au moins un contact + une identification OU plusieurs critères)
    is_interesting = score >= 3
    
    return is_interesting, reasons


def filter_results_by_zone_and_interest(
    fused_data: List[FusedData],
    center_lat: float,
    center_lon: float,
    radius_km: float,
    logger: Logger
) -> Tuple[List[FusedData], List[FusedData], List[FusedData]]:
    """
    Filtre les résultats en 3 catégories:
    1. Dans la zone (tous gardés)
    2. Hors zone mais intéressants (gardés)
    3. Hors zone et non intéressants (exclus)
    
    Returns:
        Tuple (in_zone, out_zone_interesting, out_zone_excluded)
    """
    radius_m = radius_km * 1000
    # Tolérance de 20% pour les résultats légèrement hors zone
    tolerance_m = radius_m * 1.2
    
    in_zone = []
    out_zone_interesting = []
    out_zone_excluded = []
    
    for entry in fused_data:
        lat = entry.get("latitude")
        lon = entry.get("longitude")
        
        # Si pas de coordonnées, vérifier si intéressant
        if lat is None or lon is None:
            is_interesting, reasons = is_interesting_result(entry)
            if is_interesting:
                entry["_filter_status"] = "no_coords_but_interesting"
                entry["_interest_reasons"] = reasons
                out_zone_interesting.append(entry)
            else:
                entry["_filter_status"] = "no_coords_excluded"
                out_zone_excluded.append(entry)
            continue
        
        # Calculer la distance au centre
        distance = haversine_distance(center_lat, center_lon, lat, lon)
        entry["_distance_to_center"] = round(distance)
        
        if distance <= radius_m:
            # Dans la zone - garder
            entry["_filter_status"] = "in_zone"
            in_zone.append(entry)
        elif distance <= tolerance_m:
            # Légèrement hors zone (tolérance) - garder si a des coords
            entry["_filter_status"] = "in_tolerance_zone"
            in_zone.append(entry)
        else:
            # Hors zone - vérifier si intéressant
            is_interesting, reasons = is_interesting_result(entry)
            if is_interesting:
                entry["_filter_status"] = "out_zone_interesting"
                entry["_interest_reasons"] = reasons
                out_zone_interesting.append(entry)
            else:
                entry["_filter_status"] = "out_zone_excluded"
                out_zone_excluded.append(entry)
    
    logger.log(f"Filtrage zone: {len(in_zone)} dans zone, {len(out_zone_interesting)} hors zone interessants, {len(out_zone_excluded)} exclus", "INFO")
    
    return in_zone, out_zone_interesting, out_zone_excluded


def fuse_results(
    pj_results: List[DataPJ], 
    entreprise_results: List[EntrepriseData],
    logger: Logger
) -> List[FusedData]:
    """
    Fusionne les résultats Pages Jaunes et Entreprises.
    
    Deux stratégies de matching:
    1. Par coordonnées géographiques (même lat/lon à 0.0001 près)
    2. Par adresse normalisée (numéro + voie + code postal + ville)
    """
    fused = []
    
    # Index les résultats entreprises par adresse normalisée et par coordonnées
    entreprise_by_addr = {}
    entreprise_by_coords = {}
    
    for ent in entreprise_results:
        # Par adresse
        if ent.get("address"):
            key = _normalize_address_key(ent["address"])
            entreprise_by_addr[key] = ent
        
        # Par coordonnées (arrondi pour matching approximatif)
        if ent.get("latitude") and ent.get("longitude"):
            coord_key = (round(ent["latitude"], 4), round(ent["longitude"], 4))
            entreprise_by_coords[coord_key] = ent
    
    # Set pour tracker les entreprises déjà fusionnées
    matched_ent_keys = set()
    
    # Parcourir les résultats PJ et fusionner
    for pj in pj_results:
        addr = pj.get("address")
        if not addr:
            continue
        
        # Créer l'entrée fusionnée de base
        fused_entry: FusedData = {
            "numero": addr.get("numero", ""),
            "voie": addr.get("voie", ""),
            "code_postal": addr.get("code_postal", ""),
            "ville": addr.get("ville", ""),
            "latitude": pj.get("coords", {}).get("latitude") if pj.get("coords") else None,
            "longitude": pj.get("coords", {}).get("longitude") if pj.get("coords") else None,
            
            # PJ
            "pj_title": pj.get("contact", {}).get("title") if pj.get("contact") else None,
            "pj_phone": pj.get("contact", {}).get("phone") if pj.get("contact") else None,
            
            # BDNB
            "annee_construction": pj.get("bdnb", {}).get("annee_construction") if pj.get("bdnb") else None,
            "classe_bilan_dpe": pj.get("bdnb", {}).get("classe_bilan_dpe") if pj.get("bdnb") else None,
            
            # Entreprise (à remplir)
            "entreprise_nom": None,
            "entreprise_category": None,
            "entreprise_phones": None,
            "entreprise_emails": None,
            "entreprise_websites": None,
            "entreprise_siren": None,
            "entreprise_siret": None,
            "entreprise_naf": None,
            "owner_name": None,
            "owner_role": None,
            "roof_area_m2": None,
            "parking_area_m2": None,
            "building_year": None,
        }
        
        # Chercher correspondance entreprise - d'abord par coordonnées, puis par adresse
        ent = None
        ent_key = None
        
        # Matching par coordonnées
        pj_coords = pj.get("coords") or {}
        if pj_coords.get("latitude") and pj_coords.get("longitude"):
            coord_key = (round(pj_coords["latitude"], 4), round(pj_coords["longitude"], 4))
            if coord_key in entreprise_by_coords:
                ent = entreprise_by_coords[coord_key]
                ent_key = coord_key
        
        # Matching par adresse si pas trouvé par coords
        if not ent:
            addr_key = _make_address_key(addr)
            if addr_key in entreprise_by_addr:
                ent = entreprise_by_addr[addr_key]
                ent_key = addr_key
        
        # Remplir les données entreprise si trouvé
        if ent:
            matched_ent_keys.add(ent_key)
            
            fused_entry["entreprise_nom"] = ent.get("name")
            fused_entry["entreprise_category"] = ent.get("category")
            fused_entry["entreprise_phones"] = ent.get("phones")
            fused_entry["entreprise_emails"] = ent.get("emails")
            fused_entry["entreprise_websites"] = ent.get("websites")
            
            company_info = ent.get("company_info") or {}
            fused_entry["entreprise_siren"] = company_info.get("siren")
            fused_entry["entreprise_siret"] = company_info.get("siret")
            fused_entry["entreprise_naf"] = company_info.get("naf_libelle") or company_info.get("naf")
            
            owner_parts = []
            if ent.get("owner_first_name"):
                owner_parts.append(ent["owner_first_name"])
            if ent.get("owner_last_name"):
                owner_parts.append(ent["owner_last_name"])
            fused_entry["owner_name"] = " ".join(owner_parts) if owner_parts else None
            fused_entry["owner_role"] = ent.get("owner_role")
            
            fused_entry["roof_area_m2"] = ent.get("roof_area_m2")
            fused_entry["parking_area_m2"] = ent.get("parking_area_m2")
            fused_entry["building_year"] = ent.get("building_year")
            
            # Compléter les coords si manquantes
            if fused_entry["latitude"] is None and ent.get("latitude"):
                fused_entry["latitude"] = ent["latitude"]
            if fused_entry["longitude"] is None and ent.get("longitude"):
                fused_entry["longitude"] = ent["longitude"]
        
        fused.append(fused_entry)
    
    # Ajouter les entreprises qui n'ont pas de correspondance PJ
    for ent in entreprise_results:
        if not ent.get("address"):
            continue
        
        # Vérifier si déjà matché
        coord_key = None
        if ent.get("latitude") and ent.get("longitude"):
            coord_key = (round(ent["latitude"], 4), round(ent["longitude"], 4))
            if coord_key in matched_ent_keys:
                continue
        
        addr_key = _normalize_address_key(ent["address"])
        if addr_key in matched_ent_keys:
            continue
        
        # Nouvelle entrée uniquement entreprise
        fused_entry: FusedData = {
            "numero": "",
            "voie": "",
            "code_postal": "",
            "ville": "",
            "latitude": ent.get("latitude"),
            "longitude": ent.get("longitude"),
            
            "pj_title": None,
            "pj_phone": None,
            "annee_construction": None,
            "classe_bilan_dpe": None,
            
            "entreprise_nom": ent.get("name"),
            "entreprise_category": ent.get("category"),
            "entreprise_phones": ent.get("phones"),
            "entreprise_emails": ent.get("emails"),
            "entreprise_websites": ent.get("websites"),
            "entreprise_siren": (ent.get("company_info") or {}).get("siren"),
            "entreprise_siret": (ent.get("company_info") or {}).get("siret"),
            "entreprise_naf": (ent.get("company_info") or {}).get("naf_libelle"),
            "owner_name": _make_owner_name(ent),
            "owner_role": ent.get("owner_role"),
            "roof_area_m2": ent.get("roof_area_m2"),
            "parking_area_m2": ent.get("parking_area_m2"),
            "building_year": ent.get("building_year"),
        }
        
        # Parser l'adresse si possible
        parsed = _parse_address_string(ent["address"])
        if parsed:
            fused_entry["numero"] = parsed.get("numero", "")
            fused_entry["voie"] = parsed.get("voie", "")
            fused_entry["code_postal"] = parsed.get("code_postal", "")
            fused_entry["ville"] = parsed.get("ville", "")
        
        fused.append(fused_entry)
    
    logger.log(f"Fusion terminée: {len(fused)} entrées", "INFO")
    return fused


def _normalize_address_key(address_str: str) -> str:
    """Normalise une adresse string pour servir de clé"""
    return address_str.lower().strip().replace(",", " ").replace("  ", " ")


def _make_address_key(addr: Dict) -> str:
    """Crée une clé normalisée depuis un dict Address"""
    key = f"{addr.get('numero', '')} {addr.get('voie', '')} {addr.get('code_postal', '')} {addr.get('ville', '')}"
    return _normalize_address_key(key)


def _make_owner_name(ent: Dict) -> Optional[str]:
    """Construit le nom complet du propriétaire"""
    parts = []
    if ent.get("owner_first_name"):
        parts.append(ent["owner_first_name"])
    if ent.get("owner_last_name"):
        parts.append(ent["owner_last_name"])
    return " ".join(parts) if parts else None


def _parse_address_string(address_str: str) -> Optional[Dict]:
    """Parse une adresse string en composants"""
    import re
    
    if not address_str:
        return None
    
    # Pattern: "numero voie, code_postal ville"
    pattern = r'^(\d+)\s+(.+?),?\s+(\d{5})\s+(.+)$'
    match = re.match(pattern, address_str.strip())
    
    if match:
        return {
            "numero": match.group(1),
            "voie": match.group(2).strip(),
            "code_postal": match.group(3),
            "ville": match.group(4).strip()
        }
    
    return None


def save_fused_csv(fused_data: List[FusedData], output_file: str, logger: Logger):
    """Sauvegarde les données fusionnées en CSV"""
    logger.log(f"Sauvegarde CSV fusionné: {output_file}", "INFO")
    
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
    
    headers = [
        "Numero", "Voie", "Code_Postal", "Ville",
        "Latitude", "Longitude", "Distance_Centre_m",
        "PJ_Titre", "PJ_Telephone",
        "BDNB_Annee", "BDNB_DPE",
        "Entreprise_Nom", "Entreprise_Categorie",
        "Entreprise_Telephones", "Entreprise_Emails", "Entreprise_Sites",
        "SIREN", "SIRET", "NAF",
        "Proprietaire_Nom", "Proprietaire_Role",
        "Surface_Toiture_m2", "Surface_Parking_m2", "Annee_Construction_OSM"
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for entry in fused_data:
            row = [
                entry.get("numero", ""),
                entry.get("voie", ""),
                entry.get("code_postal", ""),
                entry.get("ville", ""),
                entry.get("latitude", ""),
                entry.get("longitude", ""),
                entry.get("_distance_to_center", ""),
                entry.get("pj_title", ""),
                entry.get("pj_phone", ""),
                entry.get("annee_construction", ""),
                entry.get("classe_bilan_dpe", ""),
                entry.get("entreprise_nom", ""),
                entry.get("entreprise_category", ""),
                "; ".join(entry.get("entreprise_phones") or []),
                "; ".join(entry.get("entreprise_emails") or []),
                "; ".join(entry.get("entreprise_websites") or []),
                entry.get("entreprise_siren", ""),
                entry.get("entreprise_siret", ""),
                entry.get("entreprise_naf", ""),
                entry.get("owner_name", ""),
                entry.get("owner_role", ""),
                entry.get("roof_area_m2", ""),
                entry.get("parking_area_m2", ""),
                entry.get("building_year", ""),
            ]
            writer.writerow(row)
    
    logger.both(f"CSV fusionné sauvegardé: {output_file}", "SUCCESS")


def has_useful_data(entry: FusedData) -> bool:
    """
    Vérifie si une entrée a des données utiles (pas juste l'adresse et le statut de filtrage).
    
    Une entrée est considérée comme utile si elle a au moins un des éléments suivants:
    - Titre PJ ou téléphone PJ
    - Nom d'entreprise
    - SIREN/SIRET
    - Téléphone, email ou site web d'entreprise
    - Propriétaire identifié
    - Données BDNB (année construction ou DPE)
    """
    # Données PJ
    if entry.get("pj_title") or entry.get("pj_phone"):
        return True
    
    # Données entreprise
    if entry.get("entreprise_nom"):
        return True
    if entry.get("entreprise_siren") or entry.get("entreprise_siret"):
        return True
    
    phones = entry.get("entreprise_phones") or []
    emails = entry.get("entreprise_emails") or []
    websites = entry.get("entreprise_websites") or []
    if phones or emails or websites:
        return True
    
    # Propriétaire
    if entry.get("owner_name"):
        return True
    
    # BDNB
    if entry.get("annee_construction") or entry.get("classe_bilan_dpe"):
        return True
    
    return False


def filter_empty_results(fused_data: List[FusedData], logger: Logger) -> List[FusedData]:
    """
    Filtre les résultats pour ne garder que ceux avec des données utiles.
    """
    useful = [entry for entry in fused_data if has_useful_data(entry)]
    removed = len(fused_data) - len(useful)
    
    if removed > 0:
        logger.log(f"Filtrage: {removed} entrées vides supprimées, {len(useful)} entrées conservées", "INFO")
    
    return useful


def save_filtered_results(
    in_zone: List[FusedData],
    out_zone_interesting: List[FusedData],
    out_zone_excluded: List[FusedData],
    output_dir: str,
    logger: Logger
):
    """
    Sauvegarde les résultats filtrés.
    Ne garde que les résultats avec des données utiles.
    """
    # Résultats principaux (dans zone + hors zone intéressants)
    main_results = in_zone + out_zone_interesting
    
    # Filtrer les résultats vides
    main_results = filter_empty_results(main_results, logger)
    
    main_file = os.path.join(output_dir, 'resultats_fusionnes.csv')
    save_fused_csv(main_results, main_file, logger)
    
    # Résumé
    logger.both(f"Resultats finaux: {len(main_results)} entrées avec données utiles", "SUCCESS")
    
    return main_results


def load_fused_csv(csv_file: str, logger: Logger) -> List[Dict[str, Any]]:
    """Charge un CSV fusionné pour l'affichage carte"""
    results = []
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                entry = {
                    "numero": row.get("Numero", ""),
                    "voie": row.get("Voie", ""),
                    "code_postal": row.get("Code_Postal", ""),
                    "ville": row.get("Ville", ""),
                    "latitude": float(row["Latitude"]) if row.get("Latitude") else None,
                    "longitude": float(row["Longitude"]) if row.get("Longitude") else None,
                    "_distance_to_center": int(row["Distance_Centre_m"]) if row.get("Distance_Centre_m") else None,
                    "pj_title": row.get("PJ_Titre"),
                    "pj_phone": row.get("PJ_Telephone"),
                    "annee_construction": row.get("BDNB_Annee"),
                    "classe_bilan_dpe": row.get("BDNB_DPE"),
                    "entreprise_nom": row.get("Entreprise_Nom"),
                    "entreprise_category": row.get("Entreprise_Categorie"),
                    "entreprise_phones": row.get("Entreprise_Telephones", "").split("; ") if row.get("Entreprise_Telephones") else [],
                    "entreprise_emails": row.get("Entreprise_Emails", "").split("; ") if row.get("Entreprise_Emails") else [],
                    "entreprise_websites": row.get("Entreprise_Sites", "").split("; ") if row.get("Entreprise_Sites") else [],
                    "entreprise_siren": row.get("SIREN"),
                    "entreprise_siret": row.get("SIRET"),
                    "entreprise_naf": row.get("NAF"),
                    "owner_name": row.get("Proprietaire_Nom"),
                    "owner_role": row.get("Proprietaire_Role"),
                    "roof_area_m2": row.get("Surface_Toiture_m2"),
                    "parking_area_m2": row.get("Surface_Parking_m2"),
                    "building_year": row.get("Annee_Construction_OSM"),
                }
                results.append(entry)
        
        logger.log(f"Chargé {len(results)} entrées depuis {csv_file}", "INFO")
        
    except Exception as e:
        logger.log(f"Erreur chargement CSV {csv_file}: {e}", "ERROR")
    
    return results


def fused_to_map_features(fused_data: List[FusedData]) -> List[Dict[str, Any]]:
    """Convertit les données fusionnées en features pour la carte"""
    features = []
    
    for entry in fused_data:
        lat = entry.get("latitude")
        lon = entry.get("longitude")
        
        if lat is None or lon is None:
            continue
        
        feature = {
            "lat": lat,
            "lon": lon,
            **entry
        }
        features.append(feature)
    
    return features
