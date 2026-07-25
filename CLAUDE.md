# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projektzweck

Bachelorarbeit-Artefakt (Action Design Research): Eine Python-Pipeline, die Ladeinfrastruktur-Daten für die Stadt Göttingen von der **Mobilithek** (deutscher National Access Point) abruft und **historisiert** — d. h. zeitgestempelte Snapshots aufbaut statt einer Momentaufnahme. Die Abdeckung wird gegen das amtliche BNetzA-Register (`bnetza_goettingen.xlsx`, 192 registrierte Ladepunkte) gemessen.

Alle methodischen Designentscheidungen werden in `ENTSCHEIDUNGSLOG.md` dokumentiert (Einträge E1–E4 vorhanden). **Bei Änderungen an der Matching-Methodik oder den Datenquellen dort einen neuen Eintrag ergänzen** — das Log fließt in die schriftliche Ausarbeitung ein. `ERKLAERUNG_CODE.md` erklärt den Code auf Einsteiger-Niveau und soll bei Skript-Änderungen mitgepflegt werden. Sprache für Code-Kommentare, Commits und Doku: Deutsch.

## Befehle

```bash
# Crawler: lädt alle Mobilithek-Abos als zeitgestempelte JSONs nach data/
# (10 s Zwangspause pro Feed; Gesamtvolumen >1 GB; Dauer mehrere Minuten)
venv/bin/python main.py

# Einzelnen Feed abrufen (main.py ist import-sicher dank __main__-Guard):
venv/bin/python -c "from main import fetch_data; fetch_data('EnBW_stat', '983100939883704320')"

# BNetzA-Abgleich: Abdeckungsquote für Göttingen (parst alle *stat*-JSONs, dauert ~1–2 min)
venv/bin/python compare_bnetza.py

# Export-Pipeline für die Stadtverwaltung (in dieser Reihenfolge; Ausgabe: auswertung/*.csv)
venv/bin/python extract_stammdaten.py    # Göttinger Ladepunkte + Stammdaten (~2 min)
venv/bin/python extract_zeitreihe.py     # Statusänderungen aus den dyn-Delta-Feeds
venv/bin/python berechne_kennzahlen.py   # Ladevorgänge + Occupancy-Kennzahlen

# Dashboard (zeigt auswertung/*.csv an; pyarrow MUSS 19.x bleiben, s. requirements.txt)
venv/bin/streamlit run dashboard.py
```

Es gibt keine Tests und keinen Linter. Authentifizierung: `certificate.p12` (PKCS12-Klientzertifikat, gitignored) + Passwort aus `MOBILITHEK_CERT_PASSWORD` — Umgebungsvariable (gesetzt in Crontab und `~/.bashrc`) mit Fallback auf eine lokale, gitignored `.env`-Datei im Projektroot; kein Fallback-Wert im Code.

## Architektur

Zwei Stufen, lose gekoppelt über den `data/`-Ordner (gitignored):

1. **`main.py` (Beschaffung):** `SUBSCRIPTIONS`-Dict (Name → Mobilithek-Abo-ID) → Abruf via `requests` + `Pkcs12Adapter` → Speichern als `data/{name}_{timestamp}.json`. Pro Anbieter zwei Feeds: `*_stat` (Stammdaten: Adresse, Leistung) und `*_dyn` (Belegung). Die Zeitstempel-Dateinamen SIND die Historisierung — alte Snapshots nie überschreiben oder löschen.
2. **`compare_bnetza.py` (Evaluation):** Liest die BNetzA-Excel (Header wird dynamisch gesucht, Göttingen-Filter über Ort + PLZ 3707x/3708x), parst dann alle statischen JSONs strukturell und matcht auf **Datensatz-Ebene** über zwei Wege: (1) normalisierte EVSE-IDs, (2) Straßenname nur bei Datensätzen, deren eigene Adresse in Göttingen liegt. Ausgabe trennt harte ID-Treffer von Adress-Treffern.
3. **Export-Pipeline (`extract_stammdaten.py` → `extract_zeitreihe.py` → `berechne_kennzahlen.py`):** Setzt die Interview-Anforderungen um (E6/E7). Zentrale Fallstricke: Die **dyn-Feeds sind Delta-Feeds** (nur Änderungen, Tesla z. B. 1 Punkt pro Snapshot; in `messageContainer` verpackt, payload ist eine LISTE; EnBW nennt den Statusblock `aegiRefillPointStatus` statt `aegiElectricChargingPointStatus`). Kennzahlen sind daher **beobachtete Untergrenzen**; Events > 12 h gelten als unplausibel (verpasste Zwischen-Updates). Göttingen-Filter passiert bei der Extraktion, `auswertung/` enthält die CSVs.

## DATEX-II-Fallstricke (teuer erarbeitet, nicht neu entdecken)

Alle Feeds nutzen DATEX II v3 / AFIR (`payload → aegiEnergyInfrastructureTablePublication → energyInfrastructureTable[] → energyInfrastructureSite[]`), aber die Anbieter weichen strukturell voneinander ab — jeweils standardkonform:

- **Adresse:** Tesla/EnBW unter `locationReference.locPointLocation`, Eco-Movement unter `locAreaLocation`, HH Energienetz eine Ebene tiefer an der **Station** (`energyInfrastructureStation[].locationReference`). `extract_addresses()` in `compare_bnetza.py` prüft alle Varianten — bei neuen Anbietern zuerst dort schauen, ob deren Variante abgedeckt ist.
- **Echte EVSE-IDs** (z. B. `DE*TSL*E0K22AF`) stehen NICHT auf Site-Ebene (dort oft nur UUIDs), sondern in `refillPoint → aegiElectricChargingPoint → idG`. Vor jedem Vergleich mit `normalize_id()` Trennzeichen entfernen.
- **Volltext-Suche über Dateien ist als Matching-Methode verworfen** (Scheintreffer durch gleichnamige Straßen anderer Städte, siehe ENTSCHEIDUNGSLOG E3/E4). Nicht wieder einführen.

## Umgang mit den Datendateien

- Die statischen JSONs sind bis zu **508 MB** groß (hhenergienetz; Eco-Movement ~467 MB). Niemals per `cat`/Read komplett ausgeben; zum Inspizieren `head -c`, gezielte Python-Snippets oder `json.load` eine Datei nach der anderen mit anschließendem `del`/`gc.collect()` (VM hat ~8 GB RAM).
- Die alten Smartlab-Dateien in `data/` sind **Belege für die Thesis** (Betreiber fehlt im amtlichen Meldekanal trotz 845 bundesweiten Standorten im Feed, davon 0 in Göttingen) — nicht löschen, obwohl die Smartlab-Abos aus `main.py` entfernt wurden.
