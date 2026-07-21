# Lexika für Stufe B

| Datei | Inhalt | Herkunft |
|---|---|---|
| `nachnamen.txt` | 243'402 Nachnamen | Bundesamt für Statistik (BfS), ständige Wohnbevölkerung, Blatt `CH` |
| `vornamen.txt` | 66'916 Vornamen | Bundesamt für Statistik (BfS), Blatt `2024` |
| `wortliste.txt` | **fehlt noch** | siehe unten |

Erzeugt mit `scripts/importiere_namen.py`. Nichts davon ist erfunden.

## Warum `wortliste.txt` nicht optional ist

Deutsch schreibt **alle** Substantive gross, dazu jedes Satzanfangswort. „Grossgeschrieben" ist
darum fast kein Namenssignal — und viele Schweizer Nachnamen sind zugleich Alltagswörter.

Gemessen an einem HERMES-nahen Probetext (48 verschiedene grossgeschriebene Wörter):

| Stand | Falsche Fundstellen | Bemerkung |
|---|---|---|
| Volle BfS-Listen, ohne Regeln | **16** | u.a. `Der`, `Die`, `Das`, `Kosten`, `Recht`, `Bau` |
| + Satzanfang zählt nicht als Signal | 7 | `Der`/`Die`/`Das` weg |
| + weicher Zeilenumbruch ≠ Satzanfang | **3** | es bleiben `Bau`, `Kosten`, `Recht` |
| + gepflegte `wortliste.txt` | erwartet 0 | **noch nicht belegt** |

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
