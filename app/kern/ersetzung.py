"""Ersetzung auf dem Hinweg.

Ersetzt wird nur, was im Band "sicher" liegt. Unsichere Befunde fuehren nicht
zur Ersetzung, sondern zum Blockieren (A2) - das entscheidet der Aufrufer,
nicht dieses Modul.
"""
from . import erkennung, platzhalter


class SpeicherImArbeitsspeicher:
    """Zuordnungsspeicher ohne Datenbank - fuer Tests und den Trockenlauf.

    Der Datenbank-Speicher hat dieselbe Schnittstelle und dieselbe Zusage:
    gleiche Oberflaeche + gleiche Kategorie -> gleiche Nummer, solange
    Mandant und Projekt dieselben sind (A7).
    """

    def __init__(self):
        self._nach_schluessel = {}
        self._nach_nummer = {}

    def nummer_fuer(self, kategorie, oberflaeche):
        schluessel = (kategorie, _normiere(oberflaeche))
        if schluessel not in self._nach_schluessel:
            nummer = platzhalter.naechste_nummer(self._nach_nummer.keys())
            self._nach_schluessel[schluessel] = nummer
            self._nach_nummer[nummer] = oberflaeche
        return self._nach_schluessel[schluessel]

    def klartext(self, nummer):
        return self._nach_nummer.get(int(nummer))

    def alle(self):
        return dict(self._nach_nummer)


def _normiere(s):
    return " ".join(s.split()).casefold()


def ersetze(text, befunde, speicher):
    """Ersetzt die sicheren Befunde durch Platzhalter.

    Liefert (neuer_text, verwendet) mit verwendet = {nummer: klartext}.
    """
    sicher = [b for b in befunde if b.band == erkennung.BAND_SICHER]
    if not sicher:
        return text, {}

    verwendet = {}
    stuecke = []
    letzte = 0
    for b in sorted(sicher, key=lambda x: x.von):
        if b.von < letzte:
            # Ueberlappung - der frueher gesetzte Befund gewinnt.
            continue
        nummer = speicher.nummer_fuer(b.kategorie, b.treffer)
        verwendet[nummer] = speicher.klartext(nummer)
        stuecke.append(text[letzte:b.von])
        stuecke.append(platzhalter.bilde(nummer))
        letzte = b.bis
    stuecke.append(text[letzte:])
    return "".join(stuecke), verwendet
