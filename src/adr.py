"""Module de traitement des adresses"""

import math
import time
import requests
from tools import Coords, Address, BAN_API_URL


def adr_to_coord(adr: Address) -> Coords:
    """Converti adresse au format str en coordonnées

    Args:
        adr (str): adresse

    Returns:
        tuple[float, float]: coordonnées de l'adresse au format (longitude, latitude)
    """
    adr_str = f"{adr['numero']} {adr['voie']}, {adr['code_postal']} {adr['ville']}"
    response = requests.get(f"{BAN_API_URL}search/", params={"q": adr_str}, timeout=10)
    coords = response.json()['features'][0]['geometry']['coordinates']
    coords:  Coords = {"longitude": coords[0],
                      "latitude": coords[1]}
    return coords


def coord_to_adr(coord: Coords) -> Address:
    """Converti coordonnées au format (longitude, latitude) en adresse

    Args:
        coord (Coord): coordonnées de l'adresse au format (longitude, latitude)

    Returns:
        Address: adresse
    """
    response = requests.get(f"{BAN_API_URL}reverse/", params={"lon": coord['longitude'], "lat": coord['latitude']}, timeout=10) # pylint: disable=line-too-long
    properties = response.json()['features'][0]['properties']
    adr: Address = {"numero": properties['housenumber'],
                    "voie": properties['street'],
                    "code_postal": properties['postcode'],
                    "ville": properties['city']}
    return adr


def km_to_deg(n_km: int, latitude_deg: float)->tuple[float, float]:
    """Converti une variation en km en une variation en latitude et longitude

    Args:
        n_km (int): variation en km
        latitude_deg (float): latitude de l'origine

    Returns:
        tuple[float, float]: delta_latitude, delta_longitude
    """
    delta_latitude = n_km / 111.32
    delta_longitude = n_km / (111.32 * math.cos(math.radians(latitude_deg)))
    return delta_latitude , delta_longitude

def get_adrs(org: Coords, long: int) -> list:
    """Reccupère liste d'adresses à partir de l'origine et un rayon 

    Args:
        org (Coord): coordonnées de l'origine au format (longitude, latitude)
        long (int): longueur du carré recherché (en km)

    Returns:
        list: liste des adresses
    """
    adresses = []
    delta_max_lat, delta_max_long = km_to_deg(long, org['latitude'])
    lat_min = round(org['latitude'] - delta_max_lat / 2, 6)
    lat_max = round(org['latitude'] + delta_max_lat / 2, 6)
    lon_min = round(org['longitude'] - delta_max_long / 2, 6)
    lon_max = round(org['longitude'] + delta_max_long / 2, 6)
    pas = 0.0001

    # Calcul du nombre total d'itérations
    n_lat = int(round((lat_max - lat_min) / pas)) + 1
    n_lon = int(round((lon_max - lon_min) / pas)) + 1
    total = n_lat * n_lon
    print(f"Total de {total} points à parcourir dans le carré")
    compteur = 0
    next_progress = 0.1

    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            coord = {"longitude": round(lon, 6), "latitude": round(lat, 6)}
            try:
                adr = coord_to_adr(coord)
                if adr not in adresses:
                    adresses.append(adr)
            except Exception:
                pass  # Ignore les erreurs (ex: pas d'adresse à ce point)
            compteur += 1
            # Affichage de la progression tous les 10%
            if compteur / total >= next_progress:
                print(f"{int(next_progress*100)}% du carré parcouru")
                next_progress += 0.1
            lon += pas
            time.sleep(1/50)  # Limite à 45 requêtes/s
        lat += pas
    return adresses
