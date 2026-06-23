from pprint import pprint

from surface_year import get_surfaces_and_year


TEST_POINTS = [

    # Stades
    {
        "name": "Stade de France",
        "lat": 48.924459,
        "lon": 2.360164
    },
    {
        "name": "Parc des Princes",
        "lat": 48.841389,
        "lon": 2.253056
    },
    {
        "name": "Orange Vélodrome",
        "lat": 43.269722,
        "lon": 5.395833
    },

    # Châteaux / monuments
    {
        "name": "Château de Versailles",
        "lat": 48.804865,
        "lon": 2.120355
    },
    {
        "name": "Mont Saint-Michel",
        "lat": 48.636111,
        "lon": -1.511458
    },

    # Aéroports
    {
        "name": "Terminal 2E CDG",
        "lat": 49.0032,
        "lon": 2.5708
    },
    {
        "name": "Aéroport Orly",
        "lat": 48.7262,
        "lon": 2.3652
    },

    # Centres commerciaux
    {
        "name": "Westfield Les 4 Temps",
        "lat": 48.8919,
        "lon": 2.2381
    },
    {
        "name": "La Part-Dieu",
        "lat": 45.7602,
        "lon": 4.8599
    },

    # Musées
    {
        "name": "Musée du Louvre",
        "lat": 48.860611,
        "lon": 2.337644
    },

    # Sites industriels
    {
        "name": "Usine Airbus Toulouse",
        "lat": 43.6365,
        "lon": 1.3670
    },

    # Grandes gares
    {
        "name": "Gare de Lyon",
        "lat": 48.8443,
        "lon": 2.3730
    },
    {
        "name": "Gare Saint-Charles Marseille",
        "lat": 43.3030,
        "lon": 5.3811
    },

    # Hôpitaux
    {
        "name": "CHU Pitié-Salpêtrière",
        "lat": 48.8372,
        "lon": 2.3639
    },

    # Universités
    {
        "name": "Université Paris-Saclay",
        "lat": 48.7096,
        "lon": 2.1700
    },

    # Grandes surfaces logistiques
    {
        "name": "Amazon Boves",
        "lat": 49.8465,
        "lon": 2.3920
    }
]


for point in TEST_POINTS:

    name = point["name"]
    lat  = point["lat"]
    lon  = point["lon"]

    print()
    print("=" * 60)
    print(name)
    print("=" * 60)

    try:

        result = get_surfaces_and_year(
            lat,
            lon,
            radius=150
        )

        pprint(result)

    except Exception as e:

        print("Erreur :", e)
