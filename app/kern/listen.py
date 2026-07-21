"""Aufloesung der Freigabe- und Sperrlisten (KONZEPT 6.2).

Drei Geltungsbereiche mit harter Asymmetrie:

    betrieb     nur Betreiber, NUR Freigaben (technische Begriffe)
    anwendung   nur Betreiber, NUR Freigaben (z.B. HERMES-Fachbegriffe)
    mandant     Nutzerentscheide, Freigaben UND Sperren

Sperren wirken damit ausschliesslich auf Mandantenebene, und ein Nutzerklick
landet nie hoeher als beim eigenen Mandanten. Daraus folgt die Zusage, die
gehalten werden muss: eine Freigabe kann NIEMALS bei einem anderen Mandanten
wirken (Anforderung A5).
"""
import re

BEREICH_BETRIEB = "betrieb"
BEREICH_ANWENDUNG = "anwendung"
BEREICH_MANDANT = "mandant"

ART_FREIGABE = "freigabe"
ART_SPERRE = "sperre"

# Welche Art in welchem Bereich ueberhaupt zulaessig ist.
ERLAUBT = {
    BEREICH_BETRIEB: {ART_FREIGABE},
    BEREICH_ANWENDUNG: {ART_FREIGABE},
    BEREICH_MANDANT: {ART_FREIGABE, ART_SPERRE},
}


class BereichVerletzt(Exception):
    """Es wurde versucht, eine Sperre oberhalb der Mandantenebene abzulegen."""


def pruefe_zulaessig(bereich, art):
    if bereich not in ERLAUBT:
        raise BereichVerletzt("Unbekannter Geltungsbereich: %r" % bereich)
    if art not in ERLAUBT[bereich]:
        raise BereichVerletzt(
            "Art %r ist im Bereich %r nicht zulaessig (nur %s)."
            % (art, bereich, ", ".join(sorted(ERLAUBT[bereich])))
        )
    return True


def _passt(eintrag, treffer):
    if eintrag.mustertyp == "regex":
        return re.search(eintrag.muster, treffer, re.IGNORECASE) is not None
    return eintrag.muster.casefold() == treffer.casefold()


class Listen:
    """Haelt die fuer EINEN Mandanten geltenden Eintraege.

    Der Aufrufer laedt die Eintraege bereits gefiltert - siehe lade() unten.
    Diese Klasse trifft keine Datenbankentscheidungen.
    """

    def __init__(self, eintraege):
        self._eintraege = [e for e in eintraege if e.widerrufen_am is None]

    def entscheid(self, treffer, kategorie=None):
        """'freigabe', 'sperre' oder None.

        Eine Sperre schlaegt eine Freigabe: sie ist die vorsichtigere Aussage
        und kann ausserdem nur vom Mandanten selbst stammen.
        """
        gefunden = None
        for e in self._eintraege:
            if kategorie and e.kategorie and e.kategorie != kategorie:
                continue
            if not _passt(e, treffer):
                continue
            if e.art == ART_SPERRE:
                return ART_SPERRE
            gefunden = ART_FREIGABE
        return gefunden


def lade(sitzung, modell, anwendung_id, mandant_id):
    """Laedt genau die Eintraege, die fuer diesen Mandanten gelten.

    Die Mandantentrennung wird HIER durchgesetzt: Eintraege des Bereichs
    'mandant' werden ausschliesslich fuer die uebergebene mandant_id geladen.
    Es gibt keinen Pfad, auf dem ein fremder Mandant hereinkommt.
    """
    if mandant_id is None or anwendung_id is None:
        raise ValueError("anwendung_id und mandant_id sind zwingend.")

    q = sitzung.query(modell).filter(
        modell.widerrufen_am.is_(None),
        (
            (modell.bereich == BEREICH_BETRIEB)
            | (
                (modell.bereich == BEREICH_ANWENDUNG)
                & (modell.anwendung_id == anwendung_id)
            )
            | (
                (modell.bereich == BEREICH_MANDANT)
                & (modell.anwendung_id == anwendung_id)
                & (modell.mandant_id == mandant_id)
            )
        ),
    )
    return Listen(q.all())
