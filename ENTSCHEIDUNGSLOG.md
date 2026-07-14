# Entscheidungslog: Methodische Änderungen am BNetzA-Abgleich

*Dokumentation der Designentscheidungen für die schriftliche Ausarbeitung.
Im ADR-Rahmen (Sein et al. 2011) entsprechen diese Iterationen den
Build-Intervention-Evaluation-Zyklen (Stage 2) am IT-Artefakt.*

---

## E1 — 12.06.2026: Aufnahme von Eco-Movement als Datenquelle

**Entscheidung:** Zwei zusätzliche Mobilithek-Abonnements (Eco-Movement statisch/dynamisch) in die Pipeline aufgenommen.

**Begründung:** Eco-Movement ist ein kommerzieller Daten-Aggregator und in der Arbeit als Make-or-Buy-Option diskutiert (Interview-Leitfaden, Block C.3). Die Aufnahme erlaubt einen empirischen Vergleich: Wie viel zusätzliche Abdeckung liefert ein Aggregator gegenüber den direkten Betreiber-Feeds?

**Ergebnis:** Abdeckung stieg von ~30 % auf 42,19 % (Volltext-Methode). Bemerkenswert: Die statische Eco-Movement-Datei ist mit ~467 MB pro Snapshot mit Abstand die größte Quelle — bei täglicher Historisierung ca. 14 GB/Monat, was Speicherstrategie-Fragen aufwirft (Snapshot vs. Differenzspeicherung, vgl. Interviewfrage B.3).

## E2 — 12.06.2026: Entfernung der Smartlab-Feeds aus der Pipeline

**Entscheidung:** Beide Smartlab-AFIR-Abonnements aus dem Crawler entfernt.

**Begründung:** Der Feed lieferte über alle Durchläufe hinweg null auswertbare Göttingen-Standorte, obwohl die Rohdatei >13 MB groß ist und Smartlab-Säulen (u. a. Stadtwerke) auf Endkunden-Karten sichtbar sind. Die alten Rohdateien bleiben als Beleg archiviert. **Der Befund selbst — stadtnahe Betreiber fehlen im amtlichen Meldekanal — ist ein zentrales Ergebnis der Arbeit, nicht nur ein technischer Defekt** (vgl. Interview Block C.2).

## E3 — 12.06.2026: Getrennte Ausweisung von ID- und Heuristik-Treffern

**Entscheidung:** Der Abgleich weist seither aus, welche Treffer hart über EVSE-IDs belegt sind und welche nur auf der Straßennamen-Heuristik beruhen.

**Begründung:** Die ursprüngliche Volltext-Methode prüfte nur, ob Straßenname und das Wort „Göttingen" *irgendwo in derselben Datei* vorkommen. Bei bundesweiten Anbieter-Dateien ist diese Bedingung trivial erfüllt — eine „Theodor-Heuss-Straße" in einer anderen Stadt erzeugt dann einen Scheintreffer. Eine einzelne Abdeckungszahl verschleiert, wie viel davon auf diesem unsicheren Fundament steht.

**Ergebnis:** Nur 6 von 81 Treffern (3,12 % von 192) waren ID-belegt; 75 beruhten auf der Heuristik. Die ehrliche Aussage war damit ein Intervall von 3,12 %–42,19 % — zu breit, um als Kernergebnis tragfähig zu sein. Daraus folgte unmittelbar E4.

## E4 — 12.06.2026: Umstellung von Datei-Volltext auf Datensatz-Matching

**Entscheidung:** Der Abgleich parst die DATEX-II-Struktur jetzt vollständig und prüft beide Match-Wege auf Ebene des einzelnen Standort-Datensatzes statt auf Datei-Ebene.

**Begründung (methodisch):**
1. **Validität vor Bequemlichkeit.** Die Volltext-Suche war robust gegen die heterogenen Anbieterformate, konnte aber nicht garantieren, dass Straße und Stadt zum selben physischen Standort gehören. Das Datensatz-Matching stellt genau das sicher: Ein Straßen-Treffer zählt nur noch, wenn der Anbieter-Datensatz *selbst* eine Göttinger Adresse trägt.
2. **IDs liegen tiefer als gedacht.** Stichprobenanalyse der Rohdaten zeigte, dass echte EVSE-IDs (z. B. `DE*TSL*E0K22AF` bei Tesla) im Feld `idG` der einzelnen Ladepunkte (`refillPoint → aegiElectricChargingPoint`) liegen — nicht auf Standort-Ebene, wo nur interne UUIDs stehen. Zusätzlich werden IDs vor dem Vergleich normalisiert (Trennzeichen entfernt), da BNetzA und Betreiber unterschiedliche Schreibweisen nutzen.

**Iterationen während der Umsetzung** (dokumentiert, weil sie eine Kernaussage der Arbeit stützen):
- *Iteration 1:* Parser suchte Adressen nur unter `locPointLocation` auf Standort-Ebene → Eco-Movement und HH Energienetz lieferten fälschlich 0 Göttingen-Standorte.
- *Iteration 2:* Analyse der Rohdaten ergab, dass Eco-Movement Adressen unter `locAreaLocation` ablegt und HH Energienetz sie eine Ebene tiefer an der *Station* statt am Standort führt. Beide Varianten sind DATEX-II-konform. Der Parser prüft jetzt beide Location-Typen auf beiden Ebenen.
- **Erkenntnis daraus:** Selbst innerhalb desselben verpflichtenden Datenstandards (DATEX II/AFIR) nutzen Anbieter strukturell unterschiedliche, jeweils zulässige Ablageorte für identische Information. Interoperabilität ist damit auch bei formaler Standardkonformität nicht gegeben — ein eigenständiges Datenqualitäts-Ergebnis.

**Ergebnis (Stand 12.06.2026):**

| Methode | Abdeckung | Bewertung |
|---|---|---|
| Volltext (Datei-Ebene) | 42,19 % (81/192) | Obergrenze, enthält Scheintreffer |
| Datensatz-Matching | **26,04 % (50/192)** | belastbar, zitierfähig |
| davon hart per EVSE-ID | 1,56 % (3/192) | Untergrenze |

Pro Anbieter (Datensatz-Ebene): Eco-Movement 28 Punkte (16 Göttingen-Standorte), Tesla 8 (1 Standort), EnBW 7 (2 Standorte), HH Energienetz 7 (3 Standorte), Smartlab 0.

**Verbleibende, bewusst akzeptierte Limitationen:**
- Straßen-Matching nutzt Teilstring-Vergleich normalisierter Namen; mehrere BNetzA-Ladeeinrichtungen in derselben Straße können durch einen einzigen Anbieter-Standort als abgedeckt gelten, auch wenn der Anbieter nur einen Teil davon führt. Die 26,04 % bleiben daher eher eine obere Schätzung der echten Abdeckung.
- Nur 71 der 192 BNetzA-Punkte tragen überhaupt eine EVSE-ID im Register; die ID-basierte Untergrenze kann methodisch bedingt nie über ~37 % liegen. Auch das BNetzA-Register selbst ist also lückenhaft gepflegt.
- Die alte Volltext-Methode fand 6 ID-Treffer bei Eco-Movement, das strukturelle Parsen nur 3 — die übrigen 3 IDs stehen vermutlich in nicht ausgewerteten Feldern (z. B. URLs oder Freitext). Konservativ werden nur die strukturell belegten gezählt.

## E5 — 25.06.2026: Aufnahme von chargecloud GmbH, Abdeckung auf 84,9 %

**Entscheidung:** Zwei weitere Mobilithek-Abonnements (chargecloud GmbH, statisch/dynamisch, IDs `1006999576359198720` / `1006999499934756864`) in die Pipeline aufgenommen.

**Anlass und Recherchepfad:** In Vorbereitung auf eine Rückfrage an den Praxispartner (Mathias Willnat, Stadt Göttingen) — zugesagt im Experteninterview vom 23.06.2026 — sollte validiert werden, warum die Stadtwerke Göttingen AG trotz 115 BNetzA-Einträgen in keinem bisherigen Mobilithek-Feed erscheint. Eine gezielte Suche im Mobilithek-Datenkatalog unter „AFIR Göttingen" ergab das Datenangebot der chargecloud GmbH, das die Stadtwerke Göttingen im DATEX-II-V3-Format enthält (EVSE-IDs der Form `DE*GOE*`). Die ursprüngliche Anfrage an den Praxispartner erübrigte sich damit; stattdessen wurde ihm das Ergebnis mitgeteilt.

**Methodische Einordnung:** Die Aufnahme von chargecloud folgt derselben Logik wie E1 (Erweiterung um einen Aggregator-Feed), ist aber anders motiviert: Während Eco-Movement (E1) als Make-or-Buy-Vergleich aufgenommen wurde, ist chargecloud eine direkte Reaktion auf eine identifizierte Abdeckungslücke. Im ADR-Rahmen entspricht das einem weiteren BIE-Zyklus: Problem erkannt (fehlende Stadtwerke) → Artefakt erweitert (neues Abo) → Wirkung evaluiert (Abdeckungsrate).

**Ergänzender Befund — m8mit:** Parallel wurde festgestellt, dass auf der Kartenansicht m8mit.de/stations weitere Betreiber für den Raum Göttingen sichtbar sind (u. a. EWE Go GmbH, Pfalzwerke AG), deren Mobilithek-Feeds jedoch keine Göttingen-Daten liefern. Diese Betreiber sind im BNetzA-Register mit jeweils 2–6 Einträgen vertreten. Das Muster entspricht dem aus E2 bekannten Smartlab-Befund: Endkunden-Karten und amtlicher Meldekanal divergieren. Die betroffenen Betreiber machen einen Teil der verbleibenden ~15 % Abdeckungslücke aus; sie sind über den gewählten Ansatz strukturell nicht schließbar.

**Strukturelle Erkenntnis zur EVSE-ID-Quote:** Die EVSE-ID-basierte Trefferrate verbleibt bei 26,6 % (51/192), obwohl chargecloud 222 `DE*GOE*`-Ladepunkte enthält. Ursache: Die BNetzA hat für 121 der 192 Göttinger Ladeeinrichtungen (63 %) gar keine EVSE-IDs im Register eingetragen — diese Punkte sind per Definition nur über Adress-Matching erreichbar. Die maximale erreichbare ID-Trefferrate liegt damit strukturell bei ~37 %. Die 26,6 % entsprechen 68 % der ID-fähigen BNetzA-Punkte — ein plausibler Wert.

**Ergebnis (Stand 25.06.2026):**

| Anbieter | Göttingen-Standorte | per EVSE-ID | per Adresse | gesamt |
|---|---|---|---|---|
| chargecloud | 106 | 48 | 78 | 126 |
| Eco-Movement | 16 | 3 | 25 | 28 |
| Tesla | 1 | 0 | 8 | 8 |
| EnBW | 2 | 0 | 7 | 7 |
| HH Energienetz | 3 | 0 | 7 | 7 |
| Smartlab | 0 | 0 | 0 | 0 |

| Methode | Abdeckung | Bewertung |
|---|---|---|
| Stand nach E4 (12.06.) | 26,04 % (50/192) | belastbar, zitierfähig |
| Nach Aufnahme chargecloud | **84,9 % (163/192)** | belastbar, zitierfähig |
| davon hart per EVSE-ID | 26,6 % (51/192) | Untergrenze |
| davon nur Adress-Matching | 58,3 % (112/192) | plausibel, strukturell begründet |

## E6 — 11.07.2026: Export-Pipeline für die Stadtverwaltung (drei Ebenen, Göttingen-Filter bei der Extraktion)

**Anlass:** Umsetzung der im Experteninterview (23.06.2026, Block B und D) erhobenen Anforderungen: Der Praxispartner benötigt exportierbare Auslastungsdaten — die Exportfunktion wurde im Interview als *wichtigstes Designmerkmal* benannt. Ein Dashboard ist Ausblick; der belastbare Kern ist die Datenaufbereitung.

**Entscheidung 1 — Drei Export-Ebenen statt einer:** Die Pipeline erzeugt drei aufeinander aufbauende CSV-Dateien im neuen Ordner `auswertung/`:

| Ebene | Datei | Inhalt | Interview-Bezug |
|---|---|---|---|
| 1 Stammdaten | `stammdaten_goettingen.csv` | Eine Zeile pro Ladepunkt: EVSE-ID, Adresse, Betreiber, Leistung, AC/DC | Kennzahlen brauchen Kontext (B.5: 22 kW vs. 150 kW) |
| 2 Ereignisse | `ladevorgaenge_goettingen.csv` | Ein beobachteter Ladevorgang pro Zeile: Start, Ende, Dauer | B.2: Event-Aggregation „inhaltlich gleichwertig und datensparender" |
| 3 Kennzahlen | `kennzahlen_ladepunkte.csv` | Occupancy Rate, Anzahl/Ø-Dauer der Ladevorgänge, Wochenend-/Nachtanteil je Ladepunkt | B.1/B.4: Occupancy Rate als wichtigste Kennzahl |

Die Trennung folgt der Interview-Aussage, dass die Verwaltung sowohl fertige Kennzahlen als auch Rohmaterial für eigene Auswertungen braucht; CSV mit Semikolon-Trennung und BOM ist direkt in deutschem Excel öffenbar (das heutige Arbeitswerkzeug des Praxispartners, vgl. Block A: BNetzA-Tabelle wird manuell in Excel gefiltert).

**Entscheidung 2 — Göttingen-Filter bei der Extraktion, nicht im Export:** Die Feeds sind bundesweit (bis 542 MB pro Snapshot); ungefiltert wären es Millionen Zeilen — weder in Excel handhabbar noch im RAM der VM verarbeitbar. Gefiltert wird über die erprobte Datensatz-Logik aus E4 (Site-Adresse in Göttingen, keine Volltext-Treffer). Die rohen bundesweiten Snapshots in `data/` bleiben unverändert erhalten: Für eine andere Kommune muss nur die Filterfunktion (`is_goettingen()`) ersetzt werden, die Historie ist rückwirkend neu auswertbar. Damit bleibt das Artefakt generalisierbar (ADR Stage 4), ohne die Auswertung für den konkreten Anwendungsfall zu verwässern.

**Entscheidung 3 — Join über mehrere ID-Ebenen:** Stammdaten und Belegungsdaten werden über normalisierte IDs verknüpft (Normalisierung wie in E4). Da die Anbieter in den dynamischen Feeds auf unterschiedliche Ebenen referenzieren (Ladepunkt, Station oder Site), führt die Stammdaten-Tabelle alle drei ID-Ebenen als Join-Schlüssel mit; die Zeitreihe dokumentiert je Update, über welche Ebene der Treffer zustande kam (`match_ebene`). Ergebnis: 454 von 456 Updates matchen direkt auf Ladepunkt-Ebene.

**Ergebnis (Stand 11.07.2026):** 317 eindeutige Göttinger Ladepunkte mit vollständigen Stammdaten (chargecloud 246, Eco-Movement 38, EnBW 13, HH Energienetz 12, Tesla 8) — mehr als die 192 BNetzA-Registereinträge, was die Register-Lücke aus E5 nochmals bestätigt.

**Ergänzung — Dashboard umgesetzt (11.07.2026):** Auf die Export-Pipeline wurde eine bewusst schlichte Streamlit-Oberfläche (`dashboard.py`) gesetzt. Designentscheidungen entlang der Interview-Aussagen: (1) Die **Exportfunktion steht im Zentrum** — alle drei Ebenen als CSV-Download plus Excel-Gesamtpaket mit drei Blättern; (2) **Kennzahlen erscheinen direkt bei Auswahl einer Station** (Metrik-Kacheln + Tabelle), nicht nur als Download-Link — beides exakt die Formulierungen aus Block D; (3) ein dauerhaft sichtbarer **Lesehinweis** kennzeichnet alle Werte als beobachtete Untergrenzen (E7), damit die Zahlen in der Verwaltung nicht als vollständige Zählung fehlinterpretiert werden. Bewusst verzichtet wurde auf Karten, Prognosen (im Interview explizit abgelehnt) und Design-Ausarbeitung — das Dashboard bleibt Demonstrator für ADR Stage 4, nicht Kernartefakt. Technischer Hinweis: pyarrow musste auf 19.0.1 gepinnt werden (25.x verursacht Segfaults beim Tabellen-Rendering, siehe `requirements.txt`).

## E7 — 11.07.2026: Befund Delta-Feeds — Kennzahlen als beobachtete Untergrenzen

**Befund:** Bei der Umsetzung von E6 zeigte die Strukturanalyse der dynamischen Feeds, dass alle Anbieter **Delta-Publikationen** liefern, keine Vollabbilder: Ein Snapshot enthält nur die Ladepunkte, deren Status sich seit der letzten Publikation des Anbieters geändert hat. Extrembeispiel Tesla: exakt 1 Ladepunkt pro Snapshot (bundesweit); EnBW 2–40; chargecloud 4–54. Beim 30-Minuten-Abrufraster des Crawlers gehen damit alle Statusänderungen verloren, die zwischen zwei Abrufen publiziert und wieder überschrieben wurden.

**Konsequenzen für die Methodik:**
1. **Zeitreihen-Rekonstruktion statt Snapshot-Ablesen:** Eine Belegungszeitreihe entsteht durch Sammeln aller beobachteten Statusänderungen (dedupliziert über Ladepunkt + Änderungszeitpunkt + Status); zwischen zwei Beobachtungen gilt der letzte Status als fortbestehend. Das Feld `lastUpdated` der Anbieter liefert dabei den echten Änderungszeitpunkt — genauer als das Abrufraster.
2. **Plausibilitätsgrenze 12 h:** Verpasste Zwischen-Updates erzeugen Schein-Ladevorgänge von mehreren Tagen Dauer (61 % der segmentierten Events > 12 h). Events über 12 h werden als unplausibel markiert und fließen nicht in die Kennzahlen ein; sie bleiben im Event-Export gekennzeichnet erhalten. 12 h decken auch lange Übernacht-AC-Ladungen ab.
3. **Alle Kennzahlen sind Untergrenzen:** Occupancy Rate und Ladevorgang-Zahlen beziffern die *beobachtete* Nutzung, nicht die tatsächliche. Diese Einschränkung ist gegenüber dem Praxispartner und in der Arbeit explizit auszuweisen — sie ist zugleich ein eigenständiges Datenqualitäts-Ergebnis: Der amtliche Datenkanal ist für Auslastungsanalysen nur mit hoher Abruffrequenz brauchbar, was Ressourcenfragen kleiner Kommunen direkt berührt (vgl. Interview Block A: Einzelperson ohne IT-Team).
4. **Tesla-Totalausfall als Beleg:** Für die 8 Göttinger Tesla-Ladepunkte wurde im gesamten Zeitraum keine einzige Statusänderung erfasst — bei 1 Punkt pro Delta-Publikation ist die Trefferwahrscheinlichkeit im 30-Minuten-Raster praktisch null. Abhilfe wäre nur eine deutlich höhere Abruffrequenz.

**Ergebnis (Stand 11.07.2026, Beobachtungsfenster 12.06.–11.07.):** 456 eindeutige Statusänderungen auf 122 von 317 Ladepunkten; 49 segmentierte Ladevorgänge, davon 19 plausibel (Ø 359 min, Median 338 min — konsistent mit 22-kW-AC-Laden). Aktivste Standorte: Salinenweg (TEAG), Große Breite (Kaufland), Bahnhofsplatz (Allego) — plausible Alltagsorte.

**Abgeleitete Maßnahme (umgesetzt am 11.07.2026):** Erhöhung der Abruffrequenz der dynamischen Feeds von 30 auf 5 Minuten (Crontab von `*/30` auf `*/5` umgestellt; die statischen Feeds bleiben bei monatlichem Abruf). Abwägung:
- *Kosten:* Die dynamischen Snapshots sind klein (8–530 KB pro Anbieter); der Mehrbedarf von ca. 5 GB/Monat ist auf der VM (61 GB frei) unkritisch. Ein Abruf-Durchlauf dauert ~1 Minute und kollidiert damit nicht mit dem 5-Minuten-Takt; die 10-Sekunden-Pause zwischen den Mobilithek-Abrufen bleibt bestehen, die Last für die Plattform steigt also nur durch häufigere kleine Abrufe.
- *Nutzen:* Sechsfache Abtastrate = sechsfache Chance, eine Delta-Publikation zu erwischen, bevor die nächste sie ersetzt. Das Verlustproblem wird dadurch verringert, nicht beseitigt (Anbieter können häufiger publizieren als alle 5 Minuten) — die Kennzahlen bleiben methodisch Untergrenzen, aber mit deutlich dichterer Beobachtung.
- *Konsequenz für die Auswertung:* Das Beobachtungsfenster zerfällt in zwei Phasen unterschiedlicher Dichte (12.06.–11.07. im 30-Minuten-Raster, ab 11.07. im 5-Minuten-Raster). Bei Auswertungen über den Gesamtzeitraum ist das auszuweisen; der Vorher-Nachher-Vergleich der Beobachtungsdichte ist zugleich ein empirischer Beleg für den Frequenz-Effekt.

## E8 — 13.07.2026: Erste Befunde nach Umstellung auf 5-Minuten-Raster

**Anlass:** Zwei Tage nach der in E7 beschlossenen Umstellung wurde die Export-Pipeline neu ausgeführt (`extract_zeitreihe.py` → `berechne_kennzahlen.py`), um zu prüfen, ob die dichtere Abtastung tatsächlich mehr vollständige Ladevorgänge einfängt.

**Befund 1 — Frequenzeffekt bestätigt:** Statusänderungen stiegen von 456 auf 576 (betroffene Ladepunkte 122 → 161 von 317), segmentierte Ladevorgänge von 49 auf 65. Seit Umstellung (11.07., 22:55 Uhr) sind bereits 11 vollständige Ladevorgänge hinzugekommen — verteilt über `ecomovement` **und** erstmals auch `chargecloud` (zuvor: kein einziger vollständiger chargecloud-Zyklus im gesamten 30-Minuten-Zeitraum). Das stützt die E7-These, dass die Trefferwahrscheinlichkeit für Delta-Publikationen mit der Abtastrate skaliert.

**Befund 2 — Plausibilitätsgrenze bleibt auch im 5-Minuten-Raster relevant:** Von den 11 neuen Ladevorgängen liegen weiterhin 2 (beide `ecomovement`) über der 12-h-Grenze (18 h bzw. 21,6 h). Das spricht dagegen, den Plausibilitätscheck aus E7 nach der Frequenzerhöhung zu streichen: Die Ursache ist hier vermutlich nicht (nur) unser Abrufraster, sondern eine anbieterseitig verzögerte Aktualisierung des `lastUpdated`-Felds bei `ecomovement` — ein Datenqualitätsmerkmal des Anbieters, das auch dichteres Crawling nicht beheben kann. Empfehlung: Grenze beibehalten, aber am Monatsende (siehe unten) prüfen, ob sich die Quote unplausibler Events in der dichten Phase gegenüber der 30-Minuten-Phase signifikant verringert hat.

**Befund 3 — Meldequote schwankt stark zwischen Anbietern (nicht nur Frequenz-Artefakt):** Von 317 Ladepunkten haben 156 seit Beginn der Aufzeichnung (12.06.) keine einzige Statusänderung gemeldet. Aufschlüsselung nach Anbieter (Anteil der Ladepunkte mit ≥ 1 gemeldeter Änderung):

| Anbieter | Ladepunkte gesamt | mind. 1 Meldung | Anteil | Feed-Historie seit |
|---|---|---|---|---|
| ecomovement | 38 | 38 | 100 % | 12.06. |
| hhenergienetz | 12 | 12 | 100 % | 05.06. |
| chargecloud | 246 | 104 | 42 % | 25.06. (kürzeres Beobachtungsfenster) |
| EnBW | 13 | 4 | 31 % | 05.06. |
| Tesla | 8 | 2 | 25 % | 05.06. |

Ein Teil der Differenz erklärt sich durch unterschiedliche Subscription-Starts (chargecloud erst ab 25.06. abonniert, ~13 Tage kürzeres Fenster als der Rest). Das erklärt aber nicht, warum EnBW und Tesla trotz gleich langer Feed-Historie wie hhenergienetz (beide seit 05.06.) so viel seltener melden als hhenergienetz (100 %) bei ähnlicher oder kleinerer Flottengröße. Da alle Treffer auf Ladepunkt-Ebene matchen (kein Hinweis auf ein Matching-Problem), wird dies vorläufig als reales Nutzungsmuster gewertet (EnBW/Tesla-Standorte in Göttingen ggf. seltener frequentiert) und nicht als Parsing-Fehler — eine abschließende Bewertung erfolgt mit mehr Datenbasis Ende Juli.

**Offen — Wiedervorlage Ende Juli:** Sobald ein voller Monat im 5-Minuten-Raster vorliegt, erneut prüfen: (1) Anteil unplausibler Events in der dichten vs. sparsamen Phase (quantifiziert den Frequenz-Effekt für Kap. 5), (2) ob sich die Meldequote von EnBW/Tesla mit mehr Beobachtungszeit der von hhenergienetz annähert oder strukturell niedrig bleibt.

## E9 — 14.07.2026: Herleitung der BNetzA-Ground-Truth (134 → 192 Ladepunkte)

**Anlass:** Alle bisherigen Abdeckungsquoten (E1–E8) beziehen sich auf 192 registrierte Göttinger Ladepunkte als feste Bezugsgröße, ohne dass der Log bisher dokumentiert, wie diese Zahl selbst zustande kam. Bei einer Durchsicht älterer, lokaler Arbeitsnotizen wurde nachträglich rekonstruiert, dass auch der Ground-Truth-Filter auf die BNetzA-Excel Gegenstand einer eigenen Iteration war.

**Erste Iteration (134 Treffer):** Ursprünglich wurde ein einfacher Gleichheitsfilter auf die Spalte „Ort" angewendet (`Ort == "Göttingen"`). Dabei blieben Ladepunkte unberücksichtigt, die geografisch im Stadtgebiet liegen, aber unter abweichender Schreibweise, benachbarten Ortsteilen oder mit Erfassungsfehlern im Ortsfeld der BNetzA-Datenbank geführt werden.

**Finale Iteration (192 Treffer, aktueller Stand):** Der Filter wurde auf eine Kombination aus Postleitzahlen-Präfixen (`3707*`, `3708*`) und einer großzügigeren Ortsnamen-Prüfung (`göttingen`/`goettingen`, groß-/kleinschreibungsunabhängig) umgestellt — umgesetzt in `is_goettingen()` in `compare_bnetza.py` (vgl. CLAUDE.md: „Göttingen-Filter über Ort + PLZ 3707x/3708x"). Diese Fassung ist seither unverändert im Einsatz und bildet die Referenzzahl für E1–E8.

**Methodische Einordnung:** Die Ground-Truth-Konstruktion selbst folgte damit demselben iterativen Muster (kritische Prüfung → Verfeinerung → Validierung) wie die Matching-Methodik in E3/E4 — ein zusätzliches Beispiel für den ADR-Build-Intervention-Evaluation-Zyklus, diesmal angewendet auf die Referenzdaten statt auf den Abgleichsalgorithmus. Relevant für die Methodenkritik: Die 192 ist selbst kein unhinterfragter amtlicher Fixwert, sondern das Ergebnis einer eigenen Filterentscheidung, die transparent zu machen ist, falls in der Verteidigung nach der Reproduzierbarkeit der Bezugsgröße gefragt wird.

## E10 — 14.07.2026: Trennung von Verfügbarkeit und Ausfallzeit in den Kennzahlen

**Anlass:** Durchsicht von `berechne_kennzahlen.py` ergab, dass die Konstante `AUSSER_BETRIEB` (Statuswerte `outOfOrder`/`inoperative`/`outOfService`) zwar definiert, aber im Code nie ausgewertet wurde. Faktisch galt bislang: „nicht belegt" = „frei verfügbar" — jeder Status außerhalb von `BELEGT` beendete lediglich einen Ladevorgang, ohne dass unterschieden wurde, *warum* der Ladepunkt nicht belegt ist. Ein defekter Ladepunkt wäre damit rechnerisch als hochverfügbar erschienen.

**Entscheidung:** Zusätzlich zu den Ladevorgängen werden jetzt auch Außer-Betrieb-Phasen segmentiert (`segmentiere_ausfaelle`, technisch dieselbe Segmentierungslogik wie bei Ladevorgängen, siehe Refactoring zu `segmentiere_intervalle`). Drei neue Kennzahlen je Ladepunkt: `ausser_betrieb_stunden`, `ausfallquote_prozent` (analog zur Occupancy Rate) und `verfuegbar_prozent` (Rest des Beobachtungsfensters). Die Ausfall-Events selbst werden zusätzlich als Event-Ebene exportiert (`ausfaelle_goettingen.csv`), analog zur bereits bestehenden Ereignis-Ebene für Ladevorgänge (E6).

**Methodische Besonderheit — keine 12h-Plausibilitätsgrenze für Ausfälle:** Die in E7 eingeführte 12h-Grenze beruht auf der Annahme, dass reale Ladevorgänge (auch lange Übernacht-AC-Ladungen) selten länger dauern; alles darüber gilt als Artefakt verpasster Delta-Updates. Diese Annahme trifft auf Ausfallzeiten nicht zu: Ein defekter Ladepunkt kann plausibel tage- oder wochenlang außer Betrieb bleiben, ohne dass ein Beobachtungsfehler vorliegt. Für Ausfall-Segmente wird daher keine Obergrenze angewendet.

**Ergebnis (Stand 14.07.2026):** 20 beobachtete Ausfallzeiten auf 10 von 317 Ladepunkten. Auffälligster Fall: ein Kaufland-Standort mit `ausfallquote_prozent` von 67,3 % über das gesamte Beobachtungsfenster (12.06.–13.07.) — ohne diese Trennung wäre der Punkt mit `occupancy_rate_prozent` ≈ 1,7 % fälschlich als nahezu durchgängig frei verfügbar erschienen.

**Relevanz für die Arbeit:** Dies ist ein eigenständiger Befund für Kapitel 4 (Datenqualität/empirische Ergebnisse) und schärft die Limitationsdiskussion in Kapitel 5: „Occupancy Rate" allein beantwortet nicht die für die Verwaltung relevante Frage nach der *tatsächlichen* Verfügbarkeit der Infrastruktur — Nutzung und Störung müssen getrennt ausgewiesen werden, sonst wird eine kaputte Säule datentechnisch als „gut verfügbar" fehlinterpretiert.
