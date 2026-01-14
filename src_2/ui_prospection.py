#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import html
import traceback
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil

# UI (Qt)
from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QPushButton, QProgressBar, QMessageBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView

# Import des 2 programmes (même dossier)
try:
    import trouve_entreprise as te  # programme 1
except Exception as e:
    print("Erreur: impossible d'importer trouve_entreprise.py :", e, file=sys.stderr)
    sys.exit(1)

try:
    import recup_donnees_entreprises as rde  # programme 2
except Exception as e:
    print("Erreur: impossible d'importer recup_donnees_entreprises.py :", e, file=sys.stderr)
    sys.exit(1)


# ----------------- Utils -----------------
def sanitize(s, default=""):
    try:
        if s is None:
            return default
        return str(s)
    except Exception:
        return default


def listify(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def has_contact(data: Dict[str, Any]) -> bool:
    """
    Critère: au moins 1 email OU 1 téléphone.
    On cherche d'abord dans contacts_osm (programme 2). Si vide, on tente les champs fréquents.
    """
    contacts = data.get("contacts_osm") or {}
    phones = listify(contacts.get("phones"))
    emails = listify(contacts.get("emails"))
    # Fallback éventuels
    if not phones:
        phones = listify(contacts.get("phone") or contacts.get("tels") or [])
    if not emails:
        emails = listify(contacts.get("email") or contacts.get("mails") or [])
    return (len(phones) > 0) or (len(emails) > 0)


def extract_contacts(data: Dict[str, Any]) -> Dict[str, List[str]]:
    contacts = data.get("contacts_osm") or {}
    phones = [sanitize(x) for x in listify(contacts.get("phones") or contacts.get("phone") or []) if x]
    emails = [sanitize(x) for x in listify(contacts.get("emails") or contacts.get("email") or []) if x]
    websites = [sanitize(x) for x in listify(contacts.get("websites") or contacts.get("website") or []) if x]
    socials = [sanitize(x) for x in listify(contacts.get("socials") or []) if x]
    return {
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "socials": socials,
    }


def extract_company_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Récupère quelques champs utiles de la première entreprise candidate.
    On reste robuste face aux variations de schéma.
    """
    companies = data.get("companies") or []
    if not companies:
        return {}
    c = companies[0] or {}
    keys_try = [
        "siren", "siret", "nom_complet", "denomination", "nom_raison_sociale",
        "categorie_juridique", "activite_principale", "naf", "libelle_naf", "siege"
    ]
    out = {}
    for k in keys_try:
        if k in c:
            out[k] = c.get(k)
    # Adresse du siège si dispo
    siege = c.get("siege") or {}
    for k in ["address", "code_postal", "commune", "geo_lat", "geo_lng"]:
        if k in siege:
            out[f"siege_{k}"] = siege.get(k)
    return out


def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default


# ----------------- Worker (thread) -----------------
class ProspectWorker(QThread):
    # Signals
    progress = Signal(int, int, str)          # current, total, message
    map_ready = Signal(str)                   # html string
    error = Signal(str, str)                  # title, details (traceback)
    done = Signal()

    def __init__(self, address: str, radius_km: float, parent=None):
        super().__init__(parent)
        self.address = address.strip()
        self.radius_km = float(radius_km)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if not self.address:
                self.error.emit("Adresse vide", "Veuillez saisir une adresse.")
                self.done.emit()
                return

            # 1) Géocodage centre (programme 1)
            self.progress.emit(0, 0, "Géocodage de l'adresse…")
            lat, lon = te.geocode_address(self.address)  # peut lever Exception
            center_lat, center_lon = float(lat), float(lon)
            radius_m = int(self.radius_km * 1000)

            if self._cancelled:
                self.done.emit()
                return

            # 2) Recherche d'entreprises (programme 1)
            self.progress.emit(0, 0, "Recherche des entreprises (Overpass)…")
            try:
                raw_businesses = te.find_businesses(center_lat, center_lon, radius=radius_m)
            except TypeError:
                # Compat: certains codes utilisent radius en 3e position; on retente si nécessaire
                raw_businesses = te.find_businesses(center_lat, center_lon, radius_m)

            # Attendu: liste de tuples (name, category, distance_m, address)
            businesses = []
            for tup in raw_businesses or []:
                try:
                    name, category, distance_m, address = tup
                except Exception:
                    # format inattendu -> on ignore
                    continue
                businesses.append({
                    "name": sanitize(name, "Inconnu"),
                    "category": sanitize(category, "n/a"),
                    "distance_m": int(distance_m) if str(distance_m).isdigit() else safe_float(distance_m, 0),
                    "address": sanitize(address, "Adresse inconnue"),
                    "center_lat": center_lat,
                    "center_lon": center_lon,
                })

            total = len(businesses)
            if total == 0:
                self.error.emit(
                    "Aucune entreprise",
                    f"Aucune entreprise trouvée dans un rayon de {radius_m} m autour de l'adresse."
                )
                self.done.emit()
                return

            # 3) Enrichissement (programme 2) + géocodage BAN de chaque prospect
            self.progress.emit(0, total, f"Enrichissement de {total} prospect(s)…")
            features = []
            processed = 0

            # Limiter le parallélisme (API publiques)
            max_workers = 4
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(self._enrich_one, item) for item in businesses]
                for fut in as_completed(futures):
                    if self._cancelled:
                        break
                    processed += 1
                    try:
                        res = fut.result()
                        if res is not None:
                            features.append(res)
                    except Exception:
                        # On poursuit même si un prospect échoue
                        pass
                    self.progress.emit(processed, total, f"Traitement {processed}/{total}…")

            if self._cancelled:
                self.done.emit()
                return

            if not features:
                self.error.emit(
                    "Aucun prospect avec contact",
                    "Aucun prospect ne possède d'email ou de téléphone."
                )
                self.done.emit()
                return

            # 4) Construire la carte
            self.progress.emit(total, total, "Construction de la carte…")
            html_map = self._build_map_html(center_lat, center_lon, radius_m, features)
            self.map_ready.emit(html_map)
            self.done.emit()

        except Exception as e:
            tb = traceback.format_exc(limit=2000)
            self.error.emit("Erreur durant la prospection", f"{e}\n\n{tb}")
            self.done.emit()

    # ---- helpers internes du worker ----
    def _enrich_one(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Enrichit un prospect en appelant le programme 2.
        Retourne un Feature GeoJSON-like: {"lat":..., "lon":..., "props":{...}} ou None si pas de contact/coordonnées.
        """
        name = item["name"]
        addr = item["address"]
        distance_m = item["distance_m"]
        center_lat = item["center_lat"]
        center_lon = item["center_lon"]

        # 1) Géocodage BAN de l'adresse de l'entreprise (pour positionner le marqueur)
        lat, lon = None, None
        try:
            geo = rde.geocode_ban(addr)
            if geo:
                lat = geo.get("lat")
                lon = geo.get("lon")
        except Exception:
            lat, lon = None, None

        # 2) Enrichissement (programme 2)
        data = None
        try:
            data = rde.run_test(name, addr)
        except Exception:
            return None

        # 3) Filtre contact
        if not has_contact(data):
            return None

        # 4) Si pas de coord BAN, tenter coordonnées issues de run_test (géocodage de la requête)
        if lat is None or lon is None:
            geo2 = data.get("geocoding") or {}
            lat = lat or geo2.get("lat")
            lon = lon or geo2.get("lon")

        if lat is None or lon is None:
            return None

        lat = float(lat)
        lon = float(lon)

        contacts = extract_contacts(data)
        comp = extract_company_summary(data)
        owner = data.get("owner") or {}
        props = {
            "name": name,
            "category": item.get("category"),
            "address": addr,
            "distance_m": distance_m,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "phones": contacts.get("phones", []),
            "emails": contacts.get("emails", []),
            "websites": contacts.get("websites", []),
            "socials": contacts.get("socials", []),
            "company": comp,
            "owner_first_name": owner.get("first_name"),
            "owner_last_name": owner.get("last_name"),
            "owner_role": owner.get("role"),
            "building_year": data.get("building_year"),
            "roof_area_m2": data.get("roof_area_m2"),
            "parking_area_m2": data.get("parking_area_m2"),
        }
        return {"lat": lat, "lon": lon, "props": props}

    def _build_map_html(self, center_lat: float, center_lon: float, radius_m: int, features: List[Dict[str, Any]]) -> str:
        """
        Construit une page HTML Leaflet autonome (CDN) avec:
          - fond satellite Esri + OSM,
          - cercle du rayon,
          - clustering,
          - popups détaillées.
        """
        # Transformation en FeatureCollection GeoJSON
        gj_features = []
        for f in features:
            lat = f["lat"]; lon = f["lon"]; p = f["props"]
            # Nettoyage de propriétés pour JSON
            props = {}
            for k, v in p.items():
                if isinstance(v, (list, tuple)):
                    props[k] = [sanitize(x) for x in v]
                elif isinstance(v, (dict,)):
                    # dictionnaire simple -> on le garde
                    props[k] = v
                else:
                    props[k] = sanitize(v)
            gj_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props
            })
        feature_collection = {"type": "FeatureCollection", "features": gj_features}
        gj_json = json.dumps(feature_collection, ensure_ascii=False)

        # HTML Leaflet
        html_template = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Carte Prospection</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">

<style>
  html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
  .popup-title {{ font-weight: 700; font-size: 14px; margin-bottom: 4px; }}
  .popup-section-title {{ font-weight: 600; margin-top: 8px; }}
  .kv {{ margin: 0; }}
  .kv span.k {{ color: #666; }}
  .chips span {{ display:inline-block; background:#eef; border-radius:10px; padding:2px 6px; margin:2px; font-size:12px; }}
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

  // Centre (marqueur discret)
  L.circleMarker(CENTER, {{
    radius: 5, color: '#1d4ed8', fillColor: '#1d4ed8', fillOpacity: 0.9
  }}).bindTooltip('Centre de recherche').addTo(map);

  // Cluster
  const markers = L.markerClusterGroup();

  function esc(x) {{
    if (x === null || x === undefined) return '';
    return String(x)
      .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  }}

  function joinChips(arr) {{
    if (!arr || !arr.length) return '';
    return '<div class="chips">' + arr.map(x => '<span>' + esc(x) + '</span>').join('') + '</div>';
  }}

  function buildPopup(props) {{
    const name = esc(props.name || 'Inconnu');
    const category = esc(props.category || 'n/a');
    const addr = esc(props.address || 'Adresse inconnue');
    const dist = props.distance_m !== undefined && props.distance_m !== null ? Number(props.distance_m) : null;

    const phones = props.phones || [];
    const emails = props.emails || [];
    const websites = props.websites || [];
    const socials = props.socials || [];

    const ownerParts = [];
    if (props.owner_first_name) ownerParts.push(esc(props.owner_first_name));
    if (props.owner_last_name) ownerParts.push(esc(props.owner_last_name));
    const owner = ownerParts.join(' ') || '';

    const comp = props.company || {{}};
    const siret = comp.siret || '';
    const siren = comp.siren || '';
    const naf = comp.libelle_naf || comp.naf || comp.activite_principale || '';
    const denom = comp.nom_complet || comp.denomination || comp.nom_raison_sociale || '';

    let html = '';
    html += '<div class="popup-title">' + name + '</div>';
    html += '<p class="kv"><span class="k">Catégorie:</span> ' + category + '</p>';
    if (dist !== null) html += '<p class="kv"><span class="k">Distance (prog.1):</span> ' + dist + ' m</p>';
    html += '<p class="kv"><span class="k">Adresse:</span> ' + addr + '</p>';

    if (owner) {{
      html += '<p class="kv"><span class="k">Dirigeant (heuristique):</span> ' + owner + (props.owner_role ? ' — ' + esc(props.owner_role) : '') + '</p>';
    }}

    if (siret || siren || naf || denom) {{
      html += '<div class="popup-section-title">Entreprise</div>';
      if (denom) html += '<p class="kv"><span class="k">Dénomination:</span> ' + esc(denom) + '</p>';
      if (siret) html += '<p class="kv"><span class="k">SIRET:</span> ' + esc(siret) + '</p>';
      if (siren) html += '<p class="kv"><span class="k">SIREN:</span> ' + esc(siren) + '</p>';
      if (naf) html += '<p class="kv"><span class="k">Activité/NAF:</span> ' + esc(naf) + '</p>';
    }}

    const by = props.building_year ? esc(props.building_year) : '';
    const roof = props.roof_area_m2 ? esc(props.roof_area_m2) : '';
    const park = props.parking_area_m2 ? esc(props.parking_area_m2) : '';
    if (by || roof || park) {{
      html += '<div class="popup-section-title">Bâtiment (OSM)</div>';
      if (by) html += '<p class="kv"><span class="k">Année plausible:</span> ' + by + '</p>';
      if (roof) html += '<p class="kv"><span class="k">Toiture (m²):</span> ' + roof + '</p>';
      if (park) html += '<p class="kv"><span class="k">Parking (m²):</span> ' + park + '</p>';
    }}

    if (phones.length || emails.length || websites.length || socials.length) {{
      html += '<div class="popup-section-title">Contacts</div>';
      if (phones.length) html += '<div><span class="k">Téléphone(s):</span>' + joinChips(phones) + '</div>';
      if (emails.length) html += '<div><span class="k">Email(s):</span>' + joinChips(emails) + '</div>';
      if (websites.length) {{
        const links = websites.map(w => '<a href="' + esc(w) + '" target="_blank" rel="noreferrer noopener">' + esc(w) + '</a>');
        html += '<div><span class="k">Site(s):</span> ' + links.join(' · ') + '</div>';
      }}
      if (socials.length) html += '<div><span class="k">Réseaux:</span>' + joinChips(socials) + '</div>';
    }}

    return html;
  }}

  const gj = L.geoJSON(GEOJSON, {{
    onEachFeature: function (feature, layer) {{
      const p = feature.properties || {{}};
      layer.bindPopup(buildPopup(p), {{ maxWidth: 420 }});
    }}
  }});

  markers.addLayer(gj);
  map.addLayer(markers);

  // Ajuster le zoom sur tous les marqueurs + le cercle
  try {{
    const group = new L.featureGroup([circle, gj]);
    map.fitBounds(group.getBounds(), {{ padding: [20,20] }});
  }} catch(e) {{
    // fallback
    map.fitBounds(circle.getBounds(), {{ padding: [20,20] }});
  }}
</script>
</body>
</html>
"""
        return html_template


# ----------------- Fenêtre principale -----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prospection – Carte interactive")
        self.setMinimumSize(1024, 700)

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Ex: 10 Rue de la Paix, 75002 Paris")

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setSuffix(" km")
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSingleStep(0.1)
        self.radius_spin.setMinimum(0.1)
        self.radius_spin.setMaximum(50.0)
        self.radius_spin.setValue(0.5)  # 500 m par défaut

        self.run_btn = QPushButton("Lancer")
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        top = QHBoxLayout()
        top.addWidget(QLabel("Adresse:"))
        top.addWidget(self.address_edit, 2)
        top.addWidget(QLabel("Rayon:"))
        top.addWidget(self.radius_spin)
        top.addWidget(self.run_btn)
        top.addWidget(self.cancel_btn)

        self.web = QWebEngineView()
        self.web.setHtml("<html><body><p style='font-family:sans-serif;padding:1rem'>Saisissez une adresse et lancez la prospection.</p></body></html>")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(self.web, 1)

        self.worker: Optional[ProspectWorker] = None

        self.run_btn.clicked.connect(self.on_run)
        self.cancel_btn.clicked.connect(self.on_cancel)

    @Slot()
    def on_run(self):
        address = self.address_edit.text().strip()
        radius_km = float(self.radius_spin.value())
        if not address:
            QMessageBox.warning(self, "Adresse manquante", "Veuillez saisir une adresse.")
            return

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        self.worker = ProspectWorker(address, radius_km)
        self.worker.progress.connect(self.on_progress)
        self.worker.map_ready.connect(self.on_map_ready)
        self.worker.error.connect(self.on_error)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    @Slot()
    def on_cancel(self):
        if self.worker is not None:
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)

    @Slot(int, int, str)
    def on_progress(self, current: int, total: int, msg: str):
        if total <= 0:
            # phase indéterminée
            self.progress.setRange(0, 0)  # animation
            self.progress.setFormat(msg)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            # Affiche un texte lisible
            self.progress.setFormat(f"{msg}")

    @Slot(str)
    def on_map_ready(self, html_str: str):
        self.web.setHtml(html_str)

    @Slot(str, str)
    def on_error(self, title: str, details: str):
        QMessageBox.critical(self, title, details)

    @Slot()
    def on_done(self):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        # repasser en barre déterminée 0..100
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Terminé")


# ----------------- Entrée programme -----------------
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()