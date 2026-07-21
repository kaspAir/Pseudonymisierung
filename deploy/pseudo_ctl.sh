#!/bin/bash
# Steuerskript des Dienstes - EINE Quelle der Wahrheit fuer Deploy, Start,
# Stopp, Wachhund und Gesundheitspruefung.
#
#   pseudo_ctl.sh deploy   <umgebung>   # git reset, pip, Neustart, Pruefung
#   pseudo_ctl.sh start    <umgebung>
#   pseudo_ctl.sh stop     <umgebung>
#   pseudo_ctl.sh health   <umgebung>
#   pseudo_ctl.sh watchdog <umgebung>   # per Cron
#
# Vom Jenkins-Deploy ueber stdin gepipet:
#   ssh -T host bash -s deploy develop < deploy/pseudo_ctl.sh
#
# DREI FALLEN, DIE HIER BEWUSST VERMIEDEN WERDEN
# (teuer erkauft im Schwesterprojekt - nicht "vereinfachen"):
#
# 1. KEIN `pkill -f "gunicorn.*:<port>"`. Das Fernskript laeuft selbst als
#    `bash -s` mit genau diesem Text in der Kommandozeile - `-f` traefe die
#    eigene Deploy-Sitzung und riesse die SSH-Verbindung ab (exit 255).
#
# 2. NIE eine PID aus einer Datei blind killen. Bei PID-Wiederverwendung
#    kann die Nummer inzwischen einem fremden Prozess gehoeren, im
#    schlimmsten Fall der eigenen SSH-Sitzung. Deshalb wird vor jedem Kill
#    /proc/<pid>/cmdline auf "gunicorn" geprueft.
#
# 3. KEIN flock-FD ueber den nohup-Start hinweg. Ein so gestarteter Daemon
#    ERBT das gesperrte Dateideskriptor und haelt es dauerhaft - der naechste
#    Deploy wartet dann vergeblich. Koordination laeuft ueber eine
#    Marker-Datei, und Gunicorn wird zusaetzlich mit geschlossenen
#    Lock-Deskriptoren gestartet.
set -u

BEFEHL="${1:-}"
UMGEBUNG="${2:-}"

case "$UMGEBUNG" in
    develop)     PORT=8030; KURZ=dev  ; ZWEIG=develop     ;;
    test)        PORT=8031; KURZ=test ; ZWEIG=test        ;;
    integration) PORT=8032; KURZ=int  ; ZWEIG=integration ;;
    main)        PORT=8033; KURZ=prod ; ZWEIG=main        ;;
    *) echo "Umgebung fehlt oder unbekannt: '${UMGEBUNG}'" >&2
       echo "Erlaubt: develop test integration main" >&2; exit 2 ;;
esac

# Der Port laesst sich ueberschreiben, ohne Code zu aendern - noetig, wenn der
# vorgesehene Block auf dem Host belegt ist. Muss zur .env passen, die der
# Dienst selbst liest.
PORT="${PSEUDO_PORT:-$PORT}"

REPO="${3:-$HOME/pseudonymisierung-$KURZ}"
# Eigene virtuelle Umgebung JE STUFE: sonst aendert ein Abhaengigkeits-
# Wechsel auf develop still auch die Produktion.
VENV="${4:-$HOME/venv-pseudonymisierung-$KURZ}"

PIDDATEI="$HOME/tmp/pseudonymisierung-$KURZ.pid"
MARKER="$HOME/tmp/pseudo-deploying-$KURZ"
GESUNDHEIT="http://127.0.0.1:$PORT/pseudo/v1/health"
HERKUNFT="https://github.com/kaspAir/Pseudonymisierung.git"

mkdir -p "$HOME/tmp" "$HOME/logs"

melde() { echo "[$(date '+%F %T')] [$KURZ] $*"; }

# ---------------------------------------------------------------- Zustand

laeuft() {
    [ -f "$PIDDATEI" ] || return 1
    local pid; pid="$(cat "$PIDDATEI" 2>/dev/null)" || return 1
    [ -n "$pid" ] || return 1
    ist_gunicorn "$pid"
}

ist_gunicorn() {
    local pid="$1"
    [ -r "/proc/$pid/cmdline" ] || return 1
    grep -qa gunicorn "/proc/$pid/cmdline"
}

pruefe_gesundheit() {
    curl -sf --max-time 10 "$GESUNDHEIT" > /dev/null 2>&1
}

# ----------------------------------------------------------------- Stopp

halte_an() {
    if [ -f "$PIDDATEI" ]; then
        local pid; pid="$(cat "$PIDDATEI" 2>/dev/null || true)"
        if [ -n "${pid:-}" ] && ist_gunicorn "$pid"; then
            melde "halte Gunicorn an (PID $pid)"
            kill "$pid" 2>/dev/null || true
            local i=0
            while [ $i -lt 20 ]; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 1; i=$((i + 1))
            done
        elif [ -n "${pid:-}" ]; then
            melde "PID $pid ist kein Gunicorn - wird NICHT gekillt"
        fi
        rm -f "$PIDDATEI"
    fi
    # Zweites Netz: nur portbezogen, nie mit Kommandozeilen-Muster.
    if command -v fuser > /dev/null 2>&1; then
        fuser -k "$PORT/tcp" > /dev/null 2>&1 || true
        sleep 1
    fi
}

# ----------------------------------------------------------------- Start

port_belegt() {
    # Vorabpruefung, damit ein belegter Port SOFORT als solcher gemeldet wird.
    # Ohne sie bindet Gunicorn fuenfmal vergeblich und stirbt mit einer
    # Meldung, die nur im Fehlerprotokoll steht - der Aufrufer sieht dann bloss
    # "nicht gesund" und sucht an der falschen Stelle.
    "$VENV/bin/python" - "$PORT" <<'ENDE' 2>/dev/null
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(0)      # belegt
finally:
    s.close()
sys.exit(1)          # frei
ENDE
}

starte() {
    if laeuft; then
        melde "laeuft bereits (PID $(cat "$PIDDATEI"))"
        return 0
    fi

    [ -d "$REPO" ] || { melde "FEHLER: Repo fehlt: $REPO"; return 1; }
    cd "$REPO" || return 1

    if [ -x "$VENV/bin/python" ] && port_belegt; then
        melde "FEHLER: 127.0.0.1:$PORT ist bereits belegt - und zwar NICHT von uns."
        melde "Wer dort antwortet:"
        curl -sS -m 5 "http://127.0.0.1:$PORT/pseudo/v1/health" 2>&1 | head -c 200
        echo
        melde "Freien Port suchen und PSEUDO_PORT in der .env setzen:"
        melde "  bash deploy/pseudo_ctl.sh ports"
        return 1
    fi

    if [ -f .env ]; then
        set -a; . ./.env; set +a
    fi
    export PSEUDO_UMGEBUNG="$UMGEBUNG"

    if [ -z "${PSEUDO_TRESOR_SCHLUESSEL:-}" ]; then
        melde "FEHLER: PSEUDO_TRESOR_SCHLUESSEL fehlt - Start wird verweigert."
        melde "Ein stiller Rueckfall auf Klartextspeicherung waere schlimmer als ein Ausfall."
        return 1
    fi

    mkdir -p logs data

    # 8>&- 9>&- schliesst etwaige geerbte Lock-Deskriptoren: ein per nohup
    # gestarteter Daemon wuerde sie sonst dauerhaft halten (Falle 3).
    nohup "$VENV/bin/gunicorn" run:app \
        --bind "127.0.0.1:$PORT" \
        --workers 2 \
        --timeout 120 \
        --graceful-timeout 30 \
        --max-requests 800 --max-requests-jitter 200 \
        --access-logfile "logs/access-$KURZ.log" \
        --error-logfile "logs/error-$KURZ.log" \
        > /dev/null 2>&1 8>&- 9>&- &

    echo $! > "$PIDDATEI"
    melde "gestartet auf 127.0.0.1:$PORT (PID $!)"

    local i=0
    while [ $i -lt 15 ]; do
        sleep 1
        if pruefe_gesundheit; then
            melde "gesund"
            return 0
        fi
        i=$((i + 1))
    done
    melde "FEHLER: antwortet nicht auf $GESUNDHEIT"
    melde "letzte Zeilen aus logs/error-$KURZ.log:"
    tail -n 20 "$REPO/logs/error-$KURZ.log" 2>/dev/null || true
    return 1
}

# ---------------------------------------------------------------- Deploy

deploye() {
    touch "$MARKER"
    trap 'rm -f "$MARKER"' EXIT

    if [ ! -d "$REPO/.git" ]; then
        melde "erstmaliges Klonen nach $REPO"
        git clone "$HERKUNFT" "$REPO" || return 1
    fi
    cd "$REPO" || return 1

    git fetch origin --prune || return 1
    git reset --hard "origin/$ZWEIG" || return 1
    melde "Stand: $(git rev-parse --short HEAD) auf $ZWEIG"

    if [ ! -x "$VENV/bin/pip" ]; then
        melde "erzeuge virtuelle Umgebung: $VENV"
        # NICHT blank "python3 -m venv": auf diesem Host fehlt das Paket
        # python3-venv, dann entsteht eine Umgebung OHNE pip und alles
        # Weitere scheitert erst spaeter und unverstaendlich.
        bash "$REPO/deploy/venv_erzeugen.sh" "$VENV" || return 1
    fi
    "$VENV/bin/pip" install -r requirements.txt -q || return 1

    halte_an
    starte || return 1

    richte_wachhund_ein
    melde "Deploy abgeschlossen."
}

# --------------------------------------------------------------- Wachhund

richte_wachhund_ein() {
    mkdir -p "$HOME/bin/pseudo"
    cp "$REPO/deploy/pseudo_ctl.sh" "$HOME/bin/pseudo/pseudo_ctl.sh"
    chmod +x "$HOME/bin/pseudo/pseudo_ctl.sh"

    local zeile="*/2 * * * * bash \$HOME/bin/pseudo/pseudo_ctl.sh watchdog $UMGEBUNG >> \$HOME/logs/pseudo-watchdog.log 2>&1"
    local bestand; bestand="$(crontab -l 2>/dev/null || true)"
    if echo "$bestand" | grep -q "pseudo_ctl.sh watchdog $UMGEBUNG"; then
        return 0
    fi
    printf '%s\n%s\n' "$bestand" "$zeile" | grep -v '^$' | crontab -
    melde "Wachhund eingerichtet (alle 2 Minuten)."
}

wachhund() {
    # Waehrend eines Deploys nicht dazwischenfunken.
    if [ -f "$MARKER" ]; then
        local alter; alter=$(( $(date +%s) - $(stat -c %Y "$MARKER" 2>/dev/null || echo 0) ))
        if [ "$alter" -lt 900 ]; then
            return 0
        fi
        rm -f "$MARKER"      # aelter als 15 Minuten: abgestuerzter Deploy
    fi

    pruefe_gesundheit && return 0
    sleep 5
    pruefe_gesundheit && return 0          # Bestaetigungs-Versuch

    melde "antwortet nicht - starte neu"
    halte_an
    starte
}

# ------------------------------------------------------------------ Start

zeige_ports() {
    echo "Belegte Ports im Bereich 8000-8100 (auf 127.0.0.1):"
    if command -v ss > /dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk 'NR==1 || /127.0.0.1:80[0-9][0-9]/'
    elif command -v netstat > /dev/null 2>&1; then
        netstat -ltnp 2>/dev/null | awk 'NR<=2 || /127.0.0.1:80[0-9][0-9]/'
    else
        echo "(weder ss noch netstat vorhanden - pruefe per Bindungsversuch)"
    fi
    echo
    echo "Bindungsversuch je Port (frei = wir koennten ihn nehmen):"
    for p in $(seq 8030 8060); do
        if "$VENV/bin/python" - "$p" <<'ENDE' 2>/dev/null
import socket, sys
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(0)
finally:
    s.close()
sys.exit(1)
ENDE
        then
            printf '  %s BELEGT' "$p"
            curl -sS -m 2 "http://127.0.0.1:$p/" 2>/dev/null | head -c 60
            echo
        else
            printf '  %s frei\n' "$p"
        fi
    done
}

case "$BEFEHL" in
    deploy)   deploye ;;
    ports)    zeige_ports ;;
    start)    starte ;;
    stop)     halte_an; melde "angehalten" ;;
    health)   if pruefe_gesundheit; then curl -s "$GESUNDHEIT"; echo; else
                  melde "NICHT gesund"; exit 1; fi ;;
    watchdog) wachhund ;;
    *) echo "Befehl fehlt. Erlaubt: deploy start stop health watchdog" >&2; exit 2 ;;
esac
