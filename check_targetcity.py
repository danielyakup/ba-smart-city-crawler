"""Frueher Erkundungshelfer: zaehlt Ladeparks der Zielstadt in den Snapshots.

ACHTUNG - ueberholt. Dieses Skript stammt aus der Anfangsphase des Projekts
(vgl. ENTSCHEIDUNGSLOG E1) und ist NICHT die Matching-Methodik der Arbeit.
Zwei bekannte Schwaechen sind hier bewusst konserviert:

1. Es liest die Adresse nur unter `locPointLocation`. Eco-Movement legt sie
   unter `locAreaLocation` ab, HH Energienetz eine Ebene tiefer an der Station.
   Datensaetze dieser Anbieter fallen hier also durchs Raster.
2. Der Fallback ab Zeile ~80 sucht den Ortsnamen im Dateitext. Diese
   Volltext-Suche wurde in E3/E4 als Matching-Methode VERWORFEN, weil sie
   Scheintreffer durch gleichnamige Strassen anderer Staedte erzeugt.

Die belastbare Auswertung leistet `compare_bnetza.py`, die Extraktion fuer die
Export-Pipeline `extract_stammdaten.py`. Das Skript bleibt als Beleg des
Entwicklungsverlaufs erhalten.
"""

import os
import json
import glob

# Ortsbezug wie im uebrigen Projekt in zwei Konstanten ausgelagert, damit das
# Skript ohne Codeaenderung auf eine andere Kommune zeigt.
STADTNAMEN = ("göttingen", "goettingen")
PLZ_PRAEFIXE = ("3707", "3708")

print("Starte DATEX-II-Analyse der Ladedaten fuer die Zielstadt...\n")

json_files = glob.glob("data/*.json")

if not json_files:
    print("Keine JSON-Dateien im Ordner 'data/' gefunden.")
    exit()

sites_zielstadt = []
total_sites_all_files = 0

for file_path in json_files:
    filename = os.path.basename(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Navigiere durch die DATEX II / AFIR Struktur
            payload = data.get("payload", {})
            publication = payload.get("aegiEnergyInfrastructureTablePublication", {})
            tables = publication.get("energyInfrastructureTable", [])
            
            for table in tables:
                sites = table.get("energyInfrastructureSite", [])
                for site in sites:
                    total_sites_all_files += 1
                    
                    # Suche nach Stadt oder Postleitzahl in der tiefen Struktur
                    loc_ref = site.get("locationReference", {})
                    pt_loc = loc_ref.get("locPointLocation", {})
                    ext = pt_loc.get("locLocationExtensionG", {})
                    facility = ext.get("FacilityLocation", {})
                    address = facility.get("address", {})
                    
                    postcode = str(address.get("postcode", ""))
                    
                    # Extrahiere Städtenamen aus der values-Liste
                    city_name = ""
                    city_data = address.get("city", {})
                    city_values = city_data.get("values", [])
                    if city_values and isinstance(city_values, list):
                        city_name = city_values[0].get("value", "")
                    
                    # Extrahiere Stationsnamen für die Ausgabe
                    add_info = site.get("additionalInformation", [])
                    site_name = "Unbekannter Ladepark"
                    if add_info and isinstance(add_info, list):
                        info_values = add_info[0].get("values", [])
                        if info_values:
                            site_name = info_values[0].get("value", "Unbekannter Ladepark")

                    # Filter-Logik der Zielstadt: Ortsname ODER PLZ-Praefix
                    is_targetcity = (
                        any(name in city_name.lower() for name in STADTNAMEN)
                        or postcode.startswith(PLZ_PRAEFIXE)
                    )
                    
                    if is_targetcity:
                        sites_zielstadt.append({
                            "file": filename,
                            "name": site_name,
                            "city": city_name,
                            "zip": postcode
                        })
                        
    except Exception as e:
        # VERWORFENE METHODE (ENTSCHEIDUNGSLOG E3/E4): Volltext-Suche ueber den
        # Dateiinhalt. Sie zaehlt jede Fundstelle des Ortsnamens als Treffer,
        # auch gleichnamige Strassen in anderen Staedten, und liefert deshalb
        # eine nicht belastbare Obergrenze. Nur zur Dokumentation erhalten.
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content_str = f.read().lower()
                if any(name in content_str for name in STADTNAMEN):
                    sites_zielstadt.append({
                        "file": filename,
                        "name": "Spezifische Struktur (Fallback-Treffer, unbelastbar)",
                        "city": "Zielstadt (Volltext-Match)",
                        "zip": "-"
                    })
        except:
            print(f"Fehler beim Lesen von {filename}: {e}")

print(f"=== AKTUALISIERTES ERGEBNIS ===")
print(f"Gescannte Ladeparks/Infrastrukturen über alle Dateien: {total_sites_all_files}")
print(f"Treffer im Stadtgebiet der Zielstadt: {len(sites_zielstadt)}")
print(f"===============================\n")

if sites_zielstadt:
    print("Gefundene Infrastrukturen der Zielstadt (Auszug):")
    for i, match in enumerate(sites_zielstadt[:30], 1):
        print(f"{i}. [{match['file']}] {match['name']} ({match['zip']} {match['city']})")
else:
    print("Auch mit tieferer Analyse keine Infrastrukturen der Zielstadt extrahierbar.")