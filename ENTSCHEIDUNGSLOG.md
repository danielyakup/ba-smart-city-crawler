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

## E11 — 21.07.2026: Tesla-Feed als Beleg für strukturell begrenzte Delta-Publikationen (anbieterseitig, nicht durch Abruffrequenz behebbar)

**Anlass:** Rückfrage vor der Präsentation beim Praxispartner, ob die in E7 dokumentierte Beobachtung „exakt 1 Ladepunkt pro Tesla-Snapshot, bundesweit" angesichts des inzwischen 5-Minuten-Rasters noch plausibel ist — bei einem bundesweiten Anbieter erscheint 1 Änderung pro 5 Minuten zunächst unglaubwürdig gering.

**Verifikation:** Stichprobe von 8 konsekutiven Tesla-dyn-Snapshots vom 21.07.2026, 13:40–14:15 Uhr (5-Minuten-Raster). Jeder einzelne Snapshot enthält exakt 1 `energyInfrastructureSiteStatus`-Eintrag mit exakt 1 `refillPointStatus`, jeweils mit unterschiedlicher EVSE-ID quer über Deutschland verteilt (`E00K2NU`, `E0DLEXM`, `E00144Y`, `E000MHD`, `E001AGX`, `E00I0A5`, `E000DE9`, `E0J07HN`). Zum Vergleich: Der statische Tesla-Feed (`Tesla_stat_20260625_175910.json`) führt 3.928 `aegiElectricChargingPoint`-Stammdatensätze bundesweit. Das dynamische Delta enthält also durchgehend nur 1/3928 der Flotte pro Publikation.

**Interpretation:** Dass bundesweit bei Tesla literal nur alle 5 Minuten ein einziger realer Statuswechsel stattfindet, ist unplausibel. Wahrscheinlicher liefert der Tesla-Feed strukturell (Rate-Limit oder Pagination auf Anbieterseite) nur 1 Datensatz pro Publikationszyklus, unabhängig davon, wie viele Ladepunkte sich tatsächlich geändert haben. Das ist eine wichtige Präzisierung von E7: Bei den meisten Anbietern (chargecloud, Eco-Movement) hilft eine höhere Abruffrequenz nachweislich (E8), weil dort die *Publikationsfrequenz* des Anbieters der limitierende Faktor ist. Bei Tesla dagegen limitiert vermutlich die *Datensatzanzahl pro Publikation* — ein Limit, das durch häufigeres Abfragen nicht umgangen werden kann, da es unabhängig vom Zeitpunkt der Abfrage strukturell nur 1 Datensatz liefert.

**Konsequenz:** Der in E7 Punkt 4 dokumentierte Tesla-Totalausfall (keine einzige Statusänderung für die 8 Göttinger Tesla-Ladepunkte im gesamten Beobachtungszeitraum) ist damit nicht (nur) ein Artefakt zu niedriger Abruffrequenz, sondern zu einem erheblichen Teil ein strukturelles, anbieterseitiges Limit, das eine Kommune mit eigenen Mitteln nicht beheben kann — selbst ein minütlicher Abruf würde die Trefferwahrscheinlichkeit für die 8 Göttinger Punkte unter 3.928 bundesweiten Punkten nur graduell verbessern, nicht grundsätzlich lösen. Für die Limitationsdiskussion in Kapitel 5 ein schärferes Argument als „Abrufrate zu niedrig": Bei manchen Anbietern ist die Datengrundlage strukturell zu dünn, unabhängig vom Ressourceneinsatz der Kommune.

**Nachtrag (siehe E12): Diese Interpretation musste nach Prüfung der Mobilithek-Schnittstellendokumentation korrigiert werden** — die Ursache ist überwiegend clientseitig (fehlender `If-Modified-Since`-Header), nicht anbieterseitig. E11 bleibt als Beleg für die *Beobachtung* (1 Ladepunkt pro Snapshot) stehen, die *Erklärung* dafür ist jedoch E12 zu entnehmen.

## E12 — 21.07.2026: Ursache für „1 Ladepunkt pro Tesla-Snapshot" gefunden — fehlender `If-Modified-Since`-Header, kein Anbieter-Limit

**Anlass:** Im Betreuungsgespräch am 21.07.2026 äußerten die Betreuer Unzufriedenheit mit der geringen Zahl belastbarer Kennzahlen, sahen aber an, dass die Ursache nicht zwingend bei der Methodik liegen muss. Vorschlag: die Mobilithek-Schnittstellendokumentation daraufhin prüfen, ob eine bestimmte Abruffrequenz vorgegeben ist und wie das Verhalten einzelner Anbieter (insbesondere der in E11 beschriebene Tesla-Fall: exakt 1 Ladepunkt pro Delta-Snapshot) zu erklären ist.

**Fund in der technischen Schnittstellenbeschreibung (Version 1.3.2, 07.11.2025, Kapitel 4.8, S. 25; explizit referenziert auch aus Kapitel 6.2.1 „Client Pull HTTPS", dem von `main.py` verwendeten Endpunkt):**

> „Enthält der HTTP Request das Header-Field 'If-Modified-Since' nicht, wird das zuletzt eingelieferte Datenpaket von der Mobilithek ausgeliefert. [...] Im Zusammenhang mit Publikationen, für die Delta-Unterstützung aktiviert ist, können unter Nutzung dieses Headers auch Datennehmer über die PULL-Schnittstellen von der Bandbreitenreduktion profitieren, die durch die Nutzung von Delta-Datenpaketen möglich wird. Hierzu wird der erste PULL Request mit einem Zeitstempel weit in der Vergangenheit gestartet. Diese Anfrage liefert das älteste Datenpaket aus dem Datenpuffer aus, das per Definition ein vollständiges Datenpaket ist [...]. In den folgenden PULL Requests wird dann jeweils der Zeitstempel aus dem Header-Element 'Last-Modified' [der vorherigen Antwort] verwendet."

Ergänzend aus Kapitel 4.3: Mobilithek speichert bei aktivierter Delta-Unterstützung **mehrere** Delta-Pakete „in der Reihenfolge ihres Empfangs" in einem Paketpuffer je Subskription; Datennehmer können „auf alle existierenden Datenpakete [...] in der Reihenfolge der Anlieferung zugreifen" — aber nur über den beschriebenen Header-Mechanismus. Ohne ihn liefert jeder Aufruf ausschließlich das **jeweils neueste** Paket, unabhängig davon, wie viele ältere Delta-Pakete seit dem letzten Abruf im Puffer aufgelaufen sind.

**`main.py` (`fetch_data()`) setzt diesen Header bislang nicht** — der Request besteht nur aus `User-Agent`, `Accept`, `Connection`.

**Empirische Verifikation (21.07.2026, Live-Test gegen die Tesla-Subskription, exakt die von `main.py` verwendete URL `.../subscription?subscriptionID=983101210886012928`):**

| Request | Header | Last-Modified der Antwort | Enthaltene Ladepunkt-Einträge |
|---|---|---|---|
| wie `main.py` heute | ohne `If-Modified-Since` | 21.07.2026 13:44:35 | 1 |
| mit `If-Modified-Since` weit in der Vergangenheit | — | 21.07.2026 08:00:20 | **3.949** (vollständiges Basispaket) |
| mit `If-Modified-Since` = Last-Modified des Vorpakets | — | 21.07.2026 08:00:21 (nur 1 Sekunde später) | 1 (erstes Delta nach dem Basispaket) |

Zwischen dem letzten Vollbild (08:00 Uhr) und dem regulären Abruf (13:44 Uhr) lagen 5¾ Stunden, in denen bei Tesla fortlaufend einzelne Delta-Pakete im Puffer aufliefen — das zweite Paket kam bereits eine Sekunde nach dem ersten. Ein Abruf ohne den Header sieht davon ausschließlich das letzte.

**Einordnung — kein Endpunkt-Fehler:** Geprüft wurde auch, ob `main.py` versehentlich einen falschen (veralteten) Endpunkt verwendet, da die Dokumentation für DATEX II v3 zusätzlich einen Pfad unter Kapitel 7 „Legacy-Schnittstellen" beschreibt (`.../subscription/datexv3?subscriptionID=`). Das ist nicht der Fall: `main.py` nutzt bereits den aktuellen, formatunabhängigen REST-Endpunkt aus Kapitel 6.2.1 (`.../subscription?subscriptionID=`) — dieser unterstützt den `If-Modified-Since`-Mechanismus nachweislich ebenfalls (siehe Tabelle oben, gleiche URL verwendet).

**Methodische Einordnung:** Dies korrigiert die Interpretation aus E11 (Tesla-Feed als „strukturell begrenzte Delta-Publikation" anbieterseitig). Die *Beobachtung* aus E11 (exakt 1 Ladepunkt pro Snapshot) bleibt korrekt und reproduzierbar, die *Erklärung* war jedoch unvollständig: Es handelt sich überwiegend um ein clientseitiges Abrufproblem, nicht um ein Limit des Anbieters. Im ADR-Rahmen ist das ein lehrreicher Fall von Fehlattribution innerhalb eines BIE-Zyklus — die Betreuer-Rückmeldung, in der Primärdokumentation nachzuschauen, hat die Ursache direkt freigelegt. Für die Arbeit ist das positiv zu werten: Es zeigt, dass die Limitation *behebbar* ist und nicht (wie in E11 angenommen) strukturell beim Anbieter liegt.

**Offene Punkte für die Umsetzung (noch nicht implementiert, Stand 21.07.2026):**
1. `fetch_data()` müsste pro Feed in einer Schleife `If-Modified-Since` mitschicken (erster Aufruf: Datum weit in der Vergangenheit) und bei jedem weiteren Aufruf den `Last-Modified`-Wert der Vorantwort übernehmen, bis Status 304 („kein neueres Paket") zurückkommt.
2. Die Dokumentation nennt einen Fehlercode 404 auch für „die maximale Anzahl an Zugriffen wurde überschritten" — eine konkrete Obergrenze ist nicht dokumentiert. Die Schleife muss diesen Fall abfangen (z. B. Abbruch mit Wartezeit statt Absturz), bevor sie produktiv/per Cron läuft.
3. Kapitel 4.4 zufolge werden auch Delta-Pakete nach Ablauf einer vom Datengeber konfigurierten Gültigkeitsdauer aus dem Puffer verworfen — die Methode holt damit den seit dem letzten erfolgreichen Abruf aufgelaufenen Rückstand nach, garantiert aber keine lückenlose Historie, falls die Gültigkeitsdauer kürzer als der Abstand zwischen zwei Crawl-Läufen ist.
4. Nach Implementierung: `extract_zeitreihe.py` und `berechne_kennzahlen.py` erneut laufen lassen und die E7/E8/E11-Zahlen mit den dann deutlich dichteren Daten neu bewerten.

## E13 — 23.07.2026: E12-Nachlauf umgesetzt (Punkt 4) — Tesla-Fix bestätigt, dabei zwei weitere Bugs gefunden und behoben

**Anlass:** Umsetzung von E12 Punkt 4 — Export-Pipeline nach dem `If-Modified-Since`-Fix erneut laufen lassen und die Zahlen neu bewerten.

**Bestätigung E12:** Tesla liefert jetzt 280 Statusänderungen und 63 Ladevorgänge auf den 8 Göttinger Punkten (vorher: 0, siehe E11/E12-Totalausfall). Die Diagnose aus E12 ist damit empirisch verifiziert.

**Befund 1 — hhenergienetz blieb trotz E12-Fix bei 0 Ladevorgängen, obwohl `charging`/`occupied`-Status-Einträge im Feed auftauchen.** Ursache: `iter_status_updates()` in `extract_zeitreihe.py` sucht `lastUpdated` auf `aegiElectricChargingPointStatus`-, Station- und Site-Ebene — bei hhenergienetz existiert das Feld dort nicht. Die einzige `lastUpdated`-Angabe auf dieser Ebene steckt in `energyRateUpdate[]`, bezieht sich dort aber nachweislich auf den **Energiepreis** (`energyPrice`/`energyRateReference`), nicht auf den Ladepunkt-Status — ein naiver Fallback auf dieses Feld wäre inhaltlich falsch gewesen. Auch `reference.versionG` scheidet aus: Stichprobe über mehrere Snapshots zeigt einen sitegleichen, über den gesamten Beobachtungszeitraum konstanten Wert, keinen Änderungszeitpunkt. Als Konsequenz kollabierte der bisherige Dedup-Schlüssel `(punkt, lastUpdated, status)` bei durchgehend leerem `lastUpdated` jede Wiederholung desselben Status auf eine einzige Zeile — es blieb keine Sequenz übrig, aus der sich Ladevorgänge segmentieren ließen.

**Korrektur (noch am selben Tag, auf Nachfrage geprüft):** Die erste Fassung dieses Eintrags behauptete, hhenergienetz liefere *gar keinen* Änderungszeitpunkt. Das war voreilig — geprüft wurden nur die drei Stellen, an denen `iter_status_updates()` bisher nachsah. Ein vollständiger Abgleich aller Schlüssel eines hhenergienetz-Snapshots zeigt zwei bis dahin ungenutzte Felder auf **Publikationsebene** (nicht pro Ladepunkt, sondern pro Delta-Nachricht): `messageGenerationTimestamp` (im `exchangeInformation`-Umschlag) und `publicationTime` (in `aegiEnergyInfrastructureStatusPublication`). Beide ändern sich zwischen aufeinanderfolgenden Snapshots sub-sekundengenau und sind nachweislich kein Artefakt des E12-Fixes — dieselben Felder finden sich bereits in der ältesten vorhandenen hhenergienetz-Datei vom 05.06.2026. Sie existieren zudem generisch im DATEX-II-Umschlag anderer Anbieter (z. B. chargecloud), werden dort aber nicht gebraucht, weil deren Feeds ein echtes `lastUpdated` je Ladepunkt liefern.

**Fix 1 (korrigiert):** `iter_status_updates()` nutzt jetzt `publicationTime` der Publikation als zusätzlichen Fallback, bevor auf den Abrufzeitpunkt (`erfasst_am`) zurückgegriffen wird: `cp.lastUpdated` → `station.lastUpdated` → `site.lastUpdated` → `publicationTime` → `erfasst_am`. Für hhenergienetz greift damit ein echter, anbieterseitiger Zeitstempel — nur eben je Nachricht/Delta-Paket, nicht je einzelnem Ladepunkt (mehrere Punkte in derselben Nachricht teilen sich denselben Wert). Der `erfasst_am`-Fallback bleibt als letztes Sicherheitsnetz bestehen, für den Fall, dass eine Publikation auch `publicationTime` einmal nicht mitliefert.

**Befund 2 (bei der Fehlersuche zu Befund 1 zusätzlich entdeckt, deutlich größere Tragweite):** Der E12-Fix hat das Dateinamensformat in `main.py` (`fetch_data()`) von `{name}_{YYYYMMDD}_{HHMMSS}.json` auf `{name}_{YYYYMMDD}_{HHMMSS}_{Mikrosekunden}.json` umgestellt — notwendig, weil die Nachhol-Schleife jetzt mehrere Pakete pro Sekunde abrufen kann und eindeutige Dateinamen braucht. `snapshot_zeitpunkt()` in `extract_zeitreihe.py` wurde dabei nicht mit angepasst: Die Regex `(\d{8})_(\d{6})\.json$` griff beim neuen Format nicht mehr, wodurch `erfasst_am` für **jede seit dem 21.07.2026 abgerufene Datei leer blieb** — providerübergreifend, nicht nur bei hhenergienetz. Konkret betroffen: 4.457 von 5.724 Statusänderungen (78 %) im Stand vor diesem Fix. Da `berechne_kennzahlen.py` das Beobachtungsfenster über `erfasst_am` bestimmt (Zeile ~126–130), wurde das Fensterende dadurch stillschweigend auf die letzte Datei mit altem Namensformat zurückgestutzt — aktuellere Daten (inkl. der frisch gewonnenen Tesla-Ladevorgänge) flossen zwar in die Ladevorgangs-/Ausfall-Segmentierung ein (die über `geaendert_am` läuft), nicht aber korrekt in die Occupancy-/Ausfallquoten-Berechnung, die auf dem Fenster basiert.

**Fix 2:** Regex erweitert auf `(\d{8})_(\d{6})(?:_\d+)?\.json$` — deckt altes und neues Dateinamensformat ab.

**Ergebnis nach beiden Fixes (23.07.2026, Neulauf von `extract_zeitreihe.py` und `berechne_kennzahlen.py` nach der Korrektur):**

| Kennzahl | vorher (vor E13) | nachher |
|---|---|---|
| Statusänderungen gesamt | 5.724 | 7.098 |
| … davon `erfasst_am` leer | 4.457 (78 %) | 0 |
| Statusänderungen hhenergienetz | 44 | ca. 1.500 |
| Ladevorgänge hhenergienetz | 0 | 112 (auf allen 12 Ladepunkten) |
| Ladevorgänge gesamt | 637 | 1.044 (776 plausibel ≤ 12 h, 268 als unplausibel markiert) |
| Beobachtungsfenster | (durch Bug verkürzt) | 12.06.2026 18:48 – 23.07.2026 15:18 UTC |

**Betriebsnotiz:** Beim ersten Neulauf kam es zu einer beschädigten Zeile in `statusaenderungen_goettingen.csv` (Feldanzahl-Fehler beim Einlesen in `berechne_kennzahlen.py`), weil der manuelle Skriptaufruf zeitgleich mit dem seit dem 21.07. laufenden Cron-Job `auswertung_aktualisieren.sh` (alle 15 Minuten, siehe Crontab) in dieselbe Datei schrieb. Der Cron-Job selbst schützt sich per Lock-Datei (`data/.auswertung.lock`) vor überlappenden *eigenen* Läufen, nicht aber vor gleichzeitigen manuellen Aufrufen derselben Skripte. Betroffen war nur der eine Neulauf, behoben durch erneutes, isoliertes Ausführen zwischen zwei Cron-Takten. Für künftige manuelle Skriptaufrufe: entweder auf einen `data/.auswertung.lock`-freien Moment achten oder den Cron-Takt kurz aussetzen.

**Methodische Einordnung:** Ein weiteres Beispiel dafür, dass Anbieter-Heterogenität in den DATEX-II-Feeds nicht abschließend katalogisierbar ist (vgl. CLAUDE.md-Abschnitt zu den Fallstricken) — hhenergienetz ist damit der sechste dokumentierte Sonderfall nach der `aegiRefillPointStatus`-Umbenennung bei EnBW, diesmal in der Ausprägung „Zeitstempel existiert, aber nur auf Nachrichten- statt auf Punktebene". Befund 2 zeigt zudem ein Muster, das für die Methodenkritik in Kapitel 5 relevant ist: Ein gezielter Fix (E12) führte durch eine Nebenwirkung (Dateinamensänderung) zu einem neuen, stillen Datenqualitätsproblem, das nur auffiel, weil die Ergebnisse nach dem Fix aktiv gegengeprüft wurden. Und die Selbstkorrektur innerhalb dieses Eintrags ist selbst ein Beleg dafür: Die erste, zu schnelle Diagnose („kein Zeitstempel vorhanden") hätte unnötig Präzision verschenkt — erst die gezielte Nachfrage, ob das wirklich stimmt, deckte die bessere Lösung auf.

## E14 — 23.07.2026: Occupancy Rate & Co. durch Gesamtfenster künstlich verwässert — zweites, kürzeres "verlässliches Fenster" eingeführt

**Anlass:** Rückfrage, ob die auf E13 folgenden Kennzahlen plausibel sind — die Occupancy Rate wirkte über alle 317 Ladepunkte hinweg auffällig niedrig (Median 0,25 %, Mittelwert 0,49 %, Maximum 4,0 %).

**Diagnose:** `occupancy_rate_prozent` teilt die beobachtete Belegt-Zeit durch die Länge des GESAMTEN Beobachtungsfensters seit Crawling-Beginn (12.06.2026, aktuell 40,9 Tage). Eine Auswertung der plausiblen Ladevorgänge nach Kalenderwoche zeigt aber, dass **91 % aller 776 plausiblen Ladevorgänge aus den letzten 3,6 Tagen** des Fensters stammen (seit 20.07.2026):

| Woche | EnBW | Tesla | chargecloud | ecomovement | hhenergienetz |
|---|---|---|---|---|---|
| 22.06.–28.06. | 0 | 0 | 0 | 6 | 0 |
| 29.06.–05.07. | 0 | 0 | 0 | 8 | 0 |
| 06.07.–12.07. | 0 | 0 | 1 | 6 | 0 |
| 13.07.–19.07. | 3 | 0 | 5 | 42 | 0 |
| 20.07.–23.07. | 57 | 65 | 311 | 160 | 112 |

Das deckt sich mit der dokumentierten Historie: 30-Minuten-Raster bis 11.07. (E7/E8), chargecloud erst ab 25.06. überhaupt abonniert, Tesla komplett ausgefallen bis zum E12-Fix (21.07., 19:48 Uhr Ortszeit), hhenergienetz durch den in E13 behobenen Bug bis heute praktisch ohne segmentierbare Ladevorgänge. Konkret nachgerechnet: Occupancy übers Gesamtfenster (alle 317 Punkte zusammen) ergibt 0,49 %; dieselbe Rechnung nur über die letzten 3,6 Tage (seit 20.07., durchgängig 5-Minuten-Raster plus alle Fixes aktiv) ergibt 4,57 % — knapp Faktor 9 höher. Die Kennzahl war also kein neuer Bug, sondern die erwartbare, aber in ihrer Größenordnung unterschätzte Folge des in E7/E8 bereits dokumentierten "beobachtete Untergrenze"-Vorbehalts: Das lange Gesamtfenster besteht zu einem Großteil aus Wochen mit strukturell unvollständiger Datengrundlage, die aber weiterhin ungekürzt in den Nenner einfließen.

**Entscheidung — zwei Fenster statt eines:** `berechne_kennzahlen.py` unterscheidet jetzt zwischen dem **Gesamtfenster** (seit 12.06.2026, für absolute Zählungen: `ladevorgaenge`, `belegt_stunden`, `ausfaelle_anzahl`, `ausser_betrieb_stunden`, `mittlere_dauer_min` sowie `occupancy_rate_prozent` als Vergleichswert) und dem **verlässlichen Fenster** (seit dem präzise datierten E12-Fix-Deployment, `VERLAESSLICHES_FENSTER_START = 2026-07-21T17:48:21 UTC`). Ausschließlich übers verlässliche Fenster laufen ab sofort: `ausfallquote_prozent`, `verfuegbar_prozent`, `ladevorgaenge_pro_tag` sowie die neue Spalte `occupancy_rate_verlaesslich_prozent`. `occupancy_rate_prozent` (Gesamtfenster) bleibt zusätzlich erhalten, weil Occupancy Rate die zentrale Interview-Kennzahl ist (Block B, 23.06.2026) und der Vergleich zwischen beiden Fenstern selbst aussagekräftig ist.

**Wichtig für die Konsistenz:** `verfuegbar_prozent = 100 − occupancy_rate_verlaesslich_prozent − ausfallquote_prozent` — alle drei Anteile beziehen sich auf dasselbe (verlässliche) Fenster und summieren sich exakt auf 100 %. Vorher hätte eine Mischung aus Gesamtfenster-Occupancy und (fälschlich ebenfalls Gesamtfenster-basierter) Ausfallquote in Kombination mit einem auf das verlässliche Fenster verkürzten Zähler zu einer nicht mehr interpretierbaren Kennzahl geführt — deshalb wurde für `ausser_betrieb_stunden` intern eine zusätzliche, nur auf das verlässliche Fenster beschränkte Zwischensumme eingeführt (nicht separat exportiert), analog für die Ladevorgänge.

**Dashboard angepasst:** `dashboard.py` zeigt in der Ladepunkt-Tabelle jetzt `occupancy_rate_verlaesslich_prozent` als primäre "Occupancy (%)"-Spalte (konsistent mit Ausfallquote/Verfügbarkeit), die Gesamtfenster-Variante bleibt als "Occupancy gesamtes Fenster (%)" danebenstehen. Der Lesehinweis-Kasten erklärt die Zwei-Fenster-Logik.

**Ergebnis nach der Umstellung:** Median `occupancy_rate_verlaesslich_prozent` über alle 317 Punkte: 2,70 % (Mittelwert 6,36 %, Maximum 48,61 %) — deutlich aussagekräftiger als die 0,25 %/0,49 % übers Gesamtfenster, ohne die Gesamtfenster-Zahl als ehrlichen Kontext zu verlieren.

**Methodische Einordnung:** Das mit E14 eingeführte verlässliche Fenster ist explizit an ein dokumentiertes, präzise datiertes Ereignis (E12-Deployment) gekoppelt, nicht an ein willkürlich gewähltes Datum — wichtig für die Reproduzierbarkeit, falls in der Verteidigung nach der Herleitung des Stichtags gefragt wird. Der Befund reiht sich in E7/E8/E12/E13 ein: Ein wiederkehrendes Muster dieser Arbeit ist, dass Kennzahlen aus Delta-Feeds nur so gut sind wie die kontinuierlich verbesserte Abruf-Infrastruktur dahinter — und dass jede Verbesserung (5-Minuten-Raster, vollständige Delta-Abholung, providerspezifische Zeitstempel-Fallbacks) zunächst rückwirkend gegen die gesamte Historie geprüft werden muss, bevor aggregierte Prozentkennzahlen als aussagekräftig gelten können.

## E15 — 23.07.2026: Plausibilitätsgrenze nach Stromart getrennt, Median als robusterer Dauer-Wert ergänzt

**Anlass:** Rückfrage, ob die mittlere Ladedauer von ~118 Minuten nicht zu hoch wirkt und ob die 12h-Plausibilitätsgrenze (E7) dafür nicht zu großzügig ist.

**Diagnose:** Die 118 Minuten sind der **Mittelwert** einer stark rechtsschiefen Verteilung — der Median lag bereits vorher bei 58–59 Minuten. Der lange Schwanz verteilt sich aber nicht gleichmäßig, sondern auf zwei unterschiedliche Muster:

1. **66 AC-Sessions >4h:** enden alle sauber mit Status `available`, Start abends (17–19 Uhr), Ende morgens (4–7 Uhr) — plausibles Übernacht-Laden, kein Artefakt.
2. **36 DC-Sessions >4h:** DC-Schnellladung sollte physikalisch selten über 1–2h dauern. Aufschlüsselung nach Anbieter: 26 von 36 stammen von ecomovement — für diesen Anbieter ist ein verzögertes `lastUpdated` bereits in E8 dokumentiert. Die langen DC-Sessions sind also überwiegend ein bekanntes, anbieterspezifisches Artefakt, kein Hinweis darauf, dass die Grenze generell zu locker ist.

**Warum kein pauschal niedrigerer Cutoff:** Eine für alle Ladepunkte einheitlich abgesenkte Grenze (z. B. 4–6h) hätte die 66 legitimen AC-Übernachtladungen mit aussortiert und die ohnehin niedrige Occupancy Rate (E14) weiter gedrückt — am eigentlichen Problem (einzelne anbieterspezifische DC-Ausreißer) aber vorbeigezielt.

**Entscheidung:** `MAX_PLAUSIBLE_DAUER_MIN` durch zwei Konstanten ersetzt — `MAX_PLAUSIBLE_DAUER_AC_MIN = 12*60` (unverändert) und `MAX_PLAUSIBLE_DAUER_DC_MIN = 3*60` (physikalisch großzügig für DC-Schnellladung bemessen). `segmentiere_intervalle()` nimmt jetzt eine Funktion `schwelle_fn(evse_id)` statt eines festen Werts entgegen; `segmentiere_ladevorgaenge()` schlägt darüber die Stromart aus den Stammdaten nach (Fallback AC bei fehlender Angabe). Ausfälle (E10) bleiben unverändert ohne Obergrenze.

Zusätzlich: `kennzahlen_ladepunkte.csv` weist jetzt `median_dauer_min` neben `mittlere_dauer_min` aus — der robustere "typische" Wert, unabhängig von der Cutoff-Frage. Das Dashboard zeigt beide Werte.

**Ergebnis (Neulauf 23.07.2026, alle 317 Ladepunkte):**

| Kennzahl | vorher (E14, ein Cutoff 12h) | nachher (E15, AC 12h / DC 3h) |
|---|---|---|
| Plausible Ladevorgänge | 780 | 734 (46 DC-Ausreißer neu ausgeschlossen) |
| Mittlere Dauer | 118 min | 100 min |
| Median Dauer | 59 min | 54 min |
| Occupancy Rate (verlässliches Fenster, Median über alle Punkte) | 2,70 % | 2,64 % |

Die Korrektur ist bewusst moderat: Sie bereinigt einen konkret identifizierten, anbieterspezifischen Ausreißer-Cluster, verzerrt aber nicht die insgesamt niedrige Occupancy Rate zusätzlich.

**Methodische Einordnung:** Reiht sich in E7/E8/E14 ein — auch dieser Befund zeigt, dass eine einzelne globale Plausibilitätsgrenze die physikalisch unterschiedlichen Ladeprofile (AC/DC) und die unterschiedliche Datenqualität einzelner Anbieter vermischt. Die Differenzierung ist so gewählt, dass sie an einem nachvollziehbaren Kriterium (Ladeleistung/Stromart, nicht Anbieter-Blacklisting) hängt, auch wenn der auslösende Befund anbieterspezifisch war (ecomovement).

## E16 — 23.07.2026: Systematischer Code-Review der gesamten Export-Pipeline (sechs Befunde behoben)

**Anlass:** Nach E12–E15 wurde ein gezielter Correctness-Review über `main.py`, `extract_stammdaten.py`, `extract_zeitreihe.py`, `berechne_kennzahlen.py` und `compare_bnetza.py` angefordert — mit dem expliziten Auftrag, nach genau der Fehlerklasse zu suchen, die E12–E15 bereits mehrfach zutage gefördert hatte (anbieterspezifische DATEX-II-Annahmen, stille Fallback-Werte, inkonsistente Zeitfenster-/Nennerbezüge). Alle sechs Befunde wurden an echten Daten verifiziert und behoben.

**Befund 1 — `MAX_PAKETE_PRO_FEED = 500` kappte die Nachhol-Schleife still (main.py).** Verifiziert über die Dateinamen-Zeitstempel in `data/`: Tesla (199 von 3780 Cron-Läufen), EnBW (131 von 3778) und hhenergienetz (104 von 3787) haben das Limit wiederholt erreicht, ohne dass die Warteschlange nachweislich leer war (kein 304/204). Kein permanenter Datenverlust (`if_modified_since` bleibt korrekt gespeichert, der Rest wird nachgeholt), aber ein bis dahin unsichtbarer Bearbeitungsstau — widerspricht der in E12 dokumentierten Absicht „vollständige Abholung". **Fix:** Limit auf 1000 angehoben; `for`/`else`-Konstrukt ergänzt, das explizit warnt, wenn die Schleife das Limit erreicht, ohne dass die Warteschlange als leer gemeldet wurde.

**Befund 2 — hhenergienetz-Statusänderungen durch den E13-Fallback strukturell aufgebläht (extract_zeitreihe.py).** `publicationTime` (E13-Fallback) ist ein Nachrichten-, kein Punkt-Zeitstempel; hhenergienetz republiziert nahezu den gesamten Bestand bei fast jeder Nachricht. Jede Republikation eines UNVERÄNDERTEN Status erzeugte dadurch einen neuen Dedup-Schlüssel und sah wie eine echte Statusänderung aus. Die abgeleiteten Ladevorgänge/Ausfälle waren davon nicht betroffen (die Segmentierung überspringt ohnehin gleiche Folge-Status), aber die rohe Zeilenzahl in `statusaenderungen_goettingen.csv` war es. **Fix:** Neue Funktion `entferne_wiederholte_status()` entfernt unmittelbar aufeinanderfolgende Zeilen mit identischem Status pro Ladepunkt (ein Wechsel über einen anderen Status dazwischen bleibt erhalten). **Ergebnis:** 4.506 von 7.304 Zeilen waren solche Wiederholungen — bereinigt auf 2.798 echte Statusänderungen.

**Befund 3 — Unplausible Ladevorgänge verschwanden unbeabsichtigt im Verfügbarkeits-Topf (berechne_kennzahlen.py).** Als unplausibel markierte Sessions (E15) wurden aus `belegt_stunden`/Occupancy entfernt, flossen aber auch nicht in die Ausfallquote ein — die Restformel `100 − occupancy − ausfallquote` verbuchte diese Zeit dadurch implizit als „verfügbar", obwohl der Punkt nachweislich durchgehend `charging`/`occupied` meldete. Verifiziert: ca. 38 % der gezählten Belegt-Zeit im verlässlichen Fenster war betroffen. **Fix:** Neue Kennzahl `unklar_quote_prozent` (Zeit aus unplausiblen Sessions im verlässlichen Fenster, gleiche Fensterbasis wie Ausfallquote/Occupancy). `verfuegbar_prozent = 100 − occupancy_rate_verlaesslich_prozent − ausfallquote_prozent − unklar_quote_prozent`. Alle vier Anteile summieren sich exakt auf 100 % (geprüft über alle 317 Ladepunkte). Betroffen: 29 von 317 Punkten mit `unklar_quote_prozent` > 0, bis zu 42 % bei einzelnen Punkten.

**Befund 4 — `provider_goe_sites` wurde pro Datei überschrieben statt akkumuliert (compare_bnetza.py).** Bei zwei Snapshots desselben Anbieters gewann bisher der zuletzt verarbeitete; zusätzlich fehlte `sorted()` auf der Dateiliste (im Gegensatz zu `extract_stammdaten.py`), sodass die Verarbeitungsreihenfolge von der nicht garantierten `glob()`-Reihenfolge abhing. Betraf nur die informative „Goe-Sites"-Spalte der Konsolenausgabe, nicht die Coverage-Prozentzahlen selbst (die bereits über global akkumulierte Mengen korrekt berechnet werden). **Fix:** `sorted()` ergänzt; `provider_goe_sites` durch `provider_goe_site_ids` ersetzt — akkumuliert jetzt eindeutige Site-IDs über alle Snapshots eines Anbieters statt sie zu überschreiben. **Verifiziert:** Nach dem Fix unverändert 84,90 % Gesamtabdeckung (identisch zu E5) und identische Goe-Sites-Werte je Anbieter (z. B. chargecloud weiterhin 106) — in diesem konkreten Datenstand war der Bug folgenlos, weil die Site-Mengen zwischen den beiden Snapshots je Anbieter identisch waren, aber die Berechnung ist jetzt unabhängig vom Zufall reproduzierbar.

**Befund 5 — Smartlab-Archivdateien konnten über lose Substring-Filter wieder in die Pipeline gezogen werden.** `"stat"`/`"static"` bzw. `"dyn"`/`"dynamic"` als Substring-Test matchte auch `smartlab_afir_static_*.json`/`smartlab_afir_dynamic_*.json` — die laut CLAUDE.md bewusst als Beleg archivierten, aber nicht mehr aktiven Feeds (E2). Aktuell folgenlos (0 Göttingen-Treffer, wie in E2/E4/E5 dokumentiert), aber zufallsbedingt statt durch eine explizite Regel abgesichert. **Fix:** Alle drei betroffenen Dateilisten (`extract_stammdaten.py`, `extract_zeitreihe.py`, `compare_bnetza.py`) schließen Dateinamen mit `smartlab`-Präfix jetzt explizit aus.

**Befund 6 — Fehlendes Exception-Handling um JSON-Dekodierung/Dateischreiben (main.py).** `response.json()` und der Dateischreib-Block lagen außerhalb des `try/except`, das nur den `session.get()`-Aufruf absichert. Ein kaputtes/unerwartetes 200er-Paket hätte den gesamten Cron-Lauf abgebrochen (nur die Lock-Datei wird sauber freigegeben), statt nur den betroffenen Feed zu überspringen. Kein Hinweis, dass dies bereits eingetreten ist — Robustheits-Lücke, kein bestätigter Vorfall. **Fix:** JSON-Dekodierung und Dateischreiben in einen eigenen `try/except` gefasst; bei Fehler wird nur die Warteschlange dieses Feeds abgebrochen (ohne `if_modified_since` fortzuschreiben, sodass das Paket beim nächsten Lauf erneut versucht wird), die übrigen Feeds laufen normal weiter.

**Ergebnis nach allen Fixes (Neulauf der gesamten Pipeline, 23.07.2026):**

| Kennzahl | vorher | nachher |
|---|---|---|
| Statusänderungen gesamt | 7.304 | 2.798 (4.506 Republikations-Duplikate entfernt) |
| Ladevorgänge (plausibel) | 780 | 755 (Fenster hat sich zwischen den Läufen leicht verschoben) |
| Neue Kennzahl `unklar_quote_prozent` | — | Median 0 %, 29 von 317 Punkten > 0, max. 42,01 % |
| BNetzA-Gesamtabdeckung | 84,90 % | 84,90 % (unverändert, wie erwartet) |
| Göttinger Ladepunkte (Stammdaten) | 317 | 317 (unverändert, Smartlab-Ausschluss war erwartungsgemäß folgenlos) |

**Methodische Einordnung:** Dieser Review-Durchgang unterscheidet sich von E12–E15 dadurch, dass er nicht durch eine einzelne Rückfrage zu einer auffälligen Zahl ausgelöst wurde, sondern durch einen systematischen, gezielt nach der wiederkehrenden Fehlerklasse suchenden Agenten-Review — im ADR-Rahmen ein Übergang vom reaktiven BIE-Zyklus (Befund → Fix → Neubewertung, wie in E12–E15) zu einem proaktiven Prüfschritt. Bemerkenswert für die Methodenkritik: Trotz des systematischen Ansatzes blieben die Befunde in ihrer Schwere gestaffelt (ein struktureller Datenverlust-Kandidat, mehrere Interpretationsfehler bei abgeleiteten Kennzahlen, zwei folgenlose Robustheits-Lücken) — auch ein gezielter Review ersetzt nicht die kontinuierliche Neubewertung nach jeder Pipeline-Änderung, die sich durch E12–E16 zieht.
