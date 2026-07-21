"""Prueft einen Bestand bereits pseudonymisierter Texte auf Restbefunde.

Zweck: Ein geteilter RAG-Basiskorpus ist fuer ALLE Mandanten sichtbar. Bleibt
dort ein Personendatum stehen, kann es bei einem anderen Kunden im Retrieval
auftauchen. Dieses Skript wendet den Erkenner des Dienstes auf den Bestand an.

WICHTIG: Es gibt ausschliesslich ZAEHLER und KATEGORIEN aus, niemals die
gefundenen Werte. Ein Pruefbericht, der die Fundstellen ausschreibt, waere
selbst wieder eine Personendatensammlung.

Aufruf:
    python scripts/pruefe_korpus.py <verzeichnis> [--zeige 15]
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.kern import erkennung  # noqa: E402
from app.web import lade_lexika  # noqa: E402

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RE_MARKER = re.compile(r"\[(?:Person|Org)_\d+\]")

# Kategorien, bei denen ein Treffer praktisch nie ein Fehlalarm ist.
HART = {
    erkennung.K_PERSON_KONTAKT,
    erkennung.K_AHV,
    erkennung.K_FINANZKONTO,
    erkennung.K_ADRESSE,
}


def lies(pfad):
    for kodierung in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(pfad, encoding=kodierung) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("verzeichnis")
    p.add_argument("--zeige", type=int, default=15)
    args = p.parse_args()

    lexika = lade_lexika(os.path.join(WURZEL, "lexikon"))
    erkenner = erkennung.Erkenner(
        nachnamen=lexika["nachnamen"], vornamen=lexika["vornamen"],
        orte=lexika["orte"], wortliste=lexika["wortliste"],
    )

    dateien = sorted(n for n in os.listdir(args.verzeichnis)
                     if n.lower().endswith(".txt"))

    je_kategorie = collections.Counter()
    betroffene = collections.Counter()
    ohne_marker = []
    berichte = []
    gelesen = 0

    for name in dateien:
        text = lies(os.path.join(args.verzeichnis, name))
        if not text or not text.strip():
            continue
        gelesen += 1
        hat_marker = bool(_RE_MARKER.search(text))
        if not hat_marker:
            ohne_marker.append(name)

        befunde, _ = erkenner.pruefe(text)
        hart = [b for b in befunde if b.kategorie in HART]
        namen_sicher = [b for b in befunde
                        if b.kategorie == erkennung.K_PERSON_NAME
                        and b.band == erkennung.BAND_SICHER]
        unsicher = [b for b in befunde if b.band == erkennung.BAND_UNSICHER]

        for b in hart:
            # E-Mail und Telefon trennen: eine E-Mail der Form
            # vorname.nachname@... ist ein Personendatum, eine Sammeladresse
            # info@... nicht.
            if b.kategorie == erkennung.K_PERSON_KONTAKT:
                if "@" in b.treffer:
                    lokal = b.treffer.split("@")[0]
                    schluessel = ("email_personenbezogen" if "." in lokal
                                  else "email_sammeladresse")
                else:
                    schluessel = "telefon"
            else:
                schluessel = b.kategorie
            je_kategorie[schluessel] += 1

        for b in namen_sicher:
            # Steht der Name im BfS-Lexikon, ist der Treffer belastbar;
            # sonst kann es auch eine Organisationsbezeichnung sein.
            erstes = b.treffer.split()[0].casefold()
            bestaetigt = (erstes in erkenner._nachnamen
                          or erstes in erkenner._vornamen)
            je_kategorie["name_anker_%s"
                         % ("im_lexikon" if bestaetigt else "nicht_im_lexikon")] += 1

        if hart or namen_sicher:
            betroffene[name] = len(hart) + len(namen_sicher)
        berichte.append((len(hart) + len(namen_sicher), len(unsicher),
                         hat_marker, name))

    print("Geprueft: %d Dateien" % gelesen)
    print("Ohne Platzhalter [Person_/Org_]: %d" % len(ohne_marker))
    print()
    print("HARTE Restbefunde (Kontakt, AHV, Konto, Adresse, Name mit Anrede)")
    print("Dateien mit mindestens einem harten Befund: %d von %d"
          % (len(betroffene), gelesen))
    for kategorie, anzahl in sorted(je_kategorie.items(), key=lambda x: -x[1]):
        if anzahl:
            print("   %-28s %d" % (kategorie, anzahl))
    print()

    print("Auffaelligste Dateien (nur Zaehler, keine Werte):")
    print("%-6s %-9s %-8s %s" % ("hart", "unsicher", "Marker", "Datei"))
    for hart, unsicher, marker, name in sorted(berichte, reverse=True)[:args.zeige]:
        if hart == 0:
            break
        print("%-6d %-9d %-8s %s" % (hart, unsicher, "ja" if marker else "NEIN",
                                     name[:70]))

    if ohne_marker:
        print()
        print("Dateien OHNE jeden Platzhalter (Herkunft pruefen):")
        for name in ohne_marker:
            eintrag = next((b for b in berichte if b[3] == name), None)
            print("   hart=%d unsicher=%d  %s"
                  % (eintrag[0], eintrag[1], name[:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
