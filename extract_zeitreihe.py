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
import sys
import glob
import json

STAMMDATEN_DATEI = os.path.join("auswertung", "stammdaten_targetcity.csv")
AUSGABE_DATEI = os.path.join("auswertung", "statusaenderungen_targetcity.csv")

# Inkrementeller Betrieb (ENTSCHEIDUNGSLOG E21). Bis zur Abgabe hat dieses
# Skript bei jedem Lauf ALLE losen Snapshots in data/ neu geparst. Seit die
# dyn-Snapshots naechtlich archiviert werden, liegt dort nur noch der laufende
# Tag; ein Vollaufbau wuerde die Historie der bereits archivierten Tage
# verlieren. Deshalb werden die bisherigen Ergebnisse fortgeschrieben:
#
#   ROH_DATEI    Alle je beobachteten Statusaenderungen, UNbereinigt. Notwendig,
#                weil entferne_wiederholte_status() Zeilen verwirft, bevor die
#                Ausgabe-CSV geschrieben wird. Wuerde nur die bereinigte CSV
#                fortgeschrieben, koennte ein spaeter eintreffender lastUpdated
#                mitten in einen bereits kollabierten Statuslauf fallen und ein
#                anderes Ergebnis liefern als ein Vollaufbau. Die Bereinigung
#                laeuft daher immer ueber den vollstaendigen Rohbestand.
#   MARKEN_DATEI Pro Feed der Dateiname des zuletzt verarbeiteten Snapshots.
#                Die Dateinamen tragen den Abrufzeitpunkt, sortieren innerhalb
#                eines Feeds also chronologisch -- alles danach ist neu.
#
# Beide Dateien sind Arbeitsdateien, keine Lieferergebnisse, daher mit Punkt
# vorangestellt. Ein Vollaufbau bleibt jederzeit ueber --vollaufbau moeglich.
ROH_DATEI = os.path.join("auswertung", ".zeitreihe_roh.csv")
MARKEN_DATEI = os.path.join("auswertung", ".zeitreihe_marken.json")

SPALTEN = ["evse_id", "anbieter", "status", "geaendert_am", "erfasst_am", "match_ebene"]


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


def feed_name(filename):
    """Feed-Kennung aus dem Dateinamen, also alles vor dem Datumsteil
    ('EnBW_dyn_20260806_000015_978684.json' -> 'EnBW_dyn'). Dient als Schluessel
    fuer die Fortschrittsmarken; der Anbietername allein wuerde nicht genuegen,
    weil pro Anbieter zwei Feeds existieren."""
    m = re.match(r"(.+?)_(\d{8})_\d{6}", filename)
    return m.group(1) if m else filename


def zeilen_zu_updates(zeilen):
    """Baut aus CSV-Zeilen den Dedup-Schluessel wieder auf, den der Parser
    verwendet: (normalisierte Ladepunkt-ID, Aenderungszeitpunkt, Status).
    Der Schluessel ist verlustfrei rekonstruierbar, weil 'evse_id' entweder aus
    den Stammdaten stammt oder die rohe Punkt-ID ist -- normalize_id() liefert
    in beiden Faellen wieder dieselbe normalisierte ID."""
    updates = {}
    for row in zeilen:
        key = (normalize_id(row["evse_id"]), row["geaendert_am"], row["status"])
        updates[key] = {spalte: row.get(spalte, "") for spalte in SPALTEN}
    return updates


def lade_csv(pfad):
    """Liest eine der Arbeits-/Ausgabe-CSVs; fehlende Datei ergibt eine leere
    Liste, damit der erste Lauf ohne Sonderfall durchlaeuft."""
    if not os.path.exists(pfad):
        return []
    with open(pfad, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def schreibe_csv(pfad, zeilen):
    with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
        writer.writeheader()
        writer.writerows(zeilen)


def lade_marken():
    if not os.path.exists(MARKEN_DATEI):
        return {}
    try:
        with open(MARKEN_DATEI, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # Kaputte Marken-Datei darf nicht zu stillem Datenverlust fuehren:
        # ohne Marken werden alle vorhandenen Snapshots erneut geparst, was
        # dank Deduplizierung ueber den Rohbestand folgenlos ist.
        print(f"Warnung: '{MARKEN_DATEI}' unlesbar ({e}) -- alle vorhandenen "
              f"Snapshots werden erneut geparst.")
        return {}


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

    # Vorhandenes Ergebnis fortschreiben oder alles neu aufbauen (E21) --------
    vollaufbau = "--vollaufbau" in sys.argv
    marken = {} if vollaufbau else lade_marken()

    updates = {}       # Dedup-Schlüssel -> Zeile; ein Delta kann in mehreren
                       # aufeinanderfolgenden Abrufen stecken, wenn der Anbieter
                       # zwischen zwei Abrufen nichts Neues publiziert hat
    if not vollaufbau:
        roh_zeilen = lade_csv(ROH_DATEI)
        if roh_zeilen:
            updates = zeilen_zu_updates(roh_zeilen)
            print(f"Rohbestand geladen: {len(updates)} bereits beobachtete "
                  f"Statusänderungen.")
        else:
            # Erster inkrementeller Lauf: Der Rohbestand wird aus der
            # vorhandenen Ausgabe-CSV angelegt. Die dort durch E16 bereits
            # entfernten Wiederholungen fehlen darin, was folgenlos ist, weil
            # sie auch der Vollaufbau nicht ausgeben würde. Ab jetzt wächst der
            # Rohbestand unbereinigt weiter.
            updates = zeilen_zu_updates(lade_csv(AUSGABE_DATEI))
            if updates:
                print(f"Rohbestand erstmalig aus '{AUSGABE_DATEI}' übernommen: "
                      f"{len(updates)} Statusänderungen.")

        vorher = len(json_files)
        json_files = [
            f for f in json_files
            if os.path.basename(f) > marken.get(feed_name(os.path.basename(f)), "")
        ]
        print(f"Scanne {len(json_files)} neue von {vorher} vorhandenen "
              f"dynamischen Snapshots...")
    else:
        print(f"Vollaufbau: scanne {len(json_files)} dynamische Snapshots...")

    match_ebenen = {"punkt": 0, "station": 0, "site": 0}
    fehler = 0

    # Fortschrittsmarken werden nur bis zum ERSTEN Lesefehler eines Feeds
    # gesetzt (E21): Der Crawler schreibt alle fuenf Minuten, die Auswertung
    # liest alle fuenfzehn -- ein Lauf kann also eine gerade erst halb
    # geschriebene Datei erwischen. Wuerde die Marke darueber hinwegspringen,
    # fehlte dieses Paket dauerhaft in der Zeitreihe. Stattdessen bleibt der
    # Rest des Feeds fuer den naechsten Lauf liegen, wenn die Datei vollstaendig
    # ist.
    letzte_gute = {}
    gestoppt = set()

    for file_path in json_files:
        filename = os.path.basename(file_path)
        feed = feed_name(filename)
        if feed in gestoppt:
            continue
        anbieter = filename.split("_")[0]
        erfasst_am = snapshot_zeitpunkt(filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Fehler beim Lesen von {filename}: {e} "
                  f"-- {feed} wird beim naechsten Lauf ab hier fortgesetzt.")
            fehler += 1
            gestoppt.add(feed)
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

        if feed not in gestoppt:
            letzte_gute[feed] = filename

    # 3. CSV schreiben ------------------------------------------------------------
    zeilen = sorted(updates.values(), key=lambda r: (r["evse_id"], r["geaendert_am"]))
    vor_bereinigung = len(zeilen)
    zeilen = entferne_wiederholte_status(zeilen)

    # Schutz wie in extract_stammdaten.py (E21): Ein leeres Ergebnis ueber eine
    # gefuellte CSV zu schreiben ist immer ein Fehler. Trat vor E21 genau dann
    # ein, wenn in data/ keine losen Snapshots lagen -- nach der naechtlichen
    # Archivierung der Normalfall.
    if not zeilen:
        vorhandene = lade_csv(AUSGABE_DATEI)
        if vorhandene:
            print(f"\nABBRUCH: 0 Statusänderungen ermittelt, aber "
                  f"'{AUSGABE_DATEI}' enthält {len(vorhandene)} Zeilen.")
            print("Die vorhandene CSV bleibt unverändert. Ursache prüfen.")
            exit(1)

    schreibe_csv(AUSGABE_DATEI, zeilen)

    # Rohbestand und Marken erst NACH der erfolgreichen Ausgabe fortschreiben,
    # damit ein Abbruch oben keinen Fortschritt festschreibt, der in der
    # Ausgabe-CSV nicht angekommen ist.
    if not vollaufbau:
        schreibe_csv(ROH_DATEI, sorted(
            updates.values(), key=lambda r: (r["evse_id"], r["geaendert_am"])))
        marken.update(letzte_gute)
        with open(MARKEN_DATEI, "w", encoding="utf-8") as f:
            json.dump(marken, f, indent=2, ensure_ascii=False)

    print(f"\nFertig: {len(zeilen)} eindeutige Statusänderungen "
          f"({vor_bereinigung - len(zeilen)} Wiederholungen ohne echten "
          f"Statuswechsel entfernt, siehe E16; Match-Ebenen "
          f"{'(nur neue)' if not vollaufbau else ''}: {match_ebenen}, "
          f"Lesefehler: {fehler})")
    print(f"Betroffene Ladepunkte: {len({r['evse_id'] for r in zeilen})} von {len(punkt_keys)}")
    print(f"Gespeichert unter: {AUSGABE_DATEI}")
