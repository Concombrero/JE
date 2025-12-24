#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_data.py
Module d'export des données enrichies vers CSV et carte HTML interactive.
"""

import csv
import json
import os
from typing import List, Dict, Any
from tools import EnrichedData
from interface import Logger


class DataExporter:
    """
    Gère l'export des données enrichies vers différents formats.
    """
    
    def __init__(self, logger: Logger):
        self.logger = logger
    
    def export_to_csv(self, data_list: List[EnrichedData], output_path: str):
        """
        Exporte les données enrichies vers un fichier CSV.
        
        Args:
            data_list: Liste des données enrichies
            output_path: Chemin du fichier CSV de sortie
        """
        self.logger.log(f"Export CSV vers {output_path}", "INFO")
        
        # Créer le dossier parent si nécessaire
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            
            # En-têtes
            headers = [
                'Nom',
                'Adresse',
                'Latitude',
                'Longitude',
                'Distance (m)',
                # Source 1: Pages Jaunes + BDNB
                'PJ - Téléphone',
                'PJ - Titre',
                'BDNB - Année Construction',
                'BDNB - Classe DPE',
                # Source 2: OSM
                'OSM - Catégorie',
                'OSM - Téléphones',
                'OSM - Emails',
                'OSM - Sites Web',
                'OSM - Réseaux Sociaux',
                # Source 2: API Entreprises
                'Entreprise - SIREN',
                'Entreprise - SIRET',
                'Entreprise - Nom',
                'Entreprise - NAF',
                'Entreprise - Libellé NAF',
                'Dirigeants',
                # Source 2: Bâtiment OSM
                'Bâtiment - Année',
                'Bâtiment - Surface Toiture (m²)',
                'Bâtiment - Surface Parking (m²)',
            ]
            writer.writerow(headers)
            
            # Données
            for item in data_list:
                # Formater les listes pour CSV
                osm_phones = ', '.join(item.get('osm_phones', [])) if item.get('osm_phones') else ''
                osm_emails = ', '.join(item.get('osm_emails', [])) if item.get('osm_emails') else ''
                osm_websites = ', '.join(item.get('osm_websites', [])) if item.get('osm_websites') else ''
                osm_socials = ', '.join(item.get('osm_socials', [])) if item.get('osm_socials') else ''
                
                # Formater les dirigeants
                dirigeants = item.get('dirigeants', [])
                dirigeants_str = ''
                if dirigeants:
                    parts = []
                    for d in dirigeants:
                        name_parts = []
                        if d.get('first_name'):
                            name_parts.append(d['first_name'])
                        if d.get('last_name'):
                            name_parts.append(d['last_name'])
                        name = ' '.join(name_parts)
                        if d.get('role'):
                            name += f" ({d['role']})"
                        if name:
                            parts.append(name)
                    dirigeants_str = ' ; '.join(parts)
                
                row = [
                    item.get('name', ''),
                    item.get('address', ''),
                    item.get('lat', ''),
                    item.get('lon', ''),
                    item.get('distance_m', ''),
                    # Source 1
                    item.get('pagesjaunes_phone', ''),
                    item.get('pagesjaunes_title', ''),
                    item.get('bdnb_annee_construction', ''),
                    item.get('bdnb_classe_dpe', ''),
                    # Source 2: OSM
                    item.get('osm_category', ''),
                    osm_phones,
                    osm_emails,
                    osm_websites,
                    osm_socials,
                    # Source 2: API Entreprises
                    item.get('company_siren', ''),
                    item.get('company_siret', ''),
                    item.get('company_nom', ''),
                    item.get('company_naf', ''),
                    item.get('company_libelle_naf', ''),
                    dirigeants_str,
                    # Source 2: Bâtiment
                    item.get('building_year', ''),
                    item.get('roof_area_m2', ''),
                    item.get('parking_area_m2', ''),
                ]
                writer.writerow(row)
        
        self.logger.log(f"Export CSV réussi: {len(data_list)} lignes", "SUCCESS")
    
    def export_to_map(self, data_list: List[EnrichedData], center_lat: float, 
                     center_lon: float, radius_m: int, output_path: str):
        """
        Génère une carte HTML interactive avec les données enrichies.
        
        Args:
            data_list: Liste des données enrichies
            center_lat, center_lon: Coordonnées du centre de recherche
            radius_m: Rayon de recherche en mètres
            output_path: Chemin du fichier HTML de sortie
        """
        self.logger.log(f"Génération de la carte vers {output_path}", "INFO")
        
        # Créer le dossier parent si nécessaire
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Construire les features GeoJSON
        features = []
        for item in data_list:
            lat = item.get('lat')
            lon = item.get('lon')
            if lat is None or lon is None:
                continue
            
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [float(lon), float(lat)]
                },
                'properties': {
                    'name': str(item.get('name', 'Inconnu')),
                    'address': str(item.get('address', '')),
                    'distance_m': float(item.get('distance_m', 0)),
                    # Source 1
                    'pj_phone': str(item.get('pagesjaunes_phone', '')),
                    'pj_title': str(item.get('pagesjaunes_title', '')),
                    'bdnb_year': str(item.get('bdnb_annee_construction', '')),
                    'bdnb_dpe': str(item.get('bdnb_classe_dpe', '')),
                    # Source 2
                    'osm_category': str(item.get('osm_category', '')),
                    'osm_phones': item.get('osm_phones', []),
                    'osm_emails': item.get('osm_emails', []),
                    'osm_websites': item.get('osm_websites', []),
                    'company_siren': str(item.get('company_siren', '')),
                    'company_siret': str(item.get('company_siret', '')),
                    'company_nom': str(item.get('company_nom', '')),
                    'company_naf': str(item.get('company_naf', '')),
                    'company_libelle_naf': str(item.get('company_libelle_naf', '')),
                    'dirigeants': item.get('dirigeants', []),
                    'building_year': item.get('building_year'),
                    'roof_area_m2': item.get('roof_area_m2'),
                    'parking_area_m2': item.get('parking_area_m2'),
                }
            }
            features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        geojson_str = json.dumps(geojson, ensure_ascii=False)
        
        # Générer le HTML
        html = self._generate_map_html(center_lat, center_lon, radius_m, geojson_str)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self.logger.log(f"Carte générée: {len(features)} marqueurs", "SUCCESS")
    
    def _generate_map_html(self, center_lat: float, center_lon: float, 
                          radius_m: int, geojson_str: str) -> str:
        """
        Génère le code HTML de la carte interactive.
        """
        html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Carte Prospection - Sources Fusionnées</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">

<style>
  html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
  .popup-title {{ font-weight: 700; font-size: 16px; margin-bottom: 8px; color: #1f2937; }}
  .popup-section {{ margin-top: 12px; padding-top: 8px; border-top: 1px solid #e5e7eb; }}
  .popup-section-title {{ font-weight: 600; font-size: 14px; margin-bottom: 6px; color: #374151; }}
  .kv {{ margin: 4px 0; font-size: 13px; }}
  .kv .k {{ color: #6b7280; font-weight: 500; }}
  .kv .v {{ color: #111827; }}
  .chips {{ margin-top: 4px; }}
  .chips span {{ display:inline-block; background:#dbeafe; color:#1e40af; border-radius:10px; padding:2px 8px; margin:2px; font-size:12px; }}
  .source-badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; margin-right: 4px; }}
  .source-pj {{ background: #fef3c7; color: #92400e; }}
  .source-bdnb {{ background: #ddd6fe; color: #5b21b6; }}
  .source-osm {{ background: #d1fae5; color: #065f46; }}
  .source-api {{ background: #e0e7ff; color: #3730a3; }}
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
  const GEOJSON = {geojson_str};

  // Fonds de carte
  const esriSat = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{ attribution: 'Esri', maxZoom: 20 }}
  );
  const osmPlan = L.tileLayer(
    'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{ attribution: '&copy; OpenStreetMap', maxZoom: 20 }}
  );

  const map = L.map('map', {{
    center: CENTER,
    zoom: 14,
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
    fillOpacity: 0.1,
    weight: 2
  }}).addTo(map);

  // Centre
  L.circleMarker(CENTER, {{
    radius: 6, color: '#1d4ed8', fillColor: '#60a5fa', fillOpacity: 0.9
  }}).bindTooltip('Centre de recherche').addTo(map);

  function esc(x) {{
    if (x === null || x === undefined || x === '') return '';
    return String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  }}

  function joinChips(arr) {{
    if (!arr || !arr.length) return '';
    return '<div class="chips">' + arr.map(x => '<span>' + esc(x) + '</span>').join('') + '</div>';
  }}

  function buildPopup(p) {{
    let html = '<div class="popup-title">' + esc(p.name) + '</div>';
    html += '<div class="kv"><span class="k">Adresse:</span> <span class="v">' + esc(p.address) + '</span></div>';
    html += '<div class="kv"><span class="k">Distance:</span> <span class="v">' + Math.round(p.distance_m) + ' m</span></div>';
    
    // Source 1: Pages Jaunes
    if (p.pj_phone || p.pj_title) {{
      html += '<div class="popup-section">';
      html += '<div class="popup-section-title"><span class="source-badge source-pj">Pages Jaunes</span></div>';
      if (p.pj_title) html += '<div class="kv"><span class="k">Titre:</span> <span class="v">' + esc(p.pj_title) + '</span></div>';
      if (p.pj_phone) html += '<div class="kv"><span class="k">Téléphone:</span> <span class="v">' + esc(p.pj_phone) + '</span></div>';
      html += '</div>';
    }}
    
    // Source 1: BDNB
    if (p.bdnb_year || p.bdnb_dpe) {{
      html += '<div class="popup-section">';
      html += '<div class="popup-section-title"><span class="source-badge source-bdnb">BDNB</span></div>';
      if (p.bdnb_year) html += '<div class="kv"><span class="k">Année construction:</span> <span class="v">' + esc(p.bdnb_year) + '</span></div>';
      if (p.bdnb_dpe) html += '<div class="kv"><span class="k">Classe DPE:</span> <span class="v">' + esc(p.bdnb_dpe) + '</span></div>';
      html += '</div>';
    }}
    
    // Source 2: OSM
    if (p.osm_category || p.osm_phones.length || p.osm_emails.length || p.osm_websites.length) {{
      html += '<div class="popup-section">';
      html += '<div class="popup-section-title"><span class="source-badge source-osm">OSM</span></div>';
      if (p.osm_category) html += '<div class="kv"><span class="k">Catégorie:</span> <span class="v">' + esc(p.osm_category) + '</span></div>';
      if (p.osm_phones.length) html += '<div class="kv"><span class="k">Téléphones:</span>' + joinChips(p.osm_phones) + '</div>';
      if (p.osm_emails.length) html += '<div class="kv"><span class="k">Emails:</span>' + joinChips(p.osm_emails) + '</div>';
      if (p.osm_websites.length) {{
        const links = p.osm_websites.map(w => '<a href="' + esc(w) + '" target="_blank">' + esc(w) + '</a>');
        html += '<div class="kv"><span class="k">Sites:</span> ' + links.join(' · ') + '</div>';
      }}
      html += '</div>';
    }}
    
    // Source 2: API Entreprises
    if (p.company_nom || p.company_siren || p.company_naf) {{
      html += '<div class="popup-section">';
      html += '<div class="popup-section-title"><span class="source-badge source-api">API Entreprises</span></div>';
      if (p.company_nom) html += '<div class="kv"><span class="k">Nom:</span> <span class="v">' + esc(p.company_nom) + '</span></div>';
      if (p.company_siren) html += '<div class="kv"><span class="k">SIREN:</span> <span class="v">' + esc(p.company_siren) + '</span></div>';
      if (p.company_siret) html += '<div class="kv"><span class="k">SIRET:</span> <span class="v">' + esc(p.company_siret) + '</span></div>';
      if (p.company_naf) html += '<div class="kv"><span class="k">NAF:</span> <span class="v">' + esc(p.company_naf) + ' - ' + esc(p.company_libelle_naf) + '</span></div>';
      if (p.dirigeants && p.dirigeants.length) {{
        html += '<div class="kv"><span class="k">Dirigeants:</span></div>';
        p.dirigeants.forEach(d => {{
          const name = [d.first_name, d.last_name].filter(x => x).join(' ');
          const role = d.role ? ' (' + esc(d.role) + ')' : '';
          if (name) html += '<div style="margin-left:12px;font-size:12px;">• ' + esc(name) + role + '</div>';
        }});
      }}
      html += '</div>';
    }}
    
    // Bâtiment OSM
    if (p.building_year || p.roof_area_m2 || p.parking_area_m2) {{
      html += '<div class="popup-section">';
      html += '<div class="popup-section-title"><span class="source-badge source-osm">Bâtiment (OSM)</span></div>';
      if (p.building_year) html += '<div class="kv"><span class="k">Année:</span> <span class="v">' + esc(p.building_year) + '</span></div>';
      if (p.roof_area_m2) html += '<div class="kv"><span class="k">Toiture:</span> <span class="v">' + esc(p.roof_area_m2) + ' m²</span></div>';
      if (p.parking_area_m2) html += '<div class="kv"><span class="k">Parking:</span> <span class="v">' + esc(p.parking_area_m2) + ' m²</span></div>';
      html += '</div>';
    }}
    
    return html;
  }}

  // Marqueurs avec clustering
  const markers = L.markerClusterGroup();
  const gj = L.geoJSON(GEOJSON, {{
    onEachFeature: function (feature, layer) {{
      const p = feature.properties || {{}};
      layer.bindPopup(buildPopup(p), {{ maxWidth: 500 }});
    }}
  }});
  markers.addLayer(gj);
  map.addLayer(markers);

  // Ajuster le zoom
  try {{
    const group = new L.featureGroup([circle, gj]);
    map.fitBounds(group.getBounds(), {{ padding: [30,30] }});
  }} catch(e) {{
    map.fitBounds(circle.getBounds(), {{ padding: [30,30] }});
  }}
</script>
</body>
</html>
"""
        return html
