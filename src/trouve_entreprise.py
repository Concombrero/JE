# trouve_entreprise.py
# -*- coding: utf-8 -*-
"""
Programme 1 – Géocodage + recherche d'entreprises (OSM/Overpass)
Exporte:
  - geocode_address(address) -> (lat, lon)
  - find_businesses(lat, lon, radius=500) -> list[ (name, category, distance_m, address) ]

Remarques:
- radius en mètres.
- On interroge les nodes OSM "office" et "shop" (les plus fréquents pour entreprises/commerces).
- L'adresse est reconstruite à partir des tags OSM si disponible.
"""

import overpy
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

# Nominatim: utiliser un user_agent explicite et respecter les règles d'usage
# User-agent personnalisé avec informations de contact réelles recommandées
_GEOCODER = Nominatim(
    user_agent="ProspectionApp/2.0 (Python geopy; business prospection tool)",
    timeout=10
)


def geocode_address(address: str):
    """
    Géocode une adresse avec Nominatim (geopy).
    Retourne (lat, lon) en float ou lève Exception si introuvable.
    
    Note: Respecte un délai minimal entre les requêtes pour éviter le blocage.
    """
    # Respecter la politique d'usage de Nominatim (max 1 requête/sec)
    time.sleep(1)
    
    try:
        location = _GEOCODER.geocode(address)
        if not location:
            raise Exception("Adresse introuvable")
        return float(location.latitude), float(location.longitude)
    except Exception as e:
        # En cas d'erreur 403, suggérer d'utiliser une autre méthode
        if "403" in str(e):
            raise Exception(
                f"Erreur de géocodage (403 Forbidden). "
                f"Nominatim bloque la requête. Vous pouvez : "
                f"1) Attendre quelques minutes et réessayer, "
                f"2) Utiliser des coordonnées GPS directement si vous les connaissez."
            )
        raise


def get_address_from_tags(tags: dict) -> str:
    """
    Reconstruit une adresse lisible à partir des tags OSM s'ils existent.
    """
    address_parts = []
    if tags.get("addr:housenumber"):
        address_parts.append(tags["addr:housenumber"])
    if tags.get("addr:street"):
        address_parts.append(tags["addr:street"])
    if tags.get("addr:postcode"):
        address_parts.append(tags["addr:postcode"])
    if tags.get("addr:city"):
        address_parts.append(tags["addr:city"])
    if tags.get("addr:country"):
        address_parts.append(tags["addr:country"])
    return ", ".join(address_parts) if address_parts else "Adresse inconnue"


def find_businesses(lat: float, lon: float, radius: int = 500):
    """
    Cherche des entreprises/commerces autour d'un point (lat, lon) dans un rayon donné (m).
    Retourne une liste de tuples: (name, category, distance_m, address_str)
    """
    api = overpy.Overpass()

    # On cible des noeuds (nodes) avec tags "office" ou "shop".
    # (on pourrait élargir à ways/relations + 'out center', mais nodes suffit souvent et reste simple)
    query = f"""
    (
      node(around:{radius},{lat},{lon})["office"];
      node(around:{radius},{lat},{lon})["shop"];
    );
    out body;
    """

    result = api.query(query)

    businesses = []
    origin = (lat, lon)

    for node in result.nodes:
        name = node.tags.get("name", "Inconnu")
        category = node.tags.get("office") or node.tags.get("shop") or "n/a"
        # distance géodésique (m)
        dist_m = geodesic(origin, (node.lat, node.lon)).meters
        address = get_address_from_tags(node.tags)
        businesses.append((name, category, round(dist_m), address))

    # Tri facultatif par distance croissante
    businesses.sort(key=lambda x: x[2])
    return businesses


if __name__ == "__main__":
    # Petit test manuel (exécuter: python trouve_entreprise.py)
    addr = input("Adresse: ").strip()
    rayon_m = int(input("Rayon en mètres (ex 500): ").strip() or "500")
    clat, clon = geocode_address(addr)
    res = find_businesses(clat, clon, radius=rayon_m)
    print(f"{len(res)} résultat(s)")
    for name, category, dist, addr2 in res[:10]:
        print(f" - {name} ({category}) à {dist} m – {addr2}")
