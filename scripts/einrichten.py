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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tresor-erzeugen", action="store_true",
                   help="Neues Schluesselmaterial ausgeben und beenden")
    p.add_argument("--zeigen", action="store_true", help="Stand anzeigen")
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
