# Bestand pseudonymisieren (Wissenskorpus)

Der Dienst selbst ist ein Vorschalt-Proxy für KI-Aufrufe und kennt keine Dateiformate.
Für die Aufbereitung eines Dokumentenbestands gibt es zwei Werkzeuge unter `scripts/`, die
denselben Erkennungs- und Ersetzungskern verwenden.

```bash
pip install -r requirements-werkzeuge.txt

# 1. Trockenlauf: zeigt Zahlen, schreibt nichts
python scripts/pseudonymisiere_bestand.py <quelle> <ziel> --trocken

# 2. Scharf
python scripts/pseudonymisiere_bestand.py <quelle> <ziel>

# 3. Ergebnis prüfen
python scripts/pruefe_korpus.py <ziel>
```

Unterstützt: `.docx`, `.dotx`, `.pdf`, `.xlsx`, `.html`, `.txt`. Nicht unterstützt: `.doc`, `.msg`.

Word-Dateien werden über das rohe Dokument-XML gelesen, nicht über eine Absatz-API — so werden
auch **Tabellenzellen und Inhaltssteuerelemente** erfasst. Gerade dort stehen in
HERMES-Dokumenten die Namen.

## Richtlinienentscheid: `--unsicher ersetzen`

Im Gespräch gilt „unsicher → blockieren, der Mensch entscheidet" (A2). Bei einem Bestand von
200 Dokumenten kann niemand hunderte Fundstellen einzeln entscheiden — und ein Korpus ist etwas
anderes als ein Interview: **zu viel ersetzen kostet dort etwas Kontext, zu wenig ersetzen ist
ein Datenschutzvorfall.** Vorgabe ist deshalb `--unsicher ersetzen`. Mit `--unsicher melden`
lässt sich das umdrehen.

## Was der Lauf bewusst *nicht* tut

Es entsteht **keine Zuordnungstabelle**. Der Lauf ist einwegig; eine Rückersetzung ist weder
möglich noch erwünscht. Platzhalternummern gelten **je Dokument** — dokumentübergreifende
Konsistenz würde erlauben, Personen über Vorhaben hinweg zu verknüpfen, und wäre in einem
*geteilten* Korpus ein Rückschritt.

Beide Skripte geben ausschliesslich Zähler und Kategorien aus, **niemals Fundwerte**. Ein
Prüfbericht, der die Fundstellen ausschreibt, wäre selbst wieder eine Personendatensammlung.

## Gemessener Lauf über 218 Originaldokumente

| | Wert |
|---|---|
| Verarbeitet | 209 |
| Ohne Textinhalt (PDF, vermutlich gescannt) | 7 |
| Nicht lesbar (`.doc`, `.msg`) | 2 |
| Wörter gesamt | 530'345 |
| Platzhalter im Text | 14'240 (**2.69 %** der Wörter, 26.9 je 1000) |
| davon aus unsicheren Fundstellen | 9'713 |

### Vergleich alter / neuer Bestand

Beide mit demselben Prüfer gemessen:

| Restbefund | alter Bestand (189 Dateien) | neuer Bestand (209 Dateien) |
|---|---|---|
| Dateien mit hartem Restbefund | **86** | **1** |
| Namen mit Anker, im Lexikon bestätigt | 205 | 0 |
| Anker-Treffer ohne Lexikonbestätigung | 79 | 1 |
| E-Mail-Adressen | 35 | 0 |
| Adressen | 5 | 0 |
| Telefonnummern | 3 | 0 |

**Grenze dieser Aussage, ehrlich benannt:** Geprüft hat derselbe Erkenner, der auch ersetzt hat.
Er findet im Prüflauf nur, was er grundsätzlich findet — ein Name, den er nie erkennt, taucht in
keiner der beiden Zahlen auf. Der Prüflauf belegt also **Konsistenz, nicht Vollständigkeit**.

Belastbar ist dagegen der *Vergleich*: die 205 lexikonbestätigten Namen, die im alten Bestand
standen, sind im neuen nicht mehr da. Das ist ein von aussen nachvollziehbarer Fortschritt.

## Offene Punkte

- **7 gescannte PDF** kommen ohne Texterkennung gar nicht in den Korpus. Das ist datenschutz-
  seitig unbedenklich, inhaltlich aber eine Lücke.
- **2 Dateien** (`.doc`, `.msg`) sind nicht gelesen worden.
- Die verbleibende Fundstelle im neuen Bestand steht in
  `Projektinitialisierungsauftrag_Justizvollzug 2022+_V0.2_docx.txt` und ist von Hand anzusehen.
- `pruefe_korpus.py` meldet „ohne Platzhalter `[Person_/Org_]`" für alle neuen Dateien — das ist
  erwartet: der neue Bestand verwendet die Form `{{P1}}`. Die Meldung bezieht sich auf die
  Platzhalter des alten Werkzeugs.
