"""Module de fusion des résultats PJ et Entreprises"""

import csv
import os
from typing import List, Dict, Any, Optional

from tools import DataPJ, EntrepriseData, FusedData
from logger import Logger


def fuse_results(
    pj_results: List[DataPJ], 
    entreprise_results: List[EntrepriseData],
    logger: Logger
) -> List[FusedData]:
    """
    Fusionne les résultats Pages Jaunes et Entreprises.
    Matching par adresse (numéro + voie + code postal + ville).
    """
    fused = []
    
    # Index les résultats entreprises par adresse normalisée
    entreprise_index = {}
    for ent in entreprise_results:
        if ent.get("address"):
            key = _normalize_address_key(ent["address"])
            entreprise_index[key] = ent
    
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
        
        # Chercher correspondance entreprise
        addr_key = _make_address_key(addr)
        if addr_key in entreprise_index:
            ent = entreprise_index[addr_key]
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
    pj_keys = {_make_address_key(pj["address"]) for pj in pj_results if pj.get("address")}
    
    for ent in entreprise_results:
        if not ent.get("address"):
            continue
        
        key = _normalize_address_key(ent["address"])
        if key in pj_keys:
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
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    headers = [
        "Numero", "Voie", "Code_Postal", "Ville",
        "Latitude", "Longitude",
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
