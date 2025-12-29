"""
Interface graphique PySide6 pour le workflow de prospection
Point d'entrée principal : ui_merge.py
"""
import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QMessageBox,
    QProgressBar, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont

from interface import Logger
from adr import AddressProcessor
from scrapper import ScrapperPageJaune


class WorkflowThread(QThread):
    """Thread pour exécuter le workflow sans bloquer l'UI"""
    log_signal = Signal(str, str)  # message, level
    finished_signal = Signal(bool, str)  # success, message
    
    def __init__(self, address, radius, output_dirpath):
        super().__init__()
        self.address = address
        self.radius = radius
        self.output_dirpath = output_dirpath
        
    def run(self):
        try:
            # Créer le logger personnalisé qui émet des signaux
            logger = UILogger(os.path.join(self.output_dirpath, 'log.txt'), self.log_signal)
            
            logger.both("Démarrage du programme", "INFO")
            
            # Initialiser les processeurs
            address_processor = AddressProcessor()
            scraper_pj = ScrapperPageJaune()
            
            # Récupération des coordonnées
            logger.console("Passage à la récupération des coordonnées de l'adresse.", "PROGRESS")
            coords = address_processor.address_to_coordinates(self.address, logger)
            logger.log(f"Coordonnées récupérées: {coords}", "DEBUG")
            logger.console(f"Coordonnées récupérées: {coords}", "SUCCESS")
            
            # Récupération des rues
            logger.console(f"Passage à la récupération des rues dans un rayon de {self.radius} km autour des coordonnées.", "PROGRESS")
            dir_street = os.path.join(self.output_dirpath, 'streets')
            os.makedirs(dir_street, exist_ok=True)
            
            address_processor.get_streets_in_area(
                center_lat=coords['latitude'],
                center_lon=coords['longitude'],
                radius_km=self.radius,
                logger=logger,
                dir_street=dir_street
            )
            
            # Traitement des rues
            logger.console("Traitement des rues...", "PROGRESS")
            for file in os.listdir(dir_street):
                if file.endswith('.json'):
                    file_path = os.path.join(dir_street, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        street = json.load(f)
                        logger.log(f"Traitement de la rue: {street}", "DEBUG")
                        
                        scraper_pj.process_street(
                            street=street,
                            logger=logger,
                            output_dir=self.output_dirpath
                        )
            
            logger.both("Programme terminé avec succès.", "SUCCESS")
            self.finished_signal.emit(True, "Programme terminé avec succès.")
            
        except Exception as e:
            error_msg = f"Une erreur s'est produite: {e}"
            self.log_signal.emit(error_msg, "ERROR")
            self.finished_signal.emit(False, error_msg)


class UILogger(Logger):
    """Logger personnalisé qui émet des signaux Qt"""
    
    def __init__(self, log_path, signal):
        super().__init__(log_path)
        self.signal = signal
    
    def console(self, message, level="INFO"):
        """Affiche dans la console et émet un signal"""
        self.signal.emit(message, level)
        self.clear_log()
    
    def both(self, message, level="INFO"):
        """Affiche dans la console ET écrit dans le log"""
        self.console(message, level)
        self.log(message, level)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workflow_thread = None
        self.init_ui()
        
    def init_ui(self):
        """Initialise l'interface utilisateur"""
        self.setWindowTitle("Logiciel de Prospection")
        self.setMinimumSize(800, 600)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Titre
        title = QLabel("Logiciel de Prospection")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # Section Adresse
        address_group = QGroupBox("Adresse")
        address_layout = QVBoxLayout()
        
        # Numéro
        numero_layout = QHBoxLayout()
        numero_layout.addWidget(QLabel("Numéro:"))
        self.numero_input = QLineEdit()
        self.numero_input.setPlaceholderText("Ex: 123")
        numero_layout.addWidget(self.numero_input)
        address_layout.addLayout(numero_layout)
        
        # Voie
        voie_layout = QHBoxLayout()
        voie_layout.addWidget(QLabel("Voie:"))
        self.voie_input = QLineEdit()
        self.voie_input.setPlaceholderText("Ex: Rue de la République")
        voie_layout.addWidget(self.voie_input)
        address_layout.addLayout(voie_layout)
        
        # Code postal
        cp_layout = QHBoxLayout()
        cp_layout.addWidget(QLabel("Code postal:"))
        self.cp_input = QLineEdit()
        self.cp_input.setPlaceholderText("Ex: 38000")
        cp_layout.addWidget(self.cp_input)
        address_layout.addLayout(cp_layout)
        
        # Ville
        ville_layout = QHBoxLayout()
        ville_layout.addWidget(QLabel("Ville:"))
        self.ville_input = QLineEdit()
        self.ville_input.setPlaceholderText("Ex: Grenoble")
        ville_layout.addWidget(self.ville_input)
        address_layout.addLayout(ville_layout)
        
        address_group.setLayout(address_layout)
        main_layout.addWidget(address_group)
        
        # Section Paramètres
        params_group = QGroupBox("Paramètres de recherche")
        params_layout = QVBoxLayout()
        
        # Rayon
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(QLabel("Rayon (km):"))
        self.radius_input = QLineEdit()
        self.radius_input.setPlaceholderText("Ex: 2.5")
        radius_layout.addWidget(self.radius_input)
        params_layout.addLayout(radius_layout)
        
        # Dossier de sortie
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Dossier de sortie:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setPlaceholderText("Cliquez sur Parcourir pour choisir un dossier...")
        output_layout.addWidget(self.output_dir_input)
        
        self.browse_button = QPushButton("Parcourir...")
        self.browse_button.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(self.browse_button)
        params_layout.addLayout(output_layout)
        
        params_group.setLayout(params_layout)
        main_layout.addWidget(params_group)
        
        # Bouton de lancement
        self.start_button = QPushButton("Lancer la recherche")
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.start_workflow)
        main_layout.addWidget(self.start_button)
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)  # Mode indéterminé
        main_layout.addWidget(self.progress_bar)
        
        # Console de log
        log_group = QGroupBox("Console")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
    
    def browse_output_directory(self):
        """Ouvre un dialogue pour sélectionner le dossier de sortie"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Sélectionner le dossier de sortie",
            os.path.expanduser("~"),  # Commence dans le dossier home de l'utilisateur
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if directory:
            self.output_dir_input.setText(directory)
        
    def validate_inputs(self):
        """Valide les entrées de l'utilisateur"""
        # Vérifier que tous les champs sont remplis
        if not self.numero_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un numéro.")
            return False
            
        if not self.voie_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un nom de voie.")
            return False
            
        if not self.cp_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un code postal.")
            return False
            
        if not self.ville_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer une ville.")
            return False
            
        if not self.radius_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer un rayon.")
            return False
            
        if not self.output_dir_input.text().strip():
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un dossier de sortie.")
            return False
        
        # Vérifier que le rayon est un nombre valide
        try:
            radius = float(self.radius_input.text())
            if radius <= 0:
                QMessageBox.warning(self, "Erreur", "Le rayon doit être supérieur à 0.")
                return False
        except ValueError:
            QMessageBox.warning(self, "Erreur", "Le rayon doit être un nombre valide.")
            return False
        
        # Vérifier que le dossier de sortie existe et est accessible
        output_dir = self.output_dir_input.text().strip()
        if not os.path.exists(output_dir):
            QMessageBox.warning(self, "Erreur", f"Le dossier '{output_dir}' n'existe pas.")
            return False
        
        if not os.access(output_dir, os.W_OK):
            QMessageBox.warning(self, "Erreur", f"Vous n'avez pas les permissions d'écriture sur le dossier '{output_dir}'.")
            return False
            
        return True
    
    def start_workflow(self):
        """Lance le workflow dans un thread séparé"""
        if not self.validate_inputs():
            return
        
        # Préparer les données
        address = {
            "numero": self.numero_input.text().strip(),
            "voie": self.voie_input.text().strip(),
            "code_postal": self.cp_input.text().strip(),
            "ville": self.ville_input.text().strip()
        }
        radius = float(self.radius_input.text())
        output_dirpath = self.output_dir_input.text().strip()
        
        # Le dossier de sortie existe déjà (vérifié dans validate_inputs)
        
        # Nettoyer la console
        self.log_text.clear()
        
        # Désactiver le bouton et afficher la barre de progression
        self.start_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        
        # Créer et lancer le thread
        self.workflow_thread = WorkflowThread(address, radius, output_dirpath)
        self.workflow_thread.log_signal.connect(self.append_log)
        self.workflow_thread.finished_signal.connect(self.workflow_finished)
        self.workflow_thread.start()
    
    @Slot(str, str)
    def append_log(self, message, level):
        """Ajoute un message au log"""
        if level == "SUCCESS":
            formatted = f"✅ {message}"
        elif level == "ERROR":
            formatted = f"❌ {message}"
        elif level == "PROGRESS":
            formatted = f"⏳ {message}"
        else:
            formatted = message
            
        self.log_text.append(formatted)
        # Scroll automatique vers le bas
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    @Slot(bool, str)
    def workflow_finished(self, success, message):
        """Appelé quand le workflow est terminé"""
        self.start_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Succès", message)
        else:
            QMessageBox.critical(self, "Erreur", message)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
