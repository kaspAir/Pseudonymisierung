# Anbindung einer Anwendung — Spezifikation

Dieses Dokument beschreibt den **Weg** einer Anbindung mit Begründungen und Abnahmekriterien.
Die feldgenaue Referenz aller Endpunkte steht in [`API.md`](API.md).

Konkrete Befunde zu HERMES PIA stehen in Abschnitt 6.

---

## 1. Grundform

Der Dienst spricht die API der Anbieter selbst. In der Anwendung wird **nur die Basis-URL**
geändert — der Anbieter steckt im Pfadpräfix:

| Anbieter | Basis-URL für die Anwendung | vollständiger Pfad |
|---|---|---|
| Anthropic | `http://127.0.0.1:8040/anthropic` | `POST /anthropic/v1/messages` |
| Voyage | `http://127.0.0.1:8040/voyage` | `POST /voyage/v1/embeddings` |

Ports: `8040` develop · `8041` test · `8042` integration · `8043` main.

Der Dienst ist **nur über `127.0.0.1` erreichbar** (keine Site, keine Subdomain, kein Proxy).
Die aufrufende Anwendung läuft auf demselben Host.

Rumpf und Antwort sind **feldgleich** zur Anbieter-API. Am JSON ändert sich nichts.

---

## 2. Pflicht-Kopfzeilen

| Kopfzeile | Beispiel | Bedeutung |
|---|---|---|
| `X-Pseudo-Anwendung` | `hermes-pia` | im Dienst registrierte Anwendung |
| `X-Pseudo-Mandant` | `42` | Mandant **innerhalb** der Anwendung |
| `X-Pseudo-Projekt` | `session-137` | Konsistenzrahmen für Platzhalter |

Fehlt eine davon → **HTTP 400**, `error.type = "kontext_fehlt"`. Es gibt keinen
Standard-Mandanten; ein Vertipper darf nicht dazu führen, dass Zuordnungen im falschen Topf
landen.

**Wirkung von `X-Pseudo-Projekt`:** innerhalb desselben Projekts bekommt dieselbe Person
denselben Platzhalter — über mehrere Aufrufe hinweg. Deshalb muss dort eine ID stehen, die über
das ganze Interview stabil bleibt.

**Wirkung von `X-Pseudo-Mandant`:** Freigabe- und Sperrlisten sind strikt pro Mandant getrennt.
Eine Freigabe bei Mandant A wirkt bei Mandant B **nie**.

---

## 3. Erfolgsfall

`HTTP 200`, Rumpf feldgleich zur Anbieterantwort. Der Text ist bereits **zurückersetzt** — die
Anwendung erhält Klartext und merkt im Normalfall nichts.

Zusätzlich gesetzt: `X-Pseudo-Status: aktiv` (oder `abgeschaltet`, siehe Abschnitt 8).

---

## 4. Blockierfall — HTTP 409

Ist eine Erkennung unsicher, geht **nichts** an den Anbieter. Antwort:

```jsonc
{
  "type": "error",
  "error": {
    "type": "pseudonymisierung_blockiert",
    "message": "3 Fundstelle(n) erfordern eine Entscheidung.",
    "pseudo": {
      "vorgang_id": "vg_01H…",
      "schema": "1.0",
      "befunde": [
        {
          "befund_id": "bf_01H…",
          "kategorie": "person_name",
          "auszug": "…mit Frau Bürgi besprochen, dass…",
          "treffer": "Bürgi",
          "ort": { "feld": "messages[0].content", "von": 412, "bis": 417 },
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

- `ort.feld` ist ein Feldpfad in **dem Rumpf, den die Anwendung gesendet hat**
  (`messages[2].content[0].text`). `von`/`bis` sind Zeichenoffsets in genau diesem Feld.
  Damit lässt sich die Stelle im Diktattext punktgenau markieren.
- `auszug` ist ein kurzer Kontextausschnitt zur Einordnung durch den Nutzer.

### Weitere Fehler

| Status | `error.type` | Bedeutung |
|---|---|---|
| 400 | `kontext_fehlt` | Kopfzeile fehlt oder Anwendung unbekannt |
| 409 | `pseudonymisierung_blockiert` | Entscheidung nötig |
| 501 | `streaming_nicht_unterstuetzt` | `"stream": true` — in dieser Fassung nicht unterstützt |
| 502 | `rueckersetzung_unvollstaendig` | Antwort wurde **nicht** ausgeliefert (Leckverdacht) |
| 503 | `kein_anbieterschluessel` | für diese Anwendung ist kein Schlüssel hinterlegt |

**502 ist kein Anwendungsfehler, sondern eine Schutzabschaltung.** Der Dienst liefert lieber
einen Fehler aus als einen Text, in dem ein Platzhalter falsch aufgelöst wurde. Nicht als
„Netzwerkfehler" behandeln und stillschweigend wiederholen.

---

## 5. Entscheid zu einer Fundstelle

```
POST /pseudo/v1/befunde/{befund_id}/entscheid
Content-Type: application/json

{ "entscheid": "freigeben",
  "muster": "Bürgi",
  "begruendung": "Systemname der Fachanwendung",
  "urheber": "u.muster" }
```

**Der Klartext (`muster`) wird mitgeschickt, nicht beim Dienst nachgeschlagen** — der speichert
ihn nicht. Er wird gegen einen HMAC geprüft; wer den Klartext nicht kennt, kann den Befund nicht
entscheiden. Passt er nicht: `400 muster_passt_nicht`.

| `entscheid` | Bedeutung für den Nutzer | Wirkung |
|---|---|---|
| `freigeben` | „Fehlalarm — das ist ein Firmen- oder Systemname" | wird künftig nicht mehr gemeldet |
| `ersetzen` | „echter Personenbezug" | gilt künftig als **sicher** und wird ersetzt |

Beide wirken **nur beim eigenen Mandanten** und sind widerrufbar. Antwort `200`:

```json
{ "befund_id": "bf_01H…", "entscheid": "freigeben", "wirkt_ab": "sofort",
  "geltungsbereich": "mandant",
  "hinweis": "Den unveraenderten Originalaufruf wiederholen." }
```

### Danach: Originalaufruf **unverändert** wiederholen

Der Dienst speichert den blockierten Text nicht — sonst legte er ausgerechnet von den heikelsten
Texten eine Halde an. **Die Anwendung muss den Rumpf halten und identisch erneut senden.**
Nichts kürzen, nichts bereinigen, nichts umschreiben.

---

## 6. Konkrete Befunde zu HERMES PIA

Stand des Zweigs `main` am 21.07.2026, von aussen gelesen. Vor der Umsetzung gegen den aktuellen
Stand prüfen.

### 6.1 Es gibt genau eine Aufrufstelle

`app/domains/llm/client.py` — `LLMClient.complete(system, messages, max_tokens=1024)` sendet
direkt an `https://api.anthropic.com/v1/messages` mit `x-api-key`. Erzeugt wird der Client
einmalig in `app/factory.py` (~Zeile 54) aus `ANTHROPIC_API_KEY`.

Das ist die günstigste denkbare Ausgangslage: **eine** Datei trägt die Umstellung.

### 6.2 ⚠️ Die Falle: alle vier Aufrufe verschlucken jede Ausnahme

In `app/domains/interview/extraction.py` rufen vier Funktionen `llm_client.complete(...)` auf —
Zeilen **33, 63, 95, 140** — und **jede** ist so gebaut:

```python
try:
    raw = llm_client.complete(...)
    ...
except Exception:
    return {"text": raw_text}      # bzw. [] / Vorgabewert
```

**Wird nur die Basis-URL umgestellt, ist die Anbindung wertlos:** ein 409 landet im generischen
`except`, die Funktion gibt den unverarbeiteten Text zurück, und der Nutzer erfährt **nie**, dass
sein Aufruf angehalten wurde. Er sieht ein schlechtes Ergebnis und hält es für ein
Qualitätsproblem des Modells. Die Begründungspflicht wäre damit ausgehebelt — die Fundstellen
existieren, kommen aber nirgends an.

**Vorgabe:** eine eigene Ausnahmeklasse einführen, die **vor** dem generischen `except` gefangen
und weitergereicht wird:

```python
class PseudonymisierungBlockiert(Exception):
    def __init__(self, befunde, vorgang_id): ...
```

```python
try:
    raw = llm_client.complete(...)
    ...
except PseudonymisierungBlockiert:
    raise                       # MUSS durchschlagen
except Exception:
    return {"text": raw_text}   # unverändert
```

Dasselbe gilt für `502 rueckersetzung_unvollstaendig`: ebenfalls durchreichen, nicht schlucken.

### 6.3 Mandant und Projekt

- Ein Organisationsmodell gibt es auf `main` nicht (`org_id` kommt im Interview-Bereich nicht
  vor). Bis es eines gibt: `X-Pseudo-Mandant` aus einer Konfiguration setzen
  (z.B. `PSEUDO_MANDANT`, Vorgabe `standard`). **Nicht** leer lassen — das ergibt 400.
  Sobald es Organisationen gibt, gehört dort die `org_id` hin.
- `X-Pseudo-Projekt`: `InterviewSession.id` ist der natürliche Wert — über das ganze Interview
  stabil, und ein Interview entspricht einem Vorhaben.
- `LLMClient` wird heute **einmal beim App-Start** erzeugt und kennt keinen Anfragekontext.
  Mandant und Projekt müssen deshalb **je Aufruf** übergeben werden, z.B. als zusätzliche
  Parameter von `complete(...)`. Sie im Konstruktor festzuhalten wäre falsch.

### 6.4 Der Schlüssel wird abgegeben

`ANTHROPIC_API_KEY` verschwindet aus HERMES PIA und wird im Dienst hinterlegt. Solange die
Anwendung einen eigenen Schlüssel besitzt, ist das Umgehen der Schicht nur verboten, nicht
unmöglich — und genau darauf kommt es bei Verwaltungskunden an.

Neu in der Konfiguration, z.B.:

```
PSEUDO_BASIS_URL=http://127.0.0.1:8040/anthropic
PSEUDO_ANWENDUNG=hermes-pia
PSEUDO_MANDANT=standard
```

`app/domains/llm/client.py` schickt weiterhin `anthropic-version: 2023-06-01` mit; der Dienst
reicht die Kopfzeile durch. Ein `x-api-key` wird **nicht** mehr gesetzt.

### 6.5 Der Embedding-Weg nicht vergessen

Auf `main` gibt es kein Korpus-Modul; auf anderen Zweigen schon (`app/domains/corpus/`,
Voyage-Embeddings). **Sobald dieser Zweig zusammengeführt wird, muss er ebenfalls über den
Dienst laufen** — `http://127.0.0.1:8040/voyage`. Der Weg trägt denselben Text ins Ausland wie
der Chat und wird regelmässig übersehen.

Beim Embedding-Weg gibt es **keine** Rückersetzung (zurück kommt ein Vektor). Der erzeugte
Vektor ist der Vektor des *pseudonymisierten* Texts — das gehört dokumentiert, sonst wundert sich
später jemand über die Trefferqualität.

---

## 7. Bedienoberfläche im Blockierfall

Der Dienst liefert nur Daten; die Anzeige gehört in die aufrufende Anwendung. Nötig ist:

1. Die Fundstellen im Diktattext markieren — `ort.von`/`ort.bis` im Feld `ort.feld`.
2. Je Fundstelle zwei Schaltflächen: **„echter Personenbezug"** (`ersetzen`) und
   **„Fehlalarm"** (`freigeben`), letzteres mit Begründungsfeld.
3. Nach allen Entscheiden: den **unveränderten** Originalaufruf wiederholen.
4. Bleibt ein Befund unentschieden, bleibt der Aufruf blockiert. Kein „trotzdem senden".

Formulierungshinweis für die Oberfläche: der Dienst leistet **Pseudonymisierung, nicht
Anonymisierung**. Über den fachlichen Kontext bleibt ein Vorhaben identifizierbar. Diese Zusage
darf in keiner Oberfläche stärker formuliert werden.

---

## 8. Abschaltung zu Testzwecken

`POST /pseudo/v1/ausnahme` mit `{"berechtigt": true, "begruendung": "...", "stunden": 2}`.
Nur in `develop` und `test`; in Produktion **serverseitig verweigert** (403). Der Aufruf läuft
auch dann durch den Dienst und wird protokolliert; die Antwort trägt
`X-Pseudo-Status: abgeschaltet`. Die Anwendung sollte das sichtbar anzeigen.

---

## 9. Abnahmekriterien

Prüfbar, ohne den Dienst zu kennen:

1. In HERMES PIA existiert kein `ANTHROPIC_API_KEY` mehr; die Anwendung erreicht
   `api.anthropic.com` nicht direkt.
2. Ein Diktat mit `Zustaendig ist Herr Bürgi.` läuft durch; im Vorgangsprotokoll des Dienstes
   steht `anzahl_ersetzungen ≥ 1`; das erzeugte Dokument enthält `Bürgi` im Klartext.
3. Ein Diktat mit `Wir sprachen mit Vogt.` führt zu einer **sichtbaren Rückfrage** an den
   Nutzer — nicht zu einem stillen Ersatzergebnis. *(Das ist der Test, der die Falle aus 6.2
   aufdeckt.)*
4. Nach `freigeben` liefert die Wiederholung desselben Aufrufs ein Ergebnis.
5. Fehlt `X-Pseudo-Mandant`, schlägt der Aufruf fehl und wird nicht etwa still durchgelassen.
6. Bei Statuscode 502 wird dem Nutzer ein Fehler angezeigt und **kein** Text übernommen.

---

## 10. Was auf Seite des Dienstes noch fehlt

Ehrlich benannt, damit die Gegenseite nicht darauf wartet:

- **Es gibt noch keine Prüfung der `Authorization`-Kopfzeile.** Der Dienst verlässt sich derzeit
  allein darauf, dass er nur über `127.0.0.1` erreichbar ist. Jeder lokale Prozess auf dem Host
  könnte ihn nutzen. Für den ersten Anschluss vertretbar, vor Produktion zu schliessen.
- **Kein Einrichtungswerkzeug**: Anwendung registrieren und Anbieterschlüssel hinterlegen geht
  bisher nur direkt in der Datenbank.
- **Kein Streaming** (HTTP 501). HERMES PIA braucht es nicht; der KI-Technology-Radar schon.
- **Keine Verwaltungsoberfläche** für Listen, Schlüssel und Blockierrate.
- **Stufe C (statistisches NER) ist nicht aktiv**, solange die Latenz auf dem Zielhost nicht
  gemessen ist. Namen ausserhalb der Lexika und ohne Anrede werden derzeit nicht erkannt.
