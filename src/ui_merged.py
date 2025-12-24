#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_merged.py
Interface graphique qui utilise l'enrichissement fusionné des deux sources.
Basée sur ui_prospection.py de src_2 mais avec enrichissement complet.
"""

import sys
import os
import traceback
from typing import List, Optional

# UI (Qt)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QPushButton, QProgressBar, QMessageBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView

# Imports modules fusionnés
import trouve_entreprise as te
from enrichment import EnrichmentManager
from export_data import DataExporter
from interface import Logger
from tools import EnrichedData


class ProspectWorker(QThread):
    """
    Thread qui gère la prospection complète avec enrichissement fusionné.
    """
    # Signals
    progress = Signal(int, int, str)  # current, total, message
    map_ready = Signal(str)           # html string
    error = Signal(str, str)          # title, details
    done = Signal()

    def __init__(self, address: str, radius_km: float, output_dir: str, parent=None):
        super().__init__(parent)
        self.address = address.strip()
        self.radius_km = float(radius_km)
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        logger = None
        enrichment_manager = None
        
        try:
            # Créer le dossier de sortie
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Initialiser le logger
            log_path = os.path.join(self.output_dir, 'log.txt')
            logger = Logger(log_path)
            logger.both("Démarrage de la prospection", "INFO")
            
            if not self.address:
                self.error.emit("Adresse vide", "Veuillez saisir une adresse.")
                self.done.emit()
                return

            # 1) Géocodage du centre
            self.progress.emit(0, 0, "Géocodage de l'adresse…")
            logger.both(f"Géocodage de l'adresse: {self.address}", "INFO")
            
            lat, lon = te.geocode_address(self.address)
            center_lat, center_lon = float(lat), float(lon)
            radius_m = int(self.radius_km * 1000)
            
            logger.both(f"Coordonnées: {center_lat}, {center_lon}", "SUCCESS")

            if self._cancelled:
                self.done.emit()
                return

            # 2) Recherche d'entreprises (programme 1 - OSM)
            self.progress.emit(0, 0, "Recherche des entreprises (Overpass)…")
            logger.both("Recherche des entreprises via Overpass", "INFO")
            
            try:
                raw_businesses = te.find_businesses(center_lat, center_lon, radius=radius_m)
            except TypeError:
                raw_businesses = te.find_businesses(center_lat, center_lon, radius_m)

            businesses = []
            for tup in raw_businesses or []:
                try:
                    name, category, distance_m, address_str = tup
                except Exception:
                    continue
                businesses.append({
                    "name": str(name) if name else "Inconnu",
                    "category": str(category) if category else "n/a",
                    "distance_m": int(distance_m) if isinstance(distance_m, int) else float(distance_m) if distance_m else 0,
                    "address": str(address_str) if address_str else "Adresse inconnue",
                })

            total = len(businesses)
            if total == 0:
                self.error.emit(
                    "Aucune entreprise",
                    f"Aucune entreprise trouvée dans un rayon de {radius_m} m."
                )
                logger.both("Aucune entreprise trouvée", "ERROR")
                self.done.emit()
                return

            logger.both(f"{total} entreprises trouvées", "SUCCESS")

            # 3) Enrichissement avec les deux sources
            self.progress.emit(0, total, f"Enrichissement de {total} prospect(s)…")
            logger.both(f"Début de l'enrichissement de {total} entreprises", "INFO")
            
            enrichment_manager = EnrichmentManager(logger)
            enriched_data: List[EnrichedData] = []
            processed = 0

            # Traitement séquentiel (sans parallélisme)
            for item in businesses:
                if self._cancelled:
                    break
                
                processed += 1
                try:
                    result = self._enrich_one(item, center_lat, center_lon, enrichment_manager)
                    if result is not None:
                        enriched_data.append(result)
                        logger.log(f"Entreprise enrichie: {result.get('name')}", "DEBUG")
                except Exception as e:
                    logger.log(f"Erreur enrichissement: {e}", "ERROR")
                
                self.progress.emit(processed, total, f"Traitement {processed}/{total}…")

            if self._cancelled:
                logger.both("Prospection annulée", "INFO")
                self.done.emit()
                return

            if not enriched_data:
                self.error.emit(
                    "Aucune donnée enrichie",
                    "Impossible d'enrichir les données des entreprises trouvées."
                )
                logger.both("Aucune donnée enrichie", "ERROR")
                self.done.emit()
                return

            logger.both(f"{len(enriched_data)} entreprises enrichies", "SUCCESS")
            
            # Filtrage de qualité : éliminer les entreprises avec peu d'infos
            self.progress.emit(total, total, "Filtrage des résultats par qualité…")
            logger.both("Application du filtre de qualité", "INFO")
            
            initial_count = len(enriched_data)
            enriched_data = self._filter_by_quality(enriched_data, center_lat, center_lon, radius_m, logger)
            filtered_count = initial_count - len(enriched_data)
            
            if filtered_count > 0:
                logger.both(f"{filtered_count} entreprise(s) filtrée(s) (qualité insuffisante)", "INFO")
            
            if not enriched_data:
                self.error.emit(
                    "Aucune entreprise de qualité",
                    "Toutes les entreprises ont été filtrées car elles ne contiennent pas assez d'informations."
                )
                logger.both("Aucune entreprise après filtrage", "ERROR")
                self.done.emit()
                return
            
            logger.both(f"{len(enriched_data)} entreprises retenues après filtrage", "SUCCESS")

            # 4) Export des données
            self.progress.emit(total, total, "Export des données…")
            logger.both("Export des données", "INFO")
            
            exporter = DataExporter(logger)
            
            # Export CSV
            csv_path = os.path.join(self.output_dir, 'resultats.csv')
            exporter.export_to_csv(enriched_data, csv_path)
            
            # Export carte HTML
            map_path = os.path.join(self.output_dir, 'carte.html')
            exporter.export_to_map(enriched_data, center_lat, center_lon, radius_m, map_path)
            
            # Charger la carte générée
            with open(map_path, 'r', encoding='utf-8') as f:
                html_map = f.read()
            
            logger.both(f"Prospection terminée: {len(enriched_data)} résultats", "SUCCESS")
            logger.both(f"Fichiers générés dans: {self.output_dir}", "SUCCESS")
            
            self.map_ready.emit(html_map)
            self.done.emit()

        except Exception as e:
            tb = traceback.format_exc(limit=2000)
            self.error.emit("Erreur durant la prospection", f"{e}\n\n{tb}")
            if logger:
                logger.log(f"Erreur critique: {e}", "ERROR")
                logger.log(tb, "ERROR")
            self.done.emit()
        
        finally:
            # Nettoyer les ressources
            if enrichment_manager:
                try:
                    enrichment_manager.close()
                except Exception as e:
                    if logger:
                        logger.log(f"Erreur fermeture enrichment: {e}", "ERROR")

    def _enrich_one(self, item: dict, center_lat: float, center_lon: float, 
                    enrichment_manager: EnrichmentManager) -> Optional[EnrichedData]:
        """
        Enrichit une entreprise avec les deux sources.
        """
        try:
            name = item["name"]
            address_str = item["address"]
            category = item["category"]
            distance_m = item["distance_m"]
            
            # Géocodage BAN de l'adresse de l'entreprise
            import recup_donnees_entreprises as rde
            geo = rde.geocode_ban(address_str)
            
            if not geo:
                return None
            
            lat = geo.get("lat")
            lon = geo.get("lon")
            
            if lat is None or lon is None:
                return None
            
            # Enrichissement avec les deux sources
            enriched = enrichment_manager.enrich_business(
                name=name,
                address_str=address_str,
                category=category,
                distance_m=distance_m,
                lat=float(lat),
                lon=float(lon)
            )
            
            return enriched
            
        except Exception as e:
            return None

    def _filter_by_quality(self, enriched_data: List[EnrichedData], 
                          center_lat: float, center_lon: float, 
                          radius_m: int, logger: Logger) -> List[EnrichedData]:
        """
        Filtre les entreprises selon des critères de qualité:
        1. Distance réelle dans la zone spécifiée
        2. Informations suffisantes sur l'entreprise, l'adresse ou le bâtiment
        
        Retourne la liste filtrée.
        """
        from geopy.distance import geodesic
        
        filtered_results = []
        
        for data in enriched_data:
            # Critère 1: Vérifier que l'entreprise est bien dans la zone
            if data.get('lat') and data.get('lon'):
                distance = geodesic(
                    (center_lat, center_lon),
                    (data['lat'], data['lon'])
                ).meters
                
                # Éliminer si hors zone (avec marge de tolérance de 10%)
                if distance > radius_m * 1.1:
                    logger.log(
                        f"Entreprise '{data.get('name')}' filtrée: "
                        f"hors zone ({distance:.0f}m > {radius_m}m)",
                        "DEBUG"
                    )
                    continue
            else:
                # Pas de coordonnées = rejet
                logger.log(
                    f"Entreprise '{data.get('name')}' filtrée: coordonnées manquantes",
                    "DEBUG"
                )
                continue
            
            # Critère 2: Score de qualité des informations
            quality_score = 0
            
            # Informations de contact (5 points max)
            if data.get('pagesjaunes_phone') or data.get('osm_phones'):
                quality_score += 2
            if data.get('osm_emails'):
                quality_score += 1
            if data.get('osm_websites'):
                quality_score += 2
            
            # Informations sur l'entreprise (5 points max)
            if data.get('company_siren') or data.get('company_siret'):
                quality_score += 3
            if data.get('company_naf'):
                quality_score += 1
            if data.get('dirigeants') and len(data.get('dirigeants', [])) > 0:
                quality_score += 1
            
            # Informations sur le bâtiment (3 points max)
            if data.get('bdnb_annee_construction') or data.get('building_year'):
                quality_score += 1
            if data.get('bdnb_classe_dpe'):
                quality_score += 1
            if data.get('roof_area_m2') or data.get('parking_area_m2'):
                quality_score += 1
            
            # Informations sur l'adresse (2 points max)
            address = data.get('address', '')
            if address and address != 'Adresse inconnue':
                if any(char.isdigit() for char in address):  # Contient un numéro
                    quality_score += 1
                if ',' in address or len(address.split()) > 2:  # Adresse détaillée
                    quality_score += 1
            
            # Seuil minimum de qualité : 3 points sur 15
            MIN_QUALITY_SCORE = 3
            
            if quality_score < MIN_QUALITY_SCORE:
                logger.log(
                    f"Entreprise '{data.get('name')}' filtrée: "
                    f"qualité insuffisante (score: {quality_score}/{MIN_QUALITY_SCORE})",
                    "DEBUG"
                )
                continue
            
            # L'entreprise passe les filtres
            filtered_results.append(data)
            logger.log(
                f"Entreprise '{data.get('name')}' retenue (score qualité: {quality_score}/15)",
                "DEBUG"
            )
        
        return filtered_results


class MainWindow(QWidget):
    """
    Fenêtre principale de l'application.
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prospection Fusionnée – Sources 1 + 2")
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

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Nom du dossier de sortie (ex: ma_prospection)")
        self.output_edit.setText("prospection")

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

        second = QHBoxLayout()
        second.addWidget(QLabel("Dossier:"))
        second.addWidget(self.output_edit, 2)
        second.addWidget(self.run_btn)
        second.addWidget(self.cancel_btn)

        self.web = QWebEngineView()
        self.web.setHtml("""<html><body style="font-family:sans-serif;padding:2rem">
            <h2>Prospection Fusionnée</h2>
            <p>Cette application combine les données de deux sources:</p>
            <ul>
                <li><strong>Source 1:</strong> Pages Jaunes (téléphone, titre) + BDNB (année construction, DPE)</li>
                <li><strong>Source 2:</strong> OSM (contacts, catégories) + API Entreprises (SIREN, NAF, dirigeants)</li>
            </ul>
            <p>Saisissez une adresse, un rayon et un nom de dossier, puis lancez la prospection.</p>
            <p>Les résultats seront sauvegardés dans <code>output/[nom_dossier]/</code> avec:</p>
            <ul>
                <li><code>resultats.csv</code> - Tableur avec toutes les données</li>
                <li><code>carte.html</code> - Carte interactive</li>
                <li><code>log.txt</code> - Journal d'exécution</li>
            </ul>
        </body></html>""")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(second)
        layout.addWidget(self.progress)
        layout.addWidget(self.web, 1)

        self.worker: Optional[ProspectWorker] = None

        self.run_btn.clicked.connect(self.on_run)
        self.cancel_btn.clicked.connect(self.on_cancel)

    @Slot()
    def on_run(self):
        address = self.address_edit.text().strip()
        radius_km = float(self.radius_spin.value())
        output_name = self.output_edit.text().strip() or "prospection"
        
        if not address:
            QMessageBox.warning(self, "Adresse manquante", "Veuillez saisir une adresse.")
            return

        output_dir = os.path.join('output', output_name)
        
        # Vérifier si le dossier existe déjà
        if os.path.exists(output_dir):
            reply = QMessageBox.question(
                self, 
                "Dossier existant",
                f"Le dossier '{output_dir}' existe déjà. Voulez-vous l'écraser ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        self.worker = ProspectWorker(address, radius_km, output_dir)
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
            # Phase indéterminée
            self.progress.setRange(0, 0)
            self.progress.setFormat(msg)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
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
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Terminé")


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
