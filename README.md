# Historisierender Crawler für kommunale Ladeinfrastrukturdaten

Artefakt einer Bachelorarbeit im Studiengang Wirtschaftsinformatik (Action Design Research).
Die Pipeline ruft Ladeinfrastrukturdaten für eine mittelgroße Stadt von der
[Mobilithek](https://mobilithek.info) ab, dem deutschen National Access Point, und **historisiert**
sie: Statt einer Momentaufnahme entsteht eine zeitgestempelte Reihe unveränderter Snapshots, aus der
sich Belegungs- und Auslastungskennzahlen je Ladepunkt berechnen lassen.

Hintergrund ist eine Lücke im Verwaltungshandeln. Kommunen können den amtlichen AFIR-Datenstrom zwar
kostenfrei abrufen, er steht aber nur als aktueller Zustand bereit und verfällt ohne fortlaufende
Aufzeichnung. Das Ladesäulenregister der Bundesnetzagentur dient hier als Bezugsgröße, gegen die die
Abdeckung gemessen wird.

## Aufbau

Zwei lose gekoppelte Stufen, verbunden allein über den Ordner `data/`:

| Stufe | Skript | Aufgabe |
| --- | --- | --- |
| Beschaffung | `main.py` | Ruft alle Mobilithek-Abonnements ab und legt jeden Abruf als `data/{name}_{zeitstempel}.json` ab. Bestehende Dateien werden nie überschrieben. |
| Beschaffung (dynamisch) | `crawl_dyn.sh` | Ruft nur die fünf dynamischen Feeds ab, für den engen Cron-Takt. |
| Evaluation | `compare_bnetza.py` | Gleicht die statischen Feeds gegen das BNetzA-Register ab und weist die Abdeckungsquote aus. |
| Export 1 | `extract_stammdaten.py` | Ladepunkte der Zielstadt mit Adresse, Leistung, Stromart, Koordinaten. |
| Export 2 | `extract_zeitreihe.py` | Statusänderungen aus den dynamischen Delta-Feeds. |
| Export 3 | `berechne_kennzahlen.py` | Ladevorgänge, Ausfälle und Occupancy-Kennzahlen je Ladepunkt. |
| Demonstrator | `dashboard.py` | Streamlit-Oberfläche über den Export-CSVs, Schwerpunkt auf der Exportfunktion. |

Pro Anbieter gibt es zwei Feeds: `*_stat` mit den Stammdaten und `*_dyn` mit dem Belegungsstatus.
Die dynamischen Feeds sind **Delta-Feeds**, sie liefern nur Änderungen seit dem letzten Abruf. Alle
Belegungskennzahlen sind deshalb beobachtete Untergrenzen.

## Voraussetzungen

- Python 3.10
- Ein PKCS12-Klientzertifikat für die Mobilithek (`certificate.p12`, **nicht im Repository**)
- Die zugehörige Passphrase in der Umgebungsvariablen `MOBILITHEK_CERT_PASSWORD`, ersatzweise in
  einer lokalen `.env` im Projektwurzelverzeichnis. Einen Vorgabewert im Code gibt es bewusst nicht.

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

`pyarrow` ist bewusst auf 19.0.1 festgeschrieben. Neuere Versionen führen beim Rendern von
`st.dataframe` im Streamlit-Thread zu Segfaults. Nicht anheben, ohne `dashboard.py` erneut zu testen.

## Nutzung

```bash
# Alle Feeds abrufen (10 s Pause je Feed, Gesamtvolumen über 1 GB, Dauer mehrere Minuten)
venv/bin/python main.py

# Einzelnen Feed abrufen (main.py ist dank __main__-Guard importsicher)
venv/bin/python -c "from main import fetch_data; fetch_data('EnBW_stat', '983100939883704320')"

# Abdeckungsquote gegen das BNetzA-Register (Dauer ein bis zwei Minuten)
venv/bin/python compare_bnetza.py

# Export-Pipeline in dieser Reihenfolge, Ausgabe nach auswertung/
venv/bin/python extract_stammdaten.py
venv/bin/python extract_zeitreihe.py
venv/bin/python berechne_kennzahlen.py

# Demonstrator
venv/bin/streamlit run dashboard.py
```

`auswertung_aktualisieren.sh` fasst die drei Export-Schritte zusammen und schützt sich über eine
Lock-Datei gegen überlappende Läufe.

### Automatisierter Betrieb

Im Produktivbetrieb der Arbeit liefen drei Cron-Jobs, ergänzt um die nächtliche Archivierung:

```cron
MOBILITHEK_CERT_PASSWORD=...
*/5  * * * *  /pfad/zum/projekt/crawl_dyn.sh                >> cron_dyn.log 2>&1
0 2  1 * *    venv/bin/python /pfad/zum/projekt/main.py      >> cron_stat.log 2>&1
*/15 * * * *  /pfad/zum/projekt/auswertung_aktualisieren.sh  >> cron_auswertung.log 2>&1
15 3 * * *    /pfad/zum/projekt/archiviere_naechtlich.sh     >> cron_archiv.log 2>&1
```

Die dynamischen Feeds werden alle fünf Minuten abgerufen, die statischen monatlich. Der enge Takt
ist eine Reaktion auf einen empirischen Befund: Bei zu grobem Raster gehen zwischen zwei Abrufen
Statuswechsel verloren. Der Abruf bedient zusätzlich den `If-Modified-Since`-Mechanismus der
Mobilithek, um zwischengespeicherte Pakete vollständig nachzuholen.

### Archivierung der Rohdaten

Im Fünf-Minuten-Takt fallen etwa 3,8 GB Rohdaten pro Tag an, gepackt nur rund 0,1 GB, weil 92 bis
97 Prozent der Bytes auf den DATEX-Umschlag entfallen. Ohne Archivierung ist eine 79-GB-Platte
nach etwa 17 Tagen voll; genau das führte am 03. und 04.08.2026 zu einer Datenlücke.
`archiviere_naechtlich.sh` packt die dynamischen Snapshots deshalb pro Feed und Tag zu
`data/archiv/{feed}_{JJJJMMTT}.tar.zst` (zstd -3, Kompressionsfaktor 33 bis 51).

Zwei Eigenschaften sichern die Historisierung ab: Originaldateien werden erst gelöscht, nachdem
ihr Vorhandensein im Archiv verifiziert ist, und ein bestehendes Archiv wird nie überschrieben.
Fehlen in einem Archiv Dateien, die auf der Platte liegen, wandern genau diese in ein zusätzliches
`_nachtragN.tar.zst`. Der laufende Tag bleibt unangetastet, damit sich Archivierung und Crawler
nicht in die Quere kommen. Ein defektes Archiv wird nicht gelöscht, sondern mit der Endung
`.defekt.{Zeitstempel}` beiseitegelegt und im Log gemeldet; der Lauf endet dann mit Exit-Code 1.

## Übertragung auf eine andere Kommune

Der Ortsbezug steckt in zwei Modulkonstanten, jeweils in `extract_stammdaten.py` und
`compare_bnetza.py`:

```python
STADTNAMEN   = ("göttingen", "goettingen")
PLZ_PRAEFIXE = ("3707", "3708")
```

Weil die Rohablage bundesweite Snapshots enthält, genügt es, diese Werte auszutauschen. Die bereits
erhobene Historie lässt sich damit rückwirkend für eine andere Stadt auswerten, ohne dass an der
Beschaffung etwas geändert werden muss.

`dashboard.py` besitzt zusätzlich einen Schalter `ANONYM`. Steht er auf `True`, ersetzt die Anzeige
Ortsnamen, Straßen, Betreiber und Betreiberkürzel durch Platzhalter. Das war für die Abbildungen der
schriftlichen Ausarbeitung gedacht. Die exportierten CSVs bleiben davon unberührt.

## Nicht im Repository enthalten

| Datei / Ordner | Grund |
| --- | --- |
| `certificate.p12`, `.env` | Zugangsdaten |
| `data/` | die historisierten Snapshots, im Projektverlauf auf über 40 GB angewachsen; einzelne statische Dateien erreichen 500 MB |
| `auswertung/` | vollständig aus `data/` reproduzierbar |
| `bnetza_*.xlsx` | der Registerauszug der Bundesnetzagentur, den `compare_bnetza.py` erwartet. Er ist über das [Ladesäulenregister](https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/E-Mobilitaet/start.html) öffentlich abrufbar. |

## Dokumentation

- **`ENTSCHEIDUNGSLOG.md`** führt jede methodische Entscheidung mit Anlass, Begründung und Ergebnis.
  Es bildet die BIE-Zyklen der Arbeit ab und enthält auch die Korrekturen eigener Irrtümer.
- **`ERKLAERUNG_CODE.md`** erklärt die Skripte auf Einsteiger-Niveau.
- **`CLAUDE.md`** hält die teuer erarbeiteten Fallstricke der DATEX-II-Feeds fest, insbesondere die
  strukturellen Abweichungen zwischen den Anbietern, die sämtlich standardkonform sind.

## Datenstand

Die in der schriftlichen Ausarbeitung berichteten Kennzahlen beruhen auf dem Auswertungslauf vom
23.07.2026 und wurden für die Arbeit festgeschrieben. Die Erhebung lief darüber hinaus weiter,
spätere Läufe liefern daher abweichende Werte.
