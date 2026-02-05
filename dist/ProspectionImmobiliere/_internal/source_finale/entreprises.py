"""Module de recherche et enrichissement des entreprises (workflow src_2)

Ce module implémente:
1. Recherche d'entreprises/commerces autour d'une adresse via Overpass (OSM)
2. Enrichissement des données via API Recherche Entreprises (dirigeants, SIRET, etc.)
3. Récupération des contacts OSM (téléphone, email, site web)
4. Récupération des surfaces toiture/parking et année de construction
"""

import re
import time
import math
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from pyproj import Geod

from tools import Address, Street, EntrepriseData, listify, sanitize
from logger import Logger


# Constantes
UA = {"User-Agent": "prospection-open-data/1.2"}
BAN_URL = "https://api-adresse.data.gouv.fr/search/"
RE_URL = "https://recherche-entreprises.api.gouv.fr/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
GEOD = Geod(ellps="WGS84")

# Rayon de recherche autour de chaque adresse (en mètres)
SEARCH_RADIUS_M = 100


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
    
    def geocode_ban(self, address: str, logger: Optional[Logger] = None) -> Optional[Dict[str, Any]]:
        """Géocode une adresse via la BAN avec gestion des erreurs"""
        params = {"q": address, "limit": 1}
        
        try:
            r = _retry_get(BAN_URL, params=params, headers=UA, timeout=20)
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.HTTPError as e:
            if logger:
                logger.log(f"Erreur HTTP géocodage BAN ({e.response.status_code}): {address}", "WARNING")
            return None
        except requests.exceptions.RequestException as e:
            if logger:
                logger.log(f"Erreur réseau géocodage BAN: {address} - {e}", "WARNING")
            return None
        
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
    
    def _overpass(self, query: str, max_retries: int = 3) -> Dict:
        """Exécute une requête Overpass avec retry et fallback sur plusieurs serveurs"""
        last_error = None
        
        for url in OVERPASS_URLS:
            for attempt in range(max_retries):
                try:
                    r = requests.post(url, data={"data": query}, headers=UA, timeout=60)
                    r.raise_for_status()
                    data = r.json()
                    
                    # Vérifier que la réponse est valide
                    if "elements" in data:
                        return data
                    
                    # Réponse invalide, essayer le serveur suivant
                    break
                    
                except requests.exceptions.Timeout:
                    last_error = f"Timeout sur {url.split('/')[2]}"
                    time.sleep(2 * (attempt + 1))
                    
                except requests.exceptions.RequestException as e:
                    last_error = f"Erreur sur {url.split('/')[2]}: {e}"
                    time.sleep(2 * (attempt + 1))
                    
                except Exception as e:
                    last_error = f"Erreur inattendue: {e}"
                    time.sleep(1)
        
        # Retourner un dict vide avec elements si tous les serveurs échouent
        return {"elements": []}
    
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
    
    # ==================== Recherche de commerces/entreprises OSM ====================
    
    def find_businesses_osm(self, lat: float, lon: float, radius: int = 200, logger: Optional[Logger] = None) -> List[Dict]:
        """
        Recherche des commerces et entreprises autour d'un point via Overpass (OSM).
        
        Retourne une liste de dicts avec:
        - name: nom de l'entreprise
        - category: catégorie (shop/office/amenity)
        - lat, lon: coordonnées
        - tags: tous les tags OSM
        """
        q = f"""
        [out:json][timeout:30];
        (
          node(around:{radius},{lat},{lon})["name"]["office"];
          node(around:{radius},{lat},{lon})["name"]["shop"];
          node(around:{radius},{lat},{lon})["name"]["craft"];
          node(around:{radius},{lat},{lon})["name"]["amenity"~"restaurant|cafe|bank|pharmacy|clinic|dentist|doctors|veterinary"];
          way(around:{radius},{lat},{lon})["name"]["office"];
          way(around:{radius},{lat},{lon})["name"]["shop"];
          way(around:{radius},{lat},{lon})["name"]["craft"];
          way(around:{radius},{lat},{lon})["name"]["amenity"~"restaurant|cafe|bank|pharmacy|clinic|dentist|doctors|veterinary"];
        );
        out center tags;
        """
        
        data = self._overpass(q)
        businesses = []
        
        for elt in data.get("elements", []):
            tags = elt.get("tags") or {}
            name = tags.get("name")
            if not name:
                continue
            
            # Déterminer la catégorie
            category = None
            for cat_key in ("office", "shop", "craft", "amenity"):
                if tags.get(cat_key):
                    category = f"{cat_key}={tags[cat_key]}"
                    break
            
            # Coordonnées (pour les ways, utiliser center)
            if elt.get("type") == "node":
                b_lat = elt.get("lat")
                b_lon = elt.get("lon")
            else:
                center = elt.get("center") or {}
                b_lat = center.get("lat")
                b_lon = center.get("lon")
            
            if b_lat is None or b_lon is None:
                continue
            
            # Construire l'adresse à partir des tags
            addr_parts = []
            if tags.get("addr:housenumber"):
                addr_parts.append(tags["addr:housenumber"])
            if tags.get("addr:street"):
                addr_parts.append(tags["addr:street"])
            if tags.get("addr:postcode"):
                addr_parts.append(tags["addr:postcode"])
            if tags.get("addr:city"):
                addr_parts.append(tags["addr:city"])
            address = ", ".join(addr_parts) if addr_parts else None
            
            businesses.append({
                "name": name,
                "category": category,
                "lat": float(b_lat),
                "lon": float(b_lon),
                "address": address,
                "tags": tags,
            })
        
        return businesses

    # ==================== Workflow principal ====================
    
    def enrich_business(self, name: str, address: str, lat: float, lon: float, 
                        city: str = None, postal_code: str = None, 
                        logger: Optional[Logger] = None) -> Optional[EntrepriseData]:
        """
        Enrichit les données d'une entreprise trouvée via OSM.
        
        Étapes:
        1. Recherche dans l'API Recherche Entreprises (SIREN/SIRET + dirigeants)
        2. Récupération des contacts OSM (téléphone, email, site web)
        3. Récupération des surfaces toiture/parking et année de construction
        """
        try:
            # Déterminer le code postal et la ville
            citycode = None
            
            if not postal_code or not city:
                # Essayer de géocoder pour avoir le code postal/ville
                geo = self.geocode_ban(f"{lat},{lon}" if address is None else address, logger)
                if geo:
                    postal_code = postal_code or geo.get("postcode")
                    city = city or geo.get("city")
                    citycode = geo.get("citycode")
            
            # Recherche entreprise dans l'API officielle
            companies = []
            try:
                companies = self.search_company(
                    name,
                    commune_insee=citycode,
                    code_postal=postal_code,
                    limit=5,
                    include_dirigeants=True
                )
            except Exception as e:
                if logger:
                    logger.log(f"Erreur API Recherche Entreprises pour '{name}': {e}", "DEBUG")
            
            # Extraire owner et company_info
            owner = None
            company_info = {}
            if companies:
                best = companies[0]
                owner = self._pick_owner(best.get("dirigeants") or [])
                company_info = {
                    "siren": best.get("siren"),
                    "siret": best.get("siret_siege"),
                    "nom_complet": best.get("nom_complet"),
                    "naf": best.get("naf"),
                    "naf_libelle": best.get("naf_libelle"),
                }
            
            # Contacts OSM
            contacts = self.get_osm_contacts(lat, lon, name, radius=100)
            
            # Surfaces et année
            surf = self.get_surfaces_and_year(lat, lon, radius=150)
            
            # Construire l'adresse complète si pas fournie
            if not address:
                address = f"{city}, {postal_code}" if city and postal_code else ""
            
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
            if logger:
                logger.log(f"Erreur enrichissement entreprise {name}: {e}", "ERROR")
            return None
    
    def process_street(self, street: Street, logger: Logger) -> List[EntrepriseData]:
        """
        Traite une rue pour trouver et enrichir les entreprises.
        
        Pour chaque numéro de rue:
        1. Géocode l'adresse
        2. Recherche des entreprises/commerces OSM dans un rayon de 100m
        3. Enrichit chaque entreprise trouvée
        """
        results = []
        seen_names = set()  # Pour éviter les doublons
        
        for number in street["numbers"]:
            address_str = f"{number} {street['name']}, {street['postal_code']} {street['city']}"
            
            # Géocoder l'adresse
            geo = self.geocode_ban(address_str, logger)
            if not geo:
                logger.log(f"Impossible de géocoder: {address_str}", "DEBUG")
                continue
            
            # Rechercher les entreprises OSM autour de ce point
            businesses = self.find_businesses_osm(
                geo["lat"], geo["lon"], 
                radius=SEARCH_RADIUS_M, 
                logger=logger
            )
            
            for biz in businesses:
                # Éviter les doublons (même nom déjà traité)
                biz_key = (biz["name"].lower().strip(), biz.get("lat"), biz.get("lon"))
                if biz_key in seen_names:
                    continue
                seen_names.add(biz_key)
                
                # Utiliser l'adresse OSM si disponible, sinon l'adresse recherchée
                biz_address = biz.get("address") or address_str
                
                # Enrichir l'entreprise
                enriched = self.enrich_business(
                    name=biz["name"],
                    address=biz_address,
                    lat=biz["lat"],
                    lon=biz["lon"],
                    city=street["city"],
                    postal_code=street["postal_code"],
                    logger=logger
                )
                
                if enriched:
                    # Ajouter la catégorie OSM si pas déjà définie
                    if not enriched.get("category") and biz.get("category"):
                        enriched["category"] = biz["category"]
                    results.append(enriched)
        
        logger.log(f"[Entreprises] Rue '{street['name']}': {len(results)} entreprise(s) trouvee(s)", "INFO")
        return results
    
    def process_pj_results(self, pj_results: List[Dict], logger: Logger) -> List[EntrepriseData]:
        """
        Enrichit les résultats Pages Jaunes.
        
        Pour chaque résultat PJ qui a un nom (titre PJ):
        1. Essaie de trouver l'entreprise dans l'API Recherche Entreprises
        2. Récupère les contacts OSM et surfaces
        """
        results = []
        seen = set()
        
        for pj in pj_results:
            contact = pj.get("contact") or {}
            title = contact.get("title")
            
            # Ignorer si pas de titre
            if not title:
                continue
            
            # Extraire le nom de l'entreprise du titre PJ
            # Format typique: "Nom Entreprise Ville - Activité (adresse, horaires, avis)"
            name = title
            
            # Enlever les parenthèses et leur contenu à la fin
            # Ex: "(adresse, horaires)" ou "(adresse, horaires, avis)"
            if "(" in name:
                name = name.split("(")[0].strip()
            
            # Séparer sur " - " pour enlever l'activité
            if " - " in name:
                name = name.split(" - ")[0].strip()
            
            # Enlever le nom de ville à la fin si présent (format: "Entreprise Meylan")
            addr = pj.get("address") or {}
            city = addr.get("ville", "")
            if city and name.lower().endswith(" " + city.lower()):
                name = name[:-len(city)-1].strip()
            
            # Si le nom est toujours vide ou trop court, skip
            if len(name) < 2:
                continue
            
            # Éviter les doublons
            key = (name.lower(), addr.get("voie", "").lower(), addr.get("numero", ""))
            if key in seen:
                continue
            seen.add(key)
            
            # Coordonnées
            coords = pj.get("coords") or {}
            lat = coords.get("latitude")
            lon = coords.get("longitude")
            
            if not lat or not lon:
                continue
            
            # Construire l'adresse
            address_str = f"{addr.get('numero', '')} {addr.get('voie', '')}, {addr.get('code_postal', '')} {addr.get('ville', '')}".strip()
            
            # Enrichir
            enriched = self.enrich_business(
                name=name,
                address=address_str,
                lat=lat,
                lon=lon,
                city=addr.get("ville"),
                postal_code=addr.get("code_postal"),
                logger=logger
            )
            
            if enriched:
                results.append(enriched)
        
        logger.log(f"[Entreprises] {len(results)} entreprise(s) enrichie(s) depuis PJ", "INFO")
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
