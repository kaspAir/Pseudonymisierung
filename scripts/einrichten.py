"""Richtet den Dienst ein: Anwendung registrieren, Anbieterschluessel hinterlegen.

Ohne diesen Schritt laeuft kein einziger Aufruf - der Dienst antwortet mit
503 kein_anbieterschluessel.

DER ANBIETERSCHLUESSEL WIRD AUS DER UMGEBUNG GELESEN, nicht als Argument
uebergeben. Ein Schluessel auf der Befehlszeile landet in der Shell-Historie
und ist in der Prozessliste sichtbar.

Beispiele
---------
Neues Tresor-Schluesselmaterial erzeugen (einmalig, in die .env eintragen):

    python scripts/einrichten.py --tresor-erzeugen

Anwendung registrieren und Anthropic-Schluessel hinterlegen. Der Schluessel
wird verdeckt abgefragt - EIN Befehl, gefahrlos einzufuegen:

    python scripts/einrichten.py --anwendung hermes-pia \\
        --bezeichnung "HERMES PIA" --anbieter anthropic

Unbeaufsichtigt (z.B. aus einem Skript) geht es weiterhin ueber die Umgebung:

    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/einrichten.py --anwendung hermes-pia \\
        --anbieter anthropic --aus ANTHROPIC_API_KEY

Stand anzeigen (gibt niemals Schluesselwerte aus):

    python scripts/einrichten.py --zeigen
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config                                   # noqa: E402
from app.db import richte_ein                                    # noqa: E402
from app.models import Anbieterschluessel, Anwendung, Mandant    # noqa: E402
from app.tresor import Tresor, TresorFehlt                       # noqa: E402


def _fingerabdruck(wert):
    """Wiedererkennbar, ohne den Schluessel preiszugeben."""
    # Reines ASCII: Auslassungspunkte als Sonderzeichen kommen in manchen
    # Konsolen zerstueckelt an und verunsichern beim Vergleichen.
    sichtbar = 8 if len(wert) > 16 else 2
    return "%s...%s (Laenge %d)" % (wert[:sichtbar], wert[-4:], len(wert))


def pruefe_schluessel(sitzung, tresor, anwendung_schluessel, anbieter):
    """Prueft den hinterlegten Schluessel gegen den Anbieter.

    Gibt den Schluessel NIE aus - nur einen Fingerabdruck, an dem sich
    erkennen laesst, ob der richtige hinterlegt ist. Der Live-Aufruf verwendet
    max_tokens=1; er kostet praktisch nichts und beantwortet die Frage
    eindeutig, statt sie zu vermuten.
    """
    import requests

    q = sitzung.query(Anbieterschluessel).filter(
        Anbieterschluessel.widerrufen_am.is_(None))
    if anwendung_schluessel:
        anwendung = sitzung.query(Anwendung).filter(
            Anwendung.schluessel == anwendung_schluessel).one_or_none()
        if anwendung is None:
            print("Unbekannte Anwendung: %s" % anwendung_schluessel)
            return 1
        q = q.filter(Anbieterschluessel.anwendung_id == anwendung.id)
    if anbieter:
        q = q.filter(Anbieterschluessel.anbieter == anbieter)

    eintraege = q.all()
    if not eintraege:
        print("Kein hinterlegter Schluessel gefunden.")
        return 1

    fehler = 0
    for k in eintraege:
        try:
            wert = tresor.entschluessle(k.chiffre)
        except Exception as f:                      # noqa: BLE001
            print("%-10s ENTSCHLUESSELUNG FEHLGESCHLAGEN (%s)"
                  % (k.anbieter, type(f).__name__))
            print("           -> passt PSEUDO_TRESOR_SCHLUESSEL noch zur Datenbank?")
            fehler = 1
            continue

        print("%-10s %s" % (k.anbieter, _fingerabdruck(wert)))
        if wert != wert.strip():
            print("           WARNUNG: fuehrende/abschliessende Leerzeichen")

        if k.anbieter == "anthropic":
            if not wert.startswith("sk-ant-"):
                print("           WARNUNG: beginnt nicht mit 'sk-ant-'")
            antwort = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": wert, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=30,
            )
        elif k.anbieter == "voyage":
            antwort = requests.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": "Bearer %s" % wert,
                         "content-type": "application/json"},
                json={"model": "voyage-3", "input": ["hi"]},
                timeout=30,
            )
        else:
            print("           (kein Live-Test fuer diesen Anbieter)")
            continue

        if antwort.status_code == 200:
            print("           Live-Test: OK (HTTP 200)")
        else:
            meldung = ""
            try:
                meldung = antwort.json().get("error", {}).get("message", "")
            except ValueError:
                meldung = antwort.text[:120]
            print("           Live-Test: HTTP %d - %s" % (antwort.status_code, meldung))
            if antwort.status_code == 401:
                print("           -> Der hinterlegte Schluessel ist ungueltig.")
                print("           -> Neu hinterlegen: einrichten.py --anwendung %s "
                      "--anbieter %s" % (anwendung_schluessel or "<name>", k.anbieter))
            fehler = 1

    return fehler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tresor-erzeugen", action="store_true",
                   help="Neues Schluesselmaterial ausgeben und beenden")
    p.add_argument("--zeigen", action="store_true", help="Stand anzeigen")
    p.add_argument("--pruefen", action="store_true",
                   help="Hinterlegten Schluessel gegen den Anbieter pruefen")
    p.add_argument("--anwendung", help="Schluessel der Anwendung, z.B. hermes-pia")
    p.add_argument("--bezeichnung", default=None)
    p.add_argument("--anbieter", choices=("anthropic", "voyage"))
    p.add_argument("--aus", metavar="UMGEBUNGSVARIABLE",
                   help="Name der Variable mit dem Anbieterschluessel. "
                        "Fehlt die Angabe, wird der Schluessel verdeckt abgefragt.")
    p.add_argument("--mandant", default=None,
                   help="Schluessel nur fuer diesen Mandanten (sonst Vorgabe fuer alle)")
    args = p.parse_args()

    if args.tresor_erzeugen:
        print(Tresor.neuer_schluessel())
        print("# In die .env eintragen als PSEUDO_TRESOR_SCHLUESSEL=...",
              file=sys.stderr)
        print("# Geht dieser Wert verloren, sind alle gespeicherten Zuordnungen "
              "und Anbieterschluessel unlesbar.", file=sys.stderr)
        return 0

    config = Config()
    try:
        tresor = Tresor(config.tresor_schluessel)
    except TresorFehlt as f:
        print("FEHLER: %s" % f)
        print("Zuerst: python scripts/einrichten.py --tresor-erzeugen")
        return 1

    _, fabrik = richte_ein(config.datenbank_url)
    s = fabrik()

    if args.zeigen:
        print("Umgebung:  %s (Port %d)" % (config.umgebung, config.port))
        print("Datenbank: %s" % config.datenbank_url)
        print()
        anwendungen = s.query(Anwendung).all()
        if not anwendungen:
            print("Keine Anwendung registriert.")
        for a in anwendungen:
            mandanten = s.query(Mandant).filter(Mandant.anwendung_id == a.id).count()
            print("%-16s %-24s aktiv=%s  Mandanten=%d"
                  % (a.schluessel, a.bezeichnung, a.aktiv, mandanten))
            schluessel = s.query(Anbieterschluessel).filter(
                Anbieterschluessel.anwendung_id == a.id,
                Anbieterschluessel.widerrufen_am.is_(None),
            ).all()
            for k in schluessel:
                # Niemals den Wert ausgeben - nur, DASS einer da ist.
                print("    Anbieter %-12s hinterlegt%s"
                      % (k.anbieter,
                         "" if k.mandant_id is None else " (nur ein Mandant)"))
            if not schluessel:
                print("    KEIN Anbieterschluessel - Aufrufe scheitern mit 503.")
        s.close()
        return 0

    if args.pruefen:
        ergebnis = pruefe_schluessel(s, tresor, args.anwendung, args.anbieter)
        s.close()
        return ergebnis

    if not args.anwendung:
        print("--anwendung ist noetig (oder --zeigen / --tresor-erzeugen).")
        s.close()
        return 1

    anwendung = s.query(Anwendung).filter(
        Anwendung.schluessel == args.anwendung).one_or_none()
    if anwendung is None:
        anwendung = Anwendung(schluessel=args.anwendung,
                              bezeichnung=args.bezeichnung or args.anwendung)
        s.add(anwendung)
        s.flush()
        print("Anwendung angelegt: %s" % anwendung.schluessel)
    else:
        print("Anwendung vorhanden: %s" % anwendung.schluessel)

    if args.anbieter:
        if args.aus:
            wert = os.environ.get(args.aus, "").strip()
            quelle = "Umgebungsvariable %s" % args.aus
        else:
            # Verdeckte Abfrage im Skript statt "read -s" in der Shell: beim
            # Einfuegen eines mehrzeiligen Blocks wuerde ein Shell-read die
            # NACHFOLGENDEN Zeilen als Eingabe verschlucken.
            #
            # Terminal und Nicht-Terminal werden AUSDRUECKLICH unterschieden.
            # Sich allein auf getpass zu verlassen, waere unzuverlaessig: es
            # greift je nach Betriebssystem an stdin vorbei direkt auf die
            # Konsole zu und verhaelt sich ohne Terminal nicht einheitlich.
            try:
                if sys.stdin.isatty():
                    import getpass
                    wert = getpass.getpass(
                        "Schluessel fuer %s (Eingabe bleibt unsichtbar): "
                        % args.anbieter).strip()
                    quelle = "Eingabe"
                else:
                    zeile = sys.stdin.readline()
                    if not zeile:
                        raise EOFError
                    wert = zeile.strip()
                    quelle = "stdin"
            except (EOFError, KeyboardInterrupt):
                print("Abgebrochen: kein Schluessel eingegeben.")
                s.rollback()
                s.close()
                return 1

        if not wert:
            print("FEHLER: kein Schluessel erhalten (%s war leer)." % quelle)
            s.rollback()
            s.close()
            return 1

        mandant_id = None
        if args.mandant:
            m = s.query(Mandant).filter(
                Mandant.anwendung_id == anwendung.id,
                Mandant.externe_id == args.mandant).one_or_none()
            if m is None:
                m = Mandant(anwendung_id=anwendung.id, externe_id=args.mandant)
                s.add(m)
                s.flush()
            mandant_id = m.id

        # Alten Schluessel widerrufen statt loeschen - nachvollziehbar.
        alt = s.query(Anbieterschluessel).filter(
            Anbieterschluessel.anwendung_id == anwendung.id,
            Anbieterschluessel.anbieter == args.anbieter,
            Anbieterschluessel.mandant_id.is_(mandant_id) if mandant_id is None
            else Anbieterschluessel.mandant_id == mandant_id,
            Anbieterschluessel.widerrufen_am.is_(None),
        ).all()
        import datetime as _dt
        for k in alt:
            k.widerrufen_am = _dt.datetime.now(_dt.timezone.utc)
        if alt:
            print("Bisherigen Schluessel fuer %s widerrufen." % args.anbieter)

        s.add(Anbieterschluessel(
            anwendung_id=anwendung.id,
            mandant_id=mandant_id,
            anbieter=args.anbieter,
            chiffre=tresor.verschluessle(wert),
        ))
        print("Schluessel fuer %s hinterlegt (verschluesselt)." % args.anbieter)

    s.commit()
    s.close()
    print()
    print("Fertig. Stand pruefen: python scripts/einrichten.py --zeigen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
