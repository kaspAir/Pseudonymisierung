"""Regressionstests der Platzhalter-Konsistenz (A7)."""
from app.kern import erkennung
from app.kern.ersetzung import SpeicherImArbeitsspeicher, ersetze


def test_gleiche_person_gleicher_platzhalter():
    """Beweist: Dieselbe Person erhaelt in zwei Aufrufen desselben Projekts
    denselben Platzhalter."""
    speicher = SpeicherImArbeitsspeicher()
    e = erkennung.Erkenner(namenslexikon={"Buergi"})

    erst, _ = ersetze(*_mit(e, "Zustaendig ist Herr Buergi."), speicher=speicher)
    zweit, _ = ersetze(*_mit(e, "Frau Buergi hat zugestimmt."), speicher=speicher)

    assert "{{P1}}" in erst
    assert "{{P1}}" in zweit


def test_verschiedene_personen_verschiedene_platzhalter():
    """Beweist: Zwei verschiedene Personen erhalten verschiedene Platzhalter."""
    speicher = SpeicherImArbeitsspeicher()
    e = erkennung.Erkenner(namenslexikon={"Buergi", "Steiner"})
    text, verwendet = ersetze(
        *_mit(e, "Herr Buergi und Frau Steiner sind zustaendig."), speicher=speicher
    )
    assert len(verwendet) == 2
    assert "{{P1}}" in text and "{{P2}}" in text


def test_schreibvarianten_werden_normalisiert():
    """Beweist: Unterschiedliche Schreibweise mit gleichem Kern (Leerzeichen,
    Gross-/Kleinschreibung) fuehrt auf denselben Platzhalter."""
    speicher = SpeicherImArbeitsspeicher()
    erste = speicher.nummer_fuer("person_name", "Marc  Buergi")
    zweite = speicher.nummer_fuer("person_name", "marc buergi")
    assert erste == zweite == 1


def _mit(erkenner, text):
    befunde, _ = erkenner.pruefe(text, feld="messages[0].content")
    return text, befunde
