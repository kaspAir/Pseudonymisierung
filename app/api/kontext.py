"""Aufloesung von Anwendung, Mandant und Projekt aus den Kopfzeilen.

Grundsatz: es gibt KEINEN Standard-Mandanten. Fehlt eine Angabe, wird der
Aufruf abgewiesen - nicht auf einen Sammeltopf umgeleitet.

Anwendung muss registriert sein (der Betreiber hinterlegt ohnehin ihre
Anbieterschluessel). Mandant und Projekt entstehen bei Bedarf automatisch.
Das ist bewusst so: ein Tippfehler in der Mandanten-Kennung erzeugt dann einen
LEEREN Mandanten ohne Listen - und ein leerer Mandant blockiert, statt still
etwas durchzulassen. Der Fehler ist damit laut statt gefaehrlich.
"""
from ..models import Anwendung, Mandant, Projekt


class KontextFehler(Exception):
    def __init__(self, meldung):
        super().__init__(meldung)
        self.meldung = meldung


def loese_auf(sitzung, kopfzeilen):
    anwendung_schluessel = (kopfzeilen.get("X-Pseudo-Anwendung") or "").strip()
    mandant_extern = (kopfzeilen.get("X-Pseudo-Mandant") or "").strip()
    projekt_extern = (kopfzeilen.get("X-Pseudo-Projekt") or "").strip()

    fehlend = [
        name
        for name, wert in (
            ("X-Pseudo-Anwendung", anwendung_schluessel),
            ("X-Pseudo-Mandant", mandant_extern),
            ("X-Pseudo-Projekt", projekt_extern),
        )
        if not wert
    ]
    if fehlend:
        raise KontextFehler("Fehlende Kopfzeile(n): %s" % ", ".join(fehlend))

    anwendung = (
        sitzung.query(Anwendung)
        .filter(Anwendung.schluessel == anwendung_schluessel)
        .one_or_none()
    )
    if anwendung is None or not anwendung.aktiv:
        raise KontextFehler("Unbekannte oder inaktive Anwendung: %s" % anwendung_schluessel)

    mandant = (
        sitzung.query(Mandant)
        .filter(Mandant.anwendung_id == anwendung.id,
                Mandant.externe_id == mandant_extern)
        .one_or_none()
    )
    if mandant is None:
        mandant = Mandant(anwendung_id=anwendung.id, externe_id=mandant_extern)
        sitzung.add(mandant)
        sitzung.flush()

    projekt = (
        sitzung.query(Projekt)
        .filter(Projekt.mandant_id == mandant.id,
                Projekt.externe_id == projekt_extern)
        .one_or_none()
    )
    if projekt is None:
        projekt = Projekt(mandant_id=mandant.id, externe_id=projekt_extern)
        sitzung.add(projekt)
        sitzung.flush()

    return {"anwendung": anwendung, "mandant": mandant, "projekt": projekt}
