# Erstinstallation auf dem Host

Für `develop` (Port 8030). Die übrigen Umgebungen unterscheiden sich nur in
`PSEUDO_UMGEBUNG` und damit im Port.

**Es wird keine Site angelegt, keine Subdomain, kein PHP-Proxy.** Der Dienst bindet auf
`127.0.0.1` und ist aus dem Internet nicht erreichbar — das ist der Grund, warum sich die
Konzentration von Schlüsseltresor und Zuordnungstabelle überhaupt rechtfertigen lässt.

---

## 1. Anmelden und Repo holen

```bash
ssh u7031y_kaspar@83.228.238.194

cd $HOME
git clone https://github.com/kaspAir/Pseudonymisierung.git
cd Pseudonymisierung
git checkout develop
```

## 2. Virtuelle Umgebung

Eigene Umgebung, getrennt von der bestehenden `$HOME/venv`:

```bash
python3 -V                                   # erwartet: Python 3.9.2
python3 -m venv $HOME/venv-pseudonymisierung
$HOME/venv-pseudonymisierung/bin/pip install --upgrade pip
$HOME/venv-pseudonymisierung/bin/pip install -r requirements.txt
```

Die Pins sind gegen Python 3.9 geprüft: `Flask 3.0.3` (`>=3.8`),
`cryptography 43.0.3` (`>=3.7`), `SQLAlchemy 2.0.36`, `gunicorn 22.0.0`.
`requirements-werkzeuge.txt` wird auf dem Host **nicht** gebraucht — das sind die Skripte für
die Bestandsaufbereitung.

## 3. Schlüsselmaterial erzeugen

```bash
$HOME/venv-pseudonymisierung/bin/python scripts/einrichten.py --tresor-erzeugen
```

Gibt eine Zeile aus. Diese kommt in die `.env`:

```bash
cat > $HOME/Pseudonymisierung/.env <<'ENDE'
PSEUDO_UMGEBUNG=develop
PSEUDO_TRESOR_SCHLUESSEL=<hier die erzeugte Zeile einsetzen>
ENDE
chmod 600 $HOME/Pseudonymisierung/.env
```

> **Geht dieser Wert verloren, sind alle gespeicherten Zuordnungen und Anbieterschlüssel
> unlesbar.** Es gibt bewusst keine Hintertür. Sichere ihn dort, wo du auch andere Zugangsdaten
> aufbewahrst — nicht im Repo.

Ohne diesen Wert startet der Dienst **nicht**. Ein stiller Rückfall auf Klartextspeicherung wäre
der schlimmste denkbare Ausgang, weil ihn niemand bemerkt.

## 4. Anwendung registrieren und Anbieterschlüssel hinterlegen

Der Schlüssel wird aus einer **Umgebungsvariablen** gelesen, nicht als Argument übergeben —
sonst stünde er in der Shell-Historie und in der Prozessliste.

```bash
cd $HOME/Pseudonymisierung
set -a; . ./.env; set +a

read -s -p "Anthropic-Key: " ANTHROPIC_API_KEY; export ANTHROPIC_API_KEY; echo

$HOME/venv-pseudonymisierung/bin/python scripts/einrichten.py \
    --anwendung hermes-pia --bezeichnung "HERMES PIA" \
    --anbieter anthropic --aus ANTHROPIC_API_KEY

unset ANTHROPIC_API_KEY
```

Prüfen (gibt niemals Schlüsselwerte aus):

```bash
$HOME/venv-pseudonymisierung/bin/python scripts/einrichten.py --zeigen
```

## 5. Starten

```bash
chmod +x deploy/start.sh deploy/stop.sh
./deploy/start.sh
```

Prüfen:

```bash
curl -s http://127.0.0.1:8030/pseudo/v1/health
```

Erwartete Antwort — die Lexikonzahlen sind der Beleg, dass die Erkennung wirklich geladen ist:

```json
{"status":"bereit","umgebung":"develop","version":"0.0.1",
 "lexikon":{"nachnamen":243402,"vornamen":66916,"wortliste":131,"ortschaften":4421},
 "wortliste_fehlt":false,"stufe_c_aktiv":false}
```

Stehen dort Nullen, fehlt das Verzeichnis `lexikon/` — dann ist die Erkennung praktisch blind.

## 6. Wachhund einrichten

Wie bei den übrigen Anwendungen, da es kein systemd gibt:

```bash
crontab -e
```

```
*/5 * * * * $HOME/Pseudonymisierung/deploy/start.sh >/dev/null 2>&1
```

Startet den Dienst nur, wenn er nicht läuft.

## 7. Rauchtest über den ganzen Weg

Erst wenn HERMES PIA angebunden ist (siehe `ANBINDUNG.md`), sonst von Hand:

```bash
# Muss 400 kontext_fehlt liefern - es gibt keinen Standard-Mandanten
curl -s -X POST http://127.0.0.1:8030/anthropic/v1/messages \
  -H 'content-type: application/json' \
  -d '{"model":"claude-sonnet-4-6","max_tokens":64,
       "messages":[{"role":"user","content":"Hallo"}]}'

# Muss 409 mit Befund zu "Vogt" liefern - hier geht NICHTS ins Ausland
curl -s -X POST http://127.0.0.1:8030/anthropic/v1/messages \
  -H 'content-type: application/json' \
  -H 'X-Pseudo-Anwendung: hermes-pia' \
  -H 'X-Pseudo-Mandant: standard' \
  -H 'X-Pseudo-Projekt: rauchtest' \
  -d '{"model":"claude-sonnet-4-6","max_tokens":64,
       "messages":[{"role":"user","content":"Wir sprachen mit Vogt."}]}'
```

Der zweite Aufruf ist der aussagekräftige: **er kostet nichts**, weil er den Anbieter gar nicht
erreicht, und beweist trotzdem, dass Erkennung, Blockieren und Befundformat laufen.

Ein Aufruf, der wirklich hinausgeht (und abgerechnet wird):

```bash
curl -s -X POST http://127.0.0.1:8030/anthropic/v1/messages \
  -H 'content-type: application/json' \
  -H 'X-Pseudo-Anwendung: hermes-pia' -H 'X-Pseudo-Mandant: standard' \
  -H 'X-Pseudo-Projekt: rauchtest' \
  -d '{"model":"claude-sonnet-4-6","max_tokens":64,
       "messages":[{"role":"user","content":"Fasse zusammen: Zustaendig ist Herr Buergi."}]}'
```

Hier muss in der Antwort **`Buergi` im Klartext** stehen — das belegt Ersetzung *und*
Rückersetzung über den ganzen Weg.

---

## Was danach noch offen ist

- **`Authorization` wird noch nicht geprüft.** Der Dienst verlässt sich allein darauf, dass er
  nur über `127.0.0.1` erreichbar ist. Jeder lokale Prozess auf dem Host könnte ihn nutzen.
  Für `develop` vertretbar; vor `main` zu schliessen.
- **Kein Jenkins-Job.** Die Erstinstallation ist von Hand; die Promotion
  `develop → test → integration → main` braucht noch einen Job wie bei den übrigen Produkten.
- **Sicherung:** `data/pseudonymisierung-develop.db` enthält die Zuordnungstabelle. Sie gehört
  in dieselbe Sicherung wie die übrigen Datenbanken — und der Tresor-Schlüssel **getrennt**
  davon, sonst hebt die Sicherung die Verschlüsselung auf.
