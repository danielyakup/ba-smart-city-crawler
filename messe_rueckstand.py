#!/usr/bin/env python3
"""Misst, wie weit die dyn-Feeds beim Abruf hinter der Publikation herhinken.

Betriebsdiagnose, kein Teil der Auswertungs-Pipeline. Hintergrund: Der Crawler
holt pro HTTP-Request genau ein Paket ab (main.py, MAX_PAKETE_PRO_FEED). Wenn
ein Feed mehr Pakete produziert, als ein Zyklus abholen kann, waechst der
Rueckstand auf. Ob das passiert, sieht man nicht am Log -- die Warnung ueber das
1000er-Limit steht auch dann da, wenn der Feed sauber mitkommt.

Der Rueckstand ist die Differenz zwischen

  * der Abrufzeit (steckt im Dateinamen, lokale Zeit Europe/Berlin) und
  * der Publikationszeit (messageGenerationTimestamp im Paket, UTC).

Aufruf:
    venv/bin/python messe_rueckstand.py                # gestern, alle Feeds
    venv/bin/python messe_rueckstand.py 20260807       # bestimmter Tag
    venv/bin/python messe_rueckstand.py 20260807 hhenergienetz
"""

import glob
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASIS = os.path.dirname(os.path.abspath(__file__))
DATEN_ORDNER = os.path.join(BASIS, "data")
ARCHIV_ORDNER = os.path.join(DATEN_ORDNER, "archiv")
PROTOKOLL = os.path.join(BASIS, "rueckstand.log")

FEEDS = ["EnBW", "Tesla", "hhenergienetz", "ecomovement", "chargecloud"]

# Die Dateinamen tragen lokale Zeit, die Publikationszeit kommt in UTC. Ueber
# ZoneInfo statt festem +02:00, damit die Zeitumstellung nicht stillschweigend
# zwei Stunden Rueckstand erfindet.
LOKAL = ZoneInfo("Europe/Berlin")

# Nur so viele Pakete pro Feed auswerten -- gleichmaessig ueber den Tag verteilt.
# Ein voller Tag hat je nach Feed bis zu 40.000 Dateien, die Stichprobe genuegt
# fuer Mittelwert und Trend.
STICHPROBE = 150

# Aus dem Rohtext gelesen statt per json.load: die statusreichen Pakete sind bis
# zu 30 MB gross, und gebraucht wird genau ein Feld.
RE_PUBLIKATION = re.compile(rb'"messageGenerationTimestamp"\s*:\s*"([^"]+)"')
RE_ABRUFZEIT = re.compile(r"_(\d{8})_(\d{6})_")


def _publikationszeit(rohdaten):
    """Zieht messageGenerationTimestamp aus einem Paket, oder None."""
    treffer = RE_PUBLIKATION.search(rohdaten)
    if not treffer:
        return None
    text = treffer.group(1).decode("utf-8", "replace")
    # Die Anbieter liefern unterschiedlich viele Nachkommastellen (Tesla
    # sekundengenau, hhenergienetz mit Nanosekunden). fromisoformat vertraegt
    # hoechstens sechs, der Rest wird abgeschnitten.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _abrufzeit(dateiname):
    """Liest die Abrufzeit aus dem Dateinamen, oder None."""
    treffer = RE_ABRUFZEIT.search(os.path.basename(dateiname))
    if not treffer:
        return None
    roh = datetime.strptime(treffer.group(1) + treffer.group(2), "%Y%m%d%H%M%S")
    return roh.replace(tzinfo=LOKAL)


def _messwerte_aus_losen_dateien(feed, tag):
    """Liest die noch nicht archivierten Snapshots aus data/."""
    muster = os.path.join(DATEN_ORDNER, f"{feed}_dyn_{tag}_*.json")
    dateien = sorted(glob.glob(muster))
    if not dateien:
        return [], 0
    schritt = max(1, len(dateien) // STICHPROBE)
    werte = []
    for pfad in dateien[::schritt]:
        try:
            with open(pfad, "rb") as f:
                rohdaten = f.read()
        except OSError:
            continue
        werte.append((pfad, rohdaten))
    return werte, len(dateien)


def _messwerte_aus_archiv(feed, tag):
    """Liest denselben Tag aus data/archiv/, falls er schon gepackt ist.

    Streamt das Archiv (tar -x ist hier zu teuer, ein Feed-Tag kann 40.000
    Dateien enthalten) und parst nur jedes n-te Mitglied.
    """
    pfad = os.path.join(ARCHIV_ORDNER, f"{feed}_dyn_{tag}.tar.zst")
    if not os.path.exists(pfad):
        return [], 0

    # Erst zaehlen, damit die Stichprobe gleichmaessig ueber den Tag streut.
    zaehlung = subprocess.run(
        f"zstd -dc {pfad!r} | tar -tf -",
        shell=True, capture_output=True, text=True,
    )
    gesamt = len([z for z in zaehlung.stdout.splitlines() if z.endswith(".json")])
    if gesamt == 0:
        return [], 0
    schritt = max(1, gesamt // STICHPROBE)

    werte = []
    prozess = subprocess.Popen(["zstd", "-dc", pfad], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=prozess.stdout, mode="r|") as archiv:
            index = 0
            for mitglied in archiv:
                if not mitglied.isfile() or not mitglied.name.endswith(".json"):
                    continue
                if index % schritt == 0:
                    quelle = archiv.extractfile(mitglied)
                    if quelle is not None:
                        werte.append((mitglied.name, quelle.read()))
                index += 1
    finally:
        if prozess.stdout:
            prozess.stdout.close()
        prozess.wait()
    return werte, gesamt


def messe_feed(feed, tag):
    """Ermittelt die Rueckstandsstatistik eines Feeds fuer einen Tag."""
    rohwerte, gesamt = _messwerte_aus_losen_dateien(feed, tag)
    quelle = "lose Dateien"
    if not rohwerte:
        rohwerte, gesamt = _messwerte_aus_archiv(feed, tag)
        quelle = "Archiv"
    if not rohwerte:
        return None

    punkte = []
    for name, rohdaten in rohwerte:
        abruf = _abrufzeit(name)
        publikation = _publikationszeit(rohdaten)
        if abruf is None or publikation is None:
            continue
        minuten = (abruf - publikation).total_seconds() / 60
        # Negative Werte hiesse: abgeholt, bevor es publiziert wurde. Das kommt
        # bei leicht auseinanderlaufenden Uhren vor und wird nicht gewertet.
        if minuten < -5:
            continue
        punkte.append((abruf.timestamp() / 3600, minuten))

    if len(punkte) < 3:
        return None

    xs = [x for x, _ in punkte]
    ys = [y for _, y in punkte]
    n = len(ys)
    mittel_x = sum(xs) / n
    mittel_y = sum(ys) / n

    # Lineare Regression von Hand -- numpy waere fuer eine Steigung uebertrieben.
    nenner = sum((x - mittel_x) ** 2 for x in xs)
    steigung = sum((x - mittel_x) * (y - mittel_y) for x, y in punkte) / nenner if nenner else 0.0

    erste = [y for x, y in punkte if x < mittel_x]
    zweite = [y for x, y in punkte if x >= mittel_x]

    return {
        "feed": feed,
        "quelle": quelle,
        "pakete_gesamt": gesamt,
        "stichprobe": n,
        "min": min(ys),
        "mittel": mittel_y,
        "max": max(ys),
        "steigung": steigung,
        "erste_haelfte": sum(erste) / len(erste) if erste else float("nan"),
        "zweite_haelfte": sum(zweite) / len(zweite) if zweite else float("nan"),
    }


def main():
    argumente = sys.argv[1:]
    if argumente and re.fullmatch(r"\d{8}", argumente[0]):
        tag = argumente[0]
        argumente = argumente[1:]
    elif argumente and argumente[0] == "heute":
        # Fuer den Cron-Lauf um 23:50: so bleibt die Crontab-Zeile frei von
        # $(date +%Y%m%d), wo jedes % einzeln escaped werden muesste.
        tag = datetime.now(LOKAL).strftime("%Y%m%d")
        argumente = argumente[1:]
    else:
        tag = (datetime.now(LOKAL) - timedelta(days=1)).strftime("%Y%m%d")
    feeds = argumente or FEEDS

    kopf = f"Rueckstand dyn-Feeds fuer {tag[6:8]}.{tag[4:6]}.{tag[0:4]}"
    print(kopf)
    print("=" * len(kopf))
    print(f"{'Feed':<16}{'Pakete':>9}{'Min':>8}{'Mittel':>9}{'Max':>8}{'Trend/h':>10}  Quelle")

    zeilen = []
    for feed in feeds:
        ergebnis = messe_feed(feed, tag)
        if ergebnis is None:
            print(f"{feed:<16}{'--':>9}   keine auswertbaren Pakete gefunden")
            continue
        print(
            f"{ergebnis['feed']:<16}"
            f"{ergebnis['pakete_gesamt']:>9}"
            f"{ergebnis['min']:>7.1f}m"
            f"{ergebnis['mittel']:>8.1f}m"
            f"{ergebnis['max']:>7.1f}m"
            f"{ergebnis['steigung']:>+9.2f}m  "
            f"{ergebnis['quelle']}"
        )
        print(
            f"{'':<16}  1. Tageshaelfte {ergebnis['erste_haelfte']:.1f}m | "
            f"2. Haelfte {ergebnis['zweite_haelfte']:.1f}m | "
            f"Stichprobe {ergebnis['stichprobe']}"
        )
        zeilen.append(
            f"{tag}\t{ergebnis['feed']}\t{ergebnis['pakete_gesamt']}\t"
            f"{ergebnis['min']:.1f}\t{ergebnis['mittel']:.1f}\t{ergebnis['max']:.1f}\t"
            f"{ergebnis['steigung']:+.2f}"
        )

    if zeilen:
        # Eine Zeile pro Feed und Tag, damit sich ueber mehrere Tage ein Trend
        # ablesen laesst. Spalten: Tag, Feed, Pakete, Min, Mittel, Max, Trend/h.
        with open(PROTOKOLL, "a", encoding="utf-8") as f:
            for zeile in zeilen:
                f.write(zeile + "\n")
        print(f"\nAngehaengt an {os.path.relpath(PROTOKOLL, BASIS)}")


if __name__ == "__main__":
    main()
