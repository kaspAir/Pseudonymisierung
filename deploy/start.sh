#!/bin/sh
# Startet den Dienst, falls er nicht laeuft. Fuer den Cron-Wachhund gedacht:
#   */5 * * * * $HOME/Pseudonymisierung/deploy/start.sh >/dev/null 2>&1
#
# Der Dienst bindet auf 127.0.0.1 - keine Site, kein PHP-Proxy, keine Subdomain.
set -e

WURZEL="${PSEUDO_WURZEL:-$HOME/Pseudonymisierung}"
VENV="${PSEUDO_VENV:-$HOME/venv-pseudonymisierung}"

cd "$WURZEL"

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

: "${PSEUDO_UMGEBUNG:=develop}"
export PSEUDO_UMGEBUNG

case "$PSEUDO_UMGEBUNG" in
    develop)     PORT=8030 ;;
    test)        PORT=8031 ;;
    integration) PORT=8032 ;;
    main)        PORT=8033 ;;
    *) echo "Unbekannte PSEUDO_UMGEBUNG: $PSEUDO_UMGEBUNG" >&2; exit 1 ;;
esac

if [ -z "$PSEUDO_TRESOR_SCHLUESSEL" ]; then
    echo "PSEUDO_TRESOR_SCHLUESSEL fehlt - der Dienst startet bewusst nicht." >&2
    exit 1
fi

mkdir -p "$HOME/tmp" logs data
PIDDATEI="$HOME/tmp/pseudonymisierung-$PSEUDO_UMGEBUNG.pid"

if [ -f "$PIDDATEI" ] && kill -0 "$(cat "$PIDDATEI")" 2>/dev/null; then
    exit 0
fi

# --preload erst noetig, wenn Stufe C (statistisches NER) aktiv wird: dann wird
# das Modell vor dem Fork geladen und von den Workern per Copy-on-Write geteilt.
# Auf 4 Kernen ist das kein Feinschliff, sondern noetig.
nohup "$VENV/bin/gunicorn" run:app \
    --bind "127.0.0.1:$PORT" \
    --workers 2 \
    --timeout 120 \
    --access-logfile "logs/access-$PSEUDO_UMGEBUNG.log" \
    --error-logfile "logs/error-$PSEUDO_UMGEBUNG.log" \
    > /dev/null 2>&1 &

echo $! > "$PIDDATEI"
echo "Pseudonymisierung gestartet: $PSEUDO_UMGEBUNG auf 127.0.0.1:$PORT (PID $!)"
