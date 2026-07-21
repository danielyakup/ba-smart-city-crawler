#!/bin/bash
# Baut die Export-CSVs (auswertung/*.csv) aus den aktuell vorhandenen data/-Snapshots
# neu auf, damit das Dashboard ohne manuellen Skriptaufruf aktuell bleibt.
# Eigenes Lock, da ein Lauf bei wachsender Datenmenge laenger als der Cron-Takt
# dauern kann -- verhindert ueberlappende Auswertungs-Laeufe.

cd /home/cloud/Projekte/BA_Ladesaeulen_Crawler_

LOCK_DATEI="data/.auswertung.lock"

if [ -f "$LOCK_DATEI" ]; then
    ALTE_PID=$(cat "$LOCK_DATEI")
    if kill -0 "$ALTE_PID" 2>/dev/null; then
        echo "$(date): Vorheriger Auswertungslauf (PID $ALTE_PID) noch aktiv, breche ab."
        exit 0
    fi
    echo "$(date): Verwaiste Lock-Datei gefunden, wird ersetzt."
fi
echo $$ > "$LOCK_DATEI"
trap 'rm -f "$LOCK_DATEI"' EXIT

echo "$(date): Auswertung gestartet."
venv/bin/python extract_stammdaten.py
venv/bin/python extract_zeitreihe.py
venv/bin/python berechne_kennzahlen.py
echo "$(date): Auswertung fertig."
