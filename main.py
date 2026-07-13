import os
import json
import urllib3
import requests
import time
from datetime import datetime
from requests_pkcs12 import Pkcs12Adapter

# Warnungen unterdrücken
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- KONFIGURATION ---
CERT_FILE = "certificate.p12"

def _load_cert_password():
    """Liest das Zertifikatspasswort aus der Umgebungsvariable, sonst aus der
    lokalen, nicht versionierten .env-Datei (Fallback für nicht-interaktive
    Shells, z. B. Cron oder Skript-Ausführung ohne geladenes .bashrc)."""
    password = os.environ.get("MOBILITHEK_CERT_PASSWORD")
    if password:
        return password
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("MOBILITHEK_CERT_PASSWORD="):
                    return line.strip().split("=", 1)[1]
    raise RuntimeError(
        "MOBILITHEK_CERT_PASSWORD ist weder als Umgebungsvariable noch in .env gesetzt."
    )

# Passwort ausschließlich aus Umgebungsvariable oder lokaler .env-Datei, kein Fallback im Code (Secret-Hygiene)
CERT_PASSWORD = _load_cert_password()

# Bereinigte Liste ohne die 0-Treffer-Leichen von m8mit
SUBSCRIPTIONS = {
    "EnBW_dyn": "983100920677924864",
    "EnBW_stat": "983100939883704320",
    "Tesla_dyn": "983101210886012928",
    "Tesla_stat": "983101301264875520",
    "hhenergienetz_stat": "999765979256737792",
    "hhenergienetz_dyn": "999766014216110080",
    # Achtung: ecomovement_stat liefert ~467 MB pro Snapshot –
    # bei täglicher Historisierung ca. 14 GB/Monat Speicherbedarf
    "ecomovement_stat": "999765881516871680",
    "ecomovement_dyn": "999765843465994240",
    # chargecloud GmbH – enthält u.a. Stadtwerke Göttingen (DE*GOE*)
    "chargecloud_stat": "1006999576359198720",
    "chargecloud_dyn": "1006999499934756864"
}

def fetch_data(name, sub_id):
    url = f"https://mobilithek.info:8443/mobilithek/api/v1.0/subscription?subscriptionID={sub_id}"
    print(f"Abruf läuft für: {name} (ID: {sub_id})...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    try:
        session = requests.Session()
        adapter = Pkcs12Adapter(pkcs12_filename=CERT_FILE, pkcs12_password=CERT_PASSWORD)
        session.mount('https://mobilithek.info:8443', adapter)
        
        # Timeout erhöht, da die Smartlab-Massenpakete extrem groß sind
        response = session.get(url, headers=headers, verify=False, timeout=120)

        if response.status_code == 200:
            data = response.json()
            
            if not os.path.exists('data'): 
                os.makedirs('data')
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data/{name}_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Erfolg! Gespeichert unter: {filename}\n")
        else:
            print(f"Fehler bei {name}: Status-Code {response.status_code}\n")
            
    except Exception as e:
        print(f"Technischer Fehler bei {name}: {e}\n")

if __name__ == "__main__":
    for name, sub_id in SUBSCRIPTIONS.items():
        fetch_data(name, sub_id)
        # 10 Sekunden Zwangspause nach jedem Download, damit die Mobilithek uns nicht blockiert
        print("Warte 10 Sekunden für die API-Stabilität...")
        time.sleep(10)
        
    print("\nAlle Abrufe abgeschlossen.")