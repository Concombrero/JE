
import sys
import os

_here = os.path.dirname(__file__)          # .../src_2/oms_surface
_root = os.path.join(_here, "..")          # .../src_2

sys.path.insert(0, _here)
sys.path.insert(0, _root)

from overpass_client import overpass

from geometry_builder import (
    build_indexes,
    way_to_polygon,
    relation_to_geometry
)

from surface_finder import (
    best_candidate
)


def extract_year(tags):

    for key in (
        "start_date",
        "building:year",
        "year_built"
    ):

        value = tags.get(key)

        if value is None:
            continue

        value = str(value)

        # 1997
        if len(value) >= 4 and value[:4].isdigit():

            year = int(value[:4])

            if 1800 <= year <= 2100:
                return year

    return None


def collect_objects(data):

    nodes, ways, relations = build_indexes(data)

    objects = []

    #
    # Ways
    #
    for way in ways.values():

        try:

            geom = way_to_polygon(
                way,
                nodes
            )

            if geom is None:
                continue

            objects.append(
                (
                    geom,
                    way.get(
                        "tags",
                        {}
                    )
                )
            )

        except Exception:
            pass

    #
    # Relations
    #
    for rel in relations.values():

        try:

            geom = relation_to_geometry(
                rel,
                ways,
                nodes
            )

            if geom is None:
                continue

            objects.append(
                (
                    geom,
                    rel.get(
                        "tags",
                        {}
                    )
                )
            )

        except Exception:
            pass

    return objects


def get_surfaces_and_year(
        lat,
        lon,
        radius=150
):

    #
    # BUILDINGS
    #
    q_build = f"""
[out:json][timeout:60];
(
way(around:{radius},{lat},{lon})["building"];
relation(around:{radius},{lat},{lon})["building"];
);
(._;>;);
out body;
"""

    data = overpass(q_build)

    buildings = collect_objects(
        data
    )

    roof = best_candidate(
        lat,
        lon,
        buildings,
        min_area=10
    )

    roof_area = None
    building_year = None

    if roof:

        _, area, tags = roof

        roof_area = round(
            area,
            1
        )

        building_year = extract_year(
            tags
        )

    #
    # PARKINGS
    #
    q_park = f"""
[out:json][timeout:60];
(
way(around:{radius},{lat},{lon})["amenity"="parking"];
relation(around:{radius},{lat},{lon})["amenity"="parking"];
way(around:{radius},{lat},{lon})["landuse"="parking"];
relation(around:{radius},{lat},{lon})["landuse"="parking"];
);
(._;>;);
out body;
"""

    data = overpass(
        q_park
    )

    parkings = collect_objects(
        data
    )

    parking = best_candidate(
        lat,
        lon,
        parkings,
        min_area=5
    )

    parking_area = None

    if parking:

        _, area, _ = parking

        parking_area = round(
            area,
            1
        )

    return {
        "roof_area_m2": roof_area,
        "parking_area_m2": parking_area,
        "building_year": building_year
    }

