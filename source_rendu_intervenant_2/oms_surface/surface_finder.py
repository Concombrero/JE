from pyproj import Transformer
from shapely.ops import transform
from shapely.geometry import Point

PROJECT = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:3857",
    always_xy=True
)


def area_m2(geom):

    geom_m = transform(
        PROJECT.transform,
        geom
    )

    return abs(
        geom_m.area
    )


def distance_m(
        point,
        geom
):

    p = transform(
        PROJECT.transform,
        point
    )

    g = transform(
        PROJECT.transform,
        geom
    )

    return p.distance(g)


def best_candidate(
        lat,
        lon,
        objects,
        min_area=1
):

    p = Point(
        lon,
        lat
    )

    candidates = []

    for geom, tags in objects:

        try:

            area = area_m2(geom)

            if area < min_area:
                continue

            if geom.contains(p):

                d = 0

            else:

                d = distance_m(
                    p,
                    geom
                )

            candidates.append(
                (
                    d,
                    area,
                    tags
                )
            )

        except:
            pass

    if len(candidates) == 0:
        return None

    candidates.sort()

    return candidates[0]