"""Dashboard für die Stadtverwaltung: Ladeinfrastruktur Göttingen.

Setzt die Interview-Anforderungen um (23.06.2026, Block D):
- Exportfunktion als wichtigstes Designmerkmal (CSV je Ebene + Excel-Gesamtpaket)
- Kennzahlen direkt beim Anklicken einer Station sichtbar, nicht nur Download

Bewusst schlicht gehalten — das Dashboard ist Ausblick der Arbeit, nicht
Kernartefakt (siehe ENTSCHEIDUNGSLOG E6). Es zeigt nur an, was die
Export-Pipeline (extract_stammdaten -> extract_zeitreihe -> berechne_kennzahlen)
vorab berechnet hat.

Aufruf:  venv/bin/streamlit run dashboard.py
"""

import io
import os

import pandas as pd
import streamlit as st

ORDNER = "auswertung"
# Farbwert für alle Diagramme (einheitlich, eine Serie -> ein Farbton)
BLAU = "#2a78d6"

st.set_page_config(page_title="Ladeinfrastruktur Göttingen", page_icon="🔌", layout="wide")


@st.cache_data
def lade_daten():
    """Liest die drei Export-Ebenen der Pipeline ein."""
    stammdaten = pd.read_csv(
        os.path.join(ORDNER, "stammdaten_goettingen.csv"), sep=";", encoding="utf-8-sig"
    )
    events = pd.read_csv(
        os.path.join(ORDNER, "ladevorgaenge_goettingen.csv"), sep=";", encoding="utf-8-sig"
    )
    kennzahlen = pd.read_csv(
        os.path.join(ORDNER, "kennzahlen_ladepunkte.csv"), sep=";", encoding="utf-8-sig"
    )
    zeitreihe = pd.read_csv(
        os.path.join(ORDNER, "statusaenderungen_goettingen.csv"), sep=";", encoding="utf-8-sig"
    )
    # Zeitstempel für Anzeige und Diagramme in lokale Zeit umrechnen
    # (format="mixed": die CSV enthält Zeitstempel mit und ohne Millisekunden)
    for spalte in ("start", "ende"):
        events[spalte] = pd.to_datetime(events[spalte], utc=True, format="mixed", errors="coerce")
        events[spalte + "_lokal"] = events[spalte].dt.tz_convert("Europe/Berlin")
    abruf = pd.to_datetime(zeitreihe["erfasst_am"], utc=True, errors="coerce")
    fenster = (abruf.min(), abruf.max())
    return stammdaten, events, kennzahlen, zeitreihe, fenster


def csv_bytes(df):
    """DataFrame als Excel-taugliche CSV (Semikolon, BOM) für den Download."""
    return df.to_csv(sep=";", index=False).encode("utf-8-sig")


def excel_bytes(stammdaten, events, kennzahlen):
    """Alle drei Ebenen als eine Excel-Datei mit je einem Blatt."""
    puffer = io.BytesIO()
    with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
        stammdaten.to_excel(writer, sheet_name="Stammdaten", index=False)
        ev = events.copy()
        # Excel kann keine Zeitzonen-Zeitstempel speichern
        for spalte in ("start", "ende", "start_lokal", "ende_lokal"):
            ev[spalte] = ev[spalte].dt.tz_localize(None)
        ev.to_excel(writer, sheet_name="Ladevorgänge", index=False)
        kennzahlen.to_excel(writer, sheet_name="Kennzahlen", index=False)
    return puffer.getvalue()


stammdaten, events, kennzahlen, zeitreihe, fenster = lade_daten()
plausible = events[events["plausibel"]]

# --- Kopfbereich ---------------------------------------------------------------
st.title("🔌 Ladeinfrastruktur Göttingen")
st.caption(
    f"Datenquelle: Mobilithek (DATEX II/AFIR) · Beobachtungszeitraum "
    f"{fenster[0]:%d.%m.%Y} – {fenster[1]:%d.%m.%Y} · "
    f"{stammdaten['anbieter'].nunique()} Anbieter-Feeds"
)
st.info(
    "**Lesehinweis:** Die Anbieter melden nur Statusänderungen (Delta-Feeds). "
    "Alle Kennzahlen sind daher **beobachtete Untergrenzen** der tatsächlichen "
    "Nutzung, keine vollständige Zählung. Ladevorgänge über 12 h sind als "
    "unplausibel markiert und fließen nicht in die Kennzahlen ein.",
    icon="ℹ️",
)

# --- Gesamtübersicht -------------------------------------------------------------
spalte1, spalte2, spalte3, spalte4 = st.columns(4)
spalte1.metric("Ladepunkte (Stammdaten)", len(stammdaten))
spalte2.metric("Standorte", stammdaten["strasse"].nunique())
spalte3.metric("Beobachtete Ladevorgänge", len(plausible))
if len(plausible):
    spalte4.metric("Ø Ladedauer", f"{plausible['dauer_minuten'].mean():.0f} min")

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
    format_func=lambda s: (
        s if s == "— Alle Standorte —"
        else f"{s}  ({punkte_je_standort[s]} Ladepunkte)"
    ),
)

if auswahl == "— Alle Standorte —":
    punkte = kennzahlen
    events_auswahl = plausible
else:
    punkte = kennzahlen[kennzahlen["strasse"] == auswahl]
    events_auswahl = plausible[plausible["evse_id"].isin(punkte["evse_id"])]

# Kennzahlen der Auswahl direkt anzeigen
spalte1, spalte2, spalte3, spalte4 = st.columns(4)
spalte1.metric("Ladepunkte", len(punkte))
spalte2.metric("Ladevorgänge", int(punkte["ladevorgaenge"].sum()))
spalte3.metric("Belegungsstunden", f"{punkte['belegt_stunden'].sum():.1f} h")
if len(events_auswahl):
    spalte4.metric("Ø Ladedauer", f"{events_auswahl['dauer_minuten'].mean():.0f} min")

st.dataframe(
    punkte[[
        "evse_id", "strasse", "betreiber", "strom_art", "max_leistung_kw",
        "ladevorgaenge", "belegt_stunden", "mittlere_dauer_min",
        "occupancy_rate_prozent",
    ]]
    # Aktivste Ladepunkte zuerst — die interessieren die Verwaltung am meisten
    .sort_values("ladevorgaenge", ascending=False)
    .rename(columns={
        "evse_id": "EVSE-ID", "strasse": "Straße", "betreiber": "Betreiber",
        "strom_art": "AC/DC", "max_leistung_kw": "max. kW",
        "ladevorgaenge": "Ladevorgänge", "belegt_stunden": "Belegt (h)",
        "mittlere_dauer_min": "Ø Dauer (min)",
        "occupancy_rate_prozent": "Occupancy (%)",
    }),
    width='stretch',
    hide_index=True,
    column_config={
        "Ladevorgänge": st.column_config.NumberColumn(format="%d"),
        "Belegt (h)": st.column_config.NumberColumn(format="%.1f h"),
        "Ø Dauer (min)": st.column_config.NumberColumn(format="%.0f min"),
        "Occupancy (%)": st.column_config.NumberColumn(format="%.2f %%"),
        "max. kW": st.column_config.NumberColumn(format="%.0f kW"),
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

export1, export2, export3, export4 = st.columns(4)
export1.download_button(
    "Stammdaten (CSV)", csv_bytes(stammdaten),
    "stammdaten_goettingen.csv", "text/csv",
    help="Eine Zeile pro Ladepunkt: Adresse, Betreiber, Leistung",
)
export2.download_button(
    "Ladevorgänge (CSV)", csv_bytes(events.drop(columns=["start_lokal", "ende_lokal"])),
    "ladevorgaenge_goettingen.csv", "text/csv",
    help="Ein beobachteter Ladevorgang pro Zeile: Start, Ende, Dauer",
)
export3.download_button(
    "Kennzahlen (CSV)", csv_bytes(kennzahlen),
    "kennzahlen_ladepunkte.csv", "text/csv",
    help="Occupancy Rate, Ladevorgänge, Ø-Dauer je Ladepunkt",
)
export4.download_button(
    "Gesamtpaket (Excel)", excel_bytes(stammdaten, events, kennzahlen),
    "ladeinfrastruktur_goettingen.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Alle drei Ebenen als eine Excel-Datei mit drei Blättern",
)

if auswahl != "— Alle Standorte —":
    st.download_button(
        f"Nur Auswahl „{auswahl}“ (CSV)",
        csv_bytes(punkte),
        f"kennzahlen_{auswahl.replace(' ', '_').replace('/', '-')}.csv",
        "text/csv",
    )

# --- Rohdaten-Ebene für eigene Auswertungen --------------------------------------
with st.expander("Rohzeitreihe (alle beobachteten Statusänderungen)"):
    st.caption(
        "Feinste Export-Ebene: jede beobachtete Statusänderung einzeln — "
        "geeignet für eigene Auswertungen jenseits der fertigen Kennzahlen."
    )
    st.dataframe(zeitreihe.head(500), width='stretch', hide_index=True)
    st.download_button(
        "Rohzeitreihe (CSV)", csv_bytes(zeitreihe),
        "statusaenderungen_goettingen.csv", "text/csv",
    )
