"""Pseudonymisiert einen Bestand von Dokumenten fuer den Wissenskorpus.

Dies ist ein WERKZEUG, kein Teil des Dienstes: der Dienst ist ein Vorschalt-
Proxy fuer KI-Aufrufe. Der Erkennungs- und Ersetzungskern (app/kern) wird hier
unveraendert wiederverwendet.

RICHTLINIENENTSCHEID FUER DEN STAPELBETRIEB
-------------------------------------------
Im Gespraech gilt: unsicher -> blockieren, der Mensch entscheidet (A2). Bei
189 Dokumenten kann niemand hunderte Fundstellen einzeln entscheiden. Und ein
Korpus ist etwas anderes als ein Interview: zu viel ersetzen kostet dort etwas
Kontext, zu wenig ersetzen ist ein Datenschutzvorfall.

Darum ist die Vorgabe hier '--unsicher ersetzen': unsichere Fundstellen werden
ebenfalls ersetzt. Mit '--unsicher melden' laesst sich das umdrehen; dann wird
nur berichtet und nichts ersetzt.

WAS NICHT PASSIERT
------------------
Es wird KEINE Zuordnungstabelle angelegt. Der Lauf ist einwegig - eine
Rueckersetzung ist weder moeglich noch erwuenscht. Platzhalternummern gelten
je Dokument (ein Dossier ~ ein Vorhaben); dokumentuebergreifende Konsistenz
wuerde erlauben, Personen ueber Vorhaben hinweg zu verknuepfen, und waere in
einem GETEILTEN Korpus ein Rueckschritt.

Der Laufbericht enthaelt ausschliesslich Zaehler - niemals Fundwerte.

Aufruf:
    python scripts/pseudonymisiere_bestand.py <quelle> <ziel> [--unsicher ersetzen]
"""
import argparse
import collections
import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.kern import erkennung  # noqa: E402
from app.kern.ersetzung import SpeicherImArbeitsspeicher, ersetze  # noqa: E402
from app.web import lade_lexika  # noqa: E402

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORD = ".docx", ".dotx", ".docm"
TABELLE = ".xlsx", ".xlsm"
NICHT_UNTERSTUETZT = ".doc", ".msg"
# Alles andere wird uebersprungen statt als Fehler gemeldet - im Quellordner
# koennen Beifiles liegen, die nichts mit dem Bestand zu tun haben.
DOKUMENTFORMATE = set(WORD) | set(TABELLE) | {".pdf", ".html", ".htm", ".txt"}

_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# -- Textgewinnung ---------------------------------------------------------

def _aus_word(pfad):
    """Liest alle Textknoten aus einer Word-Datei.

    Bewusst ueber das rohe Dokument-XML statt ueber eine Absatz-API: so werden
    auch Tabellenzellen und Inhaltssteuerelemente (SDT) erfasst. Gerade dort
    stehen in HERMES-Dokumenten die Namen.
    """
    try:
        from defusedxml.ElementTree import fromstring
    except ImportError:
        from xml.etree.ElementTree import fromstring

    stuecke = []
    with zipfile.ZipFile(pfad) as z:
        teile = [n for n in z.namelist()
                 if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)]
        for name in sorted(teile):
            baum = fromstring(z.read(name))
            for absatz in baum.iter("%sp" % _NS):
                worte = [k.text for k in absatz.iter("%st" % _NS) if k.text]
                if worte:
                    stuecke.append("".join(worte))
    return "\n".join(stuecke)


def _aus_pdf(pfad):
    from pypdf import PdfReader
    leser = PdfReader(pfad)
    return "\n".join((s.extract_text() or "") for s in leser.pages)


def _aus_tabelle(pfad):
    import openpyxl
    stuecke = []
    wb = openpyxl.load_workbook(pfad, read_only=True, data_only=True)
    for blatt in wb.sheetnames:
        for zeile in wb[blatt].iter_rows(values_only=True):
            werte = [str(z) for z in zeile if z is not None]
            if werte:
                stuecke.append("\t".join(werte))
    wb.close()
    return "\n".join(stuecke)


def _aus_html(pfad):
    with open(pfad, "rb") as f:
        roh = f.read()
    for kodierung in ("utf-8", "cp1252", "latin-1"):
        try:
            text = roh.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    else:
        return ""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    return re.sub(r"<[^>]+>", " ", text)


def gewinne_text(pfad):
    """(text, fehler) - fehler ist None bei Erfolg."""
    endung = os.path.splitext(pfad)[1].lower()
    try:
        if endung in WORD:
            return _aus_word(pfad), None
        if endung == ".pdf":
            return _aus_pdf(pfad), None
        if endung in TABELLE:
            return _aus_tabelle(pfad), None
        if endung in (".html", ".htm"):
            return _aus_html(pfad), None
        if endung == ".txt":
            with open(pfad, "rb") as f:
                roh = f.read()
            for k in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    return roh.decode(k), None
                except UnicodeDecodeError:
                    continue
            return None, "Kodierung nicht erkannt"
        if endung in NICHT_UNTERSTUETZT:
            return None, "Format nicht unterstuetzt"
        return None, "unbekannte Endung"
    except Exception as f:                      # noqa: BLE001
        return None, "%s: %s" % (type(f).__name__, str(f)[:80])


# -- Lauf ------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("quelle")
    p.add_argument("ziel")
    p.add_argument("--unsicher", choices=("ersetzen", "melden"), default="ersetzen")
    p.add_argument("--trocken", action="store_true",
                   help="nur berichten, nichts schreiben")
    args = p.parse_args()

    lexika = lade_lexika(os.path.join(WURZEL, "lexikon"))
    if not lexika["nachnamen"]:
        print("FEHLER: Lexika fehlen.")
        return 1
    erkenner = erkennung.Erkenner(
        nachnamen=lexika["nachnamen"], vornamen=lexika["vornamen"],
        orte=lexika["orte"], wortliste=lexika["wortliste"],
    )

    if not args.trocken:
        os.makedirs(args.ziel, exist_ok=True)

    dateien = []
    for wurzel, _, namen in os.walk(args.quelle):
        for n in sorted(namen):
            dateien.append(os.path.join(wurzel, n))

    je_kategorie = collections.Counter()
    fehler = []
    leer = []
    uebersprungen = 0
    verarbeitet = 0
    ersetzungen_gesamt = 0
    unsicher_gesamt = 0
    woerter_gesamt = 0
    platzhalter_gesamt = 0

    for pfad in dateien:
        if os.path.splitext(pfad)[1].lower() not in DOKUMENTFORMATE \
                and os.path.splitext(pfad)[1].lower() not in NICHT_UNTERSTUETZT:
            uebersprungen += 1
            continue
        text, fehlermeldung = gewinne_text(pfad)
        if fehlermeldung:
            fehler.append((os.path.basename(pfad), fehlermeldung))
            continue
        if not text or not text.strip():
            # Bei einer PDF heisst "kein Text" fast immer: gescannt, also nur
            # Bild. Solche Dokumente kommen ohne Texterkennung gar nicht in den
            # Korpus - das muss sichtbar sein, nicht stillschweigend passieren.
            leer.append(os.path.basename(pfad))
            continue

        befunde, _ = erkenner.pruefe(text)
        unsicher = [b for b in befunde if b.band == erkennung.BAND_UNSICHER]
        unsicher_gesamt += len(unsicher)

        if args.unsicher == "ersetzen":
            # Unsichere Fundstellen auf "sicher" heben, damit ersetze() sie
            # mitnimmt. Der Zaehler oben haelt fest, wie viele es waren.
            for b in unsicher:
                b.band = erkennung.BAND_SICHER

        for b in befunde:
            if b.band == erkennung.BAND_SICHER:
                je_kategorie[b.kategorie] += 1

        # Eigener Speicher je Dokument: keine Verknuepfbarkeit ueber Vorhaben.
        speicher = SpeicherImArbeitsspeicher()
        neu, verwendet = ersetze(text, befunde, speicher)
        ersetzungen_gesamt += len(verwendet)
        verarbeitet += 1
        woerter_gesamt += len(text.split())
        platzhalter_gesamt += len(re.findall(r"\{\{P\d+\}\}", neu))

        if not args.trocken:
            name = os.path.basename(pfad)
            stamm, endung = os.path.splitext(name)
            ziel = os.path.join(args.ziel,
                                "%s_%s.txt" % (stamm, endung.lstrip(".")))
            with open(ziel, "w", encoding="utf-8", newline="\n") as f:
                f.write(neu)

    print("Dateien gefunden:      %d" % len(dateien))
    print("Verarbeitet:           %d" % verarbeitet)
    print("Uebersprungen:         %d (keine Dokumentformate)" % uebersprungen)
    print("Ohne Textinhalt:       %d (bei PDF: vermutlich gescannt)" % len(leer))
    print("Nicht lesbar:          %d" % len(fehler))
    print()
    print("Richtlinie unsicher:   %s" % args.unsicher)
    print("Unsichere Fundstellen: %d" % unsicher_gesamt)
    print("Platzhalter vergeben:  %d (verschiedene Personen/Angaben)"
          % ersetzungen_gesamt)
    print()
    print("QUALITAETSMASS")
    print("Woerter gesamt:        %d" % woerter_gesamt)
    print("Platzhalter im Text:   %d" % platzhalter_gesamt)
    if woerter_gesamt:
        print("Anteil ersetzt:        %.2f%% der Woerter"
              % (100.0 * platzhalter_gesamt / woerter_gesamt))
        print("Je 1000 Woerter:       %.1f Platzhalter"
              % (1000.0 * platzhalter_gesamt / woerter_gesamt))
    print()
    print("Ersetzt nach Kategorie:")
    for kategorie, anzahl in sorted(je_kategorie.items(), key=lambda x: -x[1]):
        print("   %-22s %d" % (kategorie, anzahl))

    if fehler:
        print()
        print("Nicht lesbar (bitte pruefen):")
        for name, grund in fehler[:20]:
            print("   %-58s %s" % (name[:58], grund))
    if leer:
        print()
        print("Ohne Textinhalt: %s" % ", ".join(n[:40] for n in leer[:10]))

    if args.trocken:
        print()
        print("(Trockenlauf - nichts geschrieben.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
