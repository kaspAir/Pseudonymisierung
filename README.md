# Pseudonymisierung

Vorschalt-Dienst für KI-Aufrufe: ersetzt Personendaten vor dem Versand an LLM- und
Embedding-Dienste im Ausland durch Platzhalter und setzt sie in der Antwort wieder ein.
Die aufrufende Anwendung erhält Klartext zurück.

Der Dienst spricht die API der Anbieter selbst — in der Anwendung wird nur die Basis-URL
geändert, kein Aufrufcode.

> **Pseudonymisierung, nicht Anonymisierung.** Über den fachlichen Kontext bleibt ein Vorhaben
> identifizierbar. Diese Zusage wird bewusst nirgends stärker formuliert.

**Stand:** Dienst gebaut und getestet, Erstinstallation auf dem Host läuft.

| Dokument | Inhalt |
|---|---|
| [`docs/API.md`](docs/API.md) | **API-Referenz** — Endpunkte, Felder, Fehlercodes |
| [`docs/ANBINDUNG.md`](docs/ANBINDUNG.md) | Anbindungsweg mit Begründungen und Abnahmekriterien |
| [`docs/KONZEPT.md`](docs/KONZEPT.md) | Entwurf, Anforderungen, Risiken |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Erstinstallation auf dem Host |
| [`docs/BETRIEB.md`](docs/BETRIEB.md) | Umgebungsvariablen, Start, Verwaltung |
| [`docs/KORPUS.md`](docs/KORPUS.md) | Bestand pseudonymisieren |
| [`lexikon/README.md`](lexikon/README.md) | Herkunft der Erkennungsdaten |

## Rahmen

- Python / Flask / SQLAlchemy / SQLite
- Gunicorn auf `127.0.0.1`, **keine Site, keine Subdomain, kein PHP-Proxy** —
  der Dienst ist aus dem Internet nicht erreichbar
- Ports 8040–8043 (develop / test / integration / main); `8030` ist auf dem Host bereits belegt
- Promotion sequenziell `develop → test → integration → main`, Version je Promotion +0.0.1
- Regressionstests beginnen mit `"""Beweist: ..."""`
