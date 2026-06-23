from shapely.geometry import Polygon
from shapely.geometry import MultiPolygon
from shapely.geometry import LineString

from shapely.ops import polygonize
from shapely.ops import unary_union
from shapely.validation import make_valid


# construction des index

def build_indexes(data):

    nodes = {}
    ways = {}
    relations = {}

    for e in data["elements"]:

        typ = e["type"]

        if typ == "node":
            nodes[e["id"]] = e

        elif typ == "way":
            ways[e["id"]] = e

        elif typ == "relation":
            relations[e["id"]] = e

    return nodes, ways, relations


def way_to_polygon(
        way,
        nodes
):

    coords = []

    for nid in way["nodes"]:

        if nid not in nodes:
            continue

        n = nodes[nid]

        coords.append(
            (
                n["lon"],
                n["lat"]
            )
        )

    if len(coords) < 4:
        return None

    if coords[0] != coords[-1]:
        coords.append(coords[0])

    poly = Polygon(coords)

    if not poly.is_valid:
        poly = make_valid(poly)

    if poly.is_empty:
        return None

    return poly


def relation_to_geometry(
        rel,
        ways,
        nodes
):

    outer_lines = []
    inner_lines = []

    for member in rel["members"]:

        if member["type"] != "way":
            continue

        ref = member["ref"]

        if ref not in ways:
            continue

        way = ways[ref]

        coords = []

        for nid in way["nodes"]:

            if nid in nodes:

                node = nodes[nid]

                coords.append(
                    (
                        node["lon"],
                        node["lat"]
                    )
                )

        if len(coords) < 2:
            continue

        line = LineString(coords)

        if member["role"] == "inner":
            inner_lines.append(line)

        else:
            outer_lines.append(line)

    if len(outer_lines) == 0:
        return None

    outer_geom = unary_union(outer_lines)

    polygons = list(
        polygonize(outer_geom)
    )

    if len(polygons) == 0:
        return None

    geom = unary_union(polygons)

    if inner_lines:

        holes = unary_union(
            polygonize(
                unary_union(inner_lines)
            )
        )

        geom = geom.difference(
            holes
        )

    if not geom.is_valid:
        geom = make_valid(geom)

    return geom