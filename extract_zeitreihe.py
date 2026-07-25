"""Rekonstruiert die Status-Zeitreihe der Göttinger Ladepunkte aus den dyn-Feeds.

Schritt 2 der Export-Pipeline (siehe ENTSCHEIDUNGSLOG E6/E7): Die dynamischen
Feeds sind DELTA-Feeds — jeder Snapshot enthält nur die Ladepunkte, deren
Status sich seit der letzten Publikation geändert hat (Tesla z. B. genau einen
Punkt pro Snapshot). Eine Zeitreihe entsteht daher nicht durch "Status pro
Snapshot ablesen", sondern durch Sammeln aller beobachteten Statusänderungen:
Zwischen zwei Änderungen gilt der zuletzt gemeldete Status als fortbestehend.

Wichtig: Das Feld lastUpdated im Feed ist der ECHTE Änderungszeitpunkt beim
Anbieter — er ist genauer als unser Abrufraster und wird deshalb mit
exportiert. Ausnahme hhenergienetz (siehe ENTSCHEIDUNGSLOG E13): liefert kein
lastUpdated auf Punkt-/Stations-/Site-Ebene, daher Fallback auf
publicationTime der Publikation, notfalls den Abrufzeitpunkt als
geaendert_am. Weil publicationTime pro NACHRICHT statt pro PUNKT gilt und
hhenergienetz fast den ganzen Bestand pro Nachricht republiziert, würden ohne
die Bereinigung in `entferne_wiederholte_status()` (ENTSCHEIDUNGSLOG E16)
viele Zeilen entstehen, die keine echte Statusänderung sind.

Voraussetzung: auswertung/stammdaten_targetcity.csv (aus extract_stammdaten.py)
Aufruf:        venv/bin/python extract_zeitreihe.py
Ausgabe:       auswertung/statusaenderungen_targetcity.csv
"""

import os
import re
import csv
import glob
import json

STAMMDATEN_DATEI = os.path.join("auswertung", "stammdaten_targetcity.csv")
AUSGABE_DATEI = os.path.join("auswertung", "statusaenderungen_targetcity.csv")


def normalize_id(value):
    """Macht IDs vergleichbar, indem alle Trennzeichen entfernt werden
    (identisch zu compare_bnetza.py / extract_stammdaten.py)."""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def iter_status_updates(data):
    """Läuft durch die Status-Publikation eines dyn-Snapshots und liefert
    jedes Status-Update einzeln als (punkt_id, station_id, site_id, status,
    last_updated). Fallstricke:
      - dyn-Feeds sind in 'messageContainer' verpackt, payload ist eine LISTE
        (stat-Feeds haben payload direkt als Dict)
      - EnBW nennt den Statusblock 'aegiRefillPointStatus', alle anderen
        'aegiElectricChargingPointStatus' — beides ist DATEX-II-konform
      - hhenergienetz liefert kein lastUpdated auf cp-/Station-/Site-Ebene;
        als Fallback dient 'publicationTime' der Publikation selbst (ein
        echter, anbieterseitiger Zeitstempel je Nachricht, sub-sekundengenau
        — nur eben nicht je Ladepunkt, siehe ENTSCHEIDUNGSLOG E13)"""
    container = data.get("messageContainer", data)
    payloads = container.get("payload", [])
    if isinstance(payloads, dict):
        payloads = [payloads]

    for payload in payloads:
        pub = payload.get("aegiEnergyInfrastructureStatusPublication", {})
        publication_time = pub.get("publicationTime", "")
        for site_status in pub.get("energyInfrastructureSiteStatus", []):
            site_id = site_status.get("reference", {}).get("idG", "")
            for station_status in site_status.get("energyInfrastructureStationStatus", []):
                station_id = station_status.get("reference", {}).get("idG", "")
                for rp_status in station_status.get("refillPointStatus", []):
                    cp = (
                        rp_status.get("aegiElectricChargingPointStatus")
                        or rp_status.get("aegiRefillPointStatus")
                        or {}
                    )
                    punkt_id = cp.get("reference", {}).get("idG", "")
                    status = cp.get("status", {}).get("value", "")
                    last_updated = (
                        cp.get("lastUpdated")
                        or station_status.get("lastUpdated")
                        or site_status.get("lastUpdated")
                        or publication_time
                        or ""
                    )
                    if punkt_id and status:
                        yield punkt_id, station_id, site_id, status, last_updated


def entferne_wiederholte_status(zeilen):
    """Entfernt aufeinanderfolgende Zeilen mit demselben Status für denselben
    Ladepunkt (ENTSCHEIDUNGSLOG E16). Hintergrund: hhenergienetz republiziert
    bei fast jeder Nachricht nahezu den gesamten Bestand, auch wenn sich am
    Status eines Punkts nichts geändert hat. Weil für diesen Anbieter
    'publicationTime' (ein Nachrichten-, kein Punkt-Zeitstempel, siehe E13)
    als geaendert_am dient, erzeugt jede Republikation eine scheinbar neue
    Statusänderung. Die Segmentierung in berechne_kennzahlen.py ignoriert
    solche Wiederholungen ohnehin (überspringt gleiche Folge-Status) — diese
    Bereinigung sorgt dafür, dass auch der Export selbst nur echte Übergänge
    zeigt, nicht Republikationen. Entfernt nur UNMITTELBAR aufeinanderfolgende
    Duplikate; ein Wechsel über einen anderen Status dazwischen (z. B.
    available -> unknown -> available) bleibt als zwei echte Übergänge
    erhalten. `zeilen` muss bereits nach (evse_id, geaendert_am) sortiert sein."""
    bereinigt = []
    letzter_punkt = None
    letzter_status = None
    for zeile in zeilen:
        if zeile["evse_id"] == letzter_punkt and zeile["status"] == letzter_status:
            continue
        bereinigt.append(zeile)
        letzter_punkt = zeile["evse_id"]
        letzter_status = zeile["status"]
    return bereinigt


def snapshot_zeitpunkt(filename):
    """Liest den Abrufzeitpunkt aus dem Dateinamen und formatiert ihn ISO-artig
    — die Dateinamen SIND die Historisierung. Seit E12 heißen neue Dateien
    {name}_{YYYYMMDD}_{HHMMSS}_{Mikrosekunden}.json (die Nachhol-Schleife kann
    mehrere Pakete pro Sekunde holen und braucht daher eindeutige Namen);
    ältere Dateien im data/-Ordner haben noch das alte Format ohne
    Mikrosekunden-Suffix — beides wird hier unterstützt (siehe E13)."""
    m = re.search(r"(\d{8})_(\d{6})(?:_\d+)?\.json$", filename)
    if not m:
        return ""
    d, t = m.group(1), m.group(2)
    return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}:{t[4:]}"


if __name__ == "__main__":
    print("Rekonstruiere Status-Zeitreihe der Göttinger Ladepunkte...\n")

    # 1. Join-Schlüssel aus den Stammdaten laden --------------------------------
    if not os.path.exists(STAMMDATEN_DATEI):
        print(f"Fehler: '{STAMMDATEN_DATEI}' fehlt — zuerst extract_stammdaten.py ausführen.")
        exit()

    punkt_keys = {}    # normalisierte Ladepunkt-ID -> EVSE-ID aus den Stammdaten
    station_keys = set()
    site_keys = set()
    with open(STAMMDATEN_DATEI, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            punkt_keys[normalize_id(row["evse_id"])] = row["evse_id"]
            if row["station_id"]:
                station_keys.add(normalize_id(row["station_id"]))
            if row["site_id"]:
                site_keys.add(normalize_id(row["site_id"]))

    print(f"Stammdaten geladen: {len(punkt_keys)} Ladepunkte, "
          f"{len(station_keys)} Stationen, {len(site_keys)} Sites\n")

    # 2. Alle dyn-Snapshots parsen ----------------------------------------------
    # smartlab-Dateien explizit ausgeschlossen (ENTSCHEIDUNGSLOG E16, analog
    # zu extract_stammdaten.py): "smartlab_afir_dynamic_*" enthält "dyn" als
    # Substring von "dynamic" und würde sonst trotz Entfernung aus
    # SUBSCRIPTIONS wieder mitgeparst.
    json_files = sorted(
        f for f in glob.glob("data/*.json")
        if "dyn" in os.path.basename(f).lower()
        and not os.path.basename(f).lower().startswith("smartlab")
    )
    print(f"Scanne {len(json_files)} dynamische Snapshots...")

    updates = {}       # Dedup-Schlüssel -> Zeile; ein Delta kann in mehreren
                       # aufeinanderfolgenden Abrufen stecken, wenn der Anbieter
                       # zwischen zwei Abrufen nichts Neues publiziert hat
    match_ebenen = {"punkt": 0, "station": 0, "site": 0}
    fehler = 0

    for file_path in json_files:
        filename = os.path.basename(file_path)
        anbieter = filename.split("_")[0]
        erfasst_am = snapshot_zeitpunkt(filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Fehler beim Lesen von {filename}: {e}")
            fehler += 1
            continue

        for punkt_id, station_id, site_id, status, last_updated in iter_status_updates(data):
            norm_punkt = normalize_id(punkt_id)

            # Göttingen-Filter über die Join-Schlüssel der Stammdaten:
            # bevorzugt über die Ladepunkt-ID, sonst über Station/Site
            # (manche Anbieter referenzieren im dyn-Feed andere Ebenen)
            if norm_punkt in punkt_keys:
                ebene = "punkt"
            elif normalize_id(station_id) in station_keys:
                ebene = "station"
            elif normalize_id(site_id) in site_keys:
                ebene = "site"
            else:
                continue

            # Fallback für Anbieter ohne echten Änderungszeitpunkt im Feed
            # (hhenergienetz liefert weder auf cp-/Station-/Site-Ebene ein
            # lastUpdated; das einzige lastUpdated im Feed steckt in
            # energyRateUpdate und bezieht sich auf den Preis, nicht auf den
            # Status — siehe E13): dann den Abrufzeitpunkt als Ersatz nehmen.
            geaendert_am = last_updated or erfasst_am

            # Deduplizieren: dieselbe Änderung (Punkt + Zeitpunkt + Status)
            # zählt nur einmal, egal in wie vielen Abrufen sie auftaucht
            key = (norm_punkt, geaendert_am, status)
            if key not in updates:
                match_ebenen[ebene] += 1
                updates[key] = {
                    "evse_id": punkt_keys.get(norm_punkt, punkt_id),
                    "anbieter": anbieter,
                    "status": status,
                    "geaendert_am": geaendert_am,
                    "erfasst_am": erfasst_am,
                    "match_ebene": ebene,
                }

    # 3. CSV schreiben ------------------------------------------------------------
    spalten = ["evse_id", "anbieter", "status", "geaendert_am", "erfasst_am", "match_ebene"]
    zeilen = sorted(updates.values(), key=lambda r: (r["evse_id"], r["geaendert_am"]))
    vor_bereinigung = len(zeilen)
    zeilen = entferne_wiederholte_status(zeilen)
    with open(AUSGABE_DATEI, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=spalten, delimiter=";")
        writer.writeheader()
        writer.writerows(zeilen)

    print(f"\nFertig: {len(zeilen)} eindeutige Statusänderungen "
          f"({vor_bereinigung - len(zeilen)} Wiederholungen ohne echten "
          f"Statuswechsel entfernt, siehe E16; Match-Ebenen: {match_ebenen}, "
          f"Lesefehler: {fehler})")
    print(f"Betroffene Ladepunkte: {len({r['evse_id'] for r in zeilen})} von {len(punkt_keys)}")
    print(f"Gespeichert unter: {AUSGABE_DATEI}")
