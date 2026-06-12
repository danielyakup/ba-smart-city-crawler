import os
import re
import gc
import glob
import json
import pandas as pd

print("Starte Göttingen-Abgleich auf Datensatz-Ebene (strukturelles Matching)...\n")

excel_path = "bnetza_goettingen.xlsx"
if not os.path.exists(excel_path):
    print(f"Fehler: Die Datei '{excel_path}' wurde nicht gefunden.")
    exit()


def clean_street(value):
    """Normalisiert einen Straßennamen für den Vergleich.
    Entfernt 'straße'/'strasse'/'str.', Hausnummern und Sonderzeichen
    und liefert GROSSBUCHSTABEN zurück."""
    s = str(value).lower()
    for token in ("straße", "strasse", "str.", "str"):
        s = s.replace(token, " ")
    s = re.sub(r"[^a-zäöüß ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()


def normalize_id(value):
    """Macht EVSE-IDs vergleichbar, indem alle Trennzeichen entfernt werden:
    'DE*TSL*E0K22AF' und 'DE-TSL-E0K22AF' werden beide zu 'DETSLE0K22AF'.
    Nötig, weil BNetzA und Anbieter die IDs unterschiedlich formatieren."""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def is_goettingen(city, postcode):
    """Prüft, ob ein Datensatz im Stadtgebiet Göttingen liegt."""
    c = city.lower()
    return (
        "göttingen" in c
        or "goettingen" in c
        or postcode.startswith("3707")
        or postcode.startswith("3708")
    )


# 1. BNetzA Excel einlesen ---------------------------------------------------
try:
    # Header dynamisch finden: die Zeile, die 'Ladeeinrichtungs-ID' UND 'Ort' enthält
    df_raw = pd.read_excel(excel_path, header=None)
    header_row_index = 0
    for idx, row in df_raw.iterrows():
        cells = [str(c).lower() for c in row.values]
        if any("id" in c for c in cells) and any(c == "ort" for c in cells):
            header_row_index = idx
            break

    df = pd.read_excel(excel_path, skiprows=header_row_index)
    df.columns = df.columns.str.strip()

    ort_col = [c for c in df.columns if c.lower() == "ort"][0]
    plz_col = [c for c in df.columns if "postleit" in c.lower() or c.lower() == "plz"][0]
    street_col = [c for c in df.columns if "stra" in c.lower()][0]
    # Eindeutiger Punkt-Schlüssel (eine Ladeeinrichtung = ein registrierter Punkt)
    key_col = [c for c in df.columns if "ladeeinrichtungs-id" in c.lower()][0]
    # Echte EVSE-IDs (DE*GOE*...) stehen in EVSE-ID1..N – das ist, was in den JSONs auftaucht
    evse_cols = [c for c in df.columns if c.lower().startswith("evse-id")]

    plz = df[plz_col].astype(str)
    df_goe = df[
        df[ort_col].astype(str).str.lower().str.contains("göttingen|goettingen", na=False)
        | plz.str.startswith("3707")
        | plz.str.startswith("3708")
    ].copy()

    # Pro registriertem Punkt: normalisierte EVSE-IDs + bereinigte Straße
    points = {}
    for _, row in df_goe.iterrows():
        key = str(row[key_col]).strip().upper()
        if not key or key == "NAN":
            continue
        ids = set()
        for col in evse_cols:
            cell = str(row[col])
            if cell and cell.upper() != "NAN":
                for raw in re.split(r"[\s;,]+", cell):
                    rid = normalize_id(raw)
                    if len(rid) > 5:
                        ids.add(rid)
        points[key] = {"ids": ids, "street": clean_street(row[street_col])}

    total_points = len(points)
    points_with_evse = sum(1 for p in points.values() if p["ids"])
    print(f"Registrierte Göttingen-Punkte (Ladeeinrichtungen): {total_points}")
    print(f"Davon mit hinterlegter EVSE-ID in der BNetzA-Excel: {points_with_evse}\n")

except Exception as e:
    print(f"Fehler beim Verarbeiten der Excel-Datei: {e}")
    exit()


# 2. Strukturelles Parsen der DATEX II / AFIR-Dateien ------------------------
def iter_sites(data):
    """Läuft durch die AFIR-Struktur und liefert jeden Standort (Site) einzeln."""
    pub = data.get("payload", {}).get("aegiEnergyInfrastructureTablePublication", {})
    for table in pub.get("energyInfrastructureTable", []):
        for site in table.get("energyInfrastructureSite", []):
            yield site


def extract_addresses(site):
    """Holt alle Adressblöcke EINES Standorts. Die Anbieter legen die Adresse
    an unterschiedlichen Stellen ab, alle sind laut DATEX II erlaubt:
      - Tesla/EnBW:      Site -> locationReference -> locPointLocation -> ...
      - Eco-Movement:    Site -> locationReference -> locAreaLocation  -> ...
      - HH Energienetz:  Station (!) -> locationReference -> locAreaLocation -> ...
    Wir prüfen daher beide Location-Typen auf Site- UND Stations-Ebene.
    Innerhalb eines Blocks gehören Stadt und Straße garantiert zusammen."""
    containers = [site.get("locationReference", {})]
    for station in site.get("energyInfrastructureStation", []):
        containers.append(station.get("locationReference", {}))

    addresses = []
    for loc_ref in containers:
        for loc_type in ("locPointLocation", "locAreaLocation"):
            addr = (
                loc_ref.get(loc_type, {})
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
            addresses.append((city, postcode, streets))
    return addresses


def extract_evse_ids(site):
    """Sammelt alle IDs eines Standorts: Site- und Stations-idG sowie die
    EVSE-IDs der einzelnen Ladepunkte (aegiElectricChargingPoint.idG –
    dort verstecken z. B. Tesla und Eco-Movement die echten DE*…-IDs)."""
    ids = set()
    if site.get("idG"):
        ids.add(normalize_id(site["idG"]))
    for station in site.get("energyInfrastructureStation", []):
        if station.get("idG"):
            ids.add(normalize_id(station["idG"]))
        for rp in station.get("refillPoint", []):
            cp = rp.get("aegiElectricChargingPoint", {})
            if cp.get("idG"):
                ids.add(normalize_id(cp["idG"]))
    return ids


json_files = [
    f for f in glob.glob("data/*.json")
    if ("stat" in os.path.basename(f).lower() or "static" in os.path.basename(f).lower())
]

provider_matches = {}      # Anbieter -> Menge der getroffenen Punkt-Schlüssel (eindeutig)
provider_id_matches = {}   # Anbieter -> davon hart über EVSE-ID belegt
provider_goe_sites = {}    # Anbieter -> Anzahl Standorte mit Göttingen-Adresse
matched_total = set()      # global eindeutige Treffer
matched_by_id = set()      # global: über EVSE-ID belegt (hart, eindeutig)
matched_by_street = set()  # global: über Straße im Göttingen-Datensatz gefunden

print(f"Scanne {len(json_files)} statische Dateien (Datensatz-Ebene)...\n")

for file_path in json_files:
    filename = os.path.basename(file_path)
    parts = filename.split("_")
    provider = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else filename

    print(f"Analysiere Datei: {filename}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Fehler beim Lesen von {filename}: {e}")
        continue

    # Pro Datei zwei Sammlungen aufbauen:
    # - alle IDs des Anbieters (EVSE-IDs sind deutschlandweit eindeutig,
    #   daher dürfen sie aus ALLEN Datensätzen kommen)
    # - Straßennamen NUR aus Datensätzen mit Göttingen-Adresse
    all_ids = set()
    goe_streets = set()
    goe_site_count = 0

    for site in iter_sites(data):
        all_ids |= extract_evse_ids(site)
        site_in_goe = False
        for city, postcode, streets in extract_addresses(site):
            if is_goettingen(city, postcode):
                site_in_goe = True
                for s in streets:
                    cs = clean_street(s)
                    if len(cs) >= 4:
                        goe_streets.add(cs)
        if site_in_goe:
            goe_site_count += 1

    # Speicher der großen Dateien (bis 508 MB) sofort wieder freigeben
    del data
    gc.collect()

    # Für den ID-Vergleich alle Anbieter-IDs zu einem Suchtext verbinden:
    # so zählt es auch, wenn die BNetzA-ID nur als Teil einer längeren
    # Anbieter-ID auftaucht (z. B. mit angehängter Steckplatz-Nummer)
    id_blob = " ".join(all_ids)

    provider_goe_sites[provider] = goe_site_count
    hits = provider_matches.setdefault(provider, set())
    id_hits = provider_id_matches.setdefault(provider, set())

    for key, p in points.items():
        match_type = None

        # Match 1 (ID-basiert): normalisierte EVSE-ID des BNetzA-Punkts
        # kommt in den IDs des Anbieters vor (exakt oder als Teilstück)
        if p["ids"] & all_ids or any(pid in id_blob for pid in p["ids"]):
            match_type = "id"

        # Match 2 (Adress-basiert): Straße stimmt mit einem Datensatz überein,
        # dessen EIGENE Adresse in Göttingen liegt (kein Datei-Volltext mehr)
        elif p["street"] and any(
            p["street"] in s or s in p["street"] for s in goe_streets
        ):
            match_type = "street"

        if match_type:
            hits.add(key)
            matched_total.add(key)
            if match_type == "id":
                id_hits.add(key)
                matched_by_id.add(key)
            else:
                matched_by_street.add(key)

print("\n")

# 3. Ausgabe -----------------------------------------------------------------
print("=== GÖTTINGEN-ABDECKUNG PRO ANBIETER (eindeutige Punkte) ===")
print(f"{'Anbieter':<24} | {'Goe-Sites':>9} | {'per EVSE-ID':>11} | {'per Adresse':>11} | {'gesamt':>6}")
print("-" * 76)
for provider, hits in sorted(provider_matches.items()):
    id_hits = provider_id_matches.get(provider, set())
    sites = provider_goe_sites.get(provider, 0)
    print(f"{provider:<24} | {sites:>9} | {len(id_hits):>11} | {len(hits - id_hits):>11} | {len(hits):>6}")
print("-" * 76)

# Ein Punkt gilt als hart belegt, sobald ihn mindestens eine Datei per ID matcht
heuristic_only = matched_by_street - matched_by_id
coverage = (len(matched_total) / total_points) * 100 if total_points else 0
coverage_hard = (len(matched_by_id) / total_points) * 100 if total_points else 0
coverage_addr = (len(heuristic_only) / total_points) * 100 if total_points else 0

print(f"\nHart belegt über EVSE-ID:      {len(matched_by_id):>3} von {total_points}  ({coverage_hard:.2f}%)")
print(f"Über Göttingen-Adresse:        {len(heuristic_only):>3} von {total_points}  ({coverage_addr:.2f}%)")
print(f"Eindeutig abgedeckt insgesamt: {len(matched_total):>3} von {total_points}  ({coverage:.2f}%)")
print(f"\n→ Beide Match-Wege prüfen jetzt auf Datensatz-Ebene; die Adress-Treffer")
print(f"  setzen voraus, dass der Anbieter-Datensatz selbst in Göttingen liegt.")
