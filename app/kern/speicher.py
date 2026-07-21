"""Zuordnungsspeicher auf der Datenbank.

Gleiche Schnittstelle wie SpeicherImArbeitsspeicher (ersetzung.py) und dieselbe
Zusage: gleiche Oberflaeche + gleiche Kategorie -> gleiche Nummer, solange
Anwendung, Mandant und Projekt dieselben sind (A7).

Der Klartext liegt hier ausschliesslich verschluesselt (models.Zuordnung).
"""
from sqlalchemy import func

from ..models import Zuordnung
from ..tresor import normiere


class DatenbankSpeicher:
    def __init__(self, sitzung, tresor, anwendung_id, mandant_id, projekt_id):
        if not all([anwendung_id, mandant_id, projekt_id]):
            raise ValueError(
                "Zuordnungen brauchen Anwendung, Mandant und Projekt - es gibt "
                "keinen Sammeltopf."
            )
        self._s = sitzung
        self._t = tresor
        self._a = anwendung_id
        self._m = mandant_id
        self._p = projekt_id
        self._klartext_zwischenspeicher = {}

    def _grundfilter(self):
        return (
            Zuordnung.anwendung_id == self._a,
            Zuordnung.mandant_id == self._m,
            Zuordnung.projekt_id == self._p,
        )

    def nummer_fuer(self, kategorie, oberflaeche):
        h = self._t.hash(normiere(oberflaeche))
        vorhanden = (
            self._s.query(Zuordnung)
            .filter(*self._grundfilter(),
                    Zuordnung.kategorie == kategorie,
                    Zuordnung.oberflaeche_hash == h)
            .one_or_none()
        )
        if vorhanden is not None:
            self._klartext_zwischenspeicher[vorhanden.nummer] = oberflaeche
            return vorhanden.nummer

        hoechste = (
            self._s.query(func.max(Zuordnung.nummer))
            .filter(*self._grundfilter())
            .scalar()
        )
        nummer = (hoechste or 0) + 1
        self._s.add(
            Zuordnung(
                anwendung_id=self._a,
                mandant_id=self._m,
                projekt_id=self._p,
                kategorie=kategorie,
                oberflaeche_hash=h,
                klartext_chiffre=self._t.verschluessle(oberflaeche),
                nummer=nummer,
            )
        )
        self._s.flush()
        self._klartext_zwischenspeicher[nummer] = oberflaeche
        return nummer

    def klartext(self, nummer):
        nummer = int(nummer)
        if nummer in self._klartext_zwischenspeicher:
            return self._klartext_zwischenspeicher[nummer]
        z = (
            self._s.query(Zuordnung)
            .filter(*self._grundfilter(), Zuordnung.nummer == nummer)
            .one_or_none()
        )
        if z is None:
            return None
        wert = self._t.entschluessle(z.klartext_chiffre)
        self._klartext_zwischenspeicher[nummer] = wert
        return wert

    def alle_klartexte(self):
        """Alle Klartexte dieses Projekts - fuer die Leckpruefung (b)."""
        werte = []
        for z in self._s.query(Zuordnung).filter(*self._grundfilter()).all():
            werte.append(self._t.entschluessle(z.klartext_chiffre))
        return werte
