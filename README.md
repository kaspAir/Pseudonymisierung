# Pseudonymisierung

Vorschalt-Dienst für KI-Aufrufe: ersetzt Personendaten vor dem Versand an LLM- und
Embedding-Dienste im Ausland durch Platzhalter und setzt sie in der Antwort wieder ein.
Die aufrufende Anwendung erhält Klartext zurück.

Der Dienst spricht die API der Anbieter selbst — in der Anwendung wird nur die Basis-URL
geändert, kein Aufrufcode.

> **Pseudonymisierung, nicht Anonymisierung.** Über den fachlichen Kontext bleibt ein Vorhaben
> identifizierbar. Diese Zusage wird bewusst nirgends stärker formuliert.

**Stand:** Entwurf freigegeben, Bau noch nicht begonnen.

- Konzept: [`docs/KONZEPT.md`](docs/KONZEPT.md)

## Rahmen

- Python / Flask / SQLAlchemy / SQLite
- Gunicorn hinter PHP-Proxy auf Infomaniak Managed Hosting (kein Docker in Produktion)
- Ports 8030–8033 (develop / test / integration / main)
- Promotion sequenziell `develop → test → integration → main`, Version je Promotion +0.0.1
- Regressionstests beginnen mit `"""Beweist: ..."""`
