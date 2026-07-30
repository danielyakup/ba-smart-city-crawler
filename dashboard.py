"""Dashboard für die Stadtverwaltung: Ladeinfrastruktur Göttingen.

Setzt die Interview-Anforderungen um (23.06.2026, Block D):
- Exportfunktion als wichtigstes Designmerkmal (CSV je Ebene + Excel-Gesamtpaket)
- Kennzahlen direkt beim Anklicken einer Station sichtbar, nicht nur Download

Bewusst schlicht gehalten — das Dashboard ist Ausblick der Arbeit, nicht
Kernartefakt (siehe ENTSCHEIDUNGSLOG E6). Es zeigt nur an, was die
Export-Pipeline (extract_stammdaten -> extract_zeitreihe -> berechne_kennzahlen)
vorab berechnet hat.

Aufruf:  venv/bin/streamlit run dashboard.py

ANONYM=True blendet den Ortsbezug aus der Anzeige aus (Titel, Straßennamen,
Betreibernamen, Betreiberkürzel in den EVSE-IDs) — gedacht für Screenshots in der schriftlichen
Ausarbeitung, die die untersuchte Stadt durchgängig umschreibt. Die exportierten
CSVs bleiben davon unberührt, sie enthalten weiterhin die echten Werte.
"""

import io
import os

import pandas as pd
import streamlit as st

ORDNER = "auswertung"
# Farbwert für alle Diagramme (einheitlich, eine Serie -> ein Farbton)
BLAU = "#2a78d6"

# Ortsbezug in der ANZEIGE ausblenden (Screenshots für die Thesis).
# Für den Praxisbetrieb auf False stellen.
ANONYM = False
STADT = "der untersuchten Stadt" if ANONYM else "Göttingen"

st.set_page_config(
    page_title=f"Ladeinfrastruktur {STADT}" if ANONYM else "Ladeinfrastruktur Göttingen",
    page_icon="🔌",
    layout="wide",
)


@st.cache_data(ttl=300)
def lade_daten():
    """Liest die Export-Ebenen der Pipeline ein."""
    stammdaten = pd.read_csv(
        os.path.join(ORDNER, "stammdaten_targetcity.csv"), sep=";", encoding="utf-8-sig", decimal=","
    )
    events = pd.read_csv(
        os.path.join(ORDNER, "ladevorgaenge_targetcity.csv"), sep=";", encoding="utf-8-sig", decimal=","
    )
    ausfaelle = pd.read_csv(
        os.path.join(ORDNER, "ausfaelle_targetcity.csv"), sep=";", encoding="utf-8-sig", decimal=","
    )
    kennzahlen = pd.read_csv(
        os.path.join(ORDNER, "kennzahlen_ladepunkte.csv"), sep=";", encoding="utf-8-sig", decimal=","
    )
    zeitreihe = pd.read_csv(
        os.path.join(ORDNER, "statusaenderungen_targetcity.csv"), sep=";", encoding="utf-8-sig", decimal=","
    )
    # Zeitstempel für Anzeige und Diagramme in lokale Zeit umrechnen
    # (format="mixed": die CSV enthält Zeitstempel mit und ohne Millisekunden)
    for df in (events, ausfaelle):
        for spalte in ("start", "ende"):
            df[spalte] = pd.to_datetime(df[spalte], utc=True, format="mixed", errors="coerce")
            df[spalte + "_lokal"] = df[spalte].dt.tz_convert("Europe/Berlin")
    abruf = pd.to_datetime(zeitreihe["erfasst_am"], utc=True, errors="coerce")
    fenster = (abruf.min(), abruf.max())
    return stammdaten, events, ausfaelle, kennzahlen, zeitreihe, fenster


def csv_bytes(df):
    """DataFrame als Excel-taugliche CSV (Semikolon, Dezimalkomma, BOM) für den
    Download. Ohne Dezimalkomma liest Excel in deutscher Spracheinstellung
    Zahlen wie "17.5" als Datum "17.05.2026" (ENTSCHEIDUNGSLOG E20)."""
    return df.to_csv(sep=";", index=False, decimal=",").encode("utf-8-sig")


def excel_bytes(stammdaten, events, ausfaelle, kennzahlen):
    """Alle Ebenen als eine Excel-Datei mit je einem Blatt."""
    puffer = io.BytesIO()
    with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
        stammdaten.to_excel(writer, sheet_name="Stammdaten", index=False)
        for name, df in (("Ladevorgänge", events), ("Ausfälle", ausfaelle)):
            df = df.copy()
            # Excel kann keine Zeitzonen-Zeitstempel speichern
            for spalte in ("start", "ende", "start_lokal", "ende_lokal"):
                df[spalte] = df[spalte].dt.tz_localize(None)
            df.to_excel(writer, sheet_name=name, index=False)
        kennzahlen.to_excel(writer, sheet_name="Kennzahlen", index=False)
    return puffer.getvalue()


stammdaten, events, ausfaelle, kennzahlen, zeitreihe, fenster = lade_daten()
plausible = events[events["plausibel"]]

# --- Anonymisierung der Anzeige (nur bei ANONYM=True) ----------------------------
# Feste Zuordnung Straße -> "Standort 01", alphabetisch vergeben, damit derselbe
# Standort über alle Tabellen und über mehrere Läufe hinweg dieselbe Nummer hat.
STANDORT_ALIAS = (
    {
        strasse: f"Standort {nummer:02d}"
        for nummer, strasse in enumerate(
            sorted(stammdaten["strasse"].dropna().unique()), start=1
        )
    }
    if ANONYM
    else {}
)


def standort_label(strasse):
    """Anzeigename eines Standorts; bei ANONYM ein neutraler Platzhalter."""
    return STANDORT_ALIAS.get(strasse, strasse)


# Betreibernamen verraten den Ort ebenso wie die Straße (z. B. die örtlichen
# Stadtwerke), deshalb bekommen sie dieselbe Alias-Behandlung.
BETREIBER_ALIAS = (
    {
        betreiber: f"Betreiber {nummer:02d}"
        for nummer, betreiber in enumerate(
            sorted(stammdaten["betreiber"].dropna().unique()), start=1
        )
    }
    if ANONYM
    else {}
)


def betreiber_label(betreiber):
    """Anzeigename eines Betreibers; bei ANONYM ein neutraler Platzhalter."""
    return BETREIBER_ALIAS.get(betreiber, betreiber)


def maskiere_id(evse_id):
    """Ersetzt das Betreiberkürzel in der EVSE-ID durch XXX.

    Gleiche Konvention wie in der schriftlichen Ausarbeitung (Tabelle 7):
    aus 'DE*ABC*E00001*001' wird 'DE*XXX*E00001*001'. IDs ohne Sternchen
    (UUIDs, Hexketten) tragen kein Betreiberkürzel und bleiben unverändert.
    """
    teile = str(evse_id).split("*")
    if len(teile) >= 3:
        teile[1] = "XXX"
        return "*".join(teile)
    return evse_id


def fuer_anzeige(df):
    """Kopie eines DataFrames mit ausgeblendetem Ortsbezug.

    Wird ausschließlich auf die angezeigten Tabellen angewandt, nicht auf die
    Daten hinter den Download-Buttons.
    """
    if not ANONYM:
        return df
    df = df.copy()
    if "strasse" in df.columns:
        df["strasse"] = df["strasse"].map(standort_label)
    if "evse_id" in df.columns:
        df["evse_id"] = df["evse_id"].map(maskiere_id)
    if "betreiber" in df.columns:
        df["betreiber"] = df["betreiber"].map(betreiber_label)
    return df


# --- Kopfbereich ---------------------------------------------------------------
st.title(f"🔌 Ladeinfrastruktur {STADT}")
st.caption(
    f"Datenquelle: Mobilithek (DATEX II/AFIR) · Beobachtungszeitraum "
    f"{fenster[0]:%d.%m.%Y} – {fenster[1]:%d.%m.%Y} · "
    f"{stammdaten['anbieter'].nunique()} Anbieter-Feeds"
)

# --- Gesamtübersicht -------------------------------------------------------------
spalte1, spalte2, spalte3, spalte4, spalte5 = st.columns(5)
spalte1.metric("Ladepunkte (Stammdaten)", len(stammdaten))
spalte2.metric("Standorte", stammdaten["strasse"].nunique())
spalte3.metric("Beobachtete Ladevorgänge", len(plausible))
if len(plausible):
    spalte4.metric("Ø Ladedauer", f"{plausible['dauer_minuten'].mean():.0f} min")
spalte5.metric(
    "Beobachtete Ausfälle",
    len(ausfaelle),
    help="Ladepunkte mit beobachteter Außer-Betrieb-Phase im Zeitraum",
)

# --- Stationsauswahl (Interview: Kennzahlen beim Anklicken sichtbar) -------------
st.divider()
st.subheader("Station auswählen")

# Auswahl über den Standort (Straße); "Alle" zeigt das Gesamtbild.
# Im Dropdown steht die Zahl der Ladepunkte gleich mit dabei.
punkte_je_standort = stammdaten["strasse"].value_counts()
standorte = sorted(stammdaten["strasse"].dropna().unique())
auswahl = st.selectbox(
    "Standort",
    ["— Alle Standorte —"] + standorte,
    # Die Auswahlwerte bleiben die echten Straßennamen (danach wird gefiltert),
    # angezeigt wird bei ANONYM der Platzhalter.
    format_func=lambda s: (
        s if s == "— Alle Standorte —"
        else f"{standort_label(s)}  ({punkte_je_standort[s]} Ladepunkte)"
    ),
)

if auswahl == "— Alle Standorte —":
    punkte = kennzahlen
    events_auswahl = plausible
    ausfaelle_auswahl = ausfaelle
else:
    punkte = kennzahlen[kennzahlen["strasse"] == auswahl]
    events_auswahl = plausible[plausible["evse_id"].isin(punkte["evse_id"])]
    ausfaelle_auswahl = ausfaelle[ausfaelle["evse_id"].isin(punkte["evse_id"])]

# Kennzahlen der Auswahl direkt anzeigen
spalte1, spalte2, spalte3, spalte4, spalte5 = st.columns(5)
spalte1.metric("Ladepunkte", len(punkte))
spalte2.metric("Ladevorgänge", int(punkte["ladevorgaenge"].sum()))
spalte3.metric("Belegungsstunden", f"{punkte['belegt_stunden'].sum():.1f} h")
if len(events_auswahl):
    spalte4.metric("Ø Ladedauer", f"{events_auswahl['dauer_minuten'].mean():.0f} min")
spalte5.metric(
    "Ø Verfügbarkeit",
    f"{punkte['verfuegbar_prozent'].mean():.1f} %" if len(punkte) else "–",
    help="Anteil des Beobachtungsfensters, der weder belegt noch außer Betrieb "
         "noch als unplausibler Ladevorgang unklar war",
)

st.caption(
    "Plausibilitätsgrenze für Ladevorgänge: 12 h bei AC, 3 h bei DC-Schnellladung. "
    "Occupancy, Ausfallquote und Verfügbarkeit beziehen sich auf das verlässliche "
    "Fenster seit dem 21.07.2026; die Occupancy übers gesamte Beobachtungsfenster "
    "steht zusätzlich zum Vergleich daneben."
)
st.dataframe(
    fuer_anzeige(punkte)[[
        "evse_id", "strasse", "betreiber", "strom_art", "max_leistung_kw",
        "ladevorgaenge", "belegt_stunden", "mittlere_dauer_min", "median_dauer_min",
        "occupancy_rate_verlaesslich_prozent", "occupancy_rate_prozent",
        "ausser_betrieb_stunden", "ausfallquote_prozent", "unklar_quote_prozent",
        "verfuegbar_prozent",
    ]]
    # Aktivste Ladepunkte zuerst — die interessieren die Verwaltung am meisten
    .sort_values("ladevorgaenge", ascending=False)
    .rename(columns={
        "evse_id": "EVSE-ID", "strasse": "Straße", "betreiber": "Betreiber",
        "strom_art": "AC/DC", "max_leistung_kw": "max. kW",
        "ladevorgaenge": "Ladevorgänge", "belegt_stunden": "Belegt (h)",
        "mittlere_dauer_min": "Ø Dauer (min)",
        # Median zusätzlich (E15): robuster gegen die wenigen sehr langen
        # Übernacht-Ladungen, die den Mittelwert nach oben ziehen.
        "median_dauer_min": "Median Dauer (min)",
        # Verlässliches Fenster ist die Kennzahl, mit der auch Ausfallquote
        # und Verfügbarkeit rechnen (in Summe = 100 %, siehe E14); die
        # Gesamtfenster-Variante bleibt zum Vergleich daneben stehen.
        "occupancy_rate_verlaesslich_prozent": "Occupancy (%)",
        "occupancy_rate_prozent": "Occupancy gesamtes Fenster (%)",
        "ausser_betrieb_stunden": "Außer Betrieb (h)",
        "ausfallquote_prozent": "Ausfallquote (%)",
        # Zeit aus als unplausibel verworfenen Ladevorgängen (E15/E16) --
        # weder Nutzung noch Ausfall, aber nachweislich nicht frei verfügbar.
        "unklar_quote_prozent": "Unklar (%)",
        "verfuegbar_prozent": "Verfügbar (%)",
    }),
    width='stretch',
    hide_index=True,
    column_config={
        "Ladevorgänge": st.column_config.NumberColumn(format="%d"),
        "Belegt (h)": st.column_config.NumberColumn(format="%.1f h"),
        "Ø Dauer (min)": st.column_config.NumberColumn(format="%.0f min"),
        "Median Dauer (min)": st.column_config.NumberColumn(format="%.0f min"),
        "Occupancy (%)": st.column_config.NumberColumn(format="%.2f %%"),
        "Occupancy gesamtes Fenster (%)": st.column_config.NumberColumn(format="%.2f %%"),
        "max. kW": st.column_config.NumberColumn(format="%.0f kW"),
        "Außer Betrieb (h)": st.column_config.NumberColumn(format="%.1f h"),
        "Ausfallquote (%)": st.column_config.NumberColumn(format="%.2f %%"),
        "Unklar (%)": st.column_config.NumberColumn(format="%.2f %%"),
        "Verfügbar (%)": st.column_config.NumberColumn(format="%.1f %%"),
    },
)

# --- Verteilungen (Interview Block B: Tageszeit, Wochentag) ----------------------
if len(events_auswahl):
    st.subheader("Wann wird geladen?")
    links, rechts = st.columns(2)

    with links:
        st.markdown("**Ladevorgänge nach Tageszeit** (Startstunde, lokale Zeit)")
        pro_stunde = (
            events_auswahl["start_lokal"].dt.hour.value_counts()
            .reindex(range(24), fill_value=0).sort_index()
        )
        pro_stunde.index = [f"{h:02d}" for h in pro_stunde.index]
        st.bar_chart(pro_stunde, color=BLAU, x_label="Uhrzeit", y_label="Ladevorgänge")

    with rechts:
        st.markdown("**Ladevorgänge nach Wochentag**")
        tage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        pro_tag = (
            events_auswahl["start_lokal"].dt.dayofweek.value_counts()
            .reindex(range(7), fill_value=0).sort_index()
        )
        pro_tag.index = tage
        st.bar_chart(pro_tag, color=BLAU, x_label="Wochentag", y_label="Ladevorgänge")

# --- Export (Interview: wichtigstes Designmerkmal) -------------------------------
st.divider()
st.subheader("📥 Datenexport")
st.caption(
    "Alle Dateien sind Semikolon-getrennte CSVs (öffnen sich direkt in Excel) "
    "bzw. eine Excel-Arbeitsmappe mit allen drei Ebenen."
)

export1, export2, export3, export4, export5 = st.columns(5)
export1.download_button(
    "Stammdaten (CSV)", csv_bytes(stammdaten),
    "stammdaten_targetcity.csv", "text/csv",
    help="Eine Zeile pro Ladepunkt: Adresse, Betreiber, Leistung",
)
export2.download_button(
    "Ladevorgänge (CSV)", csv_bytes(events.drop(columns=["start_lokal", "ende_lokal"])),
    "ladevorgaenge_targetcity.csv", "text/csv",
    help="Ein beobachteter Ladevorgang pro Zeile: Start, Ende, Dauer",
)
export3.download_button(
    "Ausfälle (CSV)", csv_bytes(ausfaelle.drop(columns=["start_lokal", "ende_lokal"])),
    "ausfaelle_targetcity.csv", "text/csv",
    help="Eine beobachtete Außer-Betrieb-Phase pro Zeile: Start, Ende, Dauer",
)
export4.download_button(
    "Kennzahlen (CSV)", csv_bytes(kennzahlen),
    "kennzahlen_ladepunkte.csv", "text/csv",
    help="Occupancy Rate, Ausfallquote, Verfügbarkeit je Ladepunkt",
)
export5.download_button(
    "Gesamtpaket (Excel)", excel_bytes(stammdaten, events, ausfaelle, kennzahlen),
    "ladeinfrastruktur_targetcity.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Alle Ebenen als eine Excel-Datei mit je einem Blatt",
)

if auswahl != "— Alle Standorte —":
    beschriftung = standort_label(auswahl)
    st.download_button(
        f"Nur Auswahl „{beschriftung}“ (CSV)",
        csv_bytes(punkte),
        f"kennzahlen_{beschriftung.replace(' ', '_').replace('/', '-')}.csv",
        "text/csv",
    )

# --- Rohdaten-Ebene für eigene Auswertungen --------------------------------------
with st.expander("Rohzeitreihe (alle beobachteten Statusänderungen)"):
    st.caption(
        "Feinste Export-Ebene: jede beobachtete Statusänderung einzeln — "
        "geeignet für eigene Auswertungen jenseits der fertigen Kennzahlen."
    )
    st.dataframe(fuer_anzeige(zeitreihe.head(500)), width='stretch', hide_index=True)
    st.download_button(
        "Rohzeitreihe (CSV)", csv_bytes(zeitreihe),
        "statusaenderungen_targetcity.csv", "text/csv",
    )
