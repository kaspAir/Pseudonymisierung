# Betrieb

## Grundsatz: kein öffentlicher Zugang

Der Dienst bindet auf `127.0.0.1`. Es gibt **keine Site, keine Subdomain, keinen PHP-Proxy**.
Alle Aufrufer laufen auf demselben Infomaniak-Host. Damit liegen weder der Schlüsseltresor noch
die Zuordnungstabelle je an einer öffentlichen Adresse.

| Umgebung | Port |
|---|---|
| develop | 8030 |
| test | 8031 |
| integration | 8032 |
| main | 8033 |

## Umgebungsvariablen

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `PSEUDO_UMGEBUNG` | ja | `develop` \| `test` \| `integration` \| `main` |
| `PSEUDO_TRESOR_SCHLUESSEL` | ja | Fernet-Schlüssel für Verschlüsselung at rest |
| `PSEUDO_DB_URL` | nein | Vorgabe: `sqlite:///data/pseudonymisierung-<umgebung>.db` |
| `PSEUDO_NAMENSLEXIKON` | nein | Pfad zu einer Namensliste (eine Zeile je Name) |
| `PSEUDO_NER_MODELL` | nein | leer = Stufe C inaktiv |

**Ohne `PSEUDO_TRESOR_SCHLUESSEL` startet der Dienst nicht.** Ein stiller Rückfall auf
Klartextspeicherung wäre der schlimmste denkbare Ausgang, weil ihn niemand bemerkt.

Schlüssel erzeugen:

```bash
python -c "from app.tresor import Tresor; print(Tresor.neuer_schluessel())"
```

## Start

```bash
gunicorn run:app --bind 127.0.0.1:8030 --workers 2 --timeout 120 \
  --access-logfile logs/access.log --error-logfile logs/error.log
```

Sobald Stufe C (statistisches NER) aktiv wird, zusätzlich `--preload`: das Modell wird dann vor
dem Fork geladen und von den Workern über Copy-on-Write geteilt, statt je Worker einmal im
Speicher zu liegen. Auf dem Zielhost mit 4 Kernen ist das nicht Feinschliff, sondern nötig.

## Anschluss einer Anwendung

1. Anwendung registrieren (Tabelle `anwendung`, z.B. `hermes-pia`).
2. Anbieterschlüssel im Dienst hinterlegen (Tabelle `anbieterschluessel`, verschlüsselt).
3. In der Anwendung den eigenen `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` **entfernen** und die
   Basis-URL umstellen:

   ```
   ANTHROPIC_BASE_URL = http://127.0.0.1:8030/anthropic
   VOYAGE_BASE_URL    = http://127.0.0.1:8030/voyage
   ```

4. Kopfzeilen bei jedem Aufruf mitgeben: `X-Pseudo-Anwendung`, `X-Pseudo-Mandant`,
   `X-Pseudo-Projekt`.
5. HTTP **409** auswerten und die Fundstellen dem Nutzer anzeigen (siehe KONZEPT 3.4/3.5).

Schritt 3 ist der eigentliche Punkt: solange die Anwendung noch einen eigenen Schlüssel hat,
ist das Umgehen der Schicht nur verboten, nicht unmöglich.

## Mandanten und Projekte

Die **Anwendung** muss registriert sein. **Mandant und Projekt entstehen automatisch.**

Das ist bewusst so: ein Tippfehler in der Mandanten-Kennung erzeugt einen leeren Mandanten ohne
Listen — und ein leerer Mandant blockiert, statt still etwas durchzulassen. Der Fehler ist damit
laut statt gefährlich.

## Verwaltung

Vorerst über einen SSH-Tunnel:

```bash
ssh -L 8030:127.0.0.1:8030 u7031y_kaspar@<host>
# danach im Browser: http://localhost:8030/pseudo/v1/health
```

## Was noch fehlt

- **Namenslexikon für Stufe B ist leer.** Es wird bewusst nicht mit erfundenen Namen
  ausgeliefert; ohne gepflegte Quelle erkennt Stufe B nur Namen *mit* Anrede-Anker.
  `/pseudo/v1/health` weist die Zahl der Einträge aus, damit die Lücke sichtbar bleibt.
- **Stufe C (statistisches NER)** ist nicht verdrahtet, solange die Latenz auf dem Zielhost
  nicht gemessen ist.
- **Streaming** wird mit HTTP 501 klar abgewiesen. Die Rückersetzung ist bereits als
  Stromautomat gebaut; der Weiterleitungsweg für SSE fehlt noch.
- **Verwaltungsoberfläche** (Listenpflege, Schlüssel, Blockierrate) — bisher nur über die
  Datenbank.
- **Jenkins-Job und Deploy-Skript.**
