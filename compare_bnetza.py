import os
import re
import glob
import pandas as pd

print("Starte ultraschnellen hybriden Göttingen-Abgleich (EVSE-ID + Straßen-Heuristik)...\n")

excel_path = "bnetza_goettingen.xlsx"
if not os.path.exists(excel_path):
    print(f"Fehler: Die Datei '{excel_path}' wurde nicht gefunden.")
    exit()


def clean_street(value):
    """Normalisiert einen Straßennamen für die Volltext-Suche.
    Entfernt 'straße'/'strasse'/'str.' und liefert GROSSBUCHSTABEN zurück,
    da die JSON-Dateien als f.read().upper() durchsucht werden."""
    s = str(value).lower()
    for token in ("straße", "strasse", "str.", "str"):
        s = s.replace(token, " ")
    # Hausnummern und Sonderzeichen raus, Mehrfach-Leerzeichen normalisieren
    s = re.sub(r"[^a-zäöüß ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()


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

    # Pro registriertem Punkt ein Datensatz: Schlüssel, Menge der EVSE-IDs, bereinigte Straße
    points = {}
    all_unique_streets = set()  # Für die Performance-Optimierung
    
    for _, row in df_goe.iterrows():
        key = str(row[key_col]).strip().upper()
        if not key or key == "NAN":
            continue
        ids = set()
        for col in evse_cols:
            cell = str(row[col])
            if cell and cell.upper() != "NAN":
                for raw in re.split(r"[\s;,]+", cell):
                    rid = raw.strip().upper()
                    if len(rid) > 5:
                        ids.add(rid)
                        
        cleaned_str = clean_street(row[street_col])
        if len(cleaned_str) >= 4:
            all_unique_streets.add(cleaned_str)
            
        points[key] = {"ids": ids, "street": cleaned_str}

    total_points = len(points)
    points_with_evse = sum(1 for p in points.values() if p["ids"])
    print(f"Registrierte Göttingen-Punkte (Ladeeinrichtungen): {total_points}")
    print(f"Davon mit hinterlegter EVSE-ID in der BNetzA-Excel: {points_with_evse}\n")

except Exception as e:
    print(f"Fehler beim Verarbeiten der Excel-Datei: {e}")
    exit()

# 2. Smart Hybrid Scan über die statischen Stammdaten ------------------------
json_files = [
    f for f in glob.glob("data/*.json")
    if ("stat" in os.path.basename(f).lower() or "static" in os.path.basename(f).lower())
]

provider_matches = {}      # Anbieter -> Menge der getroffenen Punkt-Schlüssel (eindeutig)
provider_id_matches = {}   # Anbieter -> davon hart über EVSE-ID belegt
matched_total = set()      # global eindeutige Treffer
matched_by_id = set()      # global: über EVSE-ID belegt (hart, eindeutig)
matched_by_street = set()  # global: über Straßen-Heuristik gefunden (unscharf)

print(f"Scanne {len(json_files)} statische Dateien (Optimierter Hybrid-Scan)...\n")

for file_path in json_files:
    filename = os.path.basename(file_path)
    parts = filename.split("_")
    provider = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else filename

    print(f"Analysiere Datei: {filename}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().upper()
    except Exception as e:
        print(f"Fehler beim Lesen von {filename}: {e}")
        continue

    has_goettingen = "GÖTTINGEN" in content or "GOETTINGEN" in content
    hits = provider_matches.setdefault(provider, set())
    id_hits = provider_id_matches.setdefault(provider, set())

    # Performance-Boost: Wir prüfen vorab, welche Straßen überhaupt im Text existieren
    streets_found_in_file = set()
    if has_goettingen:
        for street in all_unique_streets:
            if street in content:
                streets_found_in_file.add(street)

    # Jetzt loopen wir durch die Punkte (geht blitzschnell über Set-Lookups)
    for key, p in points.items():
        match_type = None

        # Match 1 (ID-basiert): echte EVSE-ID oder Variante ohne Trennzeichen (* / -)
        for evse_id in p["ids"]:
            clean_id = evse_id.replace("*", "").replace("-", "")
            if evse_id in content or clean_id in content:
                match_type = "id"
                break

        # Match 2 (Text-basiert): Straße wurde vorab im Text verifiziert
        if match_type is None and p["street"] in streets_found_in_file:
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
print(f"{'Anbieter':<28} | {'per EVSE-ID':>11} | {'per Straße':>10} | {'gesamt':>6}")
print("-" * 66)
for provider, hits in sorted(provider_matches.items()):
    id_hits = provider_id_matches.get(provider, set())
    print(f"{provider:<28} | {len(id_hits):>11} | {len(hits - id_hits):>10} | {len(hits):>6}")
print("-" * 66)

# Ein Punkt gilt als hart belegt, sobald ihn mindestens eine Datei per ID matcht;
# nur die restlichen Straßen-Treffer bleiben heuristisch (anfällig für
# Straßennamen, die auch in anderen Städten existieren)
heuristic_only = matched_by_street - matched_by_id
coverage = (len(matched_total) / total_points) * 100 if total_points else 0
coverage_hard = (len(matched_by_id) / total_points) * 100 if total_points else 0
coverage_heur = (len(heuristic_only) / total_points) * 100 if total_points else 0

print(f"\nHart belegt über EVSE-ID:      {len(matched_by_id):>3} von {total_points}  ({coverage_hard:.2f}%)")
print(f"Nur über Straßen-Heuristik:    {len(heuristic_only):>3} von {total_points}  ({coverage_heur:.2f}%)")
print(f"Eindeutig abgedeckt insgesamt: {len(matched_total):>3} von {total_points}  ({coverage:.2f}%)")
print(f"\n→ Belastbare Abdeckung: zwischen {coverage_hard:.2f}% (nur ID-belegt) und {coverage:.2f}% (inkl. Heuristik)")