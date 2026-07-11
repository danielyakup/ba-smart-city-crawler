"""Berechnet die Kennzahlen aus der Status-Zeitreihe (Interview-Anforderungen).

Schritt 3 der Export-Pipeline: Aus den beobachteten Statusänderungen werden
Ladevorgang-Events segmentiert und je Ladepunkt aggregiert — genau die
Kennzahlen, die im Experteninterview (23.06.2026, Block B) gefordert wurden:
Occupancy Rate, Anzahl Ladevorgänge, durchschnittliche Ladedauer,
Verteilung über Wochentag/Wochenende und Tageszeit.

WICHTIGE EINSCHRÄNKUNG (siehe ENTSCHEIDUNGSLOG E7): Die dyn-Feeds sind
Delta-Feeds und werden alle 30 Minuten abgerufen — Statusänderungen zwischen
zwei Abrufen können verloren gehen. Alle Kennzahlen sind daher BEOBACHTETE
UNTERGRENZEN der tatsächlichen Nutzung, keine vollständige Zählung.

Voraussetzung: auswertung/statusaenderungen_goettingen.csv + stammdaten_goettingen.csv
Aufruf:        venv/bin/python berechne_kennzahlen.py
Ausgabe:       auswertung/ladevorgaenge_goettingen.csv   (Event-Ebene)
               auswertung/kennzahlen_ladepunkte.csv      (Aggregat-Ebene)
"""

import os
import pandas as pd

ORDNER = "auswertung"

# Welche DATEX-II-Statuswerte bedeuten "Ladepunkt ist belegt"?
BELEGT = {"charging", "occupied", "reserved"}
# Diese Werte beenden eine Belegung, zählen aber nicht als Nutzung
AUSSER_BETRIEB = {"outOfOrder", "inoperative", "outOfService"}

# Plausibilitätsgrenze für die Dauer eines einzelnen Ladevorgangs.
# Begründung (siehe ENTSCHEIDUNGSLOG E7): Weil die Delta-Feeds nur alle
# 30 Minuten abgerufen werden, gehen Zwischen-Updates verloren — dann wirkt
# ein Ladepunkt tagelang "belegt", obwohl dazwischen unbeobachtete Wechsel
# lagen. 12 h decken auch lange Übernacht-AC-Ladungen ab; alles darüber wird
# als unplausibel markiert und fließt NICHT in die Kennzahlen ein
# (bleibt aber gekennzeichnet im Event-Export nachvollziehbar).
MAX_PLAUSIBLE_DAUER_MIN = 12 * 60


def lade_zeitreihe():
    """Liest die Statusänderungen und parst die Zeitstempel (die Anbieter
    liefern unterschiedliche ISO-Formate, teils mit/ohne Zeitzone —
    utc=True normalisiert alles auf UTC)."""
    df = pd.read_csv(
        os.path.join(ORDNER, "statusaenderungen_goettingen.csv"),
        sep=";", encoding="utf-8-sig",
    )
    df["zeit"] = pd.to_datetime(df["geaendert_am"], utc=True, format="mixed", errors="coerce")
    # Ohne auswertbaren Zeitstempel ist keine Dauer-Berechnung möglich
    df = df.dropna(subset=["zeit"]).sort_values(["evse_id", "zeit"])
    return df


def segmentiere_ladevorgaenge(df):
    """Baut aus den Status-Übergängen Ladevorgang-Events: Ein Ladevorgang
    beginnt mit dem Wechsel auf einen Belegt-Status und endet mit der
    nächsten beobachteten Änderung weg davon. Aufeinanderfolgende gleiche
    Status werden übersprungen (Deltas können z. B. Preis-Updates enthalten,
    die den Status wiederholen)."""
    events = []
    for evse_id, gruppe in df.groupby("evse_id"):
        start = None
        vorheriger_status = None
        for _, zeile in gruppe.iterrows():
            status = zeile["status"]
            if status == vorheriger_status:
                continue  # keine echte Änderung
            if status in BELEGT and start is None:
                start = zeile["zeit"]
            elif status not in BELEGT and start is not None:
                dauer_min = (zeile["zeit"] - start).total_seconds() / 60
                events.append({
                    "evse_id": evse_id,
                    "anbieter": zeile["anbieter"],
                    "start": start,
                    "ende": zeile["zeit"],
                    "dauer_minuten": round(dauer_min, 1),
                    # Ende durch Störung statt normaler Freigabe? Für Mathias
                    # erkennbar, weil solche "Ladevorgänge" verzerrt sein können
                    "ende_status": status,
                    "plausibel": dauer_min <= MAX_PLAUSIBLE_DAUER_MIN,
                })
                start = None
            vorheriger_status = status
        # Ein zum Beobachtungsende noch laufender Ladevorgang bleibt
        # bewusst unberücksichtigt (Ende unbekannt -> Dauer nicht berechenbar)
    return pd.DataFrame(events)


def aggregiere_kennzahlen(events, zeitreihe, stammdaten):
    """Aggregiert die Interview-Kennzahlen je Ladepunkt und joint die
    Stammdaten (Adresse, Betreiber, Leistung) dazu.

    Das Beobachtungsfenster wird über die ABRUF-Zeitpunkte (erfasst_am)
    bestimmt, nicht über die Anbieter-Zeitstempel: Delta-Feeds melden beim
    ersten Abruf auch Altzustände, deren lastUpdated Wochen vor dem
    Crawling-Start liegen kann — die würden das Fenster künstlich strecken."""
    abruf = pd.to_datetime(zeitreihe["erfasst_am"], utc=True, errors="coerce")
    beobachtung_start = abruf.min()
    beobachtung_ende = abruf.max()
    fenster_stunden = (beobachtung_ende - beobachtung_start).total_seconds() / 3600
    fenster_tage = fenster_stunden / 24

    if not events.empty:
        events = events[events["plausibel"]].copy()

    if not events.empty:
        # Für Tageszeit/Wochentag zählt die LOKALE Zeit (die Zeitreihe ist UTC;
        # "nachts" um 23 Uhr deutscher Zeit wäre in UTC sonst 21 Uhr)
        start_lokal = events["start"].dt.tz_convert("Europe/Berlin")
        events["wochenende"] = start_lokal.dt.dayofweek >= 5
        events["stunde"] = start_lokal.dt.hour

        agg = events.groupby("evse_id").agg(
            ladevorgaenge=("start", "count"),
            belegt_stunden=("dauer_minuten", lambda m: round(m.sum() / 60, 2)),
            mittlere_dauer_min=("dauer_minuten", lambda m: round(m.mean(), 1)),
            ladevorgaenge_wochenende=("wochenende", "sum"),
            ladevorgaenge_nachts=("stunde", lambda h: int(((h < 6) | (h >= 22)).sum())),
        ).reset_index()
        agg["ladevorgaenge_werktags"] = agg["ladevorgaenge"] - agg["ladevorgaenge_wochenende"]
        agg["ladevorgaenge_pro_tag"] = (agg["ladevorgaenge"] / fenster_tage).round(2)
        # Occupancy Rate: beobachtete Belegungszeit im Verhältnis zum
        # gesamten Beobachtungsfenster (Untergrenze, s. Docstring)
        agg["occupancy_rate_prozent"] = (agg["belegt_stunden"] / fenster_stunden * 100).round(2)
    else:
        agg = pd.DataFrame(columns=["evse_id"])

    # Stammdaten dazu — auch Ladepunkte OHNE beobachtete Ladevorgänge bleiben
    # in der Tabelle (ladevorgaenge=0): "keine Beobachtung" ist ein Befund,
    # kein fehlender Datensatz
    kennzahlen = stammdaten.merge(agg, on="evse_id", how="left")
    zahl_spalten = [c for c in agg.columns if c != "evse_id"]
    kennzahlen[zahl_spalten] = kennzahlen[zahl_spalten].fillna(0)

    return kennzahlen, beobachtung_start, beobachtung_ende


if __name__ == "__main__":
    print("Berechne Kennzahlen aus der Status-Zeitreihe...\n")

    zeitreihe = lade_zeitreihe()
    stammdaten = pd.read_csv(
        os.path.join(ORDNER, "stammdaten_goettingen.csv"),
        sep=";", encoding="utf-8-sig",
    )

    events = segmentiere_ladevorgaenge(zeitreihe)
    kennzahlen, start, ende = aggregiere_kennzahlen(events, zeitreihe, stammdaten)

    # Event-Ebene speichern (Export-Ebene 2 aus dem Interview)
    events_pfad = os.path.join(ORDNER, "ladevorgaenge_goettingen.csv")
    events.to_csv(events_pfad, sep=";", index=False, encoding="utf-8-sig")

    # Aggregat-Ebene speichern (Export-Ebene 3)
    kennzahlen_pfad = os.path.join(ORDNER, "kennzahlen_ladepunkte.csv")
    kennzahlen.to_csv(kennzahlen_pfad, sep=";", index=False, encoding="utf-8-sig")

    plausible = events[events["plausibel"]] if not events.empty else events
    print(f"Beobachtungsfenster: {start:%d.%m.%Y %H:%M} – {ende:%d.%m.%Y %H:%M} (UTC)")
    print(f"Beobachtete Ladevorgänge: {len(events)} "
          f"(davon plausibel ≤ 12 h: {len(plausible)}, "
          f"als unplausibel markiert: {len(events) - len(plausible)})")
    if not plausible.empty:
        print(f"Mittlere Dauer (plausible): {plausible['dauer_minuten'].mean():.0f} min, "
              f"Median: {plausible['dauer_minuten'].median():.0f} min")
        print(f"Ladepunkte mit mind. einem plausiblen Ladevorgang: "
              f"{plausible['evse_id'].nunique()} von {len(stammdaten)}")
    print(f"\nGespeichert: {events_pfad}")
    print(f"Gespeichert: {kennzahlen_pfad}")
