#!/bin/bash
# Erzeugt eine virtuelle Umgebung auch dort, wo "python3 -m venv" scheitert.
#
# Auf verwaltetem Debian-Hosting fehlt haeufig das Paket python3-venv. Dann
# bricht "python3 -m venv" ab mit:
#     "ensurepip is not available ... apt-get install python3-venv"
# Ohne Root laesst sich das Paket nicht nachinstallieren - aber die virtuelle
# Umgebung laesst sich trotzdem bauen: das venv-Modul selbst ist vorhanden,
# nur der pip-Bootstrap fehlt. Also ohne pip erzeugen und pip nachreichen.
#
#   bash deploy/venv_erzeugen.sh <zielverzeichnis>
set -u

ZIEL="${1:-}"
[ -n "$ZIEL" ] || { echo "Aufruf: venv_erzeugen.sh <zielverzeichnis>" >&2; exit 2; }

PY="${PYTHON:-python3}"

melde() { echo "[venv] $*"; }

if [ -x "$ZIEL/bin/pip" ]; then
    melde "vorhanden: $ZIEL"
    exit 0
fi

VERSION="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
melde "Python $VERSION"

# --- Weg 1: der uebliche -------------------------------------------------
if "$PY" -m venv "$ZIEL" 2>/dev/null && [ -x "$ZIEL/bin/pip" ]; then
    melde "mit 'python3 -m venv' erzeugt"
    "$ZIEL/bin/pip" install --upgrade pip -q 2>/dev/null || true
    exit 0
fi

melde "'python3 -m venv' liefert kein pip (vermutlich fehlt python3-venv)"
rm -rf "$ZIEL"

# --- Weg 2: ohne pip erzeugen, pip nachreichen ---------------------------
if "$PY" -m venv --without-pip "$ZIEL" 2>/dev/null && [ -x "$ZIEL/bin/python" ]; then
    melde "ohne pip erzeugt - hole pip nach"

    HOLER=""
    command -v curl > /dev/null 2>&1 && HOLER="curl -fsSL -o"
    [ -z "$HOLER" ] && command -v wget > /dev/null 2>&1 && HOLER="wget -qO"

    if [ -n "$HOLER" ]; then
        TMP="$(mktemp -d)"
        # Fuer aeltere Python-Versionen liegt get-pip.py unter einem
        # versionsbezogenen Pfad; der allgemeine Pfad verlangt inzwischen
        # neuere Versionen. Deshalb zuerst versionsbezogen versuchen.
        for URL in "https://bootstrap.pypa.io/pip/$VERSION/get-pip.py" \
                   "https://bootstrap.pypa.io/get-pip.py"; do
            melde "versuche $URL"
            if $HOLER "$TMP/get-pip.py" "$URL" 2>/dev/null \
               && "$ZIEL/bin/python" "$TMP/get-pip.py" -q 2>/dev/null \
               && [ -x "$ZIEL/bin/pip" ]; then
                melde "pip nachgereicht"
                rm -rf "$TMP"
                exit 0
            fi
        done
        rm -rf "$TMP"
    else
        melde "weder curl noch wget vorhanden"
    fi
    melde "pip liess sich nicht nachreichen"
    rm -rf "$ZIEL"
fi

# --- Weg 3: virtualenv, falls vorhanden ----------------------------------
if "$PY" -m virtualenv --version > /dev/null 2>&1; then
    melde "nutze virtualenv"
    if "$PY" -m virtualenv "$ZIEL" > /dev/null 2>&1 && [ -x "$ZIEL/bin/pip" ]; then
        melde "mit virtualenv erzeugt"
        exit 0
    fi
    rm -rf "$ZIEL"
fi

# --- Weg 4: pip des Systems kann virtualenv beschaffen -------------------
if "$PY" -m pip --version > /dev/null 2>&1; then
    melde "System-pip vorhanden - installiere virtualenv fuer den Benutzer"
    if "$PY" -m pip install --user -q virtualenv > /dev/null 2>&1 \
       && "$PY" -m virtualenv "$ZIEL" > /dev/null 2>&1 \
       && [ -x "$ZIEL/bin/pip" ]; then
        melde "mit virtualenv erzeugt"
        exit 0
    fi
    rm -rf "$ZIEL"
fi

cat >&2 <<'ENDE'
[venv] FEHLER: keine virtuelle Umgebung erzeugbar.

Bitte auf dem Host pruefen und die Ausgabe melden:
    python3 -V
    python3 -m venv --help          | head -3
    python3 -m pip --version
    python3 -m virtualenv --version
    ls -d $HOME/venv/bin/python     # wie wurde die bestehende Umgebung gebaut?
ENDE
exit 1
