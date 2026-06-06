import json

print("Prüfe Smartlab-Datei nach Geokoordinaten für Göttingen...")

# Suche nach der passenden statischen Smartlab-Datei im data-Ordner
import glob
smartlab_files = glob.glob("data/*smartlab_afir_static*.json")

if not smartlab_files:
    print("Keine statische Smartlab-Datei gefunden.")
    exit()

with open(smartlab_files[0], "r", encoding="utf-8") as f:
    data = json.load(f)

# Wir gehen tief in die DATEX II Struktur zu den Koordinaten
stations_found = 0

# Hinweis: Je nach genauer Verschachtelung kann die Schleife leicht variieren.
# Wir suchen im Rohtext nach den typischen Feldern für Breitengrade rund um Göttingen.
with open(smartlab_files[0], "r", encoding="utf-8") as f:
    text_content = f.read()
    
# Schneller Check im Rohtext, wie oft Koordinaten im Göttinger Raum auftauchen:
# Göttingen Breite ist ~51.5
matches = text_content.count('"latitude": 51.5')
print(f"Anzahl gefundener Standorte im Breitengradbereich 51.5 (Göttingen): {matches}")