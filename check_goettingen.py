import os
import json
import glob

print("Starte präzise DATEX II-Analyse der Ladedaten für Göttingen...\n")

json_files = glob.glob("data/*.json")

if not json_files:
    print("Keine JSON-Dateien im Ordner 'data/' gefunden.")
    exit()

goettingen_sites = []
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

                    # Filter-Logik für Göttingen
                    is_goettingen = (
                        "göttingen" in city_name.lower() or 
                        "goettingen" in city_name.lower() or 
                        postcode.startswith("3707") or 
                        postcode.startswith("3708")
                    )
                    
                    if is_goettingen:
                        goettingen_sites.append({
                            "file": filename,
                            "name": site_name,
                            "city": city_name,
                            "zip": postcode
                        })
                        
    except Exception as e:
        # Falls eine Datei (z.B. m8mit oder Tesla) eine andere Struktur hat, nutzen wir einen Fallback-String-Match
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content_str = f.read().lower()
                if "göttingen" in content_str or "goettingen" in content_str:
                    goettingen_sites.append({
                        "file": filename,
                        "name": "Spezifische Struktur (Fallback-Treffer)",
                        "city": "Göttingen (Match)",
                        "zip": "-"
                    })
        except:
            print(f"Fehler beim Lesen von {filename}: {e}")

print(f"=== AKTUALISIERTES ERGEBNIS ===")
print(f"Gescannte Ladeparks/Infrastrukturen über alle Dateien: {total_sites_all_files}")
print(f"Tatsächliche Treffer im Stadtgebiet Göttingen: {len(goettingen_sites)}")
print(f"===============================\n")

if goettingen_sites:
    print("Gefundene Göttingen-Infrastrukturen (Auszug):")
    for i, match in enumerate(goettingen_sites[:30], 1):
        print(f"{i}. [{match['file']}] {match['name']} ({match['zip']} {match['city']})")
else:
    print("Auch mit tieferer Analyse keine direkten Göttingen-Infrastrukturen extrahierbar.")