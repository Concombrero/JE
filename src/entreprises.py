"""Module de recherche et enrichissement des entreprises (workflow src_2)"""

import re
import time
import math
from typing import Any, Dict, List, Optional, Tuple

import requests
from pyproj import Geod

from tools import Address, Street, EntrepriseData, listify, sanitize
from logger import Logger


# Constantes
UA = {"User-Agent": "prospection-open-data/1.2"}
BAN_URL = "https://api-adresse.data.gouv.fr/search/"
RE_URL = "https://recherche-entreprises.api.gouv.fr/search"
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
GEOD = Geod(ellps="WGS84")


def _retry_get(url: str, params: Dict, headers: Dict, timeout: int = 20, tries: int = 3) -> requests.Response:
    """Requête GET avec retry"""
    last_exc = None
    for i in range(tries):
        try:
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(1.5 ** (i + 1))
    raise last_exc


def _retry_post(url: str, data: Dict, headers: Dict, timeout: int = 30, tries: int = 3) -> requests.Response:
    """Requête POST avec retry"""
    last_exc = None
    for i in range(tries):
        try:
            return requests.post(url, data=data, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(1.7 ** (i + 1))
    raise last_exc


class EntrepriseSearcher:
    """Classe pour la recherche et l'enrichissement des entreprises"""
    
    def __init__(self):
        pass
    
    # ==================== Géocodage BAN ====================
    
    def geocode_ban(self, address: str) -> Optional[Dict[str, Any]]:
        """Géocode une adresse via la BAN"""
        params = {"q": address, "limit": 1}
        r = _retry_get(BAN_URL, params=params, headers=UA, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        if not data.get("features"):
            return None
        
        f = data["features"][0]
        lon, lat = f["geometry"]["coordinates"]
        props = f.get("properties", {})
        
        return {
            "lat": float(lat),
            "lon": float(lon),
            "label": props.get("label"),
            "housenumber": props.get("housenumber"),
            "street": props.get("street"),
            "postcode": props.get("postcode"),
            "city": props.get("city"),
            "citycode": props.get("citycode"),
        }
    
    # ==================== API Recherche Entreprises ====================
    
    def _call_re(self, params: Dict) -> Dict:
        """Appel à l'API Recherche d'entreprises"""
        base = {
            "page": 1,
            "per_page": params.pop("per_page", params.pop("limit", 10)),
        }
        
        include_val = params.get("include")
        if include_val:
            base["minimal"] = "true"
        
        p = {**base, **params}
        r = _retry_get(RE_URL, params=p, headers=UA, timeout=20)
        
        if r.status_code == 400:
            raise requests.HTTPError(f"400: {r.text[:500]}", response=r)
        r.raise_for_status()
        
        return r.json()
    
    def search_company(
        self, 
        name: str, 
        commune_insee: Optional[str] = None,
        code_postal: Optional[str] = None,
        limit: int = 5,
        include_dirigeants: bool = True
    ) -> List[Dict]:
        """Recherche d'entreprises par nom"""
        params = {"q": name, "per_page": limit}
        
        if code_postal:
            params["code_postal"] = code_postal
        if commune_insee:
            params["code_commune"] = commune_insee
        if include_dirigeants:
            params["include"] = "dirigeants"
            params["minimal"] = "true"
        
        data = self._call_re(params)
        results = data.get("results", [])
        
        out = []
        for it in results:
            if not isinstance(it, dict):
                continue
            
            siege = it.get("siege") or {}
            adresse = siege.get("adresse") or {}
            naf = it.get("activite_principale") or {}
            
            # Dirigeants
            dir_list = it.get("dirigeants") or []
            dirigeants = []
            for d in dir_list:
                nd = self._normalize_dirigeant(d)
                if nd:
                    dirigeants.append(nd)
            
            out.append({
                "siren": it.get("siren"),
                "nom_complet": it.get("nom_complet") or it.get("nom_raison_sociale"),
                "etat_administratif": it.get("etat_administratif"),
                "date_creation": it.get("date_creation"),
                "categorie_juridique": it.get("categorie_juridique"),
                "naf": naf.get("code") if isinstance(naf, dict) else naf,
                "naf_libelle": naf.get("libelle") if isinstance(naf, dict) else None,
                "siret_siege": siege.get("siret"),
                "adresse_siege": adresse.get("label") if isinstance(adresse, dict) else None,
                "dirigeants": dirigeants,
            })
        
        return out
    
    def _normalize_dirigeant(self, d: Dict) -> Optional[Dict]:
        """Normalise un enregistrement dirigeant"""
        if not isinstance(d, dict):
            return None
        
        typ = (d.get("type") or "").lower()
        if "morale" in typ:
            return None
        
        last = d.get("nom") or d.get("nom_naissance")
        first = d.get("prenom") or d.get("prenoms")
        if isinstance(first, str) and " " in first:
            first = first.split(" ", 1)[0]
        
        role = d.get("fonction") or d.get("role") or d.get("qualite")
        
        if not last and not first:
            return None
        
        return {
            "first_name": first,
            "last_name": last,
            "role": role
        }
    
    # ==================== Overpass / OSM ====================
    
    def _overpass(self, query: str) -> Dict:
        """Exécute une requête Overpass"""
        r = _retry_post(OVERPASS_URL, data={"data": query}, headers=UA, timeout=60)
        r.raise_for_status()
        return r.json()
    
    def _polygon_area_m2(self, coords: List[Tuple[float, float]]) -> float:
        """Calcule l'aire d'un polygone en m²"""
        if len(coords) < 3:
            return 0.0
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        lons, lats = zip(*coords)
        area, _ = GEOD.polygon_area_perimeter(lons, lats)
        return abs(area)
    
    def _way_area_from_geom(self, elt: Dict) -> float:
        """Calcule l'aire d'un way OSM"""
        if elt.get("type") != "way":
            return 0.0
        geom = elt.get("geometry")
        if isinstance(geom, list) and len(geom) >= 3:
            coords = [(pt["lon"], pt["lat"]) for pt in geom if "lon" in pt and "lat" in pt]
            if len(coords) >= 3:
                return self._polygon_area_m2(coords)
        return 0.0
    
    def get_osm_contacts(self, lat: float, lon: float, company_name: str, radius: int = 200) -> Dict:
        """Récupère les contacts OSM pour une entreprise"""
        
        def _norm(s: str) -> str:
            if not s:
                return ""
            s = s.lower().replace("'", "'")
            s = re.sub(r"[^a-z0-9@:/._-]+", " ", s)
            return re.sub(r"\s+", " ", s).strip()
        
        def _tokens(s: str):
            return [t for t in re.split(r"[^\w]+", _norm(s)) if t and len(t) > 1]
        
        def _name_match(query: str, candidate: str) -> bool:
            nq, nc = _norm(query), _norm(candidate)
            if not nq or not nc:
                return False
            if nq == nc:
                return True
            tq, tc = set(_tokens(query)), set(_tokens(candidate))
            if tq and (tq == tc or tq.issubset(tc)):
                return True
            return False
        
        def _normalize_phone(raw: str) -> Optional[str]:
            if not raw:
                return None
            s = re.sub(r"[^\d+]", "", raw)
            if s.startswith("+"):
                return s if re.fullmatch(r"\+\d{6,15}", s) else None
            s_digits = re.sub(r"\D", "", raw)
            if re.fullmatch(r"0\d{9}", s_digits):
                return "+33" + s_digits[1:]
            return None
        
        def _is_email(s: str) -> bool:
            return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s or "", re.I))
        
        q = f"""
        [out:json][timeout:25];
        (
          node(around:{radius},{lat},{lon})[~"^(name|brand)$"~".*"];
          way(around:{radius},{lat},{lon})[~"^(name|brand)$"~".*"];
        );
        out tags center 50;
        """
        
        data = self._overpass(q)
        
        for elt in data.get("elements", []):
            tags = elt.get("tags") or {}
            name = tags.get("name") or tags.get("brand")
            if not name or not _name_match(company_name, name):
                continue
            
            # Extraire contacts
            phones, emails, websites = [], [], []
            
            for ph in [tags.get("phone"), tags.get("contact:phone")]:
                if ph:
                    for p in re.split(r"[,/;]", str(ph)):
                        norm = _normalize_phone(p)
                        if norm and norm not in phones:
                            phones.append(norm)
            
            for em in [tags.get("email"), tags.get("contact:email")]:
                if em:
                    for e in re.split(r"[,/;\s]+", str(em)):
                        if _is_email(e) and e.lower() not in emails:
                            emails.append(e.lower())
            
            for w in [tags.get("website"), tags.get("contact:website")]:
                if w:
                    for url in re.split(r"[,;\s]+", str(w)):
                        if url and url not in websites:
                            if not url.startswith("http"):
                                url = "https://" + url
                            websites.append(url)
            
            categories = []
            for k in ("amenity", "shop", "office", "craft"):
                if tags.get(k):
                    categories.append(f"{k}={tags.get(k)}")
            
            return {
                "phones": phones,
                "emails": emails,
                "websites": websites,
                "osm_categories": categories,
                "match_count": 1
            }
        
        return {"phones": [], "emails": [], "websites": [], "osm_categories": [], "match_count": 0}
    
    def get_surfaces_and_year(self, lat: float, lon: float, radius: int = 250) -> Dict:
        """Récupère les surfaces toiture/parking et année de construction"""
        
        # Bâtiments
        q_build = f"""
        [out:json][timeout:30];
        way(around:{radius},{lat},{lon})["building"];
        out tags geom;
        """
        data_b = self._overpass(q_build)
        
        total_roof = 0.0
        years = []
        
        for elt in data_b.get("elements", []):
            tags = elt.get("tags", {})
            try:
                total_roof += self._way_area_from_geom(elt)
            except Exception:
                pass
            
            for key in ("start_date", "building:year_built", "year_built"):
                v = tags.get(key)
                if v and str(v)[:4].isdigit():
                    y = int(str(v)[:4])
                    if 1700 <= y <= 2100:
                        years.append(y)
                        break
        
        # Parkings
        total_park = 0.0
        try:
            q_park = f"""
            [out:json][timeout:30];
            way(around:{radius},{lat},{lon})["amenity"="parking"];
            out tags geom;
            """
            data_p = self._overpass(q_park)
            for elt in data_p.get("elements", []):
                total_park += self._way_area_from_geom(elt)
        except Exception:
            pass
        
        return {
            "roof_area_m2": round(total_roof, 1) if total_roof > 0 else None,
            "parking_area_m2": round(total_park, 1) if total_park > 0 else None,
            "building_year": years[len(years)//2] if years else None
        }
    
    def _pick_owner(self, dirigeants: List[Dict]) -> Optional[Dict]:
        """Choisit le dirigeant principal"""
        if not dirigeants:
            return None
        if len(dirigeants) == 1:
            return dirigeants[0]
        
        def score(d):
            r = (d.get("role") or "").lower()
            if "entrepreneur" in r or "exploitant" in r:
                return 100
            if "gérant" in r or "gerant" in r:
                return 90
            if "président" in r or "president" in r:
                return 80
            return 10
        
        return max(dirigeants, key=score)
    
    # ==================== Workflow principal ====================
    
    def enrich_business(self, name: str, address: str, logger: Logger) -> Optional[EntrepriseData]:
        """Enrichit les données d'une entreprise"""
        try:
            # Géocodage
            geo = self.geocode_ban(address)
            if not geo:
                logger.log(f"Géocodage impossible pour: {address}", "DEBUG")
                return None
            
            lat, lon = geo["lat"], geo["lon"]
            
            # Recherche entreprise
            companies = self.search_company(
                name,
                commune_insee=geo.get("citycode"),
                code_postal=geo.get("postcode"),
                limit=5,
                include_dirigeants=True
            )
            
            # Owner
            owner = None
            company_info = {}
            if companies:
                owner = self._pick_owner(companies[0].get("dirigeants") or [])
                company_info = {
                    "siren": companies[0].get("siren"),
                    "siret": companies[0].get("siret_siege"),
                    "nom_complet": companies[0].get("nom_complet"),
                    "naf": companies[0].get("naf"),
                    "naf_libelle": companies[0].get("naf_libelle"),
                }
            
            # Contacts OSM
            contacts = self.get_osm_contacts(lat, lon, name, radius=200)
            
            # Surfaces et année
            surf = self.get_surfaces_and_year(lat, lon, radius=250)
            
            return {
                "name": name,
                "category": contacts.get("osm_categories", [None])[0] if contacts.get("osm_categories") else None,
                "address": address,
                "distance_m": None,
                "phones": contacts.get("phones", []),
                "emails": contacts.get("emails", []),
                "websites": contacts.get("websites", []),
                "socials": [],
                "company_info": company_info,
                "owner_first_name": owner.get("first_name") if owner else None,
                "owner_last_name": owner.get("last_name") if owner else None,
                "owner_role": owner.get("role") if owner else None,
                "building_year": surf.get("building_year"),
                "roof_area_m2": surf.get("roof_area_m2"),
                "parking_area_m2": surf.get("parking_area_m2"),
                "latitude": lat,
                "longitude": lon,
            }
            
        except Exception as e:
            logger.log(f"Erreur enrichissement entreprise {name}: {e}", "ERROR")
            return None
    
    def process_street(self, street: Street, logger: Logger) -> List[EntrepriseData]:
        """Traite une rue pour trouver et enrichir les entreprises"""
        results = []
        
        for number in street["numbers"]:
            address_str = f"{number} {street['name']}, {street['postal_code']} {street['city']}"
            
            # Rechercher entreprises à cette adresse
            geo = self.geocode_ban(address_str)
            if not geo:
                continue
            
            # Chercher les POI proches avec des contacts
            contacts = self.get_osm_contacts(geo["lat"], geo["lon"], "", radius=50)
            
            if contacts.get("phones") or contacts.get("emails"):
                data = {
                    "name": "Inconnu",
                    "category": contacts.get("osm_categories", [None])[0] if contacts.get("osm_categories") else None,
                    "address": address_str,
                    "distance_m": None,
                    "phones": contacts.get("phones", []),
                    "emails": contacts.get("emails", []),
                    "websites": contacts.get("websites", []),
                    "socials": [],
                    "company_info": {},
                    "owner_first_name": None,
                    "owner_last_name": None,
                    "owner_role": None,
                    "building_year": None,
                    "roof_area_m2": None,
                    "parking_area_m2": None,
                    "latitude": geo["lat"],
                    "longitude": geo["lon"],
                }
                results.append(data)
        
        return results


def has_contact(data: Dict) -> bool:
    """Vérifie si les données ont au moins un contact"""
    contacts = data.get("contacts_osm") or {}
    phones = listify(contacts.get("phones"))
    emails = listify(contacts.get("emails"))
    return len(phones) > 0 or len(emails) > 0


def extract_contacts(data: Dict) -> Dict:
    """Extrait les contacts d'un dict de données"""
    contacts = data.get("contacts_osm") or {}
    return {
        "phones": [sanitize(x) for x in listify(contacts.get("phones")) if x],
        "emails": [sanitize(x) for x in listify(contacts.get("emails")) if x],
        "websites": [sanitize(x) for x in listify(contacts.get("websites")) if x],
        "socials": [sanitize(x) for x in listify(contacts.get("socials")) if x],
    }
