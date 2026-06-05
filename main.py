import os
import json
import urllib3
import requests
from datetime import datetime
from requests_pkcs12 import Pkcs12Adapter

# Warnungen unterdrücken
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- KONFIGURATION ---
CERT_FILE = "certificate.p12"  
# Holt das Passwort aus den Systemeinstellungen, falls nicht vorhanden, nutzt es den Fallback
CERT_PASSWORD = os.getenv("MOBILITHEK_CERT_PASSWORD", "!Dh6J5c5gaRj") 

# Hier sind alle deine Abonnements aufgelistet
SUBSCRIPTIONS = {
    "m8mit_dyn" : "983100383290986496",
    "m8mit_stat": "983100354711126016",
    "EnBW_dyn": "983100920677924864",
    "EnBW_stat": "983100939883704320",
    "Tesla_dyn": "983101210886012928",
    "Tesla_stat": "983101301264875520"
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
        
        response = session.get(url, headers=headers, verify=False, timeout=60)

        if response.status_code == 200:
            data = response.json()
            
            if not os.path.exists('data'): 
                os.makedirs('data')
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data/{name}_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Erfolg! Gespeichert unter: {filename}")
        else:
            print(f"Fehler bei {name}: Status-Code {response.status_code}")
            
    except Exception as e:
        print(f"Technischer Fehler bei {name}: {e}")

if __name__ == "__main__":
    # Die Schleife geht jedes Abonnement in der Liste durch
    for name, sub_id in SUBSCRIPTIONS.items():
        fetch_data(name, sub_id)
    print("\nAlle Abrufe abgeschlossen.")