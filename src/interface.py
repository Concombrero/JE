import os
from datetime import datetime

class Logger:
    def __init__(self, log_path):
        self.log_file = log_path
        self.ensure_log_file_exists()
    
    def ensure_log_file_exists(self):
        """Crée le fichier de log s'il n'existe pas"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Log démarré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    def log(self, message, level="INFO"):
        """Écrit uniquement dans le fichier de log"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] [{level}] {message}\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message)
        self.clear_log() 

    def console(self, message, level="INFO"):
        """Affiche uniquement dans la console"""
        if level == "SUCCESS":
            print(f"✅ {message}")
        elif level == "ERROR":
            print(f"❌ {message}")
        elif level == "PROGRESS":
            print(f"⏳ {message}")
        else:
            print(message)
        self.clear_log() 
        
    def both(self, message, level="INFO"):
        """Affiche dans la console ET écrit dans le log"""
        self.console(message)
        self.log(message, level)
        self.clear_log() 

    def clear_log(self):
        """Conserve uniquement les 100 dernières lignes du log"""
        with open(self.log_file, 'r+', encoding='utf-8') as f:
            lines = f.readlines()
            # Conserve les 100 dernières lignes
            f.seek(0)
            f.writelines(lines[-100:])
            f.truncate()
