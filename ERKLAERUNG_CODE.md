# Code-Erklärung: `main.py` und `compare_bnetza.py`

*Für Leser ohne Python-Vorkenntnisse. Am besten neben dem jeweiligen Code öffnen und parallel lesen.*

---

## Teil 0 — Die wichtigsten Python-Grundbegriffe (5 Minuten)

Bevor wir in den Code gehen, die Bausteine, aus denen beide Programme bestehen:

**Variable** — ein benannter Behälter für einen Wert.
```python
name = "EnBW"        # Text (String)
anzahl = 192          # Zahl
```
Ab jetzt kann man überall `name` schreiben und Python setzt `"EnBW"` ein.

**String** — Text, immer in Anführungszeichen: `"Göttingen"`. Ein `f` vor dem String erlaubt es, Variablen direkt einzubauen:
```python
print(f"Abruf läuft für: {name}")   # → Abruf läuft für: EnBW
```

**Dictionary (dict)** — eine Tabelle aus Schlüssel-Wert-Paaren, wie ein Wörterbuch: links das Wort, rechts die Bedeutung.
```python
SUBSCRIPTIONS = {
    "EnBW_dyn": "983100920677924864",   # Schlüssel : Wert
    "EnBW_stat": "983100939883704320",
}
```

**Liste** — eine geordnete Sammlung von Werten: `["a", "b", "c"]`. Ein **Set** ist ähnlich, aber jeder Wert kommt automatisch nur **einmal** vor — perfekt, um Doppelzählungen zu verhindern.

**Funktion** — ein benannter, wiederverwendbarer Codeblock. Definiert mit `def`, benutzt durch Aufruf mit Klammern:
```python
def fetch_data(name, sub_id):    # Definition mit zwei "Eingabewerten" (Parametern)
    ...                          # eingerückter Code gehört zur Funktion

fetch_data("EnBW_dyn", "983...")  # Aufruf: führt den Block mit diesen Werten aus
```

**Schleife (for-loop)** — wiederholt einen Block für jedes Element einer Sammlung:
```python
for name, sub_id in SUBSCRIPTIONS.items():
    fetch_data(name, sub_id)     # läuft einmal pro Eintrag im Dictionary
```

**Einrückung** — in Python entscheiden die Leerzeichen am Zeilenanfang, was wozu gehört. Alles, was unter `def`, `for`, `if` oder `try` eingerückt ist, gehört zu diesem Block.

**`import`** — lädt Zusatzwerkzeuge ("Bibliotheken"). `import requests` holt z. B. das Werkzeug für Internetabrufe. Was importiert ist, kann man danach mit Punkt-Schreibweise benutzen: `requests.Session()`.

**`try` / `except`** — ein Sicherheitsnetz: „Versuche diesen Code; wenn dabei ein Fehler passiert, stürze nicht ab, sondern führe stattdessen den `except`-Block aus."

---

## Teil 1 — `main.py`: Der Crawler

**Aufgabe in einem Satz:** Melde dich mit unserem Zertifikat bei der Mobilithek an, lade nacheinander alle abonnierten Datenpakete herunter und speichere jedes als Datei mit Zeitstempel.

### Schritt 1: Werkzeuge laden (Zeilen 1–7)

```python
import os, json, urllib3, requests, time
from datetime import datetime
from requests_pkcs12 import Pkcs12Adapter
```

| Werkzeug | Wofür |
|---|---|
| `os` | Mit dem Betriebssystem reden (Ordner anlegen, Umgebungsvariablen lesen) |
| `json` | Das Datenformat JSON lesen/schreiben (so kommen die Mobilithek-Daten an) |
| `requests` | Webseiten/APIs im Internet abrufen — das Herzstück |
| `time` | Pausen einlegen (`time.sleep`) |
| `datetime` | Aktuelles Datum/Uhrzeit für den Dateinamen |
| `Pkcs12Adapter` | Spezialwerkzeug, das unser `.p12`-Zertifikat in den Internetabruf einbaut |

### Schritt 2: Konfiguration (Zeilen 12–30)

```python
CERT_FILE = "certificate.p12"
CERT_PASSWORD = os.getenv("MOBILITHEK_CERT_PASSWORD", "!Dh6J5c5gaRj")
```

Die Mobilithek lässt nicht jeden rein: Man muss sich mit einem **Zertifikat** ausweisen (vergleichbar mit einem digitalen Dienstausweis). `os.getenv(...)` versucht, das Passwort aus den Systemeinstellungen zu lesen; falls es dort nicht hinterlegt ist, nimmt es den zweiten Wert als Notlösung.

```python
SUBSCRIPTIONS = { "EnBW_dyn": "983100920677924864", ... }
```

Unser „Einkaufszettel": Links steht unser selbstgewählter Spitzname für den Datenstrom, rechts die offizielle Abo-Nummer bei der Mobilithek. Pro Anbieter gibt es zwei Abos: **`stat`** = Stammdaten (wo steht die Säule, wie viel Leistung — ändert sich selten) und **`dyn`** = Belegungsdaten (frei/besetzt — ändert sich minütlich).

### Schritt 3: Die Funktion `fetch_data` — ein einzelner Download (Zeilen 29–63)

Diese Funktion ist das Arbeitspferd. Sie wird später für jedes Abo einmal aufgerufen und macht fünf Dinge:

**1. Die Adresse bauen:**
```python
url = f"https://mobilithek.info:8443/...?subscriptionID={sub_id}"
```
Die Abo-Nummer wird in die Internetadresse eingesetzt — wie eine Bestellnummer in ein Bestellformular.

**2. Sich als normaler Browser ausgeben:**
```python
headers = { "User-Agent": "Mozilla/5.0 ...", ... }
```
„Headers" sind Begleitinformationen eines Internetabrufs. Der `User-Agent` sagt dem Server, wer anfragt — wir geben uns als Chrome-Browser aus, weil manche Server automatisierte Skripte sonst abweisen.

**3. Die Verbindung mit Zertifikat aufbauen:**
```python
session = requests.Session()
adapter = Pkcs12Adapter(pkcs12_filename=CERT_FILE, pkcs12_password=CERT_PASSWORD)
session.mount('https://mobilithek.info:8443', adapter)
response = session.get(url, headers=headers, verify=False, timeout=120)
```
Eine `Session` ist eine wiederverwendbare Verbindung. Mit `mount` sagen wir: „Immer wenn du mit dieser Adresse sprichst, zeige unser Zertifikat vor." Dann holt `session.get(...)` die Daten ab. `timeout=120` heißt: Warte höchstens 120 Sekunden auf Antwort (wichtig, weil z. B. die Eco-Movement-Datei riesig ist und lange braucht).

**4. Prüfen, ob es geklappt hat:**
```python
if response.status_code == 200:
```
Jede Server-Antwort hat einen Statuscode. `200` = alles gut. (Bekannt ist z. B. `404` = nicht gefunden.)

**5. Speichern mit Zeitstempel:**
```python
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
filename = f"data/{name}_{timestamp}.json"
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
```
Der Dateiname bekommt Datum und Uhrzeit eingebaut (z. B. `EnBW_stat_20260612_184752.json`). **Das ist der Kern der Historisierung deiner Arbeit:** Weil jeder Abruf eine *neue* Datei mit Zeitstempel erzeugt statt die alte zu überschreiben, entsteht über die Zeit eine lückenlose Reihe von Schnappschüssen. `with open(...)` öffnet eine Datei und schließt sie automatisch wieder; `json.dump` schreibt die Daten hübsch formatiert hinein.

Das Ganze steckt in einem `try`/`except`: Wenn bei *einem* Anbieter etwas schiefgeht (Server down, Netzwerkfehler), wird nur eine Fehlermeldung ausgegeben und das Programm macht mit dem nächsten Anbieter weiter, statt komplett abzubrechen.

### Schritt 4: Das Hauptprogramm (Zeilen 65–72)

```python
if __name__ == "__main__":
    for name, sub_id in SUBSCRIPTIONS.items():
        fetch_data(name, sub_id)
        time.sleep(10)
```

Die Zeile `if __name__ == "__main__":` bedeutet: „Führe das Folgende nur aus, wenn diese Datei direkt gestartet wird" (und nicht, wenn ein anderes Skript sie nur als Werkzeugkasten importiert). Dann läuft die Schleife einmal pro Abo und ruft jeweils `fetch_data` auf. Das `time.sleep(10)` erzwingt 10 Sekunden Pause zwischen den Downloads — sonst könnte die Mobilithek uns wegen zu vieler Anfragen hintereinander sperren (Fehlercodes 429/503).

---

## Teil 2 — `compare_bnetza.py`: Der Abdeckungs-Check

**Aufgabe in einem Satz:** Nimm die 192 offiziell bei der Bundesnetzagentur registrierten Göttinger Ladepunkte und prüfe, wie viele davon in unseren heruntergeladenen Daten tatsächlich auftauchen.

Das Programm hat drei Abschnitte: **Excel einlesen → JSON-Dateien durchsuchen → Ergebnis ausgeben.**

### Abschnitt 1: Die BNetzA-Excel einlesen (Zeilen 27–86)

Hier kommt **pandas** zum Einsatz — die Standard-Bibliothek für Tabellendaten in Python. `pd.read_excel(...)` liest eine Excel-Datei in einen sogenannten *DataFrame* (stell dir das als Excel-Tabelle im Arbeitsspeicher vor).

**Problem 1: Wo fängt die Tabelle an?** Behörden-Excels haben oft Logos und Erklärtexte über der eigentlichen Tabelle. Deshalb sucht der Code die Kopfzeile dynamisch:
```python
for idx, row in df_raw.iterrows():
    cells = [str(c).lower() for c in row.values]
    if any("id" in c for c in cells) and any(c == "ort" for c in cells):
        header_row_index = idx
        break
```
Übersetzt: „Gehe Zeile für Zeile durch. Die erste Zeile, in der irgendwo ‚id' vorkommt UND eine Zelle exakt ‚ort' heißt, ist die Überschriftenzeile." Das `break` beendet die Suche beim ersten Treffer. (Die eckigen Klammern sind eine *List Comprehension* — eine Kurzform für „baue eine neue Liste, indem du jedes Element umwandelst", hier: alles in Kleinbuchstaben.)

**Problem 2: Nur Göttingen behalten.**
```python
df_goe = df[
    df[ort_col].astype(str).str.lower().str.contains("göttingen|goettingen", na=False)
    | plz.str.startswith("3707")
    | plz.str.startswith("3708")
].copy()
```
Das ist ein Filter: Behalte nur Zeilen, bei denen der Ort „göttingen" enthält **oder** (`|`) die Postleitzahl mit 3707/3708 beginnt. So erwischen wir auch Einträge mit Schreibvarianten.

**Problem 3: Pro Ladepunkt das Suchmaterial sammeln.** Für jeden registrierten Punkt merkt sich der Code zwei Dinge in einem Dictionary namens `points`:
- die **EVSE-IDs** — das sind europaweit eindeutige Kennungen einzelner Ladepunkte (Format z. B. `DE*GOE*E1234`). Eine Ladesäule kann mehrere davon haben, deshalb ein Set.
- den **bereinigten Straßennamen** als Ersatzmerkmal, falls keine ID hinterlegt ist.

Die Hilfsfunktion `clean_street` normalisiert Straßennamen, damit Schreibweisen vergleichbar werden:
```python
"Theodor-Heuss-Straße 15a"  →  "THEODOR HEUSS"
```
Sie entfernt „straße/strasse/str.", wirft Hausnummern und Sonderzeichen raus (dafür sind die `re.sub`-Zeilen da — *reguläre Ausdrücke*, eine Mini-Sprache für Textmuster) und wandelt alles in Großbuchstaben um.

Wichtig zu wissen: Von den 192 Punkten haben nur 71 überhaupt eine EVSE-ID in der Excel — deshalb braucht es den Straßen-Trick als zweites Standbein.

### Abschnitt 2: Der Hybrid-Scan (Zeilen 88–139)

```python
json_files = [f for f in glob.glob("data/*.json") if "stat" in ... ]
```
`glob` sammelt alle Dateinamen, die auf ein Muster passen. Hier: nur die **statischen** Dateien (Stammdaten), denn nur dort stehen Adressen und IDs — die dynamischen enthalten nur frei/besetzt-Status.

Der entscheidende Trick des Skripts:
```python
content = f.read().upper()
```
Statt die kompliziert verschachtelte JSON-Struktur jedes Anbieters einzeln zu zerlegen (jeder Anbieter baut sie anders auf!), wird die **gesamte Datei als ein einziger riesiger Text** eingelesen und in Großbuchstaben umgewandelt. Dann wird einfach geprüft: *Kommt diese Zeichenkette irgendwo im Text vor?* Das ist robust gegen die chaotischen Formatunterschiede der Anbieter.

Pro Datei und pro registriertem Punkt gibt es dann **zwei Wege zum Treffer** (daher „hybrid"):

**Match 1 — über die ID (präzise):**
```python
for evse_id in p["ids"]:
    clean_id = evse_id.replace("*", "").replace("-", "")
    if evse_id in content or clean_id in content:
        matched = True
```
Steht die EVSE-ID im Text? Geprüft wird auch die Variante ohne Trennzeichen (`DE*GOE*E1234` → `DEGOEE1234`), weil Anbieter die IDs unterschiedlich formatieren.

**Match 2 — über die Straße (Heuristik als Plan B):**
```python
if not matched and p["street"] in streets_found_in_file:
    matched = True
```
Falls keine ID gefunden wurde: Kommt der bereinigte Straßenname in der Datei vor — und zwar nur in Dateien, in denen auch „GÖTTINGEN" steht? (Diese Vorbedingung verhindert, dass eine „BAHNHOFSTRASSE" in München als Göttingen-Treffer zählt.)

Die Treffer landen in **Sets** (`hits.add(key)`, `matched_total.add(key)`). Weil Sets jeden Wert nur einmal aufnehmen, kann derselbe Ladepunkt nicht doppelt gezählt werden — auch wenn er in drei Anbieter-Dateien gleichzeitig auftaucht.

### Abschnitt 3: Die Ausgabe (Zeilen 143–153)

```python
print(f"{provider:<28} | {len(hits):>18}")
coverage = (len(matched_total) / total_points) * 100
```
Die seltsamen Zeichen `:<28` und `:>18` sind nur Formatierung: „linksbündig auf 28 Zeichen auffüllen" bzw. „rechtsbündig auf 18" — so entsteht die saubere Tabelle im Terminal. `len(...)` zählt die Elemente eines Sets. Am Ende wird der Anteil der eindeutig gefundenen Punkte an allen 192 berechnet — das ist die **Abdeckungsquote** (aktuell 42,19 %).

### Eine ehrliche Einordnung der Methode

Der Volltext-Ansatz ist pragmatisch und schnell, hat aber bekannte Unschärfen, die du in der Arbeit als Limitation erwähnen kannst:
- **Straßen-Matching ist eine Heuristik:** Wenn ein Anbieter irgendeinen Standort in einer gleichnamigen Straße in Göttingen listet, zählt der BNetzA-Punkt als „gefunden", obwohl es nicht zwingend derselbe physische Ladepunkt ist.
- **Datei-Ebene statt Datensatz-Ebene:** „GÖTTINGEN und die Straße kommen in derselben *Datei* vor" ist schwächer als „im selben *Datensatz*".
- Dafür ist die Methode **robust**: Sie funktioniert für alle Anbieter gleich, egal wie unterschiedlich deren JSON-Strukturen sind.

---

## Glossar

| Begriff | Bedeutung |
|---|---|
| **API** | Schnittstelle, über die Programme Daten von einem Server abrufen |
| **JSON** | Textbasiertes Datenformat mit verschachtelten `{ "schlüssel": wert }`-Strukturen |
| **DATEX II / AFIR** | EU-Standards, die vorschreiben, wie Ladeinfrastruktur-Daten strukturiert und gemeldet werden |
| **EVSE-ID** | Eindeutige europäische Kennung eines Ladepunkts, z. B. `DE*GOE*E1234` |
| **Mobilithek** | Deutsche staatliche Datenplattform, über die Betreiber ihre Pflichtdaten bereitstellen |
| **BNetzA** | Bundesnetzagentur — führt das amtliche Ladesäulenregister (unsere „Wahrheit" mit 192 Punkten) |
| **Statuscode 200** | Server-Antwort „alles in Ordnung" |
| **Session / Adapter** | Wiederverwendbare Verbindung; der Adapter hängt unser Zertifikat an jede Anfrage |
| **DataFrame** | Tabelle im Arbeitsspeicher (pandas), wie ein Excel-Blatt in Python |
| **Set** | Sammlung ohne Duplikate — verhindert Doppelzählungen |
| **Heuristik** | Praktische Näherungslösung, die meistens stimmt, aber keine Garantie gibt |
