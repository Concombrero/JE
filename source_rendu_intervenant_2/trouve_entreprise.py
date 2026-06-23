# trouve_entreprise.py
# -*- coding: utf-8 -*-

import requests
from geopy.distance import geodesic

from overpass_client import overpass


BAN_URL = "https://api-adresse.data.gouv.fr/search/"


def geocode_address(address: str):
    """
    Géocodage via BAN.
    Retourne (lat, lon)
    """

    params = {
        "q": address,
        "limit": 1
    }

    r = requests.get(
        BAN_URL,
        params=params,
        timeout=15
    )

    r.raise_for_status()

    data = r.json()

    features = data.get("features", [])

    if not features:
        raise Exception(
            f"Adresse introuvable : {address}"
        )

    lon, lat = features[0]["geometry"]["coordinates"]

    return lat, lon


def get_address_from_tags(tags):

    parts = []

    if tags.get("addr:housenumber"):
        parts.append(tags["addr:housenumber"])

    if tags.get("addr:street"):
        parts.append(tags["addr:street"])

    if tags.get("addr:postcode"):
        parts.append(tags["addr:postcode"])

    if tags.get("addr:city"):
        parts.append(tags["addr:city"])

    if tags.get("addr:country"):
        parts.append(tags["addr:country"])

    if parts:
        return ", ".join(parts)

    return "Adresse inconnue"


def find_businesses(
        lat: float,
        lon: float,
        radius: int = 500,
        verbose=False
):

    query = f"""
[out:json][timeout:60];
(
 node(around:R,lat,lon)["office"];
 node(around:R,lat,lon)["shop"];
 node(around:R,lat,lon)["craft"];
 node(around:R,lat,lon)["amenity"];
 way(around:R,lat,lon)["office"];
 way(around:R,lat,lon)["shop"];
 way(around:R,lat,lon)["craft"];
 way(around:R,lat,lon)["amenity"];
 relation(around:R,lat,lon)["office"];
 relation(around:R,lat,lon)["shop"];
 relation(around:R,lat,lon)["craft"];
 relation(around:R,lat,lon)["amenity"];
);
out center tags;
out body;
"""

    data = overpass(
        query,
        verbose=verbose
    )

    origin = (lat, lon)

    businesses = []

    for node in data.get("elements", []):

        if node["type"] != "node":
            continue

        tags = node.get("tags", {})

        name = tags.get(
            "name",
            "Inconnu"
        )

        category = (
            tags.get("office")
            or tags.get("shop")
            or "n/a"
        )

        dist_m = geodesic(
            origin,
            (
                node["lat"],
                node["lon"]
            )
        ).meters

        address = get_address_from_tags(
            tags
        )

        businesses.append(
            (
                name,
                category,
                round(dist_m),
                address
            )
        )

    businesses.sort(
        key=lambda x: x[2]
    )

    return businesses


if __name__ == "__main__":

    addr = input(
        "Adresse: "
    ).strip()

    rayon_m = int(
        input(
            "Rayon en mètres (ex 500): "
        ).strip() or "500"
    )

    lat, lon = geocode_address(
        addr
    )

    print(
        f"\nCentre trouvé : "
        f"{lat:.6f}, {lon:.6f}"
    )

    resultats = find_businesses(
        lat,
        lon,
        rayon_m,
        verbose=True
    )

    print(
        f"\n{len(resultats)} résultat(s)\n"
    )

    for name, category, dist, address in resultats[:20]:

        print(
            f"- {name}"
            f" ({category})"
            f" à {dist} m"
            f" - {address}"
        )