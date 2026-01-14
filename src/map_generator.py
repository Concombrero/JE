"""Module de génération de carte interactive Leaflet"""

import json
import os
from typing import List, Dict, Any, Optional

from tools import sanitize


def build_map_html(
    center_lat: float, 
    center_lon: float, 
    radius_m: int, 
    features: List[Dict[str, Any]],
    title: str = "Carte Prospection"
) -> str:
    """
    Construit une page HTML Leaflet autonome avec:
    - fond satellite Esri + OSM
    - cercle du rayon
    - clustering
    - popups détaillées
    """
    
    # Transformation en FeatureCollection GeoJSON
    gj_features = []
    for f in features:
        lat = f.get("lat") or f.get("latitude")
        lon = f.get("lon") or f.get("longitude")
        
        if lat is None or lon is None:
            continue
        
        props = {}
        for k, v in f.items():
            if k in ("lat", "lon", "latitude", "longitude"):
                continue
            if isinstance(v, (list, tuple)):
                props[k] = [sanitize(x) for x in v]
            elif isinstance(v, dict):
                props[k] = v
            else:
                props[k] = sanitize(v)
        
        gj_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": props
        })
    
    feature_collection = {"type": "FeatureCollection", "features": gj_features}
    gj_json = json.dumps(feature_collection, ensure_ascii=False)
    
    html_template = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">

<style>
  html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
  .popup-title {{ font-weight: 700; font-size: 14px; margin-bottom: 4px; color: #1d4ed8; }}
  .popup-section-title {{ font-weight: 600; margin-top: 8px; color: #374151; border-bottom: 1px solid #e5e7eb; padding-bottom: 2px; }}
  .kv {{ margin: 2px 0; font-size: 13px; }}
  .kv span.k {{ color: #666; }}
  .chips span {{ display:inline-block; background:#eef; border-radius:10px; padding:2px 6px; margin:2px; font-size:12px; }}
  .contact-link {{ color: #2563eb; text-decoration: none; }}
  .contact-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<script>
  const CENTER = [{center_lat:.7f}, {center_lon:.7f}];
  const RADIUS_M = {radius_m};
  const GEOJSON = {gj_json};

  // Fonds de carte
  const esriSat = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{ attribution: 'Esri & contributors', maxZoom: 20 }}
  );
  const osmPlan = L.tileLayer(
    'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{ attribution: '&copy; OpenStreetMap', maxZoom: 20 }}
  );

  const map = L.map('map', {{
    center: CENTER,
    zoom: 13,
    layers: [esriSat]
  }});

  const baseLayers = {{
    "Satellite (Esri)": esriSat,
    "Plan (OSM)": osmPlan
  }};
  L.control.layers(baseLayers, null, {{ position: 'topleft' }}).addTo(map);
  L.control.scale().addTo(map);

  // Cercle de recherche
  const circle = L.circle(CENTER, {{
    radius: RADIUS_M,
    color: '#3b82f6',
    fillColor: '#3b82f6',
    fillOpacity: 0.08,
    weight: 2
  }}).addTo(map);
  map.fitBounds(circle.getBounds(), {{ padding: [20, 20] }});

  // Centre (marqueur)
  L.circleMarker(CENTER, {{
    radius: 6, color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.9
  }}).bindTooltip('Centre de recherche').addTo(map);

  // Cluster
  const markers = L.markerClusterGroup();

  function esc(x) {{
    if (x === null || x === undefined) return '';
    return String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  }}

  function joinChips(arr) {{
    if (!arr || !arr.length) return '';
    return '<div class="chips">' + arr.map(x => '<span>' + esc(x) + '</span>').join('') + '</div>';
  }}

  function buildPopup(props) {{
    // Identité
    const name = esc(props.name || props.pj_title || props.entreprise_nom || 'Inconnu');
    const category = esc(props.category || props.entreprise_category || 'n/a');
    
    // Adresse
    let addr = esc(props.address || '');
    if (!addr && props.numero) {{
      addr = esc((props.numero || '') + ' ' + (props.voie || '') + ', ' + (props.code_postal || '') + ' ' + (props.ville || ''));
    }}
    
    // Contacts
    const phones = props.phones || props.entreprise_phones || [];
    const pjPhone = props.pj_phone || props.pj_telephone;
    const emails = props.emails || props.entreprise_emails || [];
    const websites = props.websites || props.entreprise_websites || [];
    
    // Entreprise
    const siren = props.entreprise_siren || (props.company_info ? props.company_info.siren : '') || '';
    const siret = props.entreprise_siret || (props.company_info ? props.company_info.siret : '') || '';
    const naf = props.entreprise_naf || (props.company_info ? props.company_info.naf_libelle : '') || '';
    
    // Propriétaire
    const ownerParts = [];
    if (props.owner_first_name) ownerParts.push(esc(props.owner_first_name));
    if (props.owner_last_name) ownerParts.push(esc(props.owner_last_name));
    const owner = ownerParts.join(' ') || esc(props.owner_name || '');
    const ownerRole = esc(props.owner_role || '');
    
    // Bâtiment
    const by = props.building_year || props.annee_construction || '';
    const dpe = props.classe_bilan_dpe || '';
    const roof = props.roof_area_m2 || '';
    const park = props.parking_area_m2 || '';

    let html = '';
    html += '<div class="popup-title">' + name + '</div>';
    html += '<p class="kv"><span class="k">Catégorie:</span> ' + category + '</p>';
    html += '<p class="kv"><span class="k">Adresse:</span> ' + addr + '</p>';

    // Contacts
    const hasContacts = (phones.length > 0) || pjPhone || (emails.length > 0) || (websites.length > 0);
    if (hasContacts) {{
      html += '<div class="popup-section-title">📞 Contacts</div>';
      
      if (pjPhone) {{
        html += '<p class="kv"><span class="k">Tel (PJ):</span> <a class="contact-link" href="tel:' + esc(pjPhone) + '">' + esc(pjPhone) + '</a></p>';
      }}
      if (phones.length) {{
        html += '<p class="kv"><span class="k">Tel:</span> ' + phones.map(p => '<a class="contact-link" href="tel:' + esc(p) + '">' + esc(p) + '</a>').join(', ') + '</p>';
      }}
      if (emails.length) {{
        html += '<p class="kv"><span class="k">Email:</span> ' + emails.map(e => '<a class="contact-link" href="mailto:' + esc(e) + '">' + esc(e) + '</a>').join(', ') + '</p>';
      }}
      if (websites.length) {{
        html += '<p class="kv"><span class="k">Site:</span> ' + websites.map(w => '<a class="contact-link" href="' + esc(w) + '" target="_blank">' + esc(w) + '</a>').join(' ') + '</p>';
      }}
    }}

    // Dirigeant
    if (owner) {{
      html += '<div class="popup-section-title">👤 Dirigeant</div>';
      html += '<p class="kv">' + owner + (ownerRole ? ' — ' + ownerRole : '') + '</p>';
    }}

    // Entreprise
    if (siren || siret || naf) {{
      html += '<div class="popup-section-title">🏢 Entreprise</div>';
      if (siren) html += '<p class="kv"><span class="k">SIREN:</span> ' + esc(siren) + '</p>';
      if (siret) html += '<p class="kv"><span class="k">SIRET:</span> ' + esc(siret) + '</p>';
      if (naf) html += '<p class="kv"><span class="k">NAF:</span> ' + esc(naf) + '</p>';
    }}

    // Bâtiment
    if (by || dpe || roof || park) {{
      html += '<div class="popup-section-title">🏠 Bâtiment</div>';
      if (by) html += '<p class="kv"><span class="k">Année:</span> ' + esc(by) + '</p>';
      if (dpe) html += '<p class="kv"><span class="k">DPE:</span> ' + esc(dpe) + '</p>';
      if (roof) html += '<p class="kv"><span class="k">Toiture:</span> ' + esc(roof) + ' m²</p>';
      if (park) html += '<p class="kv"><span class="k">Parking:</span> ' + esc(park) + ' m²</p>';
    }}

    return html;
  }}

  const gj = L.geoJSON(GEOJSON, {{
    onEachFeature: function (feature, layer) {{
      const p = feature.properties || {{}};
      layer.bindPopup(buildPopup(p), {{ maxWidth: 450 }});
    }}
  }});

  markers.addLayer(gj);
  map.addLayer(markers);

  // Ajuster le zoom
  try {{
    const group = new L.featureGroup([circle, gj]);
    map.fitBounds(group.getBounds(), {{ padding: [20,20] }});
  }} catch(e) {{
    map.fitBounds(circle.getBounds(), {{ padding: [20,20] }});
  }}
</script>
</body>
</html>
"""
    return html_template


def save_map_html(
    center_lat: float,
    center_lon: float,
    radius_m: int,
    features: List[Dict[str, Any]],
    output_file: str,
    title: str = "Carte Prospection"
):
    """Génère et sauvegarde la carte HTML"""
    html = build_map_html(center_lat, center_lon, radius_m, features, title)
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)


def load_map_html(file_path: str) -> Optional[str]:
    """Charge une carte HTML existante"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None
