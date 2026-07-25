"""Extrahiert die Stammdaten aller Göttinger Ladepunkte aus den statischen Feeds.

Schritt 1 der Export-Pipeline für die Stadtverwaltung (Interview-Anforderung,
siehe ENTSCHEIDUNGSLOG E6): Pro Ladepunkt (EVSE) eine Zeile mit Adresse,
Betreiber, Leistung und allen IDs, die später als Join-Schlüssel für die
dynamischen Belegungsdaten dienen.

Der Göttingen-Filter passiert bewusst HIER (bei der Extraktion) und nicht erst
im Export: Die stat-Feeds sind bundesweit und bis zu 542 MB groß — ungefiltert
wären das Millionen Zeilen. Die rohen Snapshots in data/ bleiben unangetastet,
für eine andere Stadt muss nur is_targetcity() ersetzt werden.

Aufruf:  venv/bin/python extract_stammdaten.py
Ausgabe: auswertung/stammdaten_targetcity.csv
"""

import os
import re
import gc
import glob
import json
import csv

AUSGABE_DATEI = os.path.join("auswertung", "stammdaten_targetcity.csv")


# --- Hilfsfunktionen (übernommen aus compare_bnetza.py, dort erprobt) --------

def normalize_id(value):
    """Macht IDs vergleichbar, indem alle Trennzeichen entfernt werden:
    'DE*TSL*E0K22AF' und 'DE-TSL-E0K22AF' werden beide zu 'DETSLE0K22AF'."""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


# Ortsbezogene Konfiguration: Nur diese beiden Konstanten sind auszutauschen,
# wenn die Pipeline auf eine andere Kommune angewendet werden soll.
STADTNAMEN = ("göttingen", "goettingen")
PLZ_PRAEFIXE = ("3707", "3708")


def is_targetcity(city, postcode):
    """Prüft, ob ein Datensatz im Gebiet der untersuchten Stadt liegt.
    Ortsname und Postleitzahl werden verodert, weil manche Anbieter nur
    eines der beiden Felder befüllen."""
    c = city.lower()
    return any(name in c for name in STADTNAMEN) or postcode.startswith(PLZ_PRAEFIXE)


def iter_sites(data):
    """Läuft durch die AFIR-Struktur und liefert jeden Standort (Site) einzeln."""
    pub = data.get("payload", {}).get("aegiEnergyInfrastructureTablePublication", {})
    for table in pub.get("energyInfrastructureTable", []):
        for site in table.get("energyInfrastructureSite", []):
            yield site


def extract_addresses(site):
    """Holt alle Adressblöcke EINES Standorts (alle DATEX-II-Varianten,
    siehe compare_bnetza.py und CLAUDE.md).

    Liefert je Block zusätzlich die WGS84-Koordinaten (ENTSCHEIDUNGSLOG E17):
    Laut Profildokumentation (Kapitel 2.3 der Ausarbeitung) trägt jede Station
    verpflichtend eine Georeferenzierung als Punkt. Das Feld liegt als
    Geschwisterfeld 'coordinatesForDisplay' direkt neben locLocationExtensionG
    im selben locPointLocation-Block, nur bei locAreaLocation (flächenhafte
    Referenzierung, z. B. Eco-Movement) gibt es keinen sinnvollen Einzelpunkt."""
    containers = [site.get("locationReference", {})]
    for station in site.get("energyInfrastructureStation", []):
        containers.append(station.get("locationReference", {}))

    addresses = []
    for loc_ref in containers:
        for loc_type in ("locPointLocation", "locAreaLocation"):
            loc_block = loc_ref.get(loc_type, {})
            addr = (
                loc_block
                .get("locLocationExtensionG", {})
                .get("FacilityLocation", {})
                .get("address", {})
            )
            if not addr:
                continue
            postcode = str(addr.get("postcode", ""))
            city = ""
            city_values = addr.get("city", {}).get("values", [])
            if city_values:
                city = str(city_values[0].get("value", ""))
            streets = []
            for line in addr.get("addressLine", []):
                if line.get("type", {}).get("value") == "street":
                    text_values = line.get("text", {}).get("values", [])
                    if text_values:
                        streets.append(str(text_values[0].get("value", "")))
            koordinaten = loc_block.get("coordinatesForDisplay", {})
            breitengrad = koordinaten.get("latitude", "")
            laengengrad = koordinaten.get("longitude", "")
            addresses.append((city, postcode, streets, breitengrad, laengengrad))
    return addresses


# --- Feld-Extraktion aus der Site-Struktur -----------------------------------

def first_value(multilang):
    """Holt den ersten Text aus einem DATEX-II-Mehrsprachenfeld
    ({'values': [{'lang': ..., 'value': ...}]})."""
    values = (multilang or {}).get("values", [])
    return str(values[0].get("value", "")) if values else ""


def extract_operator(site, station=None):
    """Betreibername. Erst auf Site-Ebene versucht, sonst Fallback auf die
    Station: HH Energienetz legt den Betreiber wie schon die Adresse (siehe
    extract_addresses) eine Ebene tiefer an der Station statt an der Site ab."""
    org = site.get("operator", {}).get("afacAnOrganisation", {})
    name = first_value(org.get("name"))
    if name:
        return name
    if station is not None:
        org = station.get("operator", {}).get("afacAnOrganisation", {})
        return first_value(org.get("name"))
    return ""


def extract_rows(site, anbieter):
    """Baut aus EINER Göttinger Site die CSV-Zeilen: eine pro Ladepunkt.
    Neben der echten EVSE-ID werden auch Station- und Site-idG mitgeführt,
    weil die dynamischen Feeds je nach Anbieter auf unterschiedliche Ebenen
    referenzieren (Tesla auf den Ladepunkt, andere teils auf die Station)."""
    # Beste verfügbare Adresse der Site wählen: erst alle Göttingen-Treffer
    # sammeln, dann bevorzugt einen MIT Koordinaten nehmen (ENTSCHEIDUNGSLOG
    # E17). Grund: Manche Anbieter (z. B. EnBW) tragen auf Site-Ebene eine
    # Göttingen-Adresse OHNE coordinatesForDisplay ein, während dieselbe
    # Information auf Stations-Ebene mit echten Koordinaten vorliegt -- die
    # alte "erster Treffer gewinnt"-Logik hätte sonst immer den koordinatenlosen
    # Site-Treffer genommen, weil er zuerst in der Liste steht.
    stadt, plz, strasse, breitengrad, laengengrad = "", "", "", "", ""
    treffer_zielstadt = [
        (city, postcode, streets, lat, lon)
        for city, postcode, streets, lat, lon in extract_addresses(site)
        if is_targetcity(city, postcode)
    ]
    if treffer_zielstadt:
        city, postcode, streets, lat, lon = next(
            (t for t in treffer_zielstadt if t[3] and t[4]), treffer_zielstadt[0]
        )
        stadt, plz = city, postcode
        strasse = streets[0] if streets else ""
        breitengrad, laengengrad = lat, lon

    rows = []
    for station in site.get("energyInfrastructureStation", []):
        for rp in station.get("refillPoint", []):
            cp = rp.get("aegiElectricChargingPoint", {})
            if not cp:
                continue
            # Maximale Leistung über alle Stecker des Ladepunkts (Watt -> kW)
            max_power_w = max(
                (c.get("maxPowerAtSocket", 0) or 0 for c in cp.get("connector", [])),
                default=0,
            )
            stecker = ", ".join(
                str(c.get("connectorType", {}).get("value", ""))
                for c in cp.get("connector", [])
            )
            rows.append({
                "anbieter": anbieter,
                "evse_id": cp.get("idG", ""),
                "ladepunkt_name": first_value(cp.get("name")),
                "station_id": station.get("idG", ""),
                "site_id": site.get("idG", ""),
                "site_name": first_value(site.get("name")),
                "betreiber": extract_operator(site, station),
                "strasse": strasse,
                "plz": plz,
                "stadt": stadt,
                "breitengrad": breitengrad,
                "laengengrad": laengengrad,
                "strom_art": str(cp.get("currentType", {}).get("value", "")).upper(),
                "max_leistung_kw": round(max_power_w / 1000, 1),
                "stecker_typen": stecker,
                "ladepunkte_an_station": station.get("numberOfRefillPoints", ""),
            })
    return rows


# --- Hauptprogramm ------------------------------------------------------------

if __name__ == "__main__":
    print("Extrahiere Stammdaten der Göttinger Ladepunkte aus den stat-Feeds...\n")

    # smartlab-Dateien explizit ausgeschlossen (ENTSCHEIDUNGSLOG E16):
    # CLAUDE.md verlangt, sie als Beleg zu archivieren, aber sie sollen NICHT
    # Teil der aktiven Pipeline sein -- der lose "stat"/"static"-Substring-
    # Filter hätte sie sonst wieder mit reingezogen ("smartlab_afir_static_*"
    # enthält beide Substrings). Aktuell folgenlos (0 Göttingen-Treffer, siehe
    # E2/E4/E5), aber nicht mehr zufallsbedingt.
    json_files = sorted(
        f for f in glob.glob("data/*.json")
        if ("stat" in os.path.basename(f).lower()
            or "static" in os.path.basename(f).lower())
        and not os.path.basename(f).lower().startswith("smartlab")
    )

    # Neuere Snapshots überschreiben ältere Einträge desselben Ladepunkts
    # (sorted() stellt die zeitliche Reihenfolge über den Dateinamen sicher);
    # Ladepunkte, die nur in alten Snapshots vorkommen, bleiben erhalten.
    ladepunkte = {}  # normalisierte EVSE-ID -> Zeile

    for file_path in json_files:
        filename = os.path.basename(file_path)
        anbieter = filename.split("_")[0]
        print(f"Analysiere Datei: {filename}...")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Fehler beim Lesen von {filename}: {e}")
            continue

        goe_punkte = 0
        for site in iter_sites(data):
            # Nur Sites, deren eigene Adresse in Göttingen liegt (siehe E4:
            # kein Volltext-Matching, sonst Scheintreffer anderer Städte)
            if not any(
                is_targetcity(city, postcode)
                for city, postcode, _, _, _ in extract_addresses(site)
            ):
                continue
            for row in extract_rows(site, anbieter):
                key = normalize_id(row["evse_id"])
                if key:
                    ladepunkte[key] = row
                    goe_punkte += 1

        print(f"  -> {goe_punkte} Göttinger Ladepunkte in dieser Datei")

        # Speicher der großen Dateien (bis 542 MB) sofort wieder freigeben
        del data
        gc.collect()

    # --- CSV schreiben ---------------------------------------------------------
    os.makedirs("auswertung", exist_ok=True)
    spalten = [
        "anbieter", "evse_id", "ladepunkt_name", "station_id", "site_id",
        "site_name", "betreiber", "strasse", "plz", "stadt",
        "breitengrad", "laengengrad",
        "strom_art", "max_leistung_kw", "stecker_typen", "ladepunkte_an_station",
    ]
    with open(AUSGABE_DATEI, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=spalten, delimiter=";")
        writer.writeheader()
        for row in sorted(ladepunkte.values(), key=lambda r: (r["anbieter"], r["evse_id"])):
            writer.writerow(row)

    print(f"\nFertig: {len(ladepunkte)} eindeutige Göttinger Ladepunkte")
    print(f"Gespeichert unter: {AUSGABE_DATEI}")
