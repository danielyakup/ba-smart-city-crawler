#!/bin/bash
# Naechtliche Archivierung der dyn-Snapshots, pro Feed und Tag als tar.zst.
#
# Hintergrund: Im 5-Minuten-Takt fallen ~3,8 GB/Tag Rohdaten an, gepackt nur
# ~0,1 GB/Tag (92-97 % der Bytes sind reiner DATEX-Umschlag, Kompression 33x-51x).
# Ohne Archivierung ist die 79-GB-Platte nach ~17 Tagen voll -- genau das ist am
# 05.08.2026 passiert und hat die Datenluecke am 03./04.08. verursacht.
#
# Zwei Zusagen, die das Skript einhaelt:
#   1. Eine Originaldatei wird NIE geloescht, bevor ihr Vorhandensein in einem
#      lesbaren Archiv verifiziert ist.
#   2. Ein bestehendes Archiv wird NIE ueberschrieben. Liegen fuer einen Feed-Tag
#      Dateien auf der Platte, die im Archiv fehlen, wandern genau diese in ein
#      zusaetzliches Nachtrags-Archiv ({feed}_{tag}_nachtragN.tar.zst).
#
# Punkt 2 ist der Unterschied zur Vorlage ~/archiv_skripte/archiviere2.sh
# (Aufraeumlauf vom 05.08.2026): Die hat in diesem Fall das Archiv aus den
# Dateien neu gebaut, die gerade auf der Platte lagen -- und damit alles
# verloren, was frueher schon archiviert und von der Platte entfernt worden war.
# Das trifft z. B. den Fall, dass ein Tag nur teilweise wieder ausgepackt wurde
# (wie die chargecloud-Tage fuer den CSV-Neuaufbau am 05.08.2026).
#
# Weiter fuer den Dauerbetrieb geaendert: laeuft nur ueber abgeschlossene Tage,
# nutzt ein eigenes Temp-Verzeichnis statt fester /dev/shm-Pfade, schuetzt sich
# per flock gegen ueberlappende Laeufe und meldet Probleme per Exit-Code.

set -u

BASIS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DATA=$BASIS/data
ARCHIV=$DATA/archiv
MIN_FREI_MB=400

# Nur ein Archivierungslauf gleichzeitig. Ohne das koennten sich zwei Laeufe
# beim Neubau desselben Archivs in die Quere kommen.
LOCK=$DATA/.archiv.lock
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "$(date '+%F %T') Ein anderer Archivierungslauf ist aktiv -- Abbruch."
    exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

LISTE=$TMP/liste.txt
KOMBIS=$TMP/kombis.txt
BATCH=$TMP/batch.txt
IMARCHIV=$TMP/imarchiv.txt
NEU=$TMP/neu.txt
FRISCH=$TMP/frisch.txt

mkdir -p "$ARCHIV"

# Der laufende Tag wird ausgelassen: Der Crawler schreibt noch hinein, und der
# Dateiname traegt die Abrufzeit (main.py: datetime.now()), nicht die
# Last-Modified-Zeit des Pakets. Nach Mitternacht entstehen also keine Dateien
# mit dem Datum von gestern mehr -- abgeschlossene Tage sind damit stabil und
# koennen ohne Rennen mit dem Crawler gepackt werden.
HEUTE=$(date '+%Y%m%d')

echo "$(date '+%F %T') Erstelle Dateiliste (ohne den laufenden Tag $HEUTE)..."
ls -U "$DATA" | grep '_dyn_' | grep -v '^smartlab' > "$LISTE"
echo "$(date '+%F %T') $(wc -l < "$LISTE") dyn-Dateien gefunden."

sed -E 's/^(.*_dyn)_([0-9]{8})_.*/\1 \2/' "$LISTE" | sort -u \
    | awk -v heute="$HEUTE" '$2 < heute' > "$KOMBIS"
echo "$(date '+%F %T') $(wc -l < "$KOMBIS") abgeschlossene Feed/Tag-Kombinationen."

GEPACKT=0; UEBERNOMMEN=0; PROBLEME=0

while read -r FEED TAG; do
    grep -E "^${FEED}_${TAG}_" "$LISTE" | sort > "$BATCH"
    ANZ=$(wc -l < "$BATCH")
    [ "$ANZ" -eq 0 ] && continue

    FREI=$(df -Pm "$DATA" | awk 'NR==2{print $4}')
    if [ "$FREI" -lt "$MIN_FREI_MB" ]; then
        echo "$(date '+%F %T') ABBRUCH: nur ${FREI} MB frei."; exit 1
    fi

    # Schritt 1: ermitteln, was fuer diesen Feed-Tag schon archiviert ist --
    # ueber ALLE Archive des Tages, also auch frueher entstandene Nachtraege.
    : > "$IMARCHIV"
    DEFEKT=0
    for VORHANDEN in "$ARCHIV/${FEED}_${TAG}.tar.zst" "$ARCHIV/${FEED}_${TAG}_nachtrag"*.tar.zst; do
        [ -f "$VORHANDEN" ] || continue
        if ! zstd -t "$VORHANDEN" 2>/dev/null; then
            # Nicht loeschen: Das Archiv ist womoeglich die einzige Kopie von
            # Dateien, die nicht mehr auf der Platte liegen. Beiseitelegen,
            # melden, und seinen Inhalt als "nicht abgedeckt" behandeln.
            # Zeitstempel im Namen, damit ein frueher beiseitegelegtes defektes
            # Archiv nicht ueberschrieben wird.
            BEISEITE="$VORHANDEN.defekt.$(date '+%Y%m%d_%H%M%S')"
            echo "  DEFEKT: $(basename "$VORHANDEN") -- umbenannt nach $(basename "$BEISEITE"), bitte pruefen."
            mv -n "$VORHANDEN" "$BEISEITE"
            DEFEKT=1; continue
        fi
        zstd -dc "$VORHANDEN" 2>/dev/null | tar -tf - 2>/dev/null | sed 's|^\./||' >> "$IMARCHIV"
    done
    [ "$DEFEKT" -eq 1 ] && PROBLEME=$((PROBLEME+1))
    sort -u -o "$IMARCHIV" "$IMARCHIV"

    # Schritt 2: Was liegt auf der Platte, ist aber nirgends archiviert?
    comm -23 "$BATCH" "$IMARCHIV" > "$NEU"
    ANZ_NEU=$(wc -l < "$NEU")

    if [ "$ANZ_NEU" -eq 0 ]; then
        # Alles schon archiviert und verifiziert -> Originale koennen weg.
        (cd "$DATA" && xargs -d'\n' rm -f < "$BATCH")
        UEBERNOMMEN=$((UEBERNOMMEN+1))
        echo "$(date '+%T') VERIFIZIERT ${FEED}_${TAG}: $ANZ Originale entfernt (waren im Archiv) | frei: $(df -h "$DATA" | awk 'NR==2{print $4}')"
        continue
    fi

    # Schritt 3: Zielname bestimmen, ohne je etwas zu ueberschreiben.
    OUT="$ARCHIV/${FEED}_${TAG}.tar.zst"
    if [ -e "$OUT" ]; then
        N=2
        while [ -e "$ARCHIV/${FEED}_${TAG}_nachtrag${N}.tar.zst" ]; do N=$((N+1)); done
        OUT="$ARCHIV/${FEED}_${TAG}_nachtrag${N}.tar.zst"
        echo "  ${FEED}_${TAG}: $ANZ_NEU Datei(en) noch nicht archiviert -> Nachtrag $(basename "$OUT")"
    fi

    # Schritt 4: packen, pruefen, erst dann loeschen.
    if ! tar -C "$DATA" -cf - -T "$NEU" 2>/dev/null | zstd -3 -T0 -q -o "$OUT" 2>/dev/null; then
        echo "  FEHLER beim Packen ${FEED}_${TAG} -- Originale bleiben."
        rm -f "$OUT"; PROBLEME=$((PROBLEME+1)); continue
    fi
    if ! zstd -t "$OUT" 2>/dev/null; then
        echo "  FEHLER: Archiv defekt ${FEED}_${TAG} -- Originale bleiben."
        rm -f "$OUT"; PROBLEME=$((PROBLEME+1)); continue
    fi
    zstd -dc "$OUT" 2>/dev/null | tar -tf - 2>/dev/null | sed 's|^\./||' | sort > "$FRISCH"
    FEHLEND=$(comm -23 "$NEU" "$FRISCH" | wc -l)
    if [ "$FEHLEND" -ne 0 ]; then
        echo "  FEHLER: ${FEED}_${TAG} $FEHLEND Datei(en) fehlen im frischen Archiv -- Originale bleiben."
        rm -f "$OUT"; PROBLEME=$((PROBLEME+1)); continue
    fi

    # Jede Datei aus $BATCH ist jetzt entweder in einem alten Archiv (Schritt 1)
    # oder im gerade verifizierten $OUT -- damit darf der ganze Batch weg.
    (cd "$DATA" && xargs -d'\n' rm -f < "$BATCH")
    GEPACKT=$((GEPACKT+1))
    echo "$(date '+%T') OK ${FEED}_${TAG}: $ANZ_NEU Dateien -> $(du -m "$OUT" | cut -f1) MB | frei: $(df -h "$DATA" | awk 'NR==2{print $4}')"
done < "$KOMBIS"

echo "$(date '+%F %T') FERTIG. Neu gepackt: $GEPACKT | aus vorhandenem Archiv uebernommen: $UEBERNOMMEN | Probleme: $PROBLEME"
echo "verbleibende dyn-Dateien (laufender Tag): $(ls -U "$DATA" | grep -c '_dyn_')"
echo "Archivgroesse gesamt: $(du -sh "$ARCHIV" | cut -f1)"
df -h "$DATA"

[ "$PROBLEME" -eq 0 ] || exit 1
