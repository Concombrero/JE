"""Module de logging pour le projet"""

import os
from datetime import datetime


class Logger:
    def __init__(self, log_path: str):
        self.log_file = log_path
        self.ensure_log_file_exists()
    
    def ensure_log_file_exists(self):
        """Crée le fichier de log s'il n'existe pas"""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Log démarré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    def log(self, message: str, level: str = "INFO"):
        """Écrit uniquement dans le fichier de log"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] [{level}] {message}\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message)
        self._trim_log()

    def console(self, message: str, level: str = "INFO"):
        """Affiche uniquement dans la console"""
        prefix = {
            "SUCCESS": "[OK]",
            "ERROR": "[ERREUR]",
            "PROGRESS": "[...]",
            "WARNING": "[ATTENTION]",
            "INFO": "[INFO]",
            "DEBUG": "[DEBUG]"
        }.get(level, "")
        
        if prefix:
            print(f"{prefix} {message}")
        else:
            print(message)
        
    def both(self, message: str, level: str = "INFO"):
        """Affiche dans la console ET écrit dans le log"""
        self.console(message, level)
        self.log(message, level)

    def _trim_log(self):
        """Conserve uniquement les 500 dernières lignes du log"""
        try:
            with open(self.log_file, 'r+', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) > 500:
                    f.seek(0)
                    f.writelines(lines[-500:])
                    f.truncate()
        except Exception:
            pass
