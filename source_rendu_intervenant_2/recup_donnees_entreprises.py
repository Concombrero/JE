#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recup_donnees_entreprises.py
Test minimal: prend en entrée le nom et l'adresse de l'entreprise et renvoie un JSON:
- géocodage (BAN)
- entreprises candidates (API Recherche d'entreprises) + dirigeants (noms/prénoms si dispo)
- contacts et catégories OSM à proximité
- surfaces toiture/parking et année plausible de construction (si trouvable dans OSM)

Aucune clé API nécessaire.
"""

import sys
import json
import time
import math
from typing import Any, Dict, List, Optional, Tuple

import requests

# shapely est optionnelle (non nécessaire, on calcule les aires avec pyproj.Geod)
try:
    from shapely.geometry import Polygon  # noqa: F401  (juste pour info)
    HAVE_SHAPELY = True
except Exception:
    HAVE_SHAPELY = False

from pyproj import Geod
GEOD = Geod(ellps="WGS84")

# Constantes
UA = {"User-Agent": "prospection-open-data/1.2 (+contact@example.com)"}
BAN_URL = "https://api-adresse.data.gouv.fr/search/"
RE_URL = "https://recherche-entreprises.api.gouv.fr/search"
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"  # miroir rapide (changez au besoin)

# -------------- Utils --------------
def _retry_get(
    url: str,
    *,
    params: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int = 20,
    tries: int = 3,
    backoff: float = 1.5,
) -> requests.Response:
    last_exc: Optional[Exception] = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            return r
        except requests.RequestException as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(backoff ** (i + 1))
    if last_exc:
        raise last_exc  # type: ignore[misc]
    # fallback improbable
    raise RuntimeError("Échec inconnu dans _retry_get")

def _retry_post(
    url: str,
    *,
    data: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int = 30,
    tries: int = 3,
    backoff: float = 1.7,
) -> requests.Response:
    last_exc: Optional[Exception] = None
    for i in range(tries):
        try:
            r = requests.post(url, data=data, headers=headers, timeout=timeout)
            return r
        except requests.RequestException as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(backoff ** (i + 1))
    if last_exc:
        raise last_exc  # type: ignore[misc]
    raise RuntimeError("Échec inconnu dans _retry_post")

# -------------- BAN: géocodage --------------
def geocode_ban(address: str) -> Optional[Dict[str, Any]]:
    params = {"q": address, "limit": 1}
    r = _retry_get(BAN_URL, params=params, headers=UA, timeout=20, tries=3)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or not data.get("features"):
        return None
    f = data["features"][0]
    lon, lat = f["geometry"]["coordinates"]
    props = f.get("properties", {}) if isinstance(f.get("properties", {}), dict) else {}
    return {
        "lat": float(lat),
        "lon": float(lon),
        "label": props.get("label"),
        "housenumber": props.get("housenumber"),
        "street": props.get("street"),
        "postcode": props.get("postcode"),
        "city": props.get("city"),
        "citycode": props.get("citycode"),  # code INSEE (5 chiffres)
        "context": props.get("context"),
        "score": props.get("score"),
    }

def _call_re(params_local: Dict[str, Any]) -> Dict[str, Any]:
    """
    Appel robuste de l'API Recherche d'entreprises (/search).

    Rappels:
      - Champs 'include' autorisés: complements, dirigeants, finances, score, siege, matching_etablissements
      - Si 'include' est utilisé, l'API exige 'minimal=true' dans la requête.
    """
    # Base sûre et neutre
    base = {
        "page": 1,
        "per_page": params_local.pop("per_page", params_local.pop("limit", 10)),
    }

    # Normalisation de 'minimal' et 'include'
    include_val = params_local.get("include")
    minimal_val = params_local.get("minimal", None)

    # Convertir minimal -> "true"/"false" attendu par l'API si fourni
    if isinstance(minimal_val, bool):
        base["minimal"] = "true" if minimal_val else "false"
    elif isinstance(minimal_val, str):
        m = minimal_val.strip().lower()
        if m in ("true", "1", "yes", "oui"):
            base["minimal"] = "true"
        elif m in ("false", "0", "no", "non"):
            base["minimal"] = "false"

    # Si un include est demandé mais minimal n'est pas "true", l'activer automatiquement
    if include_val and base.get("minimal") != "true":
        base["minimal"] = "true"

    # Fusion finale des paramètres
    p = {**base, **params_local}

    # Requête avec retries
    r = _retry_get(RE_URL, params=p, headers=UA, timeout=20, tries=3)

    # Gestion des erreurs HTTP fréquentes de l'API
    if r.status_code == 400:
        # Renvoyer le message d'erreur de l'API pour debug
        try:
            msg = r.json()
        except Exception:
            msg = r.text[:500]
        raise requests.HTTPError(f"400: {msg}", response=r)
    if r.status_code in (429, 503):
        # Laisser la couche appelante gérer le retry backoff si besoin
        raise requests.HTTPError(str(r.status_code), response=r)

    # Autres erreurs éventuelles
    r.raise_for_status()

    # Parsing JSON
    try:
        data = r.json()
    except ValueError:
        raise ValueError(f"API RE: réponse non-JSON: {r.text[:300]}")

    if not isinstance(data, dict):
        raise ValueError(
            f"API RE: réponse inattendue de type {type(data).__name__}: {str(data)[:200]}"
        )

    return data

def _normalize_dirigeant_person(d: Dict[str, Any]) -> Optional[Dict[str, Optional[str]]]:
    """
    Normalise un enregistrement dirigeant (personne physique) en {first_name, last_name, role}.
    Renvoie None si l'entrée ne semble pas être une personne physique.
    """
    if not isinstance(d, dict):
        return None
    # Beaucoup d'API exposent un champ 'type' ou 'type_dirigeant'
    # On essaie de filtrer les personnes morales
    typ = (d.get("type") or d.get("type_dirigeant") or "").lower()
    if "morale" in typ:
        return None  # personne morale -> ignorer pour "nom/prénom"
    # Noms/prénoms: champs observés possibles
    last = d.get("nom") or d.get("nom_naissance") or d.get("nom_usage")
    first = d.get("prenom") or d.get("prenoms") or d.get("prénoms")
    # Certains renvoient 'prenoms' concaténés -> on garde le premier
    if isinstance(first, str) and " " in first:
        first = first.split(" ", 1)[0]
    role = d.get("fonction") or d.get("role") or d.get("qualite") or d.get("qualité")
    if not last and not first:
        return None
    return {
        "first_name": first if isinstance(first, str) else None,
        "last_name": last if isinstance(last, str) else None,
        "role": role if isinstance(role, str) else None,
    }

def search_company_re(
    name: str,
    commune_insee: Optional[str] = None,
    code_postal: Optional[str] = None,
    limit: int = 5,
    include_dirigeants: bool = True,
) -> List[Dict[str, Any]]:
    # On interroge par nom + filtres éventuels
    params: Dict[str, Any] = {
        "q": name,
        "per_page": limit,
    }
    # L’API accepte code_postal; pour la commune, on peut passer code_commune (INSEE)
    if code_postal:
        params["code_postal"] = code_postal
    if commune_insee:
        params["code_commune"] = commune_insee

    # Ajouter dirigeants si demandé
    if include_dirigeants:
        params["include"] = "dirigeants"
        params["minimal"] = "true"  # requis quand include=* est présent

    data = _call_re(params)

    if not isinstance(data, dict):
        raise ValueError(f"API RE: réponse inattendue de type {type(data).__name__}")

    results = data.get("results") or []
    out: List[Dict[str, Any]] = []
    for it in results:
        if not isinstance(it, dict):
            continue
        siege = it.get("siege") or {}
        adresse = siege.get("adresse") or {}
        naf = it.get("activite_principale") or {}

        # Dirigeants (si présents)
        dir_list_raw = it.get("dirigeants") or []
        dirigeants: List[Dict[str, Optional[str]]] = []
        if isinstance(dir_list_raw, list):
            for d in dir_list_raw:
                nd = _normalize_dirigeant_person(d)
                if nd:
                    dirigeants.append(nd)

        out.append(
            {
                "siren": it.get("siren"),
                "nom_complet": it.get("nom_complet") or it.get("nom_raison_sociale") or it.get("nom"),
                "etat_administratif": (it.get("etat_administratif") or {}).get("value") if isinstance(it.get("etat_administratif"), dict) else it.get("etat_administratif"),
                "date_creation": it.get("date_creation"),
                "categorie_juridique": it.get("categorie_juridique"),
                "tranche_effectif_salarie": it.get("tranche_effectif_salarie"),
                "naf": naf.get("code") if isinstance(naf, dict) else naf,
                "naf_libelle": naf.get("libelle") if isinstance(naf, dict) else None,
                "siret_siege": siege.get("siret"),
                "adresse_siege": {
                    "label": adresse.get("label") or " ".join(
                        str(adresse.get(k, "")) for k in ("numero_voie", "type_voie", "nom_voie", "code_postal", "commune")
                    ).strip()
                } if isinstance(adresse, dict) else None,
                "dirigeants": dirigeants,  # NEW: liste de personnes physiques [ {first_name, last_name, role}, ... ]
            }
        )
    return out

# -------------- Overpass helpers --------------
def _overpass(query: str) -> Dict[str, Any]:
    # Respecter Overpass: une légère pause peut être utile si vous enchaînez
    data = {"data": query}
    r = _retry_post(OVERPASS_URL, data=data, headers=UA, timeout=60, tries=3)
    # 429/504 sont fréquents sur Overpass: laissez _retry_post gérer les retries,
    # puis si ça persiste on lève ici
    r.raise_for_status()
    js = r.json()
    if not isinstance(js, dict):
        raise ValueError("Overpass: réponse JSON inattendue")
    return js

def _polygon_area_m2(coords: List[Tuple[float, float]]) -> float:
    """
    coords: liste [(lon, lat), ...] (anneau fermé ou non)
    Retourne aire en m² via pyproj.Geod (signée, on prend abs()).
    """
    if len(coords) < 3:
        return 0.0
    # S'assurer que l'anneau est fermé
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    lons, lats = zip(*coords)
    area, _perim = GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)

def _way_area_from_geom(elt: Dict[str, Any]) -> float:
    """
    Calcule une aire approximative pour un way avec 'geometry' (liste de points) ou center + tags area=yes.
    Ne traite pas proprement les multipolygones de relation (on se limite aux ways pour garder la simplicité).
    """
    if elt.get("type") != "way":
        return 0.0
    geom = elt.get("geometry")
    if isinstance(geom, list) and len(geom) >= 3:
        coords = [(pt["lon"], pt["lat"]) for pt in geom if isinstance(pt, dict) and "lon" in pt and "lat" in pt]
        if len(coords) >= 3:
            return _polygon_area_m2(coords)
    # fallback: aucune géométrie utilisable
    return 0.0

# -------------- Contacts OSM --------------
def get_osm_contacts(lat: float, lon: float, company_name: str, radius: int = 200) -> Dict[str, Any]:
    """
    Récupère des POI OSM à proximité, isole celui correspondant au nom d'entreprise fourni,
    et retourne un résumé des contacts + catégories.

    Retour:
      {
        "phones": [ "+33XXXXXXXXX", ... ],
        "emails": [ "contact@exemple.fr", ... ],
        "websites": [ "https://exemple.fr", ... ],
        "osm_categories": [ "shop=bicycle", "amenity=..." ],
        "match_count": 0|1
      }
    """
    import re

    # --- Helpers locaux (scopés à la fonction pour ne pas modifier le reste du fichier) ---

    def _norm(s: str) -> str:
        if not s:
            return ""
        try:
            from unidecode import unidecode
            s = unidecode(s)
        except Exception:
            pass
        s = s.lower().replace("’", "'")
        s = re.sub(r"[^a-z0-9@:/._-]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    _STOPWORDS = {
        "societe", "association", "sas", "sarl", "sa", "eurl",
        "universite", "fondation", "service", "presidence",
        "laboratoire", "departement", "centre", "batiment",
        "building", "uga"
    }

    def _tokens(s: str):
        toks = [t for t in re.split(r"[^\w]+", _norm(s)) if t]
        return [t for t in toks if t not in _STOPWORDS and len(t) > 1]

    def _name_equivalent(query_name: str, candidate_name: str) -> bool:
        nq, nc = _norm(query_name), _norm(candidate_name)
        if not nq or not nc:
            return False
        if nq == nc:
            return True
        tq, tc = set(_tokens(query_name)), set(_tokens(candidate_name))
        if tq and tq == tc:
            return True
        if tq and tq.issubset(tc):
            return True
        return False

    def _normalize_fr_phone(raw: str) -> Optional[str]:
        if not raw:
            return None
        s = re.sub(r"[^\d+]", "", raw)
        if s.startswith("+"):
            return s if re.fullmatch(r"\+\d{6,15}", s) else None
        s_digits = re.sub(r"\D", "", raw)
        if re.fullmatch(r"0\d{9}", s_digits):
            return "+33" + s_digits[1:]
        if re.fullmatch(r"\d{9}", s_digits):
            return "+33" + s_digits
        return None

    def _ensure_http(url: str) -> Optional[str]:
        if not url:
            return None
        u = url.strip()
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        return u if re.match(r"^https?://[^\s]+$", u, re.I) else None

    def _is_email(s: str) -> bool:
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s or "", re.I))

    def _normalize_contacts_from_tags(tags: Dict[str, Any]) -> Dict[str, List[str]]:
        out_phones, out_emails, out_websites = [], [], []
        # Regrouper champs OSM usuels
        candidates = {
            "phone": [tags.get("phone"), tags.get("contact:phone")],
            "email": [tags.get("email"), tags.get("contact:email")],
            "website": [tags.get("website"), tags.get("contact:website")],
        }
        # Téléphones
        for ph in candidates["phone"]:
            if not ph:
                continue
            parts = re.split(r"[,/;]|(?:\s{2,})", str(ph))
            for p in parts:
                norm = _normalize_fr_phone(p)
                if norm and norm not in out_phones:
                    out_phones.append(norm)
        # Emails
        for em in candidates["email"]:
            if not em:
                continue
            parts = re.split(r"[,/;\s]+", str(em))
            for p in parts:
                p = p.strip().lower()
                if _is_email(p) and p not in out_emails:
                    out_emails.append(p)
        # Websites
        for w in candidates["website"]:
            if not w:
                continue
            parts = re.split(r"[,;\s]+", str(w))
            for p in parts:
                url = _ensure_http(p)
                if url and url not in out_websites:
                    out_websites.append(url)
        return {"phones": out_phones, "emails": out_emails, "websites": out_websites}

    def _collect_osm_categories(tags: Dict[str, Any]) -> List[str]:
        res = []
        for k in ("amenity", "shop", "office", "craft", "tourism", "leisure", "building"):
            if tags.get(k):
                res.append(f"{k}={tags.get(k)}")
        return res

    # --- Requête Overpass: on récupère tags + center pour tri par proximité si besoin ---
    plat, plon, r = float(lat), float(lon), int(radius)
    q = f"""
    [out:json][timeout:25];
    (
      node(around:{r},{plat},{plon})[~"^(name|brand)$"~".*"];
      way(around:{r},{plat},{plon})[~"^(name|brand)$"~".*"];
      relation(around:{r},{plat},{plon})[~"^(name|brand)$"~".*"];
    );
    out tags center 50;
    """
    data = _overpass(q)

    # --- Filtrage: ne conserver que l'objet dont le nom correspond à l'entreprise ---
    candidates = []
    for elt in data.get("elements", []):
        tags = elt.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        name = tags.get("name") or tags.get("brand")
        if not name:
            continue
        if not _name_equivalent(company_name, name):
            continue
        # On garde le candidat avec ses infos utiles
        candidates.append(
            {
                "type": elt.get("type"),
                "id": elt.get("id"),
                "name": name,
                "tags": tags,
                "center": elt.get("center") or {},
            }
        )

    if not candidates:
        return {
            "phones": [],
            "emails": [],
            "websites": [],
            "osm_categories": [],
            "match_count": 0,
        }

    # S'il y a plusieurs matches, prioriser celui qui a des contacts
    def _has_contacts(cand: Dict[str, Any]) -> bool:
        nc = _normalize_contacts_from_tags(cand.get("tags") or {})
        return bool(nc["phones"] or nc["emails"] or nc["websites"])

    with_contacts = [c for c in candidates if _has_contacts(c)]

    item = with_contacts[0] if with_contacts else candidates[0]

    tags = item.get("tags") or {}
    contacts = _normalize_contacts_from_tags(tags)
    osm_categories = _collect_osm_categories(tags)

    return {
        "phones": contacts.get("phones", []),
        "emails": contacts.get("emails", []),
        "websites": contacts.get("websites", []),
        "osm_categories": osm_categories,
        "match_count": 1,
    }

# -------------- Surfaces toiture/parking + année plausible --------------
def get_surfaces_and_year(lat: float, lon: float, radius: int = 250) -> Dict[str, Optional[float]]:
    plat, plon, r = float(lat), float(lon), int(radius)

    # 1) Bâtiments (toitures)
    q_build = f"""
    [out:json][timeout:30];
    way(around:{r},{plat},{plon})["building"];
    out tags geom;
    """
    data_b = _overpass(q_build)
    total_roof = 0.0
    years: List[int] = []
    for elt in data_b.get("elements", []):
        tags = elt.get("tags", {}) if isinstance(elt.get("tags"), dict) else {}
        try:
            total_roof += _way_area_from_geom(elt)
        except Exception:
            pass
        # Recherche d'une année plausible
        for key in ("start_date", "building:year_built", "construction:year", "year_built"):
            v = tags.get(key)
            if not v:
                continue
            # extraire AAAA au début
            y = None
            # formats courants: "1998", "1998-05", "1998-05-12", "ca. 1998"
            for tok in (v, v.strip("ca. ").strip("~")):
                if isinstance(tok, str) and len(tok) >= 4 and tok[:4].isdigit():
                    y = int(tok[:4])
                    break
            if y and 1700 <= y <= 2100:
                years.append(y)
                break

    roof_area = round(total_roof, 1) if total_roof > 0 else None
    building_year: Optional[int] = None
    if years:
        years.sort()
        # médiane simple
        building_year = years[len(years) // 2]

    # 2) Parkings (surfaces approximatives)
    parking_area = None
    try:
        q_park = f"""
        [out:json][timeout:30];
        (
          way(around:{r},{plat},{plon})["amenity"="parking"];
          relation(around:{r},{plat},{plon})["amenity"="parking"];
          way(around:{r},{plat},{plon})["highway"="service"]["service"="parking_aisle"];
        );
        out tags center geom;
        """
        data_p = _overpass(q_park)
        total_p = 0.0
        for elt in data_p.get("elements", []):
            # on ne calcule l'aire que pour les ways; les relations multipolygones ne sont pas traitées ici
            try:
                total_p += _way_area_from_geom(elt)
            except Exception:
                pass
        parking_area = round(total_p, 1) if total_p > 0 else None
    except Exception:
        parking_area = None

    return {
        "roof_area_m2": roof_area,
        "parking_area_m2": parking_area,
        "building_year": building_year,
    }

# -------------- Déduction d'un "propriétaire" probable depuis les dirigeants --------------
def _pick_owner_from_dirigeants(dirigeants: List[Dict[str, Optional[str]]]) -> Optional[Dict[str, Optional[str]]]:
    """
    Heuristique simple:
      - Si une seule personne physique: la retourner.
      - Sinon prioriser certains rôles fréquents pour le "propriétaire" ressenti:
        Entrepreneur individuel / Exploitant / Commerçant / Gérant / Président
      - À défaut, retourner la première personne.
    """
    if not dirigeants:
        return None
    if len(dirigeants) == 1:
        return dirigeants[0]

    def score_role(role: Optional[str]) -> int:
        if not role:
            return 0
        r = role.lower()
        # ordre de priorité décroissant
        if "entrepreneur individuel" in r or "exploitant" in r or "commerçant" in r:
            return 100
        if "gérant" in r or "gerant" in r:
            return 90
        if "président" in r or "president" in r:
            return 80
        if "dirigeant" in r or "manager" in r:
            return 50
        return 10

    best = max(dirigeants, key=lambda d: score_role(d.get("role")))
    return best

# -------------- Test unique (main) --------------
def run_test(company_name: str, address: str) -> Dict[str, Any]:
    # 1) Géocodage
    geo = geocode_ban(address)
    if not geo:
        raise SystemExit("Géocodage impossible: adresse introuvable dans la BAN.")
    lat, lon = geo["lat"], geo["lon"]

    # 2) Entreprises candidates (avec dirigeants)
    companies = search_company_re(
        company_name,
        commune_insee=geo.get("citycode"),
        code_postal=geo.get("postcode"),
        limit=5,
        include_dirigeants=True,
    )

    # 3) Déduire un "owner" probable à partir de la meilleure entreprise (si trouvée)
    owner: Optional[Dict[str, Optional[str]]] = None
    if companies:
        # heuristique simpliste: prendre la première ligne retournée par l'API,
        # puis choisir un "owner" dans ses dirigeants personnes physiques
        owner = _pick_owner_from_dirigeants(companies[0].get("dirigeants") or [])

    # 4) Contacts OSM
    contacts = get_osm_contacts(lat, lon, company_name, radius=200)

    # 5) Surfaces + année
    surf = get_surfaces_and_year(lat, lon, radius=250)

    return {
        "query": {"company_name": company_name, "address": address},
        "geocoding": geo,
        "companies": companies,  # contient désormais "dirigeants" dans chaque item
        "contacts_osm": contacts,
        "roof_area_m2": surf.get("roof_area_m2"),
        "parking_area_m2": surf.get("parking_area_m2"),
        "building_year": surf.get("building_year"),
        "owner": owner,  # NEW: {"first_name","last_name","role"} ou None
        "owner_source": "recherche-entreprises" if owner else None,
        "energy_consumption": None,  # pas d’API publique gratuite
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python recup_donnees_entreprises.py "Nom Entreprise" "Adresse complète"', file=sys.stderr)
        sys.exit(1)
    name = sys.argv[1].strip()
    addr = sys.argv[2].strip()
    try:
        data = run_test(name, addr)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except requests.HTTPError as e:
        # Message d’erreur plus explicite, utile en cas de 429/503
        body = ""
        if getattr(e, "response", None) is not None:
            try:
                body = e.response.text[:200]
            except Exception:
                body = ""
        print(f"Erreur HTTP (appel API): {e} – réponse: {body}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Erreur: {e}", file=sys.stderr)
        sys.exit(3)
