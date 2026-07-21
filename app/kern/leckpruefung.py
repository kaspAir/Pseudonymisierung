"""Leckpruefung vor der Auslieferung an die aufrufende Anwendung.

Zweck (KONZEPT 5.2, Punkt 3): eine still falsche Rueckersetzung ist der
schlimmste Ausgang - es stuende dann ein plausibler falscher Name im
Verwaltungsdokument und niemand merkte es. Deshalb wird lieber ein Fehler
ausgeliefert als ein Text, an dem etwas nicht stimmt.
"""
import re

from . import platzhalter

# Reste einer Klammerform, die nach der Rueckersetzung nichts mehr zu suchen haben.
_RE_REST = re.compile(r"\{\{|\}\}")


class Leck(Exception):
    """Die Antwort darf nicht ausgeliefert werden."""

    def __init__(self, art, hinweis):
        super().__init__(hinweis)
        self.art = art
        self.hinweis = hinweis


def pruefe(text, rueckersetzer, nie_gesendet):
    """Prueft die fertig rueckersetzte Antwort in beide Richtungen.

    nie_gesendet: Klartextwerte aus der Zuordnungstabelle des Mandanten, die in
                  DIESEM Aufruf nicht hinausgegangen sind.
    """
    # (a) Unaufgelöste Platzhalter oder Fragmente davon.
    if rueckersetzer.unbekannt:
        raise Leck(
            "unbekannter_platzhalter",
            "Antwort verwendet nie vergebene Platzhalter: %s"
            % ", ".join(platzhalter.bilde(n) for n in sorted(rueckersetzer.unbekannt)),
        )

    if platzhalter.RE_PLATZHALTER.search(text) or _RE_REST.search(text):
        raise Leck(
            "platzhalter_rest",
            "Antwort enthaelt unaufgeloeste Platzhalter-Reste.",
        )

    # (b) Klartext, den wir nie hingeschickt haben. Dann hat das Modell geraten
    # oder wir haben auf dem Hinweg etwas uebersehen. Beides ist meldepflichtig.
    for wert in nie_gesendet:
        if wert and wert in text:
            raise Leck(
                "unerwarteter_klartext",
                "Antwort enthaelt einen Klartextwert, der nicht gesendet wurde.",
            )

    return True
