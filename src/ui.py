#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface graphique Qt pour la prospection immobilière
Combine les workflows src_1 (Pages Jaunes) et src_2 (Entreprises)
"""

import os
import sys
import json
import webbrowser
from typing import Optional, List

from PySide6.QtCore import Qt, QThread, Signal, Slot, QUrl
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QDoubleSpinBox, QPushButton, QProgressBar,
    QMessageBox, QTabWidget, QFileDialog, QComboBox, QGroupBox,
    QFormLayout, QTextEdit, QSplitter, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QSizePolicy, QScrollArea, QSpacerItem,
    QMenuBar, QMenu
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QFont, QIcon, QAction

# Import des modules du projet
from logger import Logger
from tools import Address, Street
from address_processor import AddressProcessor
from scrapper_pj import ScrapperPagesJaunes
from entreprises import EntrepriseSearcher
from fusion import (
    fuse_results, save_fused_csv, load_fused_csv, fused_to_map_features,
    filter_results_by_zone_and_interest, save_filtered_results
)
from map_generator import build_map_html, save_map_html


# ==================== WORKER THREADS ====================

class WorkerSignals:
    """Signaux communs pour les workers"""
    pass


class CompleteWorkflowWorker(QThread):
    """Worker pour le workflow complet"""
    progress = Signal(int, int, str)  # current, total, message
    log_message = Signal(str, str)     # message, level
    map_ready = Signal(str)            # html content
    finished_success = Signal(str)     # output_dir
    error = Signal(str, str)           # title, details
    
    # Poids des étapes pour la progression (total = 100%)
    # Étape 1: Géocodage (2%)
    # Étape 2: Recherche rues (3%)
    # Étape 3: Scrapping PJ (50%)
    # Étape 4: Recherche entreprises (35%)
    # Étape 5: Fusion (3%)
    # Étape 6: Filtrage (2%)
    # Étape 7: Carte (5%)
    STEP_WEIGHTS = {
        'geocoding': 2,
        'streets': 3,
        'pj_scrapping': 50,
        'entreprises': 35,
        'fusion': 3,
        'filtering': 2,
        'map': 5
    }
    
    def __init__(self, address: Address, radius_km: float, output_dir: str, parent=None):
        super().__init__(parent)
        self.address = address
        self.radius_km = radius_km
        self.output_dir = output_dir
        self._cancelled = False
        self._current_progress = 0
    
    def cancel(self):
        self._cancelled = True
    
    def _emit_progress(self, step: str, sub_progress: float, message: str):
        """Émet la progression globale basée sur l'étape et la sous-progression"""
        # Calculer le début de cette étape
        step_order = ['geocoding', 'streets', 'pj_scrapping', 'entreprises', 'fusion', 'filtering', 'map']
        step_start = sum(self.STEP_WEIGHTS[s] for s in step_order[:step_order.index(step)])
        step_weight = self.STEP_WEIGHTS[step]
        
        # Progression globale = début de l'étape + (sous-progression * poids de l'étape)
        global_progress = step_start + (sub_progress * step_weight)
        self._current_progress = int(global_progress)
        self.progress.emit(self._current_progress, 100, message)
    
    def run(self):
        try:
            # Logger personnalisé qui émet des signaux
            logger = SignalLogger(self.output_dir, self.log_message)
            
            # Étape 1: Récupération des coordonnées (2%)
            self._emit_progress('geocoding', 0, "Etape 1/7 : Recuperation des coordonnees...")
            
            address_processor = AddressProcessor()
            coords = address_processor.address_to_coordinates(self.address, logger)
            
            if not coords:
                self.error.emit("Erreur de géocodage", "Impossible de géocoder l'adresse.")
                return
            
            self._emit_progress('geocoding', 1.0, "Coordonnees recuperees")
            
            if self._cancelled:
                return
            
            # Étape 2: Recherche des rues (3%)
            self._emit_progress('streets', 0, "Etape 2/7 : Recherche des rues dans la zone...")
            
            dir_street = os.path.join(self.output_dir, 'streets')
            os.makedirs(dir_street, exist_ok=True)
            
            address_processor.get_streets_in_area(
                center_lat=coords['latitude'],
                center_lon=coords['longitude'],
                radius_km=self.radius_km,
                logger=logger,
                dir_street=dir_street
            )
            
            if self._cancelled:
                return
            
            # Charger les rues
            streets = address_processor.load_all_streets_from_dir(dir_street, logger)
            
            if not streets:
                self.error.emit("Aucune rue", "Aucune rue trouvée dans la zone.")
                return
            
            total_streets = len(streets)
            self._emit_progress('streets', 1.0, f"{total_streets} rues trouvees")
            
            # Étape 3: Scrapping Pages Jaunes (50%)
            self._emit_progress('pj_scrapping', 0, f"Etape 3/7 : Scrapping Pages Jaunes (0/{total_streets})...")
            
            scrapper = ScrapperPagesJaunes()
            pj_results = []
            
            try:
                for i, street in enumerate(streets):
                    if self._cancelled:
                        break
                    sub_progress = (i + 1) / total_streets
                    self._emit_progress('pj_scrapping', sub_progress, f"Etape 3/7 : PJ ({i + 1}/{total_streets}) - {street['name']}")
                    results = scrapper.process_street(street, logger, self.output_dir)
                    pj_results.extend(results)
            finally:
                scrapper.close_browser()
            
            if self._cancelled:
                return
            
            # Étape 4: Recherche entreprises (35%)
            # Cette étape combine:
            # - Recherche d'entreprises OSM autour de chaque adresse
            # - Enrichissement des résultats PJ avec données entreprises
            self._emit_progress('entreprises', 0, f"Etape 4/7 : Enrichissement entreprises...")
            
            entreprise_searcher = EntrepriseSearcher()
            entreprise_results = []
            
            # 4a: Enrichir les résultats PJ (50% de l'étape)
            if pj_results:
                self._emit_progress('entreprises', 0, f"Etape 4/7 : Enrichissement PJ (0/{len(pj_results)})...")
                pj_enriched = entreprise_searcher.process_pj_results(pj_results, logger)
                entreprise_results.extend(pj_enriched)
                self._emit_progress('entreprises', 0.5, f"Etape 4/7 : {len(pj_enriched)} entreprises depuis PJ")
            
            # 4b: Recherche OSM par rue (50% de l'étape)
            # Note: Optionnel car peut être long et redondant avec PJ
            # On peut commenter cette partie si trop lent
            # for i, street in enumerate(streets):
            #     if self._cancelled:
            #         break
            #     sub_progress = 0.5 + (0.5 * (i + 1) / total_streets)
            #     self._emit_progress('entreprises', sub_progress, f"Etape 4/7 : OSM ({i + 1}/{total_streets}) - {street['name']}")
            #     results = entreprise_searcher.process_street(street, logger)
            #     entreprise_results.extend(results)
            
            self._emit_progress('entreprises', 1.0, f"Etape 4/7 : {len(entreprise_results)} entreprises enrichies")
            
            if self._cancelled:
                return
            
            # Étape 5: Fusion (3%)
            self._emit_progress('fusion', 0, "Etape 5/7 : Fusion des resultats...")
            
            fused_data = fuse_results(pj_results, entreprise_results, logger)
            
            self._emit_progress('fusion', 1.0, "Fusion terminee")
            
            # Étape 6: Filtrage par zone et intérêt (2%)
            self._emit_progress('filtering', 0, "Etape 6/7 : Verification et filtrage des resultats...")
            
            in_zone, out_zone_interesting, out_zone_excluded = filter_results_by_zone_and_interest(
                fused_data,
                center_lat=coords['latitude'],
                center_lon=coords['longitude'],
                radius_km=self.radius_km,
                logger=logger
            )
            
            # Sauvegarder les résultats filtrés
            final_results = save_filtered_results(
                in_zone, out_zone_interesting, out_zone_excluded,
                self.output_dir, logger
            )
            
            self._emit_progress('filtering', 1.0, "Filtrage termine")
            
            # Étape 7: Carte (5%)
            self._emit_progress('map', 0, "Etape 7/7 : Generation de la carte...")
            
            features = fused_to_map_features(final_results)
            
            if features:
                radius_m = int(self.radius_km * 1000)
                html = build_map_html(
                    center_lat=coords['latitude'],
                    center_lon=coords['longitude'],
                    radius_m=radius_m,
                    features=features,
                    title=f"Prospection - {self.address['ville']}"
                )
                
                # Sauvegarder la carte
                map_file = os.path.join(self.output_dir, 'carte.html')
                with open(map_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                
                self.map_ready.emit(html)
            
            self._emit_progress('map', 1.0, "Recherche terminee avec succes !")
            
            self.finished_success.emit(self.output_dir)
            
        except Exception as e:
            import traceback
            self.error.emit("Erreur", f"{e}\n\n{traceback.format_exc()}")


class FromFolderWorker(QThread):
    """Worker pour reprendre depuis un dossier"""
    progress = Signal(int, int, str)
    log_message = Signal(str, str)
    map_ready = Signal(str)
    finished_success = Signal(str)
    error = Signal(str, str)
    
    # Poids des étapes pour la progression (total = 100%)
    # Étape 1: Chargement rues (5%)
    # Étape 2: Scrapping PJ (50%)
    # Étape 3: Recherche entreprises (35%)
    # Étape 4: Fusion (3%)
    # Étape 5: Filtrage (2%)
    # Étape 6: Carte (5%)
    STEP_WEIGHTS = {
        'loading': 5,
        'pj_scrapping': 50,
        'entreprises': 35,
        'fusion': 3,
        'filtering': 2,
        'map': 5
    }
    
    def __init__(self, folder_path: str, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self._cancelled = False
        self._current_progress = 0
    
    def cancel(self):
        self._cancelled = True
    
    def _emit_progress(self, step: str, sub_progress: float, message: str):
        """Émet la progression globale basée sur l'étape et la sous-progression"""
        step_order = ['loading', 'pj_scrapping', 'entreprises', 'fusion', 'filtering', 'map']
        step_start = sum(self.STEP_WEIGHTS[s] for s in step_order[:step_order.index(step)])
        step_weight = self.STEP_WEIGHTS[step]
        
        global_progress = step_start + (sub_progress * step_weight)
        self._current_progress = int(global_progress)
        self.progress.emit(self._current_progress, 100, message)
    
    def run(self):
        try:
            logger = SignalLogger(self.folder_path, self.log_message)
            
            # Étape 1: Chargement des rues (5%)
            self._emit_progress('loading', 0, "Etape 1/6 : Chargement des rues...")
            
            dir_street = os.path.join(self.folder_path, 'streets')
            
            if not os.path.exists(dir_street):
                self.error.emit("Erreur", f"Pas de dossier 'streets' dans {self.folder_path}")
                return
            
            address_processor = AddressProcessor()
            streets = address_processor.load_all_streets_from_dir(dir_street, logger)
            
            if not streets:
                self.error.emit("Erreur", "Aucune rue trouvée dans le dossier.")
                return
            
            total_streets = len(streets)
            
            # Trouver le centre
            center_lat, center_lon = None, None
            for street in streets:
                if street.get("numbers"):
                    geo = address_processor.address_to_coordinates({
                        "numero": street['numbers'][0],
                        "voie": street['name'],
                        "code_postal": street['postal_code'],
                        "ville": street['city']
                    }, logger)
                    if geo:
                        center_lat = geo['latitude']
                        center_lon = geo['longitude']
                        break
            
            self._emit_progress('loading', 1.0, f"{total_streets} rues chargees")
            
            # Étape 2: Scrapping PJ (50%)
            self._emit_progress('pj_scrapping', 0, f"Etape 2/6 : Scrapping Pages Jaunes (0/{total_streets})...")
            
            scrapper = ScrapperPagesJaunes()
            pj_results = []
            
            try:
                for i, street in enumerate(streets):
                    if self._cancelled:
                        break
                    sub_progress = (i + 1) / total_streets
                    self._emit_progress('pj_scrapping', sub_progress, f"Etape 2/6 : PJ ({i + 1}/{total_streets}) - {street['name']}")
                    results = scrapper.process_street(street, logger, self.folder_path)
                    pj_results.extend(results)
            finally:
                scrapper.close_browser()
            
            if self._cancelled:
                return
            
            # Étape 3: Entreprises (35%)
            # Cette étape enrichit les résultats PJ avec données entreprises
            self._emit_progress('entreprises', 0, f"Etape 3/6 : Enrichissement entreprises...")
            
            entreprise_searcher = EntrepriseSearcher()
            entreprise_results = []
            
            # Enrichir les résultats PJ
            if pj_results:
                self._emit_progress('entreprises', 0, f"Etape 3/6 : Enrichissement PJ (0/{len(pj_results)})...")
                pj_enriched = entreprise_searcher.process_pj_results(pj_results, logger)
                entreprise_results.extend(pj_enriched)
                self._emit_progress('entreprises', 1.0, f"Etape 3/6 : {len(pj_enriched)} entreprises depuis PJ")
            
            if self._cancelled:
                return
            
            # Étape 4: Fusion (3%)
            self._emit_progress('fusion', 0, "Etape 4/6 : Fusion des resultats...")
            
            fused_data = fuse_results(pj_results, entreprise_results, logger)
            
            self._emit_progress('fusion', 1.0, "Fusion terminee")
            
            # Étape 5: Filtrage par zone et intérêt (2%)
            if center_lat and center_lon:
                self._emit_progress('filtering', 0, "Etape 5/6 : Verification et filtrage des resultats...")
                
                # Estimer le rayon basé sur les rues trouvées
                radius_km = 0.5  # Par défaut
                
                in_zone, out_zone_interesting, out_zone_excluded = filter_results_by_zone_and_interest(
                    fused_data,
                    center_lat=center_lat,
                    center_lon=center_lon,
                    radius_km=radius_km,
                    logger=logger
                )
                
                final_results = save_filtered_results(
                    in_zone, out_zone_interesting, out_zone_excluded,
                    self.folder_path, logger
                )
            else:
                # Pas de coordonnées centre, sauvegarder tout
                fused_csv = os.path.join(self.folder_path, 'resultats_fusionnes.csv')
                save_fused_csv(fused_data, fused_csv, logger)
                final_results = fused_data
            
            self._emit_progress('filtering', 1.0, "Filtrage termine")
            
            # Étape 6: Carte (5%)
            if center_lat and center_lon:
                self._emit_progress('map', 0, "Etape 6/6 : Generation de la carte...")
                features = fused_to_map_features(final_results)
                if features:
                    html = build_map_html(
                        center_lat=center_lat,
                        center_lon=center_lon,
                        radius_m=500,
                        features=features,
                        title="Prospection"
                    )
                    
                    map_file = os.path.join(self.folder_path, 'carte.html')
                    with open(map_file, 'w', encoding='utf-8') as f:
                        f.write(html)
                    
                    self.map_ready.emit(html)
            
            self._emit_progress('map', 1.0, "Recherche terminee avec succes !")
            
            self.finished_success.emit(self.folder_path)
            
        except Exception as e:
            import traceback
            self.error.emit("Erreur", f"{e}\n\n{traceback.format_exc()}")


class SignalLogger(Logger):
    """Logger qui émet des signaux Qt en plus du fichier"""
    def __init__(self, output_dir: str, signal):
        super().__init__(os.path.join(output_dir, 'log.txt'))
        self.signal = signal
    
    def console(self, message: str, level: str = "INFO"):
        # Émet seulement le signal, pas d'appel au parent pour éviter les doublons
        self.signal.emit(message, level)
    
    def both(self, message: str, level: str = "INFO"):
        # Écrit dans le fichier log
        self.log(message, level)
        # Émet le signal pour l'UI
        self.signal.emit(message, level)


# ==================== WIDGETS ====================

class AddressForm(QGroupBox):
    """Formulaire de saisie d'adresse"""
    
    def __init__(self, parent=None):
        super().__init__("Adresse de départ", parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QFormLayout(self)
        
        self.numero_edit = QLineEdit()
        self.numero_edit.setPlaceholderText("Ex: 10")
        layout.addRow("Numéro:", self.numero_edit)
        
        self.voie_edit = QLineEdit()
        self.voie_edit.setPlaceholderText("Ex: Rue de la Paix")
        layout.addRow("Voie:", self.voie_edit)
        
        self.code_postal_edit = QLineEdit()
        self.code_postal_edit.setPlaceholderText("Ex: 75002")
        self.code_postal_edit.setMaxLength(5)
        layout.addRow("Code postal:", self.code_postal_edit)
        
        self.ville_edit = QLineEdit()
        self.ville_edit.setPlaceholderText("Ex: Paris")
        layout.addRow("Ville:", self.ville_edit)
    
    def get_address(self) -> Optional[Address]:
        """Retourne l'adresse saisie ou None si invalide"""
        numero = self.numero_edit.text().strip()
        voie = self.voie_edit.text().strip()
        code_postal = self.code_postal_edit.text().strip()
        ville = self.ville_edit.text().strip()
        
        if not all([numero, voie, code_postal, ville]):
            return None
        
        return {
            "numero": numero,
            "voie": voie,
            "code_postal": code_postal,
            "ville": ville
        }
    
    def clear(self):
        self.numero_edit.clear()
        self.voie_edit.clear()
        self.code_postal_edit.clear()
        self.ville_edit.clear()


class SearchParamsForm(QGroupBox):
    """Formulaire des paramètres de recherche"""
    
    def __init__(self, parent=None):
        super().__init__("Paramètres", parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QFormLayout(self)
        
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setSuffix(" km")
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSingleStep(0.1)
        self.radius_spin.setMinimum(0.1)
        self.radius_spin.setMaximum(10.0)
        self.radius_spin.setValue(0.5)
        layout.addRow("Rayon:", self.radius_spin)
        
        # Dossier de sortie
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Nom de la recherche")
        folder_layout.addWidget(self.folder_edit)
        
        layout.addRow("Dossier:", folder_layout)
    
    def get_radius(self) -> float:
        return self.radius_spin.value()
    
    def get_folder_name(self) -> str:
        return self.folder_edit.text().strip()


class LogViewer(QTextEdit):
    """Widget d'affichage des logs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Monospace", 9))
        self.setMaximumHeight(150)
    
    @Slot(str, str)
    def append_log(self, message: str, level: str):
        color = {
            "SUCCESS": "#22c55e",
            "ERROR": "#ef4444",
            "WARNING": "#f59e0b",
            "PROGRESS": "#3b82f6",
            "INFO": "#6b7280"
        }.get(level, "#6b7280")
        
        self.append(f'<span style="color: {color}">{message}</span>')
        # Auto-scroll
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


# ==================== PAGES ====================

class CompletePage(QWidget):
    """Page pour le workflow complet"""
    
    map_ready = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Titre de la page
        header = QLabel("Nouvelle recherche")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1e293b;")
        layout.addWidget(header)
        
        subtitle = QLabel("Lancez une prospection a partir d'une adresse de depart")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(subtitle)
        
        # Formulaire d'adresse
        self.address_form = AddressForm()
        layout.addWidget(self.address_form)
        
        # Paramètres
        self.params_form = SearchParamsForm()
        layout.addWidget(self.params_form)
        
        # Boutons d'action
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.start_btn = QPushButton("Lancer la recherche")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                padding: 12px 25px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_workflow)
        btn_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                padding: 12px 25px;
                font-size: 14px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton:disabled {
                color: #cbd5e1;
            }
        """)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_workflow)
        btn_layout.addWidget(self.cancel_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Progress section
        progress_group = QGroupBox("Progression")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMinimumHeight(10)
        self.progress.setMaximumHeight(10)
        progress_layout.addWidget(self.progress)
        
        self.status_label = QLabel("En attente...")
        self.status_label.setStyleSheet("color: #64748b; font-size: 13px;")
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # Logs
        log_group = QGroupBox("Journal")
        log_layout = QVBoxLayout(log_group)
        self.log_viewer = LogViewer()
        self.log_viewer.setMinimumHeight(150)
        self.log_viewer.setMaximumHeight(250)
        log_layout.addWidget(self.log_viewer)
        layout.addWidget(log_group)
        
        layout.addStretch()
    
    @Slot()
    def start_workflow(self):
        address = self.address_form.get_address()
        if not address:
            QMessageBox.warning(self, "Erreur", "Veuillez remplir tous les champs de l'adresse.")
            return
        
        folder_name = self.params_form.get_folder_name()
        if not folder_name:
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un nom de dossier.")
            return
        
        output_dir = os.path.join('output', folder_name)
        
        if os.path.exists(output_dir):
            reply = QMessageBox.question(
                self, "Dossier existant",
                f"Le dossier '{folder_name}' existe déjà. Continuer ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        os.makedirs(output_dir, exist_ok=True)
        
        radius = self.params_form.get_radius()
        
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_viewer.clear()
        self.progress.setRange(0, 0)
        
        self.worker = CompleteWorkflowWorker(address, radius, output_dir)
        self.worker.progress.connect(self.on_progress)
        self.worker.log_message.connect(self.log_viewer.append_log)
        self.worker.map_ready.connect(self.on_map_ready)
        self.worker.finished_success.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    @Slot()
    def cancel_workflow(self):
        if self.worker:
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)
    
    @Slot(int, int, str)
    def on_progress(self, current: int, total: int, message: str):
        if total <= 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.status_label.setText(message)
    
    @Slot(str)
    def on_map_ready(self, html: str):
        self.map_ready.emit(html)
    
    @Slot(str)
    def on_finished(self, output_dir: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText("Recherche terminee avec succes")
        self.status_label.setStyleSheet("color: #22c55e; font-size: 13px; font-weight: bold;")
        
        QMessageBox.information(
            self, "Succès",
            f"Recherche terminée!\n\nDossier: {output_dir}"
        )
    
    @Slot(str, str)
    def on_error(self, title: str, details: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("Une erreur s'est produite")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold;")
        
        QMessageBox.critical(self, title, details)


class FromFolderPage(QWidget):
    """Page pour reprendre depuis un dossier"""
    
    map_ready = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Titre de la page
        header = QLabel("Reprendre depuis un dossier")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #1e293b;")
        layout.addWidget(header)
        
        subtitle = QLabel("Continuez le traitement a partir d'un dossier de rues existant")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(subtitle)
        
        # Sélection du dossier
        folder_group = QGroupBox("Selection du dossier")
        folder_layout = QVBoxLayout(folder_group)
        
        # Liste des dossiers disponibles
        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(180)
        self.folder_list.setMaximumHeight(250)
        self.refresh_folder_list()
        folder_layout.addWidget(self.folder_list)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        refresh_btn = QPushButton("Rafraichir")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                padding: 8px 15px;
                border-radius: 6px;
                border: 1px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_folder_list)
        btn_row.addWidget(refresh_btn)
        
        browse_btn = QPushButton("Parcourir...")
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                padding: 8px 15px;
                border-radius: 6px;
                border: 1px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        browse_btn.clicked.connect(self.browse_folder)
        btn_row.addWidget(browse_btn)
        
        btn_row.addStretch()
        folder_layout.addLayout(btn_row)
        
        layout.addWidget(folder_group)
        
        # Boutons d'action
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        self.start_btn = QPushButton("Lancer le traitement")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                padding: 12px 25px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #047857;
            }
            QPushButton:pressed {
                background-color: #065f46;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
        """)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_processing)
        action_layout.addWidget(self.start_btn)
        
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                padding: 12px 25px;
                font-size: 14px;
                border-radius: 8px;
                border: 1px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
            QPushButton:disabled {
                color: #cbd5e1;
            }
        """)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        action_layout.addWidget(self.cancel_btn)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # Progress section
        progress_group = QGroupBox("Progression")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMinimumHeight(10)
        self.progress.setMaximumHeight(10)
        progress_layout.addWidget(self.progress)
        
        self.status_label = QLabel("En attente de sélection...")
        self.status_label.setStyleSheet("color: #64748b; font-size: 13px;")
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # Logs
        log_group = QGroupBox("Journal")
        log_layout = QVBoxLayout(log_group)
        self.log_viewer = LogViewer()
        self.log_viewer.setMinimumHeight(120)
        self.log_viewer.setMaximumHeight(200)
        log_layout.addWidget(self.log_viewer)
        layout.addWidget(log_group)
        
        layout.addStretch()
    
    def refresh_folder_list(self):
        self.folder_list.clear()
        
        output_dir = 'output'
        if not os.path.exists(output_dir):
            return
        
        for folder in sorted(os.listdir(output_dir)):
            folder_path = os.path.join(output_dir, folder)
            if not os.path.isdir(folder_path):
                continue
            
            streets_dir = os.path.join(folder_path, 'streets')
            has_streets = os.path.exists(streets_dir) and any(
                f.endswith('.json') for f in os.listdir(streets_dir)
            ) if os.path.exists(streets_dir) else False
            
            status = "✓" if has_streets else "○"
            item = QListWidgetItem(f"{status} {folder}")
            item.setData(Qt.UserRole, folder_path)
            self.folder_list.addItem(item)
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Sélectionner un dossier",
            'output' if os.path.exists('output') else '.'
        )
        if folder:
            # Ajouter à la liste
            item = QListWidgetItem(f"> {os.path.basename(folder)}")
            item.setData(Qt.UserRole, folder)
            self.folder_list.addItem(item)
            self.folder_list.setCurrentItem(item)
    
    @Slot()
    def start_processing(self):
        current = self.folder_list.currentItem()
        if not current:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un dossier.")
            return
        
        folder_path = current.data(Qt.UserRole)
        
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_viewer.clear()
        self.progress.setRange(0, 0)
        
        self.worker = FromFolderWorker(folder_path)
        self.worker.progress.connect(self.on_progress)
        self.worker.log_message.connect(self.log_viewer.append_log)
        self.worker.map_ready.connect(self.on_map_ready)
        self.worker.finished_success.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    @Slot()
    def cancel_processing(self):
        if self.worker:
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)
    
    @Slot(int, int, str)
    def on_progress(self, current: int, total: int, message: str):
        if total <= 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
        self.status_label.setText(message)
    
    @Slot(str)
    def on_map_ready(self, html: str):
        self.map_ready.emit(html)
    
    @Slot(str)
    def on_finished(self, output_dir: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText("Traitement termine avec succes")
        self.status_label.setStyleSheet("color: #22c55e; font-size: 13px; font-weight: bold;")
        
        QMessageBox.information(self, "Succes", f"Traitement termine!\n\nDossier: {output_dir}")
    
    @Slot(str, str)
    def on_error(self, title: str, details: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("Une erreur s'est produite")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold;")
        
        QMessageBox.critical(self, title, details)


class MapPage(QWidget):
    """Page pour afficher la carte"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("mapToolbar")
        toolbar.setStyleSheet("""
            #mapToolbar {
                background-color: white;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 10, 15, 10)
        
        title = QLabel("Carte interactive")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e293b;")
        toolbar_layout.addWidget(title)
        
        toolbar_layout.addStretch()
        
        open_file_btn = QPushButton("Ouvrir un fichier")
        open_file_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                padding: 8px 15px;
                border-radius: 6px;
                border: 1px solid #e2e8f0;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        open_file_btn.setCursor(Qt.PointingHandCursor)
        open_file_btn.clicked.connect(self.open_file)
        toolbar_layout.addWidget(open_file_btn)
        
        open_browser_btn = QPushButton("Ouvrir dans le navigateur")
        open_browser_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        open_browser_btn.setCursor(Qt.PointingHandCursor)
        open_browser_btn.clicked.connect(self.open_in_browser)
        toolbar_layout.addWidget(open_browser_btn)
        
        layout.addWidget(toolbar)
        
        # WebView
        self.web_view = QWebEngineView()
        self.web_view.setHtml(self.get_placeholder_html())
        layout.addWidget(self.web_view)
    
    def get_placeholder_html(self) -> str:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                * { box-sizing: border-box; margin: 0; padding: 0; }
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 20px;
                }
                .container {
                    text-align: center;
                    color: white;
                    max-width: 400px;
                }
                .icon { 
                    font-size: 80px; 
                    margin-bottom: 25px;
                    animation: float 3s ease-in-out infinite;
                }
                @keyframes float {
                    0%, 100% { transform: translateY(0px); }
                    50% { transform: translateY(-10px); }
                }
                h1 { 
                    margin: 0 0 15px 0; 
                    font-weight: 600;
                    font-size: 28px;
                }
                p { 
                    opacity: 0.85;
                    font-size: 16px;
                    line-height: 1.6;
                }
                .hint {
                    margin-top: 30px;
                    padding: 15px 20px;
                    background: rgba(255,255,255,0.15);
                    border-radius: 12px;
                    font-size: 14px;
                }
                .hint strong {
                    display: block;
                    margin-bottom: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">MAP</div>
                <h1>Carte interactive</h1>
                <p>Lancez une recherche ou ouvrez un fichier existant pour visualiser les resultats sur la carte.</p>
                <div class="hint">
                    <strong>Astuce</strong>
                    Utilisez Ctrl+3 ou le menu Vue pour acceder rapidement a cette page
                </div>
            </div>
        </body>
        </html>
        """
    
    @Slot(str)
    def display_map(self, html: str):
        self.web_view.setHtml(html)
    
    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier",
            'output' if os.path.exists('output') else '.',
            "Fichiers carte (*.html);;Fichiers CSV (*.csv)"
        )
        
        if not file_path:
            return
        
        if file_path.endswith('.html'):
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.web_view.setHtml(html)
            self.current_file = file_path
        
        elif file_path.endswith('.csv'):
            self.load_from_csv(file_path)
    
    def load_from_csv(self, csv_file: str):
        """Génère une carte depuis un CSV"""
        from fusion import load_fused_csv
        from map_generator import build_map_html
        
        class DummyLogger:
            def log(self, *args, **kwargs): pass
            def both(self, *args, **kwargs): pass
            def console(self, *args, **kwargs): pass
        
        logger = DummyLogger()
        data = load_fused_csv(csv_file, logger)
        
        if not data:
            QMessageBox.warning(self, "Erreur", "Aucune donnée dans le CSV.")
            return
        
        valid_coords = [
            (d["latitude"], d["longitude"]) 
            for d in data 
            if d.get("latitude") and d.get("longitude")
        ]
        
        if not valid_coords:
            QMessageBox.warning(self, "Erreur", "Aucune coordonnée valide.")
            return
        
        center_lat = sum(c[0] for c in valid_coords) / len(valid_coords)
        center_lon = sum(c[1] for c in valid_coords) / len(valid_coords)
        
        features = [d for d in data if d.get("latitude") and d.get("longitude")]
        
        html = build_map_html(
            center_lat=center_lat,
            center_lon=center_lon,
            radius_m=500,
            features=features,
            title="Carte depuis CSV"
        )
        
        self.web_view.setHtml(html)
        
        # Sauvegarder
        map_file = csv_file.replace('.csv', '_carte.html')
        with open(map_file, 'w', encoding='utf-8') as f:
            f.write(html)
        self.current_file = map_file
    
    def open_in_browser(self):
        if self.current_file and os.path.exists(self.current_file):
            webbrowser.open('file://' + os.path.abspath(self.current_file))
        else:
            QMessageBox.information(
                self, "Info",
                "Aucun fichier carte à ouvrir. Lancez d'abord une recherche."
            )


# ==================== MAIN WINDOW ====================

class NavButton(QPushButton):
    """Bouton de navigation stylisé"""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setMinimumHeight(45)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application avec navigation par menu"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prospection Immobiliere")
        self.setMinimumSize(800, 600)
        self.setup_menu_bar()
        self.setup_ui()
    
    def setup_menu_bar(self):
        """Configure la barre de menu"""
        menubar = self.menuBar()
        
        # Menu Fichier
        file_menu = menubar.addMenu("&Fichier")
        
        open_map_action = QAction("Ouvrir une carte...", self)
        open_map_action.setShortcut("Ctrl+O")
        open_map_action.triggered.connect(self.open_map_file)
        file_menu.addAction(open_map_action)
        
        open_csv_action = QAction("Ouvrir un CSV...", self)
        open_csv_action.triggered.connect(self.open_csv_file)
        file_menu.addAction(open_csv_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Menu Vue
        view_menu = menubar.addMenu("&Vue")
        
        self.view_actions = []
        
        new_search_action = QAction("Nouvelle recherche", self)
        new_search_action.setShortcut("Ctrl+1")
        new_search_action.triggered.connect(lambda: self.switch_page(0))
        view_menu.addAction(new_search_action)
        self.view_actions.append(new_search_action)
        
        folder_action = QAction("Depuis un dossier", self)
        folder_action.setShortcut("Ctrl+2")
        folder_action.triggered.connect(lambda: self.switch_page(1))
        view_menu.addAction(folder_action)
        self.view_actions.append(folder_action)
        
        map_action = QAction("Carte interactive", self)
        map_action.setShortcut("Ctrl+3")
        map_action.triggered.connect(lambda: self.switch_page(2))
        view_menu.addAction(map_action)
        self.view_actions.append(map_action)
    
    def setup_ui(self):
        # Widget central
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Panel de navigation à gauche
        nav_panel = QFrame()
        nav_panel.setObjectName("navPanel")
        nav_panel.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(10, 15, 10, 15)
        nav_layout.setSpacing(5)
        
        # Titre dans la nav
        nav_title = QLabel("Navigation")
        nav_title.setObjectName("navTitle")
        nav_title.setAlignment(Qt.AlignCenter)
        nav_layout.addWidget(nav_title)
        
        nav_layout.addSpacing(15)
        
        # Boutons de navigation
        self.nav_buttons = []
        
        self.btn_new_search = NavButton("Nouvelle recherche")
        self.btn_new_search.clicked.connect(lambda: self.switch_page(0))
        nav_layout.addWidget(self.btn_new_search)
        self.nav_buttons.append(self.btn_new_search)
        
        self.btn_from_folder = NavButton("Depuis dossier")
        self.btn_from_folder.clicked.connect(lambda: self.switch_page(1))
        nav_layout.addWidget(self.btn_from_folder)
        self.nav_buttons.append(self.btn_from_folder)
        
        self.btn_map = NavButton("Carte interactive")
        self.btn_map.clicked.connect(lambda: self.switch_page(2))
        nav_layout.addWidget(self.btn_map)
        self.nav_buttons.append(self.btn_map)
        
        nav_layout.addStretch()
        
        # Info version
        version_label = QLabel("v1.0")
        version_label.setObjectName("versionLabel")
        version_label.setAlignment(Qt.AlignCenter)
        nav_layout.addWidget(version_label)
        
        main_layout.addWidget(nav_panel)
        
        # Zone de contenu principale (pages empilées)
        self.stack = QStackedWidget()
        
        # Page 1: Nouvelle recherche (dans un scroll area)
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QFrame.NoFrame)
        self.complete_page = CompletePage()
        self.complete_page.map_ready.connect(self.on_map_ready)
        scroll1.setWidget(self.complete_page)
        self.stack.addWidget(scroll1)
        
        # Page 2: Depuis dossier (dans un scroll area)
        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setFrameShape(QFrame.NoFrame)
        self.folder_page = FromFolderPage()
        self.folder_page.map_ready.connect(self.on_map_ready)
        scroll2.setWidget(self.folder_page)
        self.stack.addWidget(scroll2)
        
        # Page 3: Carte
        self.map_page = MapPage()
        self.stack.addWidget(self.map_page)
        
        main_layout.addWidget(self.stack)
        
        # Sélectionner la première page par défaut
        self.switch_page(0)
        
        # Appliquer le style global
        self.apply_styles()
    
    def switch_page(self, index: int):
        """Change de page et met à jour les boutons de navigation"""
        self.stack.setCurrentIndex(index)
        
        # Mettre à jour l'état des boutons
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)


    def apply_styles(self):
        """Applique le style global de l'application"""
        self.setStyleSheet("""
            /* Style global */
            * {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            QMainWindow {
                background-color: #f1f5f9;
            }
            
            /* BARRE DE MENU - TOUJOURS NOIRE */
            QMenuBar {
                background-color: #000000 !important;
                color: white !important;
                padding: 4px;
                border: none;
            }
            
            QMenuBar::item {
                background-color: #000000 !important;
                color: white !important;
                padding: 8px 16px;
                margin: 0px 2px;
                border-radius: 4px;
            }
            
            QMenuBar::item:selected {
                background-color: #333333 !important;
                color: white !important;
            }
            
            QMenuBar::item:pressed {
                background-color: #1a1a1a !important;
                color: white !important;
            }
            
            /* Menus déroulants - NOIR */
            QMenu {
                background-color: #000000 !important;
                color: white !important;
                border: 1px solid #333333;
                padding: 5px;
            }
            
            QMenu::item {
                padding: 8px 30px 8px 20px;
                border-radius: 4px;
                background-color: #000000 !important;
                color: white !important;
            }
            
            QMenu::item:selected {
                background-color: #333333 !important;
                color: white !important;
            }
            
            QMenu::item:pressed {
                background-color: #1a1a1a !important;
                color: white !important;
            }
            
            /* FOND DES PAGES - GRIS CLAIR */
            QWidget {
                background-color: #f1f5f9;
            }
            
            /* CHAMPS DE SAISIE - Texte en noir */
            QLineEdit {
                color: #000000 !important;
                background-color: white;
            }
            
            QDoubleSpinBox {
                color: #000000 !important;
                background-color: white;
            }
            
            QComboBox {
                color: #000000 !important;
                background-color: white;
            }
            
            QSpinBox {
                color: #000000 !important;
                background-color: white;
            }
            
            /* Panel de navigation */
            #navPanel {
                background-color: #1e293b;
                border-right: 1px solid #cbd5e1;
            }
            
            #navTitle {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            #versionLabel {
                color: #64748b;
                font-size: 11px;
            }
            
            /* Boutons de navigation */
            QPushButton[checkable="true"] {
                background-color: transparent;
                border: none;
                text-align: left;
                padding: 12px 20px;
                color: #cbd5e1;
                font-size: 14px;
                font-weight: 500;
                border-radius: 8px;
            }
            
            QPushButton[checkable="true"]:checked {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
            }
            
            QPushButton[checkable="true"]:hover {
                background-color: rgba(59, 130, 246, 0.1);
                color: white;
            }
            
            /* GroupBox */
            QGroupBox {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 10px;
                padding: 20px 15px 15px 15px;
                font-weight: 600;
                color: #1e293b;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                padding: 0 8px;
                color: #1e293b;
                font-size: 14px;
            }
            
            /* Labels */
            QLabel {
                color: #334155;
                background-color: transparent;
            }
            
            /* LineEdit standard */
            QLineEdit {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background-color: white;
                font-size: 13px;
            }
            
            QLineEdit:focus {
                border: 1px solid #3b82f6;
                outline: none;
            }
            
            /* SpinBox */
            QDoubleSpinBox {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background-color: white;
                font-size: 13px;
            }
            
            QDoubleSpinBox:focus {
                border: 1px solid #3b82f6;
            }
            
            /* Boutons */
            QPushButton {
                background-color: #3b82f6;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            
            QPushButton:hover {
                background-color: #2563eb;
            }
            
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
            
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            
            /* Progress bar */
            QProgressBar {
                border: none;
                border-radius: 4px;
                text-align: center;
                background-color: #e2e8f0;
                height: 8px;
            }
            
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 4px;
            }
            
            /* Liste */
            QListWidget {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: white;
                outline: none;
            }
            
            QListWidget::item {
                padding: 12px 15px;
                border-bottom: 1px solid #f1f5f9;
                color: #334155;
            }
            
            QListWidget::item:last {
                border-bottom: none;
            }
            
            QListWidget::item:selected {
                background-color: #eff6ff;
                color: #1d4ed8;
            }
            
            QListWidget::item:hover {
                background-color: #f8fafc;
            }
            
            /* Scroll area */
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            
            QScrollBar:vertical {
                background-color: #f1f5f9;
                width: 10px;
                border-radius: 5px;
            }
            
            QScrollBar::handle:vertical {
                background-color: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #94a3b8;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            /* TextEdit (logs) */
            QTextEdit {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: #1e293b;
                color: #e2e8f0;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                padding: 10px;
            }
            
            /* Titres des pages - EN ROUGE VIF */
            #pageTitle {
                color: #ef4444 !important;
                font-size: 28px;
                font-weight: bold;
                background-color: transparent;
            }
        """)



    @Slot(str)
    def on_map_ready(self, html: str):
        """Affiche la carte et switch sur la page carte"""
        self.map_page.display_map(html)
        self.switch_page(2)
    
    def open_map_file(self):
        """Ouvre un fichier carte HTML"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir une carte",
            'output' if os.path.exists('output') else '.',
            "Fichiers HTML (*.html)"
        )
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            self.map_page.display_map(html)
            self.map_page.current_file = file_path
            self.switch_page(2)
    
    def open_csv_file(self):
        """Ouvre un fichier CSV et génère une carte"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un CSV",
            'output' if os.path.exists('output') else '.',
            "Fichiers CSV (*.csv)"
        )
        if file_path:
            self.map_page.load_from_csv(file_path)
            self.switch_page(2)


# ==================== MAIN ====================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Prospection Immobilière")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
