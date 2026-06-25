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
