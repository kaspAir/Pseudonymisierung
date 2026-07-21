"""Leitet lexikon/wortliste.txt aus bereits pseudonymisierten Fachtexten ab.

GRUNDGEDANKE
------------
In den pseudonymisierten Volltexten wurden Personennamen durch Platzhalter der
Form [Person_099] ersetzt. Jedes verbliebene grossgeschriebene Wort ist damit
PER KONSTRUKTION kein Personenname - sondern Fachsprache. Genau das brauchen
wir als Gegensignal zu den BfS-Namenslisten.

DIE ABSICHERUNG: DOKUMENTHAEUFIGKEIT
------------------------------------
War die damalige Pseudonymisierung lueckenhaft, koennten einzelne echte Namen
stehengeblieben sein. Deshalb zaehlt nicht, wie OFT ein Wort vorkommt, sondern
in wie VIELEN Dokumenten. Ein uebersehener Personenname steht in einem, selten
zwei Dossiers. Fachsprache ("Kosten", "Recht", "Bau") steht in fast allen.
Die Schwelle ist damit der eigentliche Schutz - nicht eine Annahme ueber die
Qualitaet der damaligen Pseudonymisierung.

Aufgenommen werden ausserdem NUR Woerter, die ueberhaupt in den Namenslisten
stehen. Alles andere kann gar keinen Fehlalarm ausloesen und hat in der Liste
nichts verloren.

Das Ergebnis ist ein VORSCHLAG zur Durchsicht (Bereich 'betrieb', kuratiert,
im Diff pruefbar) - keine automatisch scharfgeschaltete Liste.

Aufruf:
    python scripts/leite_wortliste_ab.py <verzeichnis> [--schwelle 20] [--schreiben]
"""
import argparse
import collections
import os
import re
import sys

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEXIKON = os.path.join(WURZEL, "lexikon")

_RE_WORT = re.compile(r"\b[A-ZÄÖÜ][\wäöüéèàáâêîôûëïüç-]{1,}\b")
_RE_MARKER = re.compile(r"\[(?:Person|Org)_\d+\]")


def lies(pfad):
    for kodierung in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(pfad, encoding=kodierung) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return None


def lade_liste(name):
    pfad = os.path.join(LEXIKON, name)
    werte = set()
    if not os.path.exists(pfad):
        return werte
    with open(pfad, encoding="utf-8") as f:
        for z in f:
            z = z.strip()
            if z and not z.startswith("#"):
                werte.add(z.casefold())
    return werte


def main():
    p = argparse.ArgumentParser()
    p.add_argument("verzeichnis")
    p.add_argument("--schwelle", type=int, default=20,
                   help="Mindestzahl Dokumente, in denen ein Wort vorkommen muss")
    p.add_argument("--schreiben", action="store_true")
    args = p.parse_args()

    dateien = sorted(
        os.path.join(args.verzeichnis, n)
        for n in os.listdir(args.verzeichnis)
        if n.lower().endswith(".txt")
    )

    dok_haeufigkeit = collections.Counter()
    gelesen = 0
    ohne_marker = []
    for pfad in dateien:
        text = lies(pfad)
        if not text or not text.strip():
            continue
        gelesen += 1
        if not _RE_MARKER.search(text):
            ohne_marker.append(os.path.basename(pfad))
        # Platzhalter entfernen, damit "Person"/"Org" nicht als Wort zaehlen.
        text = _RE_MARKER.sub(" ", text)
        for wort in set(_RE_WORT.findall(text)):
            dok_haeufigkeit[wort] += 1

    nachnamen = lade_liste("nachnamen.txt")
    vornamen = lade_liste("vornamen.txt")
    orte = lade_liste("ortschaften.txt")
    namen = nachnamen | vornamen

    print("Dokumente gelesen: %d von %d" % (gelesen, len(dateien)))
    if ohne_marker:
        # Ehrlich melden: ohne Platzhalter ist unklar, ob das Dokument
        # ueberhaupt pseudonymisiert wurde.
        print("WARNUNG: %d Dokument(e) ohne Platzhalter - Herkunft unklar:"
              % len(ohne_marker))
        for n in ohne_marker[:5]:
            print("   ", n)
    print("Verschiedene grossgeschriebene Woerter: %d" % len(dok_haeufigkeit))

    # Nur Woerter, die ueberhaupt einen Fehlalarm ausloesen koennten.
    kandidaten = {w: n for w, n in dok_haeufigkeit.items()
                  if w.casefold() in namen and w.casefold() not in orte}
    print("Davon in den Namenslisten (= moegliche Fehlalarme): %d" % len(kandidaten))
    print()

    print("%-10s %-10s %s" % ("Schwelle", "Woerter", "Beispiele (haeufigste)"))
    for schwelle in (2, 5, 10, 20, 40, 80):
        treffer = sorted(((n, w) for w, n in kandidaten.items() if n >= schwelle),
                         reverse=True)
        beispiele = ", ".join(w for _, w in treffer[:8])
        markierung = " <-" if schwelle == args.schwelle else ""
        print("%-10d %-10d %s%s" % (schwelle, len(treffer), beispiele, markierung))
    print()

    gewaehlt = sorted(w for w, n in kandidaten.items() if n >= args.schwelle)
    print("Gewaehlt bei Schwelle %d: %d Woerter" % (args.schwelle, len(gewaehlt)))
    print()
    print("Vollstaendige Vorschlagsliste zur Durchsicht:")
    for i in range(0, len(gewaehlt), 6):
        print("   " + "  ".join("%-18s" % w for w in gewaehlt[i:i + 6]))

    if not args.schreiben:
        print()
        print("(Nichts geschrieben. Mit --schreiben wird lexikon/wortliste.txt erzeugt.)")
        return 0

    pfad = os.path.join(LEXIKON, "wortliste.txt")
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Alltags- und Fachwortschatz, der zugleich als Name vorkommt.\n")
        f.write("# Abgeleitet aus bereits pseudonymisierten Fachtexten:\n")
        f.write("# jedes dort verbliebene grossgeschriebene Wort ist per\n")
        f.write("# Konstruktion kein Personenname.\n")
        f.write("# Schwelle: in mindestens %d von %d Dokumenten.\n"
                % (args.schwelle, gelesen))
        f.write("# Kuratiert - vor Aenderungen im Diff pruefen.\n#\n")
        for w in gewaehlt:
            f.write("%s\n" % w)
    print()
    print("Geschrieben: %s (%d Woerter)" % (pfad, len(gewaehlt)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
