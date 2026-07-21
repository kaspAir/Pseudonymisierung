"""Regressionstests gegen die AUSGELIEFERTEN Lexika.

Die uebrigen Tests arbeiten mit kleinen, erfundenen Wortmengen. Hier wird die
echte Konfiguration geprueft - denn genau ihr Zusammenspiel entscheidet, ob der
Dienst auf gewoehnlichem Verwaltungsdeutsch benutzbar ist oder nicht.
"""
import os

import pytest

from app.kern import erkennung
from app.web import lade_lexika

LEXIKON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "lexikon")


@pytest.fixture(scope="module")
def lexika():
    daten = lade_lexika(LEXIKON)
    if not daten["nachnamen"]:
        pytest.skip("Lexika nicht vorhanden")
    return daten


@pytest.fixture(scope="module")
def erkenner(lexika):
    return erkennung.Erkenner(
        nachnamen=lexika["nachnamen"], vornamen=lexika["vornamen"],
        orte=lexika["orte"], wortliste=lexika["wortliste"],
    )


def test_lexika_sind_vollstaendig_ausgeliefert(lexika):
    """Beweist: Alle vier Listen liegen bei und haben die erwartete
    Groessenordnung - fehlt eine, aendert sich das Verhalten stillschweigend."""
    assert len(lexika["nachnamen"]) > 200000
    assert len(lexika["vornamen"]) > 60000
    assert len(lexika["orte"]) > 4000
    assert len(lexika["wortliste"]) > 100


def test_hermes_vokabular_blockiert_nicht(erkenner):
    """Beweist: Kernvokabular der Verwaltung blockiert nicht, obwohl jedes
    dieser Woerter zugleich ein Schweizer Nachname ist."""
    text = ("Der Bericht nennt Kosten und Termine. Die Fachstelle Recht prueft "
            "die Rechtsgrundlagen. Der Bau beginnt im Juni. Die Justiz ist "
            "beteiligt. Der Betrag lautet auf Franken.")
    befunde, _ = erkenner.pruefe(text)
    unsicher = [b.treffer for b in befunde if b.band == erkennung.BAND_UNSICHER]
    assert unsicher == []


def test_ortschaften_blockieren_nicht(erkenner):
    """Beweist: Schweizer Gemeinden blockieren nicht, obwohl 359 Ortsnamen
    zugleich Nachnamen sind."""
    befunde, _ = erkenner.pruefe(
        "Die Standorte sind Basel, Arbon und Baden; Bellinzona folgt."
    )
    assert [b for b in befunde if b.band == erkennung.BAND_UNSICHER] == []


def test_echter_name_blockiert_weiterhin(erkenner):
    """Beweist: Die Gegensignale oeffnen kein Loch - ein alleinstehender
    Nachname haelt den Aufruf weiterhin an."""
    befunde, _ = erkenner.pruefe("Projektleitung: Steiner")
    unsicher = [b.treffer for b in befunde if b.band == erkennung.BAND_UNSICHER]
    assert unsicher == ["Steiner"]


def test_namen_mit_stuetzsignal_werden_ersetzt(erkenner):
    """Beweist: Mit Anrede oder als Vorname+Nachname werden Namen sicher
    erkannt und ersetzt, statt zu blockieren."""
    befunde, _ = erkenner.pruefe(
        "Zustaendig ist Herr Buergi. Die Stellvertretung hat Anna Meier."
    )
    sicher = [b.treffer for b in befunde if b.band == erkennung.BAND_SICHER]
    assert "Buergi" in sicher
    assert "Anna Meier" in sicher


def test_adresse_samt_ortschaft_als_einheit(erkenner):
    """Beweist: Mit dem amtlichen Verzeichnis wird die Adresse als eine
    Fundstelle erfasst."""
    befunde, _ = erkenner.pruefe("Der Sitz ist an der Musterstrasse 5, 3011 Bern.")
    adressen = [b.treffer for b in befunde if b.kategorie == erkennung.K_ADRESSE]
    assert adressen == ["Musterstrasse 5, 3011 Bern"]
