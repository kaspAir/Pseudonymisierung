#!/bin/sh
# Haelt den Dienst an. Nach dem Anhalten scheitern die Aufrufe der Anwendungen -
# das ist gewollt: die Schicht ist blockierend, kein Beiwerk.
set -e

: "${PSEUDO_UMGEBUNG:=develop}"
PIDDATEI="$HOME/tmp/pseudonymisierung-$PSEUDO_UMGEBUNG.pid"

if [ ! -f "$PIDDATEI" ]; then
    echo "Keine PID-Datei fuer $PSEUDO_UMGEBUNG - laeuft vermutlich nicht."
    exit 0
fi

PID="$(cat "$PIDDATEI")"
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Angehalten: $PSEUDO_UMGEBUNG (PID $PID)"
else
    echo "PID $PID laeuft nicht mehr."
fi
rm -f "$PIDDATEI"
