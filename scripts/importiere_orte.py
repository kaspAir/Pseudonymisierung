"""Erzeugt lexikon/ortschaften.txt aus dem amtlichen Ortschaftenverzeichnis.

Quelle: Amtliches Ortschaftenverzeichnis mit Postleitzahl und Perimeter
(AMTOVZ, swisstopo/Post). Semikolon-getrennt, UTF-8 mit BOM.

Die Ortsnamen dienen NICHT als Ersetzungsgrund - eine Ortschaft ist fuer sich
kein Personendatum, und das Modell braucht den fachlichen Kontext (dieselbe
Ueberlegung wie bei Organisationen, KONZEPT 1.1).

Sie dienen als GEGENSIGNAL: 359 der 4421 Ortsnamen sind zugleich Nachnamen
(Basel, Baden, Arbon, Arosa, Bellinzona, Cham ...). Ohne diese Liste blockierte
jeder Satz, der eine Schweizer Gemeinde nennt.

Aufruf:
    python scripts/importiere_orte.py <AMTOVZ_CSV_LV95.csv>
"""
import csv
import os
import re
import sys

ZIEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lexikon")

SPALTEN = ("Ortschaftsname", "Gemeindename")


def lies(pfad):
    orte = set()
    with open(pfad, encoding="utf-8-sig", newline="") as f:
        for zeile in csv.DictReader(f, delimiter=";"):
            for spalte in SPALTEN:
                wert = (zeile.get(spalte) or "").strip()
                if not wert:
                    continue
                # "Lausanne 25" -> "Lausanne": die Zusatzziffer ist Postsache
                # und kommt in laufendem Text nicht vor.
                wert = re.sub(r"\s+\d+$", "", wert).strip()
                if len(wert) >= 2:
                    orte.add(wert)
    return orte


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    orte = lies(sys.argv[1])
    os.makedirs(ZIEL, exist_ok=True)
    pfad = os.path.join(ZIEL, "ortschaften.txt")
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Schweizer Ortschaften und Gemeinden\n")
        f.write("# Quelle: Amtliches Ortschaftenverzeichnis (AMTOVZ)\n")
        f.write("# Gegensignal, KEIN Ersetzungsgrund. %d Eintraege.\n#\n" % len(orte))
        for o in sorted(orte):
            f.write("%s\n" % o)

    print("Ortschaften: %d -> %s" % (len(orte), pfad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
