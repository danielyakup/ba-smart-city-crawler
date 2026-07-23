# Code-Erklärung: Crawler, Abdeckungs-Check und Export-Pipeline

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
CERT_PASSWORD = _load_cert_password()
```

Die Mobilithek lässt nicht jeden rein: Man muss sich mit einem **Zertifikat** ausweisen (vergleichbar mit einem digitalen Dienstausweis). `_load_cert_password()` liest das Passwort zuerst aus der Umgebungsvariable `MOBILITHEK_CERT_PASSWORD` (gesetzt in Crontab und `~/.bashrc`); falls die nicht gesetzt ist, aus einer lokalen, nicht versionierten `.env`-Datei im Projektordner. Bewusst **kein** Passwort direkt im Code — das würde bei jedem `git push` mit ins Repository wandern.

```python
SUBSCRIPTIONS = { "EnBW_dyn": "983100920677924864", ... }
```

Unser „Einkaufszettel": Links steht unser selbstgewählter Spitzname für den Datenstrom, rechts die offizielle Abo-Nummer bei der Mobilithek. Pro Anbieter gibt es zwei Abos: **`stat`** = Stammdaten (wo steht die Säule, wie viel Leistung — ändert sich selten) und **`dyn`** = Belegungsdaten (frei/besetzt — ändert sich minütlich).

Aktuell sind fünf Anbieter abonniert (zehn Abos): EnBW, Tesla, HH Energienetz, Eco-Movement und — seit 25.06.2026 — **chargecloud GmbH**, deren Feed erstmals auch die Stadtwerke Göttingen enthält (`DE*GOE*`-IDs, siehe `ENTSCHEIDUNGSLOG.md` E5). Die früher abonnierten Smartlab-Feeds wurden entfernt, weil sie über alle Durchläufe hinweg null auswertbare Göttingen-Standorte lieferten (E2) — die alten Rohdateien in `data/` bleiben trotzdem als Beleg für die Thesis erhalten.

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

### Abschnitt 2: Strukturelles Parsen auf Datensatz-Ebene

```python
json_files = [f for f in glob.glob("data/*.json") if "stat" in ... ]
```
`glob` sammelt alle Dateinamen, die auf ein Muster passen. Hier: nur die **statischen** Dateien (Stammdaten), denn nur dort stehen Adressen und IDs — die dynamischen enthalten nur frei/besetzt-Status.

**Warum nicht einfach Volltext-Suche?** Eine frühere Version las jede Datei als einen riesigen Text und prüfte nur: „Kommt der Straßenname *irgendwo* vor und steht *irgendwo* GÖTTINGEN?" Bei bundesweiten Dateien führte das zu Scheintreffern — eine Theodor-Heuss-Straße in Berlin zählte als Göttingen-Treffer. Deshalb zerlegt das Skript die JSON-Struktur jetzt richtig (Details und Begründung: siehe `ENTSCHEIDUNGSLOG.md`, Eintrag E4).

Drei Hilfsfunktionen erledigen die Strukturarbeit:

**`iter_sites`** — läuft die DATEX-II-Verschachtelung ab (`payload → …Publication → Tabelle → Standort`) und liefert jeden Standort einzeln. Das `yield` macht die Funktion zu einem „Generator": Sie gibt die Standorte einen nach dem anderen heraus, statt alle auf einmal in einer Liste zu sammeln — schonend für den Arbeitsspeicher bei 500-MB-Dateien.

**`extract_addresses`** — holt Stadt, PLZ und Straße aus dem Adressblock. Die Pointe: Die Anbieter legen die Adresse an **unterschiedlichen, jeweils standardkonformen Stellen** ab (Tesla/EnBW unter `locPointLocation` am Standort, Eco-Movement unter `locAreaLocation`, HH Energienetz sogar eine Ebene tiefer an der Station). Die Funktion prüft alle Varianten. Entscheidend: Innerhalb eines Adressblocks gehören Stadt und Straße **garantiert zusammen** — genau das fehlte der Volltext-Methode.

**`extract_evse_ids`** — sammelt alle IDs eines Standorts ein, inklusive der tief versteckten echten EVSE-IDs der einzelnen Ladepunkte (`refillPoint → aegiElectricChargingPoint → idG`, z. B. `DE*TSL*E0K22AF` bei Tesla). `normalize_id` entfernt vorher alle Trennzeichen, damit Schreibvarianten von BNetzA und Anbietern vergleichbar werden.

Pro Datei entstehen so zwei Sammlungen: **alle IDs des Anbieters** (IDs sind deutschlandweit eindeutig, dürfen also aus allen Datensätzen kommen) und **Straßennamen nur aus Datensätzen mit Göttinger Adresse**. Dann gibt es pro BNetzA-Punkt zwei Wege zum Treffer:

- **Match 1 (ID):** Eine normalisierte BNetzA-EVSE-ID kommt in den Anbieter-IDs vor (exakt oder als Teilstück).
- **Match 2 (Adresse):** Der bereinigte BNetzA-Straßenname stimmt mit der Straße eines Datensatzes überein, der **selbst in Göttingen liegt**.

Die Treffer landen in **Sets** (`hits.add(key)`, `matched_total.add(key)`). Weil Sets jeden Wert nur einmal aufnehmen, kann derselbe Ladepunkt nicht doppelt gezählt werden — auch wenn er in drei Anbieter-Dateien gleichzeitig auftaucht.

### Abschnitt 3: Die Ausgabe (Zeilen 143–153)

```python
print(f"{provider:<28} | {len(hits):>18}")
coverage = (len(matched_total) / total_points) * 100
```
Die seltsamen Zeichen `:<28` und `:>11` sind nur Formatierung: „linksbündig auf 28 Zeichen auffüllen" bzw. „rechtsbündig auf 11" — so entsteht die saubere Tabelle im Terminal. `len(...)` zählt die Elemente eines Sets.

Das Skript zählt die beiden Match-Arten **getrennt**: Pro Anbieter und insgesamt wird ausgewiesen, wie viele Treffer hart über die EVSE-ID belegt sind und wie viele über die Göttingen-Adresse kamen. Zusätzlich zeigt die Spalte „Goe-Sites", wie viele Standorte mit Göttinger Adresse der Anbieter überhaupt führt — eine wichtige Plausibilitätskontrolle. Ein Punkt gilt als „hart", sobald ihn mindestens eine Anbieter-Datei per ID matcht — auch wenn andere Dateien ihn nur über die Adresse finden.

Aktueller Stand (Datensatz-Matching, nach Aufnahme von chargecloud GmbH, siehe `ENTSCHEIDUNGSLOG.md` E5): **84,9 %** Gesamtabdeckung (163 von 192), davon 26,6 % (51 Punkte) hart per EVSE-ID belegt und 58,3 % (112 Punkte) nur über die Adress-Heuristik. Vor E5 (nur EnBW, Tesla, HH Energienetz, Eco-Movement) lag der Wert bei 26,04 % (50/192, E4) — der Sprung kam durch chargecloud, dessen Feed erstmals auch die Stadtwerke Göttingen (`DE*GOE*`-IDs) enthält.

### Eine ehrliche Einordnung der Methode

Das Datensatz-Matching hat die größte Schwäche der alten Volltext-Methode beseitigt (Scheintreffer durch gleichnamige Straßen in anderen Städten). Restliche Unschärfen, die als Limitation in die Arbeit gehören, sind in `ENTSCHEIDUNGSLOG.md` (E4, E5) dokumentiert — die wichtigste: Stehen mehrere registrierte Ladeeinrichtungen in derselben Göttinger Straße, kann ein einziger Anbieter-Standort sie alle als „abgedeckt" markieren. Die 84,9 % sind daher eher eine obere Schätzung. Zudem trägt die BNetzA für 121 der 192 Göttinger Ladeeinrichtungen (63 %) gar keine EVSE-ID im Register ein — diese Punkte sind strukturell nur über die Adress-Heuristik erreichbar, die maximal erreichbare ID-Trefferquote liegt daher bei ~37 %.

---

## Teil 3 — Die Export-Pipeline: `extract_stammdaten.py`, `extract_zeitreihe.py`, `berechne_kennzahlen.py`

Diese drei Skripte setzen die Interview-Anforderungen um (Exportfunktion, Occupancy Rate — siehe ENTSCHEIDUNGSLOG E6/E7). Sie bauen aufeinander auf und werden **in dieser Reihenfolge** ausgeführt; alle Ergebnisse landen als Excel-taugliche CSV-Dateien (Semikolon-getrennt) im Ordner `auswertung/`.

### Skript 1: `extract_stammdaten.py` — Wer und wo sind die Göttinger Ladepunkte?

Geht alle **statischen** Feeds durch (dieselbe Parsing-Logik wie `compare_bnetza.py`: `iter_sites`, `extract_addresses`, `normalize_id` — bewusst kopiert statt importiert, damit jedes Skript für sich lesbar bleibt) und schreibt **eine Zeile pro Ladepunkt**: EVSE-ID, Adresse, Betreiber, Leistung in kW, AC/DC, Steckertypen.

Zwei Dinge sind besonders:
- **Der Göttingen-Filter passiert hier**, nicht später: Nur Standorte, deren eigene Adresse in Göttingen liegt, kommen in die Tabelle. Die bundesweiten Rohdaten in `data/` bleiben unberührt — für eine andere Stadt müsste man nur `is_goettingen()` austauschen.
- Neben der EVSE-ID werden auch **Station- und Site-ID mitgespeichert**. Das sind die „Join-Schlüssel": Skript 2 braucht sie, um Belegungs-Updates dem richtigen Ladepunkt zuzuordnen, denn die Anbieter referenzieren in den dynamischen Feeds mal den Punkt, mal die Station.

Ergebnis: `stammdaten_goettingen.csv` mit 317 Ladepunkten.

### Skript 2: `extract_zeitreihe.py` — Wann hat sich welcher Status geändert?

Hier steckt die wichtigste Erkenntnis der ganzen Auswertung: Die dynamischen Feeds sind **Delta-Feeds**. Ein Snapshot enthält *nicht* den Zustand aller Ladepunkte, sondern nur die, deren Status sich gerade geändert hat (Tesla: genau einer pro Snapshot — bundesweit!). Man kann den Status also nicht einfach „ablesen", sondern muss alle beobachteten Änderungen einsammeln und davon ausgehen, dass ein Status so lange gilt, bis die nächste Änderung beobachtet wird.

Das Skript geht alle dynamischen Snapshots durch (mehrere Tausend, Tendenz stark wachsend — Stand 14.07.2026 über 8.000 Dateien), behält nur Updates, deren ID zu einem Göttinger Ladepunkt aus Skript 1 passt, und **dedupliziert**: Dieselbe Änderung (gleicher Punkt, gleicher Zeitpunkt, gleicher Status) kann in mehreren Abrufen stecken, zählt aber nur einmal. Praktischer Nebengewinn: Das Anbieter-Feld `lastUpdated` verrät den *echten* Änderungszeitpunkt — genauer als unser Abrufraster.

**Ausnahme hhenergienetz (ENTSCHEIDUNGSLOG E13):** Dieser Anbieter liefert kein `lastUpdated` auf Punkt-/Stations-/Site-Ebene — das einzige `lastUpdated` an dieser Stelle steckt in `energyRateUpdate` und meint dort den Preis, nicht den Status. Ohne Fallback wären dadurch alle Wiederholungen desselben Status auf eine Zeile kollabiert (Dedup-Schlüssel enthält den Zeitpunkt). Es gibt aber einen echten, brauchbaren Zeitstempel eine Ebene höher: `publicationTime` der gesamten Publikation, sub-sekundengenau vom Anbieter gesetzt — nur eben je Delta-Nachricht, nicht je einzelnem Ladepunkt. Das Skript nutzt diesen als Fallback, bevor es notfalls auf den eigenen Abrufzeitpunkt (`erfasst_am`) zurückfällt.

**Das Abrufraster wurde zwischenzeitlich verschärft:** Anfangs liefen die dynamischen Feeds im 30-Minuten-Takt. Nach dem in E7 dokumentierten Befund, dass Delta-Feeds bei diesem Raster reihenweise Statusänderungen verpassen (Tesla z. B. 0 von 8 Göttinger Ladepunkten je erfasst), wurde die Crontab am 11.07.2026 auf ein 5-Minuten-Raster umgestellt. Der Effekt ist messbar: Statusänderungen stiegen von 456 auf inzwischen 576, betroffene Ladepunkte von 122 auf 161 von 317 (siehe `ENTSCHEIDUNGSLOG.md` E7/E8). Das Beobachtungsfenster zerfällt dadurch in zwei Phasen unterschiedlicher Dichte — bei Auswertungen über den Gesamtzeitraum ist das auszuweisen.

Ergebnis: `statusaenderungen_goettingen.csv` — eine Zeile pro beobachteter Statusänderung.

### Skript 3: `berechne_kennzahlen.py` — Die Zahlen fürs Rathaus

Segmentiert aus der Zeitreihe **Ladevorgänge** (Status wechselt auf `charging`/`occupied` → Beginn; nächste Änderung weg davon → Ende) und aggregiert daraus je Ladepunkt die Interview-Kennzahlen: Occupancy Rate, Anzahl Ladevorgänge, mittlere Dauer, Wochenend- und Nachtanteil.

Die wichtigste Zeile ist die **Plausibilitätsgrenze** (seit ENTSCHEIDUNGSLOG E15 getrennt nach Stromart: 12 Stunden für AC, 3 Stunden für DC-Schnellladung): Wenn zwischen zwei Abrufen Updates verloren gehen (Delta-Problem!), sieht ein Ladepunkt stundenlang „belegt" aus. Solche Schein-Ladevorgänge werden markiert und fließen nicht in die Kennzahlen ein — sie bleiben aber im Export sichtbar, damit nichts stillschweigend verschwindet. Deshalb gilt für alle Kennzahlen: Es sind **beobachtete Untergrenzen** der echten Nutzung, keine vollständige Zählung (ausführlich: ENTSCHEIDUNGSLOG E7). Die Grenze bleibt auch nach der Umstellung auf das 5-Minuten-Raster relevant: In E8 lagen zwei neu hinzugekommene Ladevorgänge trotzdem über 12 h — vermutlich, weil ein Anbieter (Eco-Movement) `lastUpdated` verzögert aktualisiert, nicht wegen unseres Abrufrasters.

**Ergänzung (ENTSCHEIDUNGSLOG E15): Zwei Plausibilitätsgrenzen statt einer, plus Median.** Eine einheitliche 12h-Grenze für alle Ladepunkte hätte lange, aber legitime AC-Übernachtladungen mit denselben Maßstab gemessen wie physikalisch unrealistisch lange DC-Sessions (Stichprobe: 26 von 36 DC-Sessions >4h kamen von Eco-Movement, dessen verzögertes `lastUpdated` bereits aus E8 bekannt ist). `segmentiere_intervalle()` nimmt daher jetzt eine Funktion statt eines festen Grenzwerts entgegen, die je Ladepunkt anhand der Stammdaten-Stromart entscheidet. Außerdem weist `kennzahlen_ladepunkte.csv` jetzt zusätzlich `median_dauer_min` aus: Die Dauerverteilung ist rechtsschief (wenige sehr lange Ladungen ziehen den Mittelwert nach oben), der Median ist der robustere „typische" Wert.

Ergebnis: `ladevorgaenge_goettingen.csv` (ein Ladevorgang pro Zeile) und `kennzahlen_ladepunkte.csv` (eine Zeile pro Ladepunkt, inklusive Stammdaten — auch für Punkte ganz ohne beobachtete Ladevorgänge, denn „nichts beobachtet" ist ein Befund, kein Loch). Stand 13.07.2026 (5-Minuten-Raster, seit 12.06.): 65 segmentierte Ladevorgänge, davon 28 als plausibel (≤ 12 h) markiert.

**Ergänzung (ENTSCHEIDUNGSLOG E10): Verfügbarkeit getrennt von Ausfallzeit.** Bisher galt implizit „nicht belegt = frei" — dabei kann ein Ladepunkt auch schlicht kaputt sein (`outOfOrder`/`inoperative`/`outOfService`). Das Skript segmentiert daher jetzt **zusätzlich** Außer-Betrieb-Phasen (dieselbe Segmentierungslogik wie bei Ladevorgängen, ausgelagert in die Hilfsfunktion `segmentiere_intervalle`, nur mit einer anderen Status-Menge). Wichtiger Unterschied: Für Ladevorgänge gilt die 12h-Plausibilitätsgrenze (reale Ladungen dauern selten länger), für Ausfälle **nicht** — ein defekter Ladepunkt kann durchaus tagelang außer Betrieb bleiben, das ist plausibel und kein Zeichen für verpasste Updates.

**Ergänzung (ENTSCHEIDUNGSLOG E14): Zwei Beobachtungsfenster statt einem.** Die Occupancy Rate wirkte über alle Ladepunkte hinweg unplausibel niedrig (Median 0,25 %). Ursache: Sie wurde durch die Länge des GESAMTEN Beobachtungsfensters seit Crawling-Beginn (12.06.2026) geteilt — obwohl 91 % aller beobachteten Ladevorgänge aus den letzten paar Tagen stammen (davor: 30-Minuten-Raster bis E8, Tesla komplett ausgefallen bis E12, hhenergienetz bis E13 kaputt). Das lange Fenster besteht also größtenteils aus Wochen mit unvollständiger Datengrundlage, zieht den Nenner aber trotzdem künstlich in die Länge. Das Skript unterscheidet daher jetzt zwei Fenster: Absolute Zählungen (`ladevorgaenge`, `belegt_stunden` usw.) und `occupancy_rate_prozent` laufen weiterhin übers **Gesamtfenster** (zum Vergleich); `ausfallquote_prozent`, `verfuegbar_prozent`, `ladevorgaenge_pro_tag` und die neue Spalte `occupancy_rate_verlaesslich_prozent` laufen nur noch übers **verlässliche Fenster** seit dem präzise datierten E12-Fix-Deployment (`VERLAESSLICHES_FENSTER_START`). Wichtig: Occupancy, Ausfallquote und Verfügbarkeit beziehen sich damit alle drei auf dasselbe (verlässliche) Fenster und summieren sich exakt auf 100 % — würde man Occupancy übers lange und Ausfallquote übers kurze Fenster rechnen, wäre die Summe nicht mehr interpretierbar. Das Dashboard zeigt entsprechend beide Occupancy-Varianten nebeneinander.

Drei neue Spalten in `kennzahlen_ladepunkte.csv`: `ausser_betrieb_stunden` (beobachtete Ausfallzeit), `ausfallquote_prozent` (Ausfallzeit / Beobachtungsfenster, analog zur Occupancy Rate) und `verfuegbar_prozent` (Rest des Fensters: weder belegt noch außer Betrieb). Die Ausfall-Events selbst landen in einer neuen Datei `ausfaelle_goettingen.csv` (Event-Ebene, analog zu `ladevorgaenge_goettingen.csv`). Erster Befund (13.07.2026): 20 beobachtete Ausfallzeiten auf 10 Ladepunkten — ein Kaufland-Standort war rechnerisch 67 % des Beobachtungsfensters außer Betrieb, was ohne diese Trennung als „98 % frei verfügbar" missverständlich gewesen wäre.

### Obendrauf: `dashboard.py` — die Oberfläche für die Stadtverwaltung

Ein **Streamlit**-Dashboard (Streamlit macht aus einem Python-Skript eine kleine Web-App, ohne dass man HTML oder JavaScript schreiben muss). Start mit `venv/bin/streamlit run dashboard.py`, dann im Browser unter `localhost:8501` erreichbar.

Es berechnet selbst nichts — es zeigt nur die CSVs aus `auswertung/` an. Aufbau von oben nach unten: Lesehinweis (Untergrenzen!), Gesamt-Kennzahlen, Stationsauswahl per Dropdown (die Kennzahlen der Auswahl erscheinen sofort — die Interview-Anforderung „beim Anklicken sichtbar"), zwei Balkendiagramme (Tageszeit, Wochentag) und der Export-Bereich mit Download-Buttons für alle Ebenen einzeln plus ein Excel-Gesamtpaket. `@st.cache_data` sorgt dafür, dass die CSVs nur einmal gelesen werden, nicht bei jedem Klick neu.

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
