# Erstinstallation auf dem Host

Für `develop` (Port 8030). Die übrigen Umgebungen unterscheiden sich nur in
`PSEUDO_UMGEBUNG` und damit im Port.

**Es wird keine Site angelegt, keine Subdomain, kein PHP-Proxy.** Der Dienst bindet auf
`127.0.0.1` und ist aus dem Internet nicht erreichbar — das ist der Grund, warum sich die
Konzentration von Schlüsseltresor und Zuordnungstabelle überhaupt rechtfertigen lässt.

---

## Verzeichnisse je Stufe

| Stufe | Zweig | Port | Repo | virtuelle Umgebung |
|---|---|---|---|---|
| develop | `develop` | 8030 | `~/pseudonymisierung-dev` | `~/venv-pseudonymisierung-dev` |
| test | `test` | 8031 | `~/pseudonymisierung-test` | `~/venv-pseudonymisierung-test` |
| integration | `integration` | 8032 | `~/pseudonymisierung-int` | `~/venv-pseudonymisierung-int` |
| main | `main` | 8033 | `~/pseudonymisierung-prod` | `~/venv-pseudonymisierung-prod` |

**Eine virtuelle Umgebung je Stufe** — bewusst anders als bei den übrigen Anwendungen, die sich
eine teilen. Sonst ändert ein Abhängigkeits-Wechsel auf `develop` still auch die Produktion.

Alles Weitere erledigt `deploy/pseudo_ctl.sh`; von Hand sind nur Schritt 1 und 2 nötig.

## 1. Repo holen und Schlüsselmaterial erzeugen

```bash
ssh u7031y_kaspar@83.228.238.194

cd $HOME
git clone https://github.com/kaspAir/Pseudonymisierung.git pseudonymisierung-dev
cd pseudonymisierung-dev && git checkout develop

python3 -V                                          # erwartet: Python 3.9.2
bash deploy/venv_erzeugen.sh $HOME/venv-pseudonymisierung-dev
$HOME/venv-pseudonymisierung-dev/bin/pip install -r requirements.txt

$HOME/venv-pseudonymisierung-dev/bin/python scripts/einrichten.py --tresor-erzeugen
```

> **Warum nicht einfach `python3 -m venv`?** Auf diesem Host fehlt das Paket `python3-venv`, und
> ohne Root lässt es sich nicht nachinstallieren. `python3 -m venv` bricht dann ab mit
> *„ensurepip is not available"* — und alles Weitere scheitert als Folgefehler an einem
> fehlenden `pip`. `deploy/venv_erzeugen.sh` erzeugt die Umgebung stattdessen **ohne** pip und
> reicht pip anschliessend nach; es probiert mehrere Wege durch und meldet klar, wenn keiner
> greift.

Die Pins sind gegen Python 3.9 geprüft: `Flask 3.0.3` (`>=3.8`),
`cryptography 43.0.3` (`>=3.7`), `SQLAlchemy 2.0.36`, `gunicorn 22.0.0`.
`requirements-werkzeuge.txt` wird auf dem Host **nicht** gebraucht — das sind die Skripte für
die Bestandsaufbereitung.

## 2. `.env` anlegen

```bash
cat > $HOME/pseudonymisierung-dev/.env <<'ENDE'
PSEUDO_UMGEBUNG=develop
PSEUDO_TRESOR_SCHLUESSEL=<hier die erzeugte Zeile einsetzen>
ENDE
chmod 600 $HOME/pseudonymisierung-dev/.env
```

Die `.env` liegt **ausserhalb** von git (`.gitignore`) und überlebt jedes `git reset --hard`
des Deploys.

> **Geht dieser Wert verloren, sind alle gespeicherten Zuordnungen und Anbieterschlüssel
> unlesbar.** Es gibt bewusst keine Hintertür. Sichere ihn dort, wo du auch andere Zugangsdaten
> aufbewahrst — nicht im Repo.

Ohne diesen Wert startet der Dienst **nicht**. Ein stiller Rückfall auf Klartextspeicherung wäre
der schlimmste denkbare Ausgang, weil ihn niemand bemerkt.

## 3. Anwendung registrieren und Anbieterschlüssel hinterlegen

Der Schlüssel wird aus einer **Umgebungsvariablen** gelesen, nicht als Argument übergeben —
sonst stünde er in der Shell-Historie und in der Prozessliste.

```bash
cd $HOME/pseudonymisierung-dev
set -a; . ./.env; set +a

read -s -p "Anthropic-Key: " ANTHROPIC_API_KEY; export ANTHROPIC_API_KEY; echo

$HOME/venv-pseudonymisierung-dev/bin/python scripts/einrichten.py \
    --anwendung hermes-pia --bezeichnung "HERMES PIA" \
    --anbieter anthropic --aus ANTHROPIC_API_KEY

unset ANTHROPIC_API_KEY
```

Prüfen (gibt niemals Schlüsselwerte aus):

```bash
$HOME/venv-pseudonymisierung-dev/bin/python scripts/einrichten.py --zeigen
```

## 4. Starten

Ab hier übernimmt das Steuerskript — es ist zugleich das, was Jenkins aufruft:

```bash
bash deploy/pseudo_ctl.sh start develop
bash deploy/pseudo_ctl.sh health develop
```

Der Wachhund (Cron alle 2 Minuten) wird beim ersten Jenkins-Deploy automatisch eingerichtet.
Von Hand:

```bash
bash deploy/pseudo_ctl.sh deploy develop
```

Erwartete Antwort — die Lexikonzahlen sind der Beleg, dass die Erkennung wirklich geladen ist:

```json
{"status":"bereit","umgebung":"develop","version":"0.0.1",
 "lexikon":{"nachnamen":243402,"vornamen":66916,"wortliste":131,"ortschaften":4421},
 "wortliste_fehlt":false,"stufe_c_aktiv":false}
```

Stehen dort Nullen, fehlt das Verzeichnis `lexikon/` — dann ist die Erkennung praktisch blind.

## 5. Jenkins

Die vier Jobs (dev/test/int/prod) verwenden **dasselbe** `Jenkinsfile`; die Stufe wird aus dem
ausgecheckten Zweig abgeleitet, nicht aus dem Jobnamen. Je Job nur der Branch Specifier:
`*/develop`, `*/test`, `*/integration`, `*/main`.

Nötig sind nur das SSH-Credential `hermespia-deploy` und Docker auf dem Agenten — beides ist für
die übrigen Produkte bereits eingerichtet.

Getestet wird im Container `python:3.9-slim`, also auf der **Python-Version des Zielhosts**.
Das ist bewusst anders als bei HERMES PIA (dort `3.12-slim`): eine Unverträglichkeit mit 3.9
soll die Pipeline melden und nicht erst der Deploy.

## 6. Rauchtest über den ganzen Weg

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
- **Promotion sequenziell**, wie bei den übrigen Produkten: `develop → test → integration → main`.
  Keine Stufe überspringen — auch nicht, wenn der Code identisch ist.
- **Sicherung:** `data/pseudonymisierung-develop.db` enthält die Zuordnungstabelle. Sie gehört
  in dieselbe Sicherung wie die übrigen Datenbanken — und der Tresor-Schlüssel **getrennt**
  davon, sonst hebt die Sicherung die Verschlüsselung auf.
