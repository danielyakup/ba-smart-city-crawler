import os
import sys
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

# Merkt sich pro Feed den Last-Modified-Zeitstempel des zuletzt abgeholten
# Pakets (siehe ENTSCHEIDUNGSLOG E12). Ohne diese Datei würde jeder Lauf
# wieder bei "weit in der Vergangenheit" anfangen und die komplette
# Warteschlange erneut abholen.
STATUS_DATEI = "data/.abruf_status.json"
# Verhindert, dass zwei main.py-Läufe gleichzeitig laufen: Seit ein Lauf bei
# grossem Rueckstand (siehe E12) laenger als die 5-Minuten-Cron-Taktung
# dauern kann, koennten sich sonst zwei Prozesse beim Schreiben von
# STATUS_DATEI ueberschneiden.
LOCK_DATEI = "data/.crawler.lock"
# Startwert für einen Feed, der noch nie mit If-Modified-Since abgerufen
# wurde: liefert laut Doku (Kapitel 4.8) das aelteste im Puffer vorhandene
# Datenpaket zurueck, nicht wirklich alles seit dem Jahr 2000.
EPOCH_HEADER = "Sat, 01 Jan 2000 00:00:00 GMT"
# Sicherheitsgrenze pro Feed und Lauf, falls ein Anbieter unerwartet viele
# Pakete gepuffert hat -- verhindert eine Endlosschleife bzw. dass ein
# einzelner Feed den ganzen Cron-Lauf blockiert.
# Ursprünglich 500 (E12); ein Code-Review nach E12/E13 fand anhand der
# Dateinamen-Zeitstempel, dass Tesla/EnBW/hhenergienetz dieses Limit in
# 2,7-5,3% aller Cron-Läufe erreichten, OHNE dass die Warteschlange leer war
# (kein 304/204) -- der Rückstand wurde dann erst über mehrere weitere
# Läufe nachgeholt, ohne dass das sichtbar war. Auf 1000 angehoben, um das
# seltener zu machen; die Schleife loggt seit ENTSCHEIDUNGSLOG E16 zusätzlich
# explizit, wenn das Limit trotzdem greift, statt es kommentarlos abzuschneiden.
MAX_PAKETE_PRO_FEED = 1000


def _lade_status():
    if os.path.exists(STATUS_DATEI):
        with open(STATUS_DATEI, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _speichere_status(status):
    os.makedirs(os.path.dirname(STATUS_DATEI), exist_ok=True)
    with open(STATUS_DATEI, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def _prozess_laeuft(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existiert, gehoert nur einem anderen User
    return True


def _lock_belegen():
    """Bricht den Lauf ab, falls schon ein anderer main.py-Prozess aktiv ist
    (z. B. weil der vorherige Cron-Tick wegen eines grossen Rueckstands noch
    laeuft). Eine Lock-Datei mit einer toten PID gilt als verwaist und wird
    ueberschrieben."""
    if os.path.exists(LOCK_DATEI):
        with open(LOCK_DATEI, encoding="utf-8") as f:
            alte_pid_text = f.read().strip()
        if alte_pid_text.isdigit() and _prozess_laeuft(int(alte_pid_text)):
            print(f"Ein anderer Lauf (PID {alte_pid_text}) ist noch aktiv -- breche ab.")
            sys.exit(0)
        print(f"Verwaiste Lock-Datei (PID {alte_pid_text} existiert nicht mehr) -- wird ersetzt.")
    os.makedirs(os.path.dirname(LOCK_DATEI), exist_ok=True)
    with open(LOCK_DATEI, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def _lock_freigeben():
    if os.path.exists(LOCK_DATEI):
        os.remove(LOCK_DATEI)

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

def fetch_data(name, sub_id, status=None):
    """Holt alle seit dem letzten Lauf aufgelaufenen Datenpakete fuer einen
    Feed ab, nicht nur das neueste (siehe ENTSCHEIDUNGSLOG E12: Mobilithek
    puffert bei Delta-Unterstuetzung mehrere Pakete; ohne den
    If-Modified-Since/Last-Modified-Header liefert jeder Aufruf immer nur
    das zuletzt eingelieferte Paket, der Rest bleibt unsichtbar).

    status: das ueber Laeufe hinweg persistierte dict {feed_name:
    Last-Modified-String}; wird hier aktualisiert, wenn 'save_status'
    (Aufrufer) nicht selbst dafuer sorgt. Bleibt None fuer Aufrufe aus dem
    Debug-Snippet in der CLAUDE.md (dann kein Fortschritt zwischen Laeufen).
    """
    url = f"https://mobilithek.info:8443/mobilithek/api/v1.0/subscription?subscriptionID={sub_id}"
    print(f"Abruf läuft für: {name} (ID: {sub_id})...")

    if status is None:
        status = {}

    session = requests.Session()
    adapter = Pkcs12Adapter(pkcs12_filename=CERT_FILE, pkcs12_password=CERT_PASSWORD)
    session.mount('https://mobilithek.info:8443', adapter)

    if not os.path.exists('data'):
        os.makedirs('data')

    if_modified_since = status.get(name, EPOCH_HEADER)
    n_gespeichert = 0

    for _ in range(MAX_PAKETE_PRO_FEED):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Connection": "keep-alive",
            "If-Modified-Since": if_modified_since,
        }
        try:
            # Timeout erhöht, da die Smartlab-Massenpakete extrem groß sind
            response = session.get(url, headers=headers, verify=False, timeout=120)
        except Exception as e:
            print(f"Technischer Fehler bei {name}: {e}\n")
            break

        if response.status_code == 200:
            # JSON-Dekodierung und Dateischreiben abgesichert (ENTSCHEIDUNGSLOG
            # E16): Ein kaputtes/unerwartetes Paket sollte nur diesen einen
            # Feed abbrechen, nicht den ganzen Cron-Lauf (der if_modified_since
            # wird in diesem Fall NICHT fortgeschrieben, das Paket wird beim
            # naechsten Lauf einfach erneut versucht).
            try:
                data = response.json()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"data/{name}_{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"Fehler beim Verarbeiten/Speichern der Antwort von {name}: {e}\n")
                break
            n_gespeichert += 1

            neuer_stand = response.headers.get("Last-Modified")
            if not neuer_stand:
                # Sollte laut Doku nicht vorkommen (Kapitel 4.8.2: Responses
                # enthalten immer Last-Modified) -- ohne den Wert koennten wir
                # nicht sauber weiterlaufen, also lieber abbrechen als raten.
                print(f"Warnung: {name} lieferte kein Last-Modified-Header, breche Warteschlange ab.\n")
                break
            if_modified_since = neuer_stand
            status[name] = neuer_stand
            # Kurze Pause zwischen aufeinanderfolgenden Paketen desselben
            # Feeds -- das dokumentierte Zugriffslimit ist nicht beziffert,
            # daher lieber vorsichtig sein.
            time.sleep(0.3)
            continue

        elif response.status_code == 304:
            # Kein neueres Paket als if_modified_since -- Warteschlange
            # fuer diesen Feed ist bis zum aktuellen Stand abgearbeitet.
            break
        elif response.status_code == 204:
            # Noch nie ein Paket fuer diese Subskription eingeliefert.
            break
        else:
            print(f"Fehler bei {name}: Status-Code {response.status_code}\n")
            break
    else:
        # Die Schleife ist ausgelaufen, OHNE dass 304/204/ein Fehler kam --
        # das Sicherheitslimit wurde erreicht, während die Warteschlange
        # nachweislich noch nicht leer war (ENTSCHEIDUNGSLOG E16: Code-Review
        # fand das bei Tesla/EnBW/hhenergienetz in 2,7-5,3% aller Läufe, ohne
        # dass es je geloggt wurde). Kein Datenverlust -- if_modified_since
        # ist gespeichert und der Rest wird beim naechsten Lauf nachgeholt --
        # aber es soll sichtbar sein statt kommentarlos abgeschnitten zu werden.
        print(f"Warnung: {name} hat das Sicherheitslimit von {MAX_PAKETE_PRO_FEED} "
              f"Paketen erreicht, ohne dass die Warteschlange als leer gemeldet "
              f"wurde (kein 304/204). Es koennten noch weitere Pakete im Puffer "
              f"liegen -- werden beim naechsten Lauf nachgeholt.\n")

    print(f"Erfolg! {n_gespeichert} Paket(e) für {name} gespeichert.\n")
    return status


if __name__ == "__main__":
    _lock_belegen()
    try:
        status = _lade_status()
        for name, sub_id in SUBSCRIPTIONS.items():
            status = fetch_data(name, sub_id, status)
            # Nach jedem Feed sichern, damit ein Fehler bei einem spaeteren Feed
            # nicht den Fortschritt der vorherigen verwirft.
            _speichere_status(status)
            # 10 Sekunden Zwangspause nach jedem Feed, damit die Mobilithek uns nicht blockiert
            print("Warte 10 Sekunden für die API-Stabilität...")
            time.sleep(10)

        print("\nAlle Abrufe abgeschlossen.")
    finally:
        _lock_freigeben()