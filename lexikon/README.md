# Lexika für Stufe B

| Datei | Inhalt | Rolle | Herkunft |
|---|---|---|---|
| `nachnamen.txt` | 243'402 | Namenssignal | Bundesamt für Statistik (BfS), ständige Wohnbevölkerung, Blatt `CH` |
| `vornamen.txt` | 66'916 | Namenssignal | Bundesamt für Statistik (BfS), Blatt `2024` |
| `ortschaften.txt` | 4'421 | **Gegensignal** + Adresse | Amtliches Ortschaftenverzeichnis (AMTOVZ) |
| `wortliste.txt` | **fehlt noch** | Gegensignal | siehe unten |

Erzeugt mit `scripts/importiere_namen.py` und `scripts/importiere_orte.py`.
Nichts davon ist erfunden.

## Ortschaften: Gegensignal, kein Ersetzungsgrund

Ortsnamen werden **nicht ersetzt** — dieselbe Überlegung wie bei Organisationen (KONZEPT 1.1):
eine Ortschaft ist für sich kein Personendatum, und das Modell braucht den fachlichen Kontext
(„Projekt der Gemeinde Wetzikon"). Sie haben deshalb bewusst keine eigene Ersetzungskategorie.

Ihr Wert liegt woanders: **359 der 4'421 Ortsnamen sind zugleich Nachnamen** — Basel, Baden,
Arbon, Arosa, Bellinzona, Cham. Ohne diese Liste blockierte jeder Satz, der eine Schweizer
Gemeinde nennt.

Zweitnutzen: eine Adresse wird samt `PLZ Ortschaft` als **eine** Fundstelle erfasst
(`Musterstrasse 5, 3011 Bern`), statt nach der Ersetzung `{{P1}}, 3011 Bern` stehen zu lassen.
Erweitert wird nur mit einer Ortschaft aus dem amtlichen Verzeichnis — geraten wird nichts.

## Warum `wortliste.txt` nicht optional ist

Deutsch schreibt **alle** Substantive gross, dazu jedes Satzanfangswort. „Grossgeschrieben" ist
darum fast kein Namenssignal — und viele Schweizer Nachnamen sind zugleich Alltagswörter.

Gemessen an einem HERMES-nahen Probetext (48 verschiedene grossgeschriebene Wörter):

| Stand | Falsche Fundstellen | Bemerkung |
|---|---|---|
| Volle BfS-Listen, ohne Regeln | **16** | u.a. `Der`, `Die`, `Das`, `Kosten`, `Recht`, `Bau` |
| + Satzanfang zählt nicht als Signal | 7 | `Der`/`Die`/`Das` weg |
| + weicher Zeilenumbruch ≠ Satzanfang | **3** | es bleiben `Bau`, `Kosten`, `Recht` |
| + `ortschaften.txt`, + Anredewort gesperrt | 3 | `Basel`/`Arbon`/`Baden` und `Herr` kämen sonst dazu |
| + gepflegte `wortliste.txt` | erwartet 0 | **noch nicht belegt** |

An einem längeren Probetext mit Namen, Adresse und Ortschaften erkennt der Dienst heute
richtig: `Herr Bürgi` (Anrede), `Anna Meier` (Vorname + Nachname), E-Mail, Telefon,
`Musterstrasse 5, 3011 Bern` (Adresse als Einheit) — und blockiert korrekt bei
`Projektleitung: Steiner`. Fälschlich blockieren noch `Kosten`, `Recht`, `Bau`, `Sitz`.

`Der`, `Die` und `Das` sind tatsächlich Schweizer Nachnamen — deshalb stehen sie in der BfS-Liste.
Die verbleibenden drei Kollisionen sind sprachlich nicht auflösbar: `Bau`, `Kosten` und `Recht`
sind Nachname **und** Kernvokabular jedes Projektdokuments. Nur eine Wortliste trennt sie.

Ohne `wortliste.txt` blockiert der Dienst auf gewöhnlichem Verwaltungsdeutsch.
`/pseudo/v1/health` weist das mit `wortliste_fehlt: true` aus.

## Wie die Wortliste entstehen soll

Zwei Wege, beide ohne Erfindung:

1. **Aus dem eigenen Bestand** (bevorzugt): die rund 200 bereits pseudonymisierten PIA-Volltexte.
   Dort wurden Personennamen durch `[Person_099]` ersetzt — **jedes verbliebene grossgeschriebene
   Wort ist per Konstruktion kein Personenname.** Das ergibt eine Wortliste in genau der
   Fachsprache, um die es geht. Vorbehalt: war die damalige Pseudonymisierung lückenhaft, können
   echte Namen mitkommen. Die Liste gehört deshalb in den Bereich `betrieb` — kuratiert,
   im Repo, im Diff prüfbar.

2. **Aus einem offenen Wörterbuch**: die Rechtschreibwörterbücher `de_CH`, `fr_CH`, `it_CH`
   (Hunspell/LibreOffice) enthalten den Grundwortschatz je Sprache. Breiter, aber nicht auf die
   Fachsprache zugeschnitten.

Die Wortliste wirkt nur auf Lexikontreffer **ohne** Stützsignal. Ein Name mit Anrede
(„Frau Bau") oder in der Folge Vorname + Nachname („Anna Bau") wird weiterhin erkannt und
ersetzt — die Wortliste öffnet also kein Loch in der Erkennung.
