# Pseudonymisierung — Konzept

Stand: 2026-07-20 · Version 0.0.1 · Status: **Entwurf freigegeben, Bau noch nicht begonnen**

---

## 1. Zweck und Abgrenzung

Mehrere Schweizer Verwaltungsanwendungen (u.a. HERMES PIA, KI-Technology-Radar) senden Text an
LLM- und Embedding-Dienste im Ausland. Dabei gehen Klarnamen, Geschäfts- und Verfahrensnummern
und weitere Personendaten mit. Bei Justiz- und Verwaltungskunden ist das ein Ausschlusskriterium.

**Pseudonymisierung** ist ein eigenständiger Vorschalt-Dienst, durch den alle KI-Aufrufe laufen.
Er ersetzt Personendaten vor dem Versand durch Platzhalter und setzt sie in der Antwort wieder
ein. Die aufrufende Anwendung erhält Klartext zurück und merkt im Normalfall nichts.

### 1.1 Was dieser Dienst NICHT ist

- **Keine allgemeine Data-Loss-Prevention-Lösung.** Der Umfang ist auf Personendaten in
  KI-Aufrufen begrenzt.
- **Keine Anonymisierung.** Der Dienst leistet *Pseudonymisierung*. Über den fachlichen Kontext
  bleibt ein Vorhaben identifizierbar. Diese Zusage darf nirgends anders formuliert werden —
  weder in der Dokumentation, noch in der API, noch im Vertrieb.
- **Keine Ersetzung von Organisationsnamen.** Das LLM braucht den fachlichen Kontext, sonst
  bricht die Textqualität ein. Organisationen haben deshalb bewusst *gar keine*
  Ersetzungskategorie — die Entscheidung ist im Modell verankert, nicht bloss in der Konfiguration.

### 1.2 Die zentrale Einsicht

Die Schicht muss vor **jedem** Aufruf sitzen, der Text ins Ausland trägt — also auch vor den
Embedding-Aufrufen für den Wissenskorpus, nicht nur vor dem Chat. Das wird regelmässig übersehen.
Im KI-Technology-Radar gehen zusätzlich **Anhänge** durch denselben Ausgangspfad.

---

## 2. Anforderungen (verbindlich)

| Nr. | Anforderung |
|-----|-------------|
| A1 | **Bidirektional.** Ersetzen auf dem Hinweg, Zurückersetzen auf dem Rückweg — robust gegen deutsche Beugung, Zeilenumbrüche und Wiederholung in anderer Form. |
| A2 | **Blockierend.** Ist die Erkennung unsicher, wird der Aufruf NICHT durchgelassen. |
| A3 | **Begründungspflicht.** Beim Blockieren kommt maschinenlesbar zurück, WAS und WARUM beanstandet wurde (Textstelle, Kategorie, Sicherheit). |
| A4 | **Behebbar.** Der Nutzer entscheidet je Fundstelle: echter Personenbezug (ersetzen) oder Fehlalarm (Firmen-/Systemname). |
| A5 | **Lernen nur über gepflegte Listen**, kein Nachtrainieren: deterministisch, prüfbar, rückgängig zu machen. Listen strikt pro Mandant getrennt. |
| A6 | **Abschaltbar, eng begrenzt.** Nur dev/test, nur mit Berechtigung, sichtbar, protokolliert — und auch dann läuft der Aufruf durch den Dienst. |
| A7 | **Mandantenfähig.** Zuordnungen und Listen pro Mandant und Projekt konsistent (dieselbe Person → derselbe Platzhalter). |
| A8 | **Erkennung ausschliesslich lokal** auf dem Schweizer Host. Kein Erkennungsdienst in der Cloud — der sähe genau das, was wir schützen. |
| A9 | **Blockieren vernichtet keinen Text.** Der Aufruf muss nach der Bereinigung unverändert wiederholbar sein. |

---

## 3. Schnittstellenvertrag

### 3.1 Grundform: anbieterkompatibler Stellvertreter

Der Dienst spricht die API der Anbieter selbst. In der Anwendung wird **nur die Basis-URL**
geändert, kein Aufrufcode. Der Anbieter steckt im **Pfadpräfix**:

| `base_url` der Anwendung | resultierende Route | Anbieter |
|---|---|---|
| `https://…:8030/anthropic` | `/anthropic/v1/messages` | Anthropic Messages API |
| `https://…:8030/voyage` | `/voyage/v1/embeddings` | Voyage Embeddings |
| `https://…:8030/<weiterer>` | … | später, ohne Umbau |

Das SDK hängt `/v1/messages` selbst an. Damit bleibt die Zusage «nur Basis-URL ändern» erhalten
und der Dienst ist trotzdem mehr-anbieter-fähig.

### 3.2 Kopfzeilen

| Kopfzeile | Pflicht | Bedeutung |
|---|---|---|
| `X-Pseudo-Anwendung` | ja | `hermes-pia`, `ki-radar`, … |
| `X-Pseudo-Mandant` | ja | Mandanten-ID **innerhalb** der Anwendung (z.B. `org_id`) |
| `X-Pseudo-Projekt` | ja | Konsistenzrahmen für Platzhalter |
| `Authorization` | ja | dienst-eigener Schlüssel (nicht der Anbieterschlüssel) |

Fehlt Anwendung oder Mandant → harter Fehler. **Es gibt keinen Standard-Mandanten.** Ein
Vertipper darf nicht dazu führen, dass Zuordnungen im falschen Topf landen.

### 3.3 Eigener Namensraum (ausserhalb des Anbieterprotokolls)

| Zweck | Aufruf |
|---|---|
| Entscheid zu einem Befund | `POST /pseudo/v1/befunde/{befund_id}/entscheid` |
| Listen lesen/pflegen | `GET\|POST\|DELETE /pseudo/v1/listen/...` |
| Abschaltung beantragen | `POST /pseudo/v1/ausnahme` |
| Gesundheit | `GET /pseudo/v1/health` |

Getrennter Präfix, damit nie ein Feld mit einem Anbieterfeld kollidiert.

### 3.4 Fehlerformat beim Blockieren

**HTTP 409 Conflict**, Rumpf im Anthropic-Fehlerumschlag mit eigenem Fehlertyp:

```jsonc
{
  "type": "error",
  "error": {
    "type": "pseudonymisierung_blockiert",
    "message": "3 Fundstellen erfordern eine Entscheidung.",
    "pseudo": {
      "vorgang_id": "vg_01H...",
      "schema": "1.0",
      "befunde": [
        {
          "befund_id": "bf_01H...",
          "kategorie": "person_name",
          "auszug": "…mit Frau Bürgi besprochen, dass…",
          "treffer": "Bürgi",
          "ort": { "feld": "messages[2].content[0].text", "von": 412, "bis": 417 },
          "sicherheit": 0.61,
          "band": "unsicher",
          "grund": "erkannt_lexikon_nachname; kein_kontextanker_anrede",
          "vorschlag": "ersetzen",
          "moegliche_entscheide": ["ersetzen", "freigeben"]
        }
      ]
    }
  }
}
```

**Begründung 409 statt 400:** 400 heisst im Anbieterprotokoll «Anfrage kaputt» und wird von
Client-SDKs teils nicht wiederholt. 409 heisst «an sich gültig, im aktuellen Zustand nicht
ausführbar» — genau das trifft zu.

**Offen benannter Preis:** Dies ist die einzige Stelle, an der die Anwendungen doch Code
anfassen müssen — sie müssen 409 abfangen und den Rumpf auswerten. «Gar kein Aufrufcode» ist
mit blockierendem Verhalten nicht erreichbar. Wer nicht auswertet, sieht nur einen Fehler; nichts
geht dabei still hinaus. Die Alternative (HTTP 200 mit Ersatzantwort) wurde **verworfen**, weil
ein blockierter Aufruf dann wie ein Erfolg aussähe.

`ort` mit Feldpfad und Zeichenoffsets erlaubt der aufrufenden UI, die Stelle im Diktattext
punktgenau zu markieren.

---

### 3.5 Der Entscheid zu einer Fundstelle

```
POST /pseudo/v1/befunde/{befund_id}/entscheid
{ "entscheid": "freigeben", "muster": "Vogt",
  "begruendung": "Systemname der Fachanwendung", "urheber": "…" }
```

**Der Klartext wird vom Aufrufer mitgeschickt, nicht beim Dienst nachgeschlagen.** Der Dienst
speichert ihn nicht (`befund.treffer_hash` statt Klartext). Zur Absicherung wird das übergebene
`muster` gegen den gespeicherten Wert geprüft — wer den Klartext nicht kennt, kann den Befund
nicht entscheiden. Der gespeicherte Wert ist ein **HMAC**, kein blosser Hash: ein blosser
SHA-256 eines kurzen Nachnamens wäre durch Ausprobieren sofort aufzulösen und damit kein Schutz.

Die beiden Entscheide wirken unterschiedlich:

| Entscheid | Bedeutung | Listeneintrag | Wirkung beim nächsten Aufruf |
|---|---|---|---|
| `freigeben` | Fehlalarm (Firmen-/Systemname) | Freigabe, Bereich `mandant` | Stelle wird nicht mehr gemeldet |
| `ersetzen` | echter Personenbezug | **Sperre**, Bereich `mandant` | Stelle gilt als `sicher` und wird ersetzt |

Ohne den zweiten Fall bliebe eine bestätigte Person dauerhaft im Band `unsicher` und würde bei
jedem Aufruf erneut blockieren.

## 4. Erkennungsstrategie

Alles lokal auf dem Schweizer Host (A8).

### 4.1 Drei Stufen

**Stufe A — deterministische Muster** (hohe Sicherheit, direkt ersetzen):
AHV-Nummer (mit Prüfziffer), IBAN, E-Mail, Telefon CH/LI, Geschäfts- und Verfahrensnummern
(**pro Mandant konfigurierbar** — die Formate der Justiz sind kantonal verschieden),
Sozialversicherungs-/Fallnummern, Adressen mit Hausnummer.

**Stufe B — Lexika und Kontextanker:** CH-Vor-/Nachnamenlisten, Ortschaften; Anker wie
«Herr/Frau/Dr./Regierungsrat/zuständig ist». Ein Anker hebt die Sicherheit; ein blosser
Lexikontreffer ohne Anker tut das nicht.

**Stufe C — lokales statistisches NER** für alles, was Muster und Listen nicht fangen.
**Noch nicht zugesagt** — siehe Abschnitt 8 (Machbarkeit).

### 4.2 Drei Bänder

| Band | Bedeutung | Verhalten |
|---|---|---|
| **sicher** (≥ obere Schwelle) | eindeutig Personenbezug | ersetzen, durchlassen |
| **unsicher** (Graubereich) | könnte Person, könnte Firma/System sein | **blockieren + Befund** (A2) |
| **unauffällig** | kein Signal | durchlassen |

### 4.3 Kategorien (Startmenge)

`person_name`, `person_kontakt`, `geschaeftsnummer`, `verfahrensnummer`, `adresse`, `ahv`,
`finanzkonto`, `datum_geburt`, `benutzerkonto`.

Zusätzlich, **nicht ersetzend**: `bereits_pseudonymisiert` — Platzhalter der Form
`[Person_099]`/`[Org_148]` aus dem bestehenden Seed-Korpus werden erkannt, unangetastet
durchgereicht, nicht als Befund gemeldet und auf dem Rückweg nicht angefasst.

**Organisationen haben bewusst keine Kategorie** (siehe 1.1).

---

## 5. Platzhalter und Rückersetzung

Das technisch heikelste Stück.

### 5.0 Form des Markers — Korrektur gegenüber dem ersten Entwurf

Im ersten Entwurf stand `«P3»`. Diese Form ist **verworfen**: im Schweizer Deutsch sind `« »`
die normalen Anführungszeichen. Ein Modell, das Schweizer Verwaltungstext schreibt, setzt und
normalisiert diese Zeichen ständig — das Gegenteil dessen, was ein Marker braucht.

**Gewählt: `{{P3}}`** — reines ASCII (überlebt cp1252-Exporte, JSON, SQLite), kommt in deutscher
Prosa praktisch nicht vor, hat in Markdown keine Bedeutung und ist kollisionsfrei zu den
Bestandsplatzhaltern `[Person_099]`/`[Org_148]`.

**Nicht behauptet:** ob gängige Tokenizer `{{P3}}` stabil zusammenhalten, ist **nicht gemessen**.
Die Form ist deshalb in `app/kern/platzhalter.py` gekapselt und austauschbar.

### 5.1 Entscheid: Marker statt realistischer Ersatznamen

| Variante | Vorteil | Nachteil |
|---|---|---|
| **A: Marker** (`«P3»`) | Fehlschlag ist **sichtbar** | LLM beugt/zerteilt sie; Textqualität leidet, weil Genus/Numerus fehlen |
| B: realistische Ersatznamen | Textqualität bleibt intakt | Fehlschlag ist **unsichtbar** — ein plausibler falscher Name landet im Verwaltungsdokument |

**Gewählt: Variante A.** Bei Verwaltungsdokumenten ist «still falsch» der schlimmere Ausgang
als «sichtbar kaputt».

### 5.2 Vier Absicherungen

1. **Kollisionsfreie Form.** Muss nachweislich kollisionsfrei zu den Bestandsplatzhaltern
   `[Person_099]`/`[Org_148]` sein, sonst ersetzen wir Korpus-Artefakte zurück. Der genaue
   Zeichensatz ist zusätzlich darauf zu prüfen, ob Tokenizer ihn stabil zusammenhalten.
2. **Toleranter Rückersetzer.** Akzeptiert um den Kern herum: eingeschobene
   Leerzeichen/Zeilenumbrüche, Markdown-Auszeichnung (`*«P3»*`), angehängte Beugungssuffixe
   (`«P3»s`, `«P3»n` → Suffix bleibt am rückersetzten Namen erhalten), Gross-/Kleinschreibung.
3. **Leckprüfung in beide Richtungen**, vor Auslieferung an die Anwendung:
   - (a) unaufgelöste Platzhalter-Fragmente in der Antwort → **Fehler**, keine stille Auslieferung;
   - (b) ein Klartextwert aus der Zuordnungstabelle, den wir nie hingeschickt haben → das Modell
     hat geraten oder wir haben auf dem Hinweg etwas übersehen → melden.
4. **Zeichenstrom-Automat statt `str.replace`.** Bei SSE-Streaming kommt `«P3»` über
   Chunk-Grenzen zerschnitten; die Ausgabe wird nur bis zum letzten sicher unverdächtigen Punkt
   freigegeben, der Rest wartet auf das nächste Chunk. Dasselbe gilt für Platzhalter innerhalb
   von Tool-Use-JSON und strukturierter Ausgabe.
   **v1 unterstützt kein Streaming** (HERMES PIA braucht es nicht), aber die Rückersetzung wird
   **von Anfang an als Zustandsautomat über einen Zeichenstrom** gebaut — sonst müsste sie für den
   Radar vollständig neu geschrieben werden. Nicht-Streaming ist dann der Sonderfall
   «ein einziges grosses Chunk».

### 5.3 Embeddings

Auf dem Embedding-Weg gibt es **keine** Rückersetzung — zurück kommt ein Vektor, kein Text.
Der Hinweg ist aber genauso pflichtig. Folge, die dokumentiert sein muss: der Vektor ist der
Vektor des *pseudonymisierten* Texts.

---

## 6. Datenmodell

```
anwendung(id, schluessel, bezeichnung, aktiv)          # hermes-pia, ki-radar
mandant(id, anwendung_id, externe_id, bezeichnung)     # org_id der Anwendung
projekt(id, mandant_id, externe_id)                    # Konsistenzrahmen

zuordnung(id, anwendung_id, mandant_id, projekt_id, kategorie,
          oberflaeche_hash,          # Suchschlüssel, HMAC (nicht blosser Hash)
          klartext_chiffre,          # verschlüsselt at rest — einzige Klartextquelle
          platzhalter,
          erstellt_am, letzte_nutzung)
  UNIQUE (anwendung_id, mandant_id, projekt_id, kategorie, oberflaeche_hash)
  UNIQUE (anwendung_id, mandant_id, projekt_id, platzhalter)

zuordnung_variante(zuordnung_id, oberflaeche_hash)     # "Bürgi" / "M. Bürgi" / "Marc Bürgi"

listeneintrag(id, bereich, anwendung_id, mandant_id, art,
              muster, mustertyp,      # woertlich | regex
              kategorie, begruendung, urheber,
              gueltig_ab, widerrufen_am, widerrufen_durch)

vorgang(id, anwendung_id, mandant_id, projekt_id, weg, entscheid,
        anzahl_ersetzungen, anzahl_befunde, modell, dauer_ms, erstellt_am)
        # KEIN Klartext, KEINE Prompts

befund(id, vorgang_id, kategorie, band, sicherheit, treffer_hash,
       grund, entschieden_als, entschieden_am, entschieden_durch)

ausnahme(id, anwendung_id, mandant_id, umgebung, beantragt_von,
         begruendung, gueltig_bis, widerrufen_am)      # nur dev/test

anbieterschluessel(id, anwendung_id, mandant_id, anbieter, chiffre, gueltig_ab, widerrufen_am)
```

### 6.1 Mandantenmodell (zweistufig)

```
anwendung        "hermes-pia", "ki-radar"
  └─ mandant     org_id 42 aus HERMES PIA
       └─ projekt
```

Der Schlüssel für Zuordnungen und Listen ist immer das **Blatt** `(anwendung, mandant)` — nie
eine höhere Ebene.

### 6.2 Listen: drei Geltungsbereiche mit harter Asymmetrie

| Bereich | Wer pflegt | Was darf hinein |
|---|---|---|
| `betrieb` | nur Betreiber, versioniert im Repo | **nur Freigaben** technischer Begriffe, nie aus Nutzerklicks |
| `anwendung` | nur Betreiber | **nur Freigaben**, z.B. HERMES-Fachbegriffe |
| `mandant` | Nutzerentscheide | Freigaben **und** Sperren |

Sperren wirken ausschliesslich auf Mandantenebene. Ein Nutzerklick landet **nie** höher als
beim eigenen Mandanten. Damit gilt A5 unverändert: eine Freigabe kann niemals zu einem anderen
Kunden überlaufen. Die geteilten Listen sind kuratiert, im Repo nachlesbar und im Diff prüfbar.

### 6.3 Der unbequeme Punkt

`zuordnung` verknüpft Klarnamen mit Platzhaltern und konzentriert damit genau die
Personendatensammlung, die wir schützen wollen, an einem Ort. **Das ist der bewusst bezahlte
Preis für A7** (Konsistenz über Projekt und Zeit). Die Alternative — rein flüchtige Zuordnung
pro Aufruf — hätte kein Kronjuwel, aber auch keine Konsistenz zwischen zwei Aufrufen desselben
Interviews; HERMES-Dokumente würden uneinheitlich.

Gegenmassnahmen: Verschlüsselung at rest (Schlüsselmaterial aus der Umgebung, nicht in der DB);
Vorgangsprotokolle enthalten **keinen** Klartext und keine Prompts, nur Zähler und Hashes.

### 6.4 Anbieterschlüssel: zentral im Dienst

Die Anwendungen geben ihre Anbieterschlüssel ab; der Dienst hält sie verschlüsselt, pro
`(anwendung, mandant)`, mit Rückfall auf einen Anwendungs-Standardschlüssel.

**Ausschlaggebende Begründung:** Solange HERMES PIA einen eigenen `ANTHROPIC_API_KEY` besitzt,
kann es jederzeit direkt hinausrufen — versehentlich, durch neuen Code, oder weil jemand die
Schicht als Störung empfindet. Ohne Schlüssel ist die Umgehung nicht mehr verboten, sondern
**unmöglich**. Das ist der Unterschied zwischen einer Richtlinie und einer Kontrolle; bei
Justizkunden zählt nur die Kontrolle. Nebeneffekte: Schlüsselwechsel an einer Stelle statt in
vier `.env`-Dateien; Kosten pro Mandant werden ableitbar.

**Preis, offen benannt:** Der Dienst wird zum Schlüsselverwahrer und damit zum lohnenden Ziel.
Er wird ausserdem zum Ausfallpunkt für jede KI-Funktion aller Anwendungen — das ist allerdings
schon durch A2 der Fall und keine Folge der Schlüsselhaltung.

---

## 7. Ablauf bei einem blockierten Aufruf

```
Anwendung ──POST /anthropic/v1/messages──▶ Dienst
                                            │ Erkennung (lokal)
                                            │ ► nur "sicher"   → ersetzen → Anbieter
                                            │                  → zurückersetzen → 200
                                            │ ► ein "unsicher" → NICHTS geht hinaus
                                            ◀── 409 + befunde[]
Anwendung markiert die Fundstellen im Diktattext
Nutzer entscheidet je Fundstelle:
   "echter Personenbezug"   → POST /pseudo/v1/befunde/{id}/entscheid {"entscheid":"ersetzen"}
   "Fehlalarm (Systemname)" → …{"entscheid":"freigeben","begruendung":"Systemname der Fachanwendung"}
                                            │ schreibt listeneintrag (Bereich: mandant)
Anwendung wiederholt den UNVERÄNDERTEN Originalaufruf
                                            │ Befund durch Liste abgedeckt → läuft durch
```

Zwei bewusste Festlegungen:

- **Der Dienst speichert den blockierten Text nicht.** Die Anwendung hält ihn und wiederholt
  ihn (A9). Der Entscheid referenziert die *Textstelle*, nicht die Anfrage. Andernfalls würde
  der Dienst ausgerechnet die heikelsten Texte in einer Zwischenhalde einsammeln.
- **Eine Freigabe wirkt nie mandantenübergreifend** (A5) — durchgesetzt in der Abfrage und
  zusätzlich als eigener Regressionstest festgenagelt.

### 7.1 Abschaltung (A6)

`ausnahme` ist gebunden an Umgebung (`dev`/`test`; in Produktion **serverseitig hart verweigert**,
nicht per Konfiguration), Rolle, Begründung und Ablaufzeit. Der Aufruf läuft weiterhin durch den
Dienst, wird protokolliert, und jede Antwort trägt `X-Pseudo-Status: abgeschaltet`, damit die
Anwendung es sichtbar anzeigen kann.

---

## 8. Betrieb und Machbarkeit

### 8.1 Zielumgebung — kein öffentlicher Zugang

Geteiltes Infomaniak Managed Hosting, Gunicorn, kein Docker in Produktion. SQLite.
CI/CD über Jenkins per SSH. Promotion sequenziell **develop → test → integration → main**,
Version bei jedem Promoten +0.0.1.

**Port-Block: 8030–8033** (develop/test/integration/main).

**Der Dienst bekommt keine Site, keine Subdomain und keinen PHP-Proxy.** Er bindet auf
`127.0.0.1` und ist aus dem Internet nicht erreichbar. Alle Aufrufer laufen auf demselben Host
(HERMES PIA 8000/8003, ProS 8010–8012, Dashboard 8020–8023, KI-Technology-Radar); sie setzen
ihre `base_url` auf `http://127.0.0.1:8030/anthropic` bzw. `…/voyage`.

Der PHP-Proxy existiert bei den übrigen Anwendungen nur, weil Apache öffentlichen Verkehr zu
Gunicorn bringen muss. Hier gibt es keinen öffentlichen Verkehr — und damit liegen weder der
Schlüsseltresor (6.4) noch die Zuordnungstabelle (6.3) je an einer öffentlichen Adresse.
Das ist die einzige Konstellation, in der sich die Konzentration dieser Daten überhaupt
rechtfertigen lässt.

Verwaltung (Listenpflege, Schlüssel, Blockierrate) vorerst über einen SSH-Tunnel
(`ssh -L 8030:127.0.0.1:8030 …`). Eine öffentliche Admin-Site liesse sich später nachrüsten;
den umgekehrten Weg — erst exponieren, dann zurücknehmen — gibt es nicht.

Die Befund-Anzeige für den Nutzer (A4) gehört in die **aufrufende** Anwendung: HERMES PIA
markiert die Stelle im Diktattext, nicht der Dienst.

### 8.2 Gemessene Host-Kennzahlen (2026-07-20)

| Kennzahl | Wert | Bewertung |
|---|---|---|
| Kerne | **4** (geteilt mit allen Anwendungen) | **Engpass** |
| RAM | 11 974 MB total / **7 962 MB verfügbar** | reichlich |
| Swap | 4 095 MB | — |
| Prozesslimit (`ulimit -u`) | 480 | unkritisch |
| Platte | 272 GB frei | unkritisch |
| Python | **3.9.2** | **Risiko** |

**Folgerung:** Stufe C ist speichertechnisch machbar. Mit `gunicorn --preload` wird das Modell
vor dem Fork geladen, sodass Worker es über Copy-on-Write teilen statt es je einmal zu halten.
Der Engpass sind die 4 Kerne: NER läuft auf CPU, ein HERMES-Diktat ist kein kurzer Satz.

### 8.3 Zwei Messungen VOR dem Produktcode

**1. Python-3.9-Kompatibilität — ERLEDIGT (2026-07-20, gegen PyPI geprüft):**

| Bibliothek | Version | `requires_python` | auf 3.9.2 |
|---|---|---|---|
| spaCy | 3.8.14 | `<3.15,>=3.9` | **läuft** |
| presidio-analyzer | 2.2.363 | `<3.15,>=3.10` | **fällt aus** |

**Folgerung:** Die Erkennung wird direkt auf **spaCy** aufgebaut, nicht auf einem Rahmenwerk
darüber. Presidio wäre der naheliegende Fertigbaustein gewesen, ist auf dem Zielhost aber nicht
installierbar. Angesichts der mandantenspezifischen Verfahrensnummern-Muster (4.1 Stufe A) und
der Drei-Bänder-Logik (4.2) hätten wir Presidio an genau diesen Stellen ohnehin aufgebogen.
Eine eigene Python-Version im Home-Verzeichnis ist damit **nicht** nötig.

**2. NER-Latenz an einem echten HERMES-Diktattext** auf dem Host messen — **offen**.
Die Sekundenzahl wird nicht geschätzt.

Erst danach steht fest, ob Stufe C in v1 vorkommt. Bis dahin gilt sie als offen, nicht als zugesagt.

---

## 9. Risiken, nach Gewicht

1. **Stille Falschrückersetzung.** Ein falsch aufgelöster Platzhalter setzt einen plausiblen
   falschen Namen ins Verwaltungsdokument — schlimmer als ein Absturz, weil es niemand merkt.
   *Gegenmittel:* Marker-Variante, Leckprüfung, Fehler statt Auslieferung (5.1/5.2).
2. **Blockierrate frisst die Akzeptanz.** Ein Diktat mit 15 Unterbrechungen benutzt niemand
   freiwillig. Der Erfolg hängt weniger an der Erkennung als daran, wie schnell die Listen pro
   Mandant satt werden. *Gegenmittel:* Blockierrate pro Mandant messbar machen; die Einlernphase
   offen als solche benennen.
3. **Erkennungslücke als falsches Sicherheitsgefühl.** Lokale Erkennung übersieht seltene Namen,
   Diktat-Tippfehler («Bürgi» → «Bürki») und Namen in Anhängen. Der Dienst darf nirgends als
   «garantiert bereinigt» auftreten (siehe 1.1).
4. **Die Zuordnungstabelle als neues Angriffsziel** (6.3).
5. **Streaming und Tool-Use** — lösbar, aber die Stelle mit den meisten Sonderfällen (5.2).
6. **Betrieb auf geteiltem Host** — Modell im Speicher, mehrere Worker, Kaltstart nach dem
   Cron-Neustart; Latenz und CPU sind eine echte Grenze (8.2).
7. **Umgehung durch Vergessen.** Weitgehend entschärft durch die zentrale Schlüsselhaltung (6.4),
   aber nicht für Pfade, die einen eigenen Weg hinaus haben.

---

## 10. Testprinzip

Jeder Regressionstest beginnt mit einem Docstring `"""Beweist: ..."""`.
Unverzichtbar, bevor irgendetwas produktiv geht:

- Beweist: Ein Platzhalter mit deutschem Beugungssuffix wird korrekt zurückersetzt und behält das Suffix.
- Beweist: Ein durch Zeilenumbruch oder Markdown zerteilter Platzhalter wird erkannt.
- Beweist: Eine Freigabe bei Mandant A wirkt bei Mandant B nicht.
- Beweist: Ein unsicherer Befund lässt keinen einzigen Aufruf hinaus — auch keinen Embedding-Aufruf.
- Beweist: Nach dem Entscheid läuft der unveränderte Originalaufruf durch.
- Beweist: Eine Antwort mit unaufgelöstem Platzhalter-Rest wird nicht ausgeliefert.
- Beweist: In Produktion lässt sich keine Ausnahme aktivieren.
- Beweist: Bestandsplatzhalter `[Person_099]` kollidieren nicht mit der eigenen Platzhalterform.

---

## 11. Reihenfolge des Anschlusses

1. **Embedding-Weg des Wissenskorpus** (HERMES PIA) — gleicher Ernst, aber kein Streaming, kein
   Tool-Use, keine Rückersetzung. Die Schicht lässt sich dort vollständig belegen, bevor das
   schwierigste Teil drankommt.
2. **HERMES-PIA-Interview-Loop** — freie Diktattexte, der härteste Fall.
3. **KI-Technology-Radar** mit Streaming (Nähte `_outbound`/`_inbound` liegen bereits;
   **Anhänge gehen ebenfalls durch `_outbound`**).

---

## 12. Grundsatz

Nichts erfinden. Lieber ein Feld leer lassen als eine geratene Angabe. Das gilt für die
Erkennung, für die Dokumentation und für dieses Konzept: was nicht gemessen ist, steht hier
als offen und nicht als Zusage.
