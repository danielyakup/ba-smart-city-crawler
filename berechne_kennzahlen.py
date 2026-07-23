"""Berechnet die Kennzahlen aus der Status-Zeitreihe (Interview-Anforderungen).

Schritt 3 der Export-Pipeline: Aus den beobachteten Statusänderungen werden
Ladevorgang-Events segmentiert und je Ladepunkt aggregiert — genau die
Kennzahlen, die im Experteninterview (23.06.2026, Block B) gefordert wurden:
Occupancy Rate, Anzahl Ladevorgänge, durchschnittliche Ladedauer,
Verteilung über Wochentag/Wochenende und Tageszeit.

Zusätzlich (siehe ENTSCHEIDUNGSLOG E10) werden AUSSER_BETRIEB-Phasen separat
segmentiert: "nicht belegt" heißt nicht automatisch "verfügbar" — ein
Ladepunkt kann auch defekt sein. occupancy_rate_prozent (Nutzung) und
ausfallquote_prozent (Störung) werden daher getrennt ausgewiesen. Seit E16
gibt es zusätzlich unklar_quote_prozent: Zeit aus als unplausibel verworfenen
Ladevorgängen (E15) landete vorher unbeabsichtigt im Verfügbarkeits-Rest,
obwohl der Punkt nachweislich belegt war — jetzt ein eigener dritter Anteil.
verfuegbar_prozent ist der verbleibende Rest des Beobachtungsfensters
(Nutzung + Störung + Unklar abgezogen).

WICHTIGE EINSCHRÄNKUNG (siehe ENTSCHEIDUNGSLOG E7/E8): Die dyn-Feeds sind
Delta-Feeds und werden alle 5 Minuten abgerufen (bis 11.07.2026: 30 Minuten)
— Statusänderungen zwischen zwei Abrufen können verloren gehen. Alle
Kennzahlen sind daher BEOBACHTETE UNTERGRENZEN der tatsächlichen Nutzung,
keine vollständige Zählung.

ZWEI BEOBACHTUNGSFENSTER (siehe ENTSCHEIDUNGSLOG E14): Absolute Zahlen
(ladevorgaenge, belegt_stunden, ausfaelle_anzahl, ausser_betrieb_stunden,
mittlere_dauer_min) und occupancy_rate_prozent laufen übers GESAMTE Fenster
seit Crawling-Beginn (12.06.2026). ausfallquote_prozent, verfuegbar_prozent,
ladevorgaenge_pro_tag und occupancy_rate_verlaesslich_prozent laufen dagegen
NUR übers VERLÄSSLICHE Fenster seit dem E12-Fix (siehe VERLAESSLICHES_FENSTER_START
unten) — sonst würden Prozent-Kennzahlen mit dem langen Gesamtfenster als
Nenner künstlich auf einen Bruchteil gedrückt, weil der Großteil davon aus
Wochen mit unvollständiger Datengrundlage besteht (Tesla komplett ausgefallen
bis E12, hhenergienetz durch einen weiteren Bug bis E13, 30-Minuten-Raster
bis E8).

Voraussetzung: auswertung/statusaenderungen_goettingen.csv + stammdaten_goettingen.csv
Aufruf:        venv/bin/python berechne_kennzahlen.py
Ausgabe:       auswertung/ladevorgaenge_goettingen.csv   (Event-Ebene, Nutzung)
               auswertung/ausfaelle_goettingen.csv       (Event-Ebene, Störung)
               auswertung/kennzahlen_ladepunkte.csv      (Aggregat-Ebene)
"""

import os
import pandas as pd

ORDNER = "auswertung"

# Welche DATEX-II-Statuswerte bedeuten "Ladepunkt ist belegt"?
BELEGT = {"charging", "occupied", "reserved"}

# Diese Werte beenden eine Belegung, zählen aber nicht als Nutzung.
# ENTSCHEIDUNGSLOG E17: Beim Schreiben von Kapitel 2.3 wurde die vollständige
# RefillPointStatusEnum aus der Profildokumentation bekannt: available, blocked,
# charging, faulted, inoperative, occupied, outOfOrder, outOfStock, planned,
# removed, reserved, unavailable, unknown. Abgleich gegen die echten Daten ergab
# zwei Korrekturen: "outOfService" kam in keiner einzigen Zeile vor (0 von 3.995
# AUSSER_BETRIEB-Kandidaten), der tatsächliche Enum-Wert lautet "outOfStock" --
# das war also toter Code. Außerdem fehlten "faulted", "blocked" und
# "unavailable", obwohl sie in den echten Daten auftreten (2, 3 bzw. 31 Mal) und
# semantisch klar "nicht nutzbar" bedeuten -- ohne diese Ergänzung wären sie
# still als "verfügbar" durchgegangen, obwohl der Punkt gerade nicht nutzbar war.
# "planned"/"removed" bewusst NICHT aufgenommen: Das sind Lebenszyklus-Zustände
# (noch nicht bzw. nicht mehr in Betrieb), keine temporäre Störung eines
# bestehenden Punkts, und kommen in den Daten aktuell nicht vor. "unknown"
# bleibt ebenfalls bewusst außen vor -- der Zustand ist per Definition nicht
# feststellbar, weder Nutzung noch Störung zuzuordnen.
AUSSER_BETRIEB = {"outOfOrder", "inoperative", "faulted", "outOfStock", "blocked", "unavailable"}

# Plausibilitätsgrenze für die Dauer eines einzelnen Ladevorgangs — seit
# ENTSCHEIDUNGSLOG E15 getrennt nach Stromart, vorher ein einheitlicher Wert.
# Begründung (siehe E7/E8): Weil die Delta-Feeds nur alle 5 Minuten abgerufen
# werden (bis 11.07.2026: 30 Minuten), gehen Zwischen-Updates verloren — dann
# wirkt ein Ladepunkt stundenlang "belegt", obwohl dazwischen unbeobachtete
# Wechsel lagen. AC deckt mit 12 h auch lange Übernacht-Ladungen ab (durch
# Stichprobe bestätigt: Sessions nahe der Grenze enden sauber mit "available"
# und folgen dem Muster abends-rein/morgens-raus). DC-Schnellladung ist
# physikalisch nie so lang — die Grenze liegt daher niedriger, was zugleich
# einen bekannten Artefakt-Fall auffängt: Eco-Movement liefert laut E8
# verzögerte lastUpdated-Werte, die bei DC-Punkten sonst mehrstündige
# Scheinladungen erzeugen. Alles über der jeweiligen Grenze wird als
# unplausibel markiert und fließt NICHT in die Kennzahlen ein (bleibt aber im
# Event-Export nachvollziehbar gekennzeichnet).
MAX_PLAUSIBLE_DAUER_AC_MIN = 12 * 60
MAX_PLAUSIBLE_DAUER_DC_MIN = 3 * 60

# Für AUSSER_BETRIEB gilt bewusst KEINE Plausibilitätsgrenze (ENTSCHEIDUNGSLOG
# E10): Die 12h-Grenze bei Ladevorgängen beruht darauf, dass reale Ladungen
# (auch Übernacht-AC) selten länger dauern. Ein defekter Ladepunkt kann aber
# durchaus tage- oder wochenlang außer Betrieb bleiben — eine lange Ausfallzeit
# ist plausibel, keine verpasste Statusänderung.

# Beginn des "verlässlichen Fensters" (ENTSCHEIDUNGSLOG E14): Zeitpunkt des
# E12-Fix-Deployments (main.py holt seither pro Feed vollständig alle im
# Mobilithek-Puffer wartenden Delta-Pakete statt nur des letzten). Vor diesem
# Zeitpunkt fehlten je nach Anbieter Statusänderungen strukturell (Tesla
# komplett bis E12, hhenergienetz durch einen weiteren Bug bis E13) — das
# Gesamtfenster (seit 12.06.2026) enthält daher überwiegend Wochen mit
# unvollständiger Datengrundlage. Prozent-Kennzahlen, die eine Fensterlänge
# als Nenner nutzen, würden dadurch künstlich auf einen Bruchteil ihres
# tatsächlichen Werts gedrückt (siehe E14 für die quantifizierte Herleitung:
# ca. Faktor 9 bei der Occupancy Rate). Deshalb rechnen ausfallquote_prozent,
# verfuegbar_prozent und ladevorgaenge_pro_tag ab sofort NUR noch über dieses
# kürzere, aber durchgängig verlässliche Fenster; occupancy_rate_prozent
# bleibt zusätzlich auch übers Gesamtfenster erhalten (occupancy_rate_verlaesslich_prozent
# ist das Pendant übers verlässliche Fenster) — zum Vergleich, weil die
# Occupancy Rate die zentrale Interview-Kennzahl ist (Block B, 23.06.2026).
VERLAESSLICHES_FENSTER_START = pd.Timestamp("2026-07-21T17:48:21", tz="UTC")


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


def segmentiere_intervalle(df, status_menge, schwelle_fn):
    """Baut aus den Status-Übergängen Intervall-Events: Ein Intervall beginnt
    mit dem Wechsel auf einen Status aus `status_menge` und endet mit der
    nächsten beobachteten Änderung weg davon. Aufeinanderfolgende gleiche
    Status werden übersprungen (Deltas können z. B. Preis-Updates enthalten,
    die den Status wiederholen). Wird sowohl für Ladevorgänge (BELEGT) als
    auch für Ausfallzeiten (AUSSER_BETRIEB) verwendet — mit jeweils eigener
    Plausibilitätsgrenze (siehe ENTSCHEIDUNGSLOG E7/E10/E15).

    `schwelle_fn(evse_id)` liefert die Plausibilitätsgrenze in Minuten für
    diesen Ladepunkt, oder `None` für "jede Dauer gilt als plausibel"
    (so für Ausfälle, siehe E10). Seit E15 je nach Stromart unterschiedlich
    (Ladevorgänge), damit AC-Übernachtladungen nicht mit demselben Maßstab
    gemessen werden wie DC-Schnellladung."""
    events = []
    for evse_id, gruppe in df.groupby("evse_id"):
        max_plausible_min = schwelle_fn(evse_id)
        start = None
        vorheriger_status = None
        for _, zeile in gruppe.iterrows():
            status = zeile["status"]
            if status == vorheriger_status:
                continue  # keine echte Änderung
            if status in status_menge and start is None:
                start = zeile["zeit"]
            elif status not in status_menge and start is not None:
                dauer_min = (zeile["zeit"] - start).total_seconds() / 60
                events.append({
                    "evse_id": evse_id,
                    "anbieter": zeile["anbieter"],
                    "start": start,
                    "ende": zeile["zeit"],
                    "dauer_minuten": round(dauer_min, 1),
                    # Welcher Status hat das Intervall beendet? Für Mathias
                    # erkennbar, weil z. B. ein Ladevorgang, der mit einer
                    # Störung endet, verzerrt sein kann
                    "ende_status": status,
                    "plausibel": max_plausible_min is None or dauer_min <= max_plausible_min,
                })
                start = None
            vorheriger_status = status
        # Ein zum Beobachtungsende noch laufendes Intervall bleibt bewusst
        # unberücksichtigt (Ende unbekannt -> Dauer nicht berechenbar)
    return pd.DataFrame(events)


def segmentiere_ladevorgaenge(df, strom_art_je_punkt):
    """Ladevorgänge: Intervalle mit Status aus BELEGT. Plausibilitätsgrenze
    je nach Stromart des Ladepunkts (E15); unbekannte/fehlende Stromart
    (sollte nicht vorkommen) fällt auf die großzügigere AC-Grenze zurück."""
    def schwelle(evse_id):
        art = strom_art_je_punkt.get(evse_id, "AC")
        return MAX_PLAUSIBLE_DAUER_DC_MIN if art == "DC" else MAX_PLAUSIBLE_DAUER_AC_MIN
    return segmentiere_intervalle(df, BELEGT, schwelle)


def segmentiere_ausfaelle(df):
    """Ausfallzeiten: Intervalle mit Status aus AUSSER_BETRIEB (keine
    Plausibilitätsgrenze, siehe Begründung oben)."""
    return segmentiere_intervalle(df, AUSSER_BETRIEB, lambda evse_id: None)


def aggregiere_kennzahlen(events, ausfaelle, zeitreihe, stammdaten):
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

    # Verlässliches Fenster (ENTSCHEIDUNGSLOG E14): kürzerer, aber
    # durchgängig vollständig erfasster Ausschnitt seit dem E12-Fix.
    verlaesslich_start = max(VERLAESSLICHES_FENSTER_START, beobachtung_start)
    verlaesslich_stunden = (beobachtung_ende - verlaesslich_start).total_seconds() / 3600
    verlaesslich_tage = verlaesslich_stunden / 24

    # Als unplausibel markierte Ladevorgänge (E15) vor dem Verwerfen sichern
    # (ENTSCHEIDUNGSLOG E16): Sie wurden bisher schlicht aus der Aggregation
    # entfernt und flossen dadurch über die Restformel unbeabsichtigt in
    # verfuegbar_prozent ein, obwohl der Ladepunkt in dieser Zeit nachweislich
    # NICHT frei war (er meldete durchgehend charging/occupied, nur die Dauer
    # gilt als unglaubwürdig lang). Diese Zeit bekommt jetzt einen eigenen,
    # dritten Anteil (unklar_quote_prozent) statt stillschweigend als
    # "verfügbar" gezählt zu werden.
    unplausibel = events[~events["plausibel"]].copy() if not events.empty else events

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
            # Median zusätzlich zum Mittelwert (ENTSCHEIDUNGSLOG E15): Die
            # Dauerverteilung ist rechtsschief (wenige sehr lange Übernacht-
            # Ladungen ziehen den Mittelwert nach oben) — der Median ist der
            # robustere "typische" Wert.
            median_dauer_min=("dauer_minuten", lambda m: round(m.median(), 1)),
            ladevorgaenge_wochenende=("wochenende", "sum"),
            ladevorgaenge_nachts=("stunde", lambda h: int(((h < 6) | (h >= 22)).sum())),
        ).reset_index()
        agg["ladevorgaenge_werktags"] = agg["ladevorgaenge"] - agg["ladevorgaenge_wochenende"]
        # Occupancy Rate übers GESAMTE Beobachtungsfenster (seit 12.06.2026) —
        # bleibt zum Vergleich erhalten, ist aber wegen der vielen Wochen
        # unvollständiger Datengrundlage eine stark verwässerte Untergrenze
        # (siehe E14: rund Faktor 9 niedriger als übers verlässliche Fenster).
        agg["occupancy_rate_prozent"] = (agg["belegt_stunden"] / fenster_stunden * 100).round(2)

        # Dieselbe Aggregation, aber nur für Ladevorgänge, die im
        # verlässlichen Fenster STARTEN — Grundlage für die beiden Kennzahlen,
        # die ab E14 ausschließlich darauf beruhen.
        events_verlaesslich = events[events["start"] >= verlaesslich_start]
        if not events_verlaesslich.empty:
            agg_verlaesslich = events_verlaesslich.groupby("evse_id").agg(
                ladevorgaenge_verlaesslich=("start", "count"),
                belegt_stunden_verlaesslich=("dauer_minuten", lambda m: m.sum() / 60),
            ).reset_index()
        else:
            agg_verlaesslich = pd.DataFrame(columns=["evse_id", "ladevorgaenge_verlaesslich", "belegt_stunden_verlaesslich"])
        agg = agg.merge(agg_verlaesslich, on="evse_id", how="left")
        agg[["ladevorgaenge_verlaesslich", "belegt_stunden_verlaesslich"]] = (
            agg[["ladevorgaenge_verlaesslich", "belegt_stunden_verlaesslich"]].fillna(0)
        )
        agg["ladevorgaenge_pro_tag"] = (agg["ladevorgaenge_verlaesslich"] / verlaesslich_tage).round(2)
        agg["occupancy_rate_verlaesslich_prozent"] = (
            agg["belegt_stunden_verlaesslich"] / verlaesslich_stunden * 100
        ).round(2)
        agg = agg.drop(columns=["ladevorgaenge_verlaesslich", "belegt_stunden_verlaesslich"])
    else:
        agg = pd.DataFrame(columns=[
            "evse_id", "ladevorgaenge", "belegt_stunden", "mittlere_dauer_min", "median_dauer_min",
            "ladevorgaenge_wochenende", "ladevorgaenge_nachts", "ladevorgaenge_werktags",
            "occupancy_rate_prozent", "ladevorgaenge_pro_tag", "occupancy_rate_verlaesslich_prozent",
        ])

    if not ausfaelle.empty:
        ausfall_agg = ausfaelle.groupby("evse_id").agg(
            ausfaelle_anzahl=("start", "count"),
            ausser_betrieb_stunden=("dauer_minuten", lambda m: round(m.sum() / 60, 2)),
        ).reset_index()
        ausfaelle_verlaesslich = ausfaelle[ausfaelle["start"] >= verlaesslich_start]
        if not ausfaelle_verlaesslich.empty:
            ausfall_agg_verlaesslich = ausfaelle_verlaesslich.groupby("evse_id").agg(
                ausser_betrieb_stunden_verlaesslich=("dauer_minuten", lambda m: m.sum() / 60),
            ).reset_index()
        else:
            ausfall_agg_verlaesslich = pd.DataFrame(columns=["evse_id", "ausser_betrieb_stunden_verlaesslich"])
        ausfall_agg = ausfall_agg.merge(ausfall_agg_verlaesslich, on="evse_id", how="left")
        ausfall_agg["ausser_betrieb_stunden_verlaesslich"] = ausfall_agg["ausser_betrieb_stunden_verlaesslich"].fillna(0)
    else:
        ausfall_agg = pd.DataFrame(columns=["evse_id", "ausfaelle_anzahl", "ausser_betrieb_stunden", "ausser_betrieb_stunden_verlaesslich"])

    # Unplausible Ladevorgänge (E15/E16): dieselbe Aggregation wie oben, aber
    # nur für die als unplausibel verworfenen Sessions, die im verlässlichen
    # Fenster STARTEN — Grundlage für unklar_quote_prozent.
    if not unplausibel.empty:
        unplausibel_verlaesslich = unplausibel[unplausibel["start"] >= verlaesslich_start]
        if not unplausibel_verlaesslich.empty:
            unklar_agg = unplausibel_verlaesslich.groupby("evse_id").agg(
                unklar_stunden_verlaesslich=("dauer_minuten", lambda m: m.sum() / 60),
            ).reset_index()
        else:
            unklar_agg = pd.DataFrame(columns=["evse_id", "unklar_stunden_verlaesslich"])
    else:
        unklar_agg = pd.DataFrame(columns=["evse_id", "unklar_stunden_verlaesslich"])

    # Stammdaten dazu — auch Ladepunkte OHNE beobachtete Ladevorgänge/Ausfälle
    # bleiben in der Tabelle (ladevorgaenge=0): "keine Beobachtung" ist ein
    # Befund, kein fehlender Datensatz
    kennzahlen = (
        stammdaten.merge(agg, on="evse_id", how="left")
        .merge(ausfall_agg, on="evse_id", how="left")
        .merge(unklar_agg, on="evse_id", how="left")
    )
    zahl_spalten = [c for c in list(agg.columns) + list(ausfall_agg.columns) + list(unklar_agg.columns) if c != "evse_id"]
    kennzahlen[zahl_spalten] = kennzahlen[zahl_spalten].fillna(0)

    # Ausfallquote, Unklar-Quote und Verfügbarkeit (ENTSCHEIDUNGSLOG E10/E16)
    # rechnen seit E14 NUR noch übers verlässliche Fenster — sonst wären die
    # Werte (Zähler aus dem kurzen verlässlichen Fenster, Nenner aus dem
    # langen Gesamtfenster) nicht konsistent zueinander. clip(lower=0) fängt
    # Rundungsartefakte ab.
    kennzahlen["ausfallquote_prozent"] = (
        kennzahlen["ausser_betrieb_stunden_verlaesslich"] / verlaesslich_stunden * 100
    ).round(2)
    # unklar_quote_prozent (E16): Zeit aus als unplausibel verworfenen
    # Ladevorgängen — weder als Nutzung noch als Ausfall zählbar, aber
    # nachweislich NICHT frei verfügbar. Wird explizit ausgewiesen statt
    # stillschweigend in verfuegbar_prozent zu verschwinden.
    kennzahlen["unklar_quote_prozent"] = (
        kennzahlen["unklar_stunden_verlaesslich"] / verlaesslich_stunden * 100
    ).round(2)
    kennzahlen = kennzahlen.drop(columns=["ausser_betrieb_stunden_verlaesslich", "unklar_stunden_verlaesslich"])
    kennzahlen["verfuegbar_prozent"] = (
        100 - kennzahlen["occupancy_rate_verlaesslich_prozent"]
        - kennzahlen["ausfallquote_prozent"] - kennzahlen["unklar_quote_prozent"]
    ).clip(lower=0).round(2)

    return kennzahlen, beobachtung_start, beobachtung_ende, verlaesslich_start


if __name__ == "__main__":
    print("Berechne Kennzahlen aus der Status-Zeitreihe...\n")

    zeitreihe = lade_zeitreihe()
    stammdaten = pd.read_csv(
        os.path.join(ORDNER, "stammdaten_goettingen.csv"),
        sep=";", encoding="utf-8-sig",
    )

    # Stromart je Ladepunkt für die getrennte Plausibilitätsgrenze (E15)
    strom_art_je_punkt = dict(zip(stammdaten["evse_id"], stammdaten["strom_art"]))

    events = segmentiere_ladevorgaenge(zeitreihe, strom_art_je_punkt)
    ausfaelle = segmentiere_ausfaelle(zeitreihe)
    kennzahlen, start, ende, verlaesslich_start = aggregiere_kennzahlen(events, ausfaelle, zeitreihe, stammdaten)

    # Event-Ebene speichern (Export-Ebene 2 aus dem Interview: Nutzung)
    events_pfad = os.path.join(ORDNER, "ladevorgaenge_goettingen.csv")
    events.to_csv(events_pfad, sep=";", index=False, encoding="utf-8-sig")

    # Event-Ebene Ausfälle (ENTSCHEIDUNGSLOG E10: Störung getrennt von Nutzung)
    ausfaelle_pfad = os.path.join(ORDNER, "ausfaelle_goettingen.csv")
    ausfaelle.to_csv(ausfaelle_pfad, sep=";", index=False, encoding="utf-8-sig")

    # Aggregat-Ebene speichern (Export-Ebene 3)
    kennzahlen_pfad = os.path.join(ORDNER, "kennzahlen_ladepunkte.csv")
    kennzahlen.to_csv(kennzahlen_pfad, sep=";", index=False, encoding="utf-8-sig")

    plausible = events[events["plausibel"]] if not events.empty else events
    print(f"Beobachtungsfenster (gesamt): {start:%d.%m.%Y %H:%M} – {ende:%d.%m.%Y %H:%M} (UTC)")
    print(f"Verlässliches Fenster (E14, seit E12-Fix): {verlaesslich_start:%d.%m.%Y %H:%M} – "
          f"{ende:%d.%m.%Y %H:%M} (UTC) — Basis für ausfallquote_prozent, "
          f"verfuegbar_prozent, ladevorgaenge_pro_tag, occupancy_rate_verlaesslich_prozent")
    print(f"Beobachtete Ladevorgänge: {len(events)} "
          f"(davon plausibel [AC ≤ 12 h / DC ≤ 3 h, siehe E15]: {len(plausible)}, "
          f"als unplausibel markiert: {len(events) - len(plausible)})")
    if not plausible.empty:
        print(f"Mittlere Dauer (plausible): {plausible['dauer_minuten'].mean():.0f} min, "
              f"Median: {plausible['dauer_minuten'].median():.0f} min")
        print(f"Ladepunkte mit mind. einem plausiblen Ladevorgang: "
              f"{plausible['evse_id'].nunique()} von {len(stammdaten)}")
    print(f"Beobachtete Ausfallzeiten (AUSSER_BETRIEB): {len(ausfaelle)} "
          f"auf {ausfaelle['evse_id'].nunique() if not ausfaelle.empty else 0} Ladepunkten")
    print(f"\nGespeichert: {events_pfad}")
    print(f"Gespeichert: {ausfaelle_pfad}")
    print(f"Gespeichert: {kennzahlen_pfad}")
