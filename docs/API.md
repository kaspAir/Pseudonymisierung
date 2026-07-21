# API-Referenz

Version 0.0.1 · gegen den Code geprüft am 2026-07-21

Für den Anbindungsweg mit Begründungen und Abnahmekriterien siehe
[`ANBINDUNG.md`](ANBINDUNG.md). Dieses Dokument ist die reine Referenz.

---

## Basis

| | |
|---|---|
| Adresse | `http://127.0.0.1:<port>` — **nur lokal**, keine Site, kein TLS nötig |
| Ports | `8040` develop · `8041` test · `8042` integration · `8043` main |
| Inhaltstyp | `application/json` |
| Zeichensatz | UTF-8 |

Zwei Namensräume:

| Präfix | Zweck |
|---|---|
| `/<anbieter>/…` | **anbieterkompatibel.** Rumpf und Antwort sind feldgleich zur API des Anbieters |
| `/pseudo/v1/…` | **dienst-eigen.** Befund-Entscheide, Ausnahmen, Gesundheit |

---

## 1. Anbieter-Weiterleitung

### `POST /anthropic/v1/messages`
### `POST /voyage/v1/embeddings`

Die Anwendung setzt ihre Basis-URL auf `http://127.0.0.1:8040/anthropic` bzw. `…/voyage`;
das SDK hängt den Rest selbst an. **Am Rumpf ändert sich nichts.**

#### Kopfzeilen

| Kopfzeile | Pflicht | Beispiel | Bedeutung |
|---|---|---|---|
| `X-Pseudo-Anwendung` | ja | `hermes-pia` | im Dienst registrierte Anwendung |
| `X-Pseudo-Mandant` | ja | `42` | Mandant **innerhalb** der Anwendung |
| `X-Pseudo-Projekt` | ja | `session-137` | Konsistenzrahmen für Platzhalter |
| `content-type` | ja | `application/json` | |

Die Anwendung sendet **keinen** Anbieterschlüssel. Der Dienst hält ihn und setzt ihn selbst ein.

- `X-Pseudo-Projekt` steuert die Platzhalter-Konsistenz: dieselbe Person erhält innerhalb
  desselben Projekts über alle Aufrufe hinweg denselben Platzhalter. Der Wert muss über das
  ganze Interview stabil sein.
- `X-Pseudo-Mandant` trennt Freigabe- und Sperrlisten. Eine Freigabe bei Mandant A wirkt bei
  Mandant B **nie**.
- Fehlt eine der drei Kopfzeilen → `400 kontext_fehlt`. Es gibt **keinen** Standard-Mandanten.

#### Antwort 200

Feldgleich zur Anbieterantwort. Der Text ist bereits **zurückersetzt** — die Anwendung erhält
Klartext.

| Antwort-Kopfzeile | Werte |
|---|---|
| `X-Pseudo-Status` | `aktiv` · `abgeschaltet` |

`abgeschaltet` heisst: eine befristete Ausnahme ist aktiv, es wurde **nicht** pseudonymisiert.
Die Anwendung sollte das sichtbar anzeigen.

#### Beispiel

```bash
curl -s -X POST http://127.0.0.1:8040/anthropic/v1/messages \
  -H 'content-type: application/json' \
  -H 'X-Pseudo-Anwendung: hermes-pia' \
  -H 'X-Pseudo-Mandant: 42' \
  -H 'X-Pseudo-Projekt: session-137' \
  -d '{"model":"claude-sonnet-4-6","max_tokens":256,
       "messages":[{"role":"user","content":"Zustaendig ist Herr Buergi."}]}'
```

Hinausgegangen ist `Zustaendig ist {{P1}}.` — zurück kommt `Buergi` im Klartext.

#### Besonderheit Embeddings

Auf `/voyage/v1/embeddings` gibt es **keine Rückersetzung** — zurück kommt ein Vektor, kein Text.
Der Hinweg wird trotzdem vollständig bereinigt. Folge: der erzeugte Vektor ist der Vektor des
*pseudonymisierten* Texts.

---

## 2. `POST /pseudo/v1/befunde/{befund_id}/entscheid`

Entscheid zu einer beim Blockieren gemeldeten Fundstelle.

#### Rumpf

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `entscheid` | string | ja | `ersetzen` oder `freigeben` |
| `muster` | string | ja | der Klartext der Fundstelle (aus `befunde[].treffer`) |
| `begruendung` | string | nein | wird im Listeneintrag gespeichert |
| `urheber` | string | nein | wird im Listeneintrag und am Befund gespeichert |

**`muster` wird mitgeschickt, nicht beim Dienst nachgeschlagen** — der speichert den Klartext
nicht. Er wird gegen einen HMAC geprüft; wer den Klartext nicht kennt, kann den Befund nicht
entscheiden.

| `entscheid` | Bedeutung für den Nutzer | Listeneintrag | Wirkung beim nächsten Aufruf |
|---|---|---|---|
| `freigeben` | „Fehlalarm — Firmen- oder Systemname" | Freigabe, Bereich `mandant` | wird nicht mehr gemeldet |
| `ersetzen` | „echter Personenbezug" | **Sperre**, Bereich `mandant` | gilt als `sicher` und wird ersetzt |

Beide wirken ausschliesslich beim eigenen Mandanten und sind widerrufbar.

#### Antwort 200

```json
{
  "befund_id": "bf_00c89787f7d24c5dbe64cd",
  "entscheid": "freigeben",
  "wirkt_ab": "sofort",
  "geltungsbereich": "mandant",
  "hinweis": "Den unveraenderten Originalaufruf wiederholen."
}
```

#### Fehler

| Status | `error.type` | Ursache |
|---|---|---|
| 400 | `ungueltiger_entscheid` | `entscheid` ist weder `ersetzen` noch `freigeben` |
| 400 | `muster_fehlt` | `muster` fehlt oder ist leer |
| 400 | `muster_passt_nicht` | `muster` gehört nicht zu diesem Befund |
| 404 | `unbekannter_befund` | `befund_id` existiert nicht |
| 409 | `bereits_entschieden` | dieser Befund wurde schon entschieden |

#### Beispiel

```bash
curl -s -X POST http://127.0.0.1:8040/pseudo/v1/befunde/bf_00c89787f7d24c5dbe64cd/entscheid \
  -H 'content-type: application/json' \
  -d '{"entscheid":"freigeben","muster":"Vogt",
       "begruendung":"Systemname der Fachanwendung","urheber":"u.muster"}'
```

Danach den **unveränderten** Originalaufruf wiederholen.

---

## 3. `GET /pseudo/v1/health`

Ohne Kopfzeilen aufrufbar.

```json
{
  "status": "bereit",
  "umgebung": "develop",
  "version": "0.0.1",
  "lexikon": { "nachnamen": 243402, "vornamen": 66916,
               "wortliste": 131, "ortschaften": 4421 },
  "wortliste_fehlt": false,
  "stufe_c_aktiv": false
}
```

| Feld | Bedeutung |
|---|---|
| `lexikon.*` | Grösse der geladenen Erkennungslisten. **Nullen heissen: die Erkennung ist praktisch blind.** |
| `wortliste_fehlt` | `true` → der Dienst blockiert auf gewöhnlichem Verwaltungsdeutsch |
| `stufe_c_aktiv` | statistisches NER; derzeit immer `false` |

Die drei letzten Felder sind bewusst da: **eine Erkennungslücke soll sichtbar sein, nicht
verschwiegen.**

---

## 4. `POST /pseudo/v1/ausnahme`

Pseudonymisierung befristet abschalten. **Nur in `develop` und `test`** — in `integration` und
`main` serverseitig verweigert.

Verlangt zusätzlich die drei `X-Pseudo-*`-Kopfzeilen.

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `berechtigt` | boolean | ja | muss `true` sein |
| `begruendung` | string | ja | darf nicht leer sein |
| `stunden` | number | ja | Geltungsdauer; ohne Frist keine Ausnahme |
| `urheber` | string | nein | Vorgabe `unbekannt` |

Antwort 200:

```json
{ "ausnahme_id": 1, "umgebung": "develop",
  "gueltig_bis": "2026-07-21T20:00:00+00:00",
  "hinweis": "Aufrufe laufen weiterhin durch den Dienst und werden protokolliert." }
```

Fehler `403 ausnahme_verweigert` bei falscher Umgebung, fehlender Berechtigung, leerer
Begründung oder fehlender Frist.

Während einer aktiven Ausnahme tragen alle Antworten `X-Pseudo-Status: abgeschaltet`.

---

## 5. Fehlerformat

Alle Fehler verwenden den Anthropic-Fehlerumschlag:

```json
{ "type": "error", "error": { "type": "<kennung>", "message": "<Klartext>" } }
```

### Übersicht

| Status | `error.type` | Bedeutung | Reaktion der Anwendung |
|---|---|---|---|
| 400 | `kontext_fehlt` | Kopfzeile fehlt oder Anwendung unbekannt | Fehler in der Verdrahtung |
| 400 | `invalid_request_error` | kein JSON-Rumpf | Fehler in der Verdrahtung |
| **409** | **`pseudonymisierung_blockiert`** | **Entscheidung nötig** | **Fundstellen anzeigen** |
| 404 | `not_found` | unbekannter Anbieter oder Pfad | Basis-URL prüfen |
| 501 | `streaming_nicht_unterstuetzt` | `"stream": true` gesendet | ohne Streaming aufrufen |
| 502 | `rueckersetzung_unvollstaendig` | Antwort **nicht** ausgeliefert (Leckverdacht) | Fehler zeigen, **keinen** Text übernehmen |
| 4xx/5xx | `anbieter_fehler` | der Anbieter hat abgelehnt | wie bisher behandeln |
| 503 | `kein_anbieterschluessel` | kein Schlüssel hinterlegt | Betreiber informieren |

> **502 ist kein Netzwerkfehler.** Der Dienst liefert lieber einen Fehler als einen Text, in dem
> ein Platzhalter falsch aufgelöst wurde. Nicht stillschweigend wiederholen.

### 409 im Detail

```jsonc
{
  "type": "error",
  "error": {
    "type": "pseudonymisierung_blockiert",
    "message": "1 Fundstelle(n) erfordern eine Entscheidung.",
    "pseudo": {
      "vorgang_id": "vg_d4af579df0404ef4a6ff98",
      "schema": "1.0",
      "befunde": [
        {
          "befund_id": "bf_00c89787f7d24c5dbe64cd",
          "kategorie": "person_name",
          "auszug": "Wir sprachen mit Vogt.",
          "treffer": "Vogt",
          "ort": { "feld": "messages[0].content", "von": 17, "bis": 21 },
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

| Feld | Bedeutung |
|---|---|
| `vorgang_id` | Prüflauf; erscheint im Protokoll des Dienstes |
| `befund_id` | für den Entscheid-Aufruf |
| `kategorie` | siehe Tabelle unten |
| `auszug` | Kontextausschnitt zur Einordnung durch den Nutzer |
| `treffer` | der beanstandete Text — wird als `muster` zurückgeschickt |
| `ort.feld` | Feldpfad **im gesendeten Rumpf**, z.B. `messages[2].content[0].text` |
| `ort.von` / `ort.bis` | Zeichenoffsets **in genau diesem Feld** |
| `sicherheit` | 0…1 |
| `band` | im 409 immer `unsicher` — nur unsichere Fundstellen blockieren |
| `grund` | maschinenlesbare Kennungen, mit `; ` getrennt |

`ort` erlaubt es, die Stelle im Diktattext punktgenau zu markieren.

---

## 6. Kategorien

| Kategorie | Beispiel | Erkannt über |
|---|---|---|
| `person_name` | `Bürgi` | Anrede-Anker, Vorname + Nachname, Lexikon |
| `person_kontakt` | E-Mail, Telefon | Muster |
| `adresse` | `Musterstrasse 5, 3011 Bern` | Muster + amtliches Ortschaftenverzeichnis |
| `ahv` | AHV-Nummer | Muster **mit Prüfziffer** |
| `finanzkonto` | IBAN | Muster **mit Mod-97-Prüfung** |
| `geschaeftsnummer` | `GS-2026/017` | **pro Mandant konfigurierbar** |
| `verfahrensnummer` | | **pro Mandant konfigurierbar** |
| `datum_geburt`, `benutzerkonto` | | vorgesehen |
| `bereits_pseudonymisiert` | `[Person_099]` | erkannt, **nicht ersetzt**, nicht gemeldet |

**Organisationen und Ortschaften haben bewusst keine Kategorie.** Das Modell braucht den
fachlichen Kontext; ein Ortsname ist für sich kein Personendatum. Ortsnamen dienen als
*Gegensignal* — 359 von 4'421 sind zugleich Nachnamen.

### Bänder

| Band | Verhalten |
|---|---|
| `sicher` | ersetzen, Aufruf läuft durch |
| `unsicher` | **blockieren** (409) |
| `unauffaellig` | durchlassen |

Ein einziger unsicherer Befund hält den gesamten Aufruf an — auch einen Embedding-Aufruf.

---

## 7. Platzhalter

Form `{{P1}}`, `{{P2}}`, … — fortlaufend je Projekt.

Bei der Rückersetzung toleriert der Dienst, was ein Modell mit Markern anstellt: eingeschobene
Leerzeichen und Zeilenumbrüche (`{{P\n1}}`), Kleinschreibung (`{{p1}}`), Markdown ringsum
(`**{{P1}}**`). Deutsche Beugung bleibt erhalten: aus `des {{P1}}s` wird `des Bürgis`.

Bestandsplatzhalter der Form `[Person_099]` und `[Org_148]` werden **unangetastet
durchgereicht**.

Findet der Dienst in der Antwort einen Platzhalter, den er nie vergeben hat, liefert er
`502` statt eines möglicherweise falsch aufgelösten Textes.

---

## 8. Mindestumsetzung in der aufrufenden Anwendung

1. Basis-URL auf `http://127.0.0.1:8040/<anbieter>` umstellen.
2. Eigenen Anbieterschlüssel entfernen.
3. Die drei `X-Pseudo-*`-Kopfzeilen je Aufruf mitgeben.
4. **HTTP 409 gesondert behandeln** — nicht in einen allgemeinen `except`-Zweig fallen lassen.
5. Fundstellen anzeigen, Entscheide senden, Originalaufruf **unverändert** wiederholen.
6. Bei 502 einen Fehler zeigen und keinen Text übernehmen.

Punkt 4 ist der einzige, an dem Anbindungen erfahrungsgemäss scheitern: fängt ein
`except Exception` den 409 ab und liefert einen Ersatzwert, sieht der Nutzer nur ein schlechteres
Ergebnis und erfährt nie, dass sein Aufruf angehalten wurde.

---

## 9. Was der Dienst nicht leistet

- **Keine Anonymisierung.** Über den fachlichen Kontext bleibt ein Vorhaben identifizierbar.
  Diese Zusage darf in keiner Oberfläche stärker formuliert werden.
- **Kein Streaming** (`501`).
- **Keine Prüfung der `Authorization`-Kopfzeile** — der Dienst verlässt sich derzeit allein
  darauf, dass er nur über `127.0.0.1` erreichbar ist.
- **Kein statistisches NER.** Namen ausserhalb der Lexika und ohne Anrede werden nicht erkannt.
