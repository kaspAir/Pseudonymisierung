"""Regressionstests des blockierenden Verhaltens (A2, A3, A9)."""
import datetime as _dt

import pytest

from app import adapter
from app.kern import abschaltung, erkennung
from app.kern.ersetzung import SpeicherImArbeitsspeicher, ersetze
from app.kern.leckpruefung import Leck, pruefe
from app.kern.rueckersetzung import rueckersetze

LEXIKON = {"Buergi", "Steiner", "Vogt"}


def _erkenner(listen=None):
    return erkennung.Erkenner(listen=listen, namenslexikon=LEXIKON)


def test_unsicherer_befund_blockiert_den_chat_aufruf():
    """Beweist: Ein unsicherer Befund laesst keinen Chat-Aufruf hinaus."""
    rumpf = {
        "model": "claude-opus-4-8",
        "messages": [{"role": "user", "content": "Wir haben mit Vogt gesprochen."}],
    }
    a = adapter.hole("anthropic")
    alle = []
    for pfad, text in a.texte(rumpf):
        befunde, _ = _erkenner().pruefe(text, feld=pfad)
        alle.extend(befunde)
    assert erkennung.blockiert(alle)
    assert [b.band for b in alle] == [erkennung.BAND_UNSICHER]


def test_unsicherer_befund_blockiert_auch_den_embedding_aufruf():
    """Beweist: Ein unsicherer Befund laesst auch keinen Embedding-Aufruf
    hinaus - der Weg, der gern uebersehen wird."""
    rumpf = {"model": "voyage-3", "input": ["Projektleitung: Steiner", "harmloser Text"]}
    v = adapter.hole("voyage")
    alle = []
    for pfad, text in v.texte(rumpf):
        befunde, _ = _erkenner().pruefe(text, feld=pfad)
        alle.extend(befunde)
    assert erkennung.blockiert(alle)
    assert any(b.feld == "input[0]" for b in alle)


def test_befund_ist_maschinenlesbar_begruendet():
    """Beweist: Beim Blockieren kommt maschinenlesbar zurueck, WAS und WARUM
    beanstandet wurde - mit Textstelle, Kategorie und Sicherheit (A3)."""
    text = "Wir haben mit Vogt gesprochen."
    befunde, _ = _erkenner().pruefe(text, feld="messages[0].content")
    d = befunde[0].als_dict("bf_1", text)
    assert d["kategorie"] == erkennung.K_PERSON_NAME
    assert d["band"] == erkennung.BAND_UNSICHER
    assert d["ort"]["feld"] == "messages[0].content"
    assert text[d["ort"]["von"]:d["ort"]["bis"]] == "Vogt"
    assert 0 < d["sicherheit"] < 1
    assert d["grund"]
    assert d["moegliche_entscheide"] == ["ersetzen", "freigeben"]


class _Liste:
    """Minimale Liste mit einer Freigabe - steht fuer den Nutzerentscheid."""

    def __init__(self, freigaben):
        self._f = set(f.casefold() for f in freigaben)

    def entscheid(self, treffer, kategorie=None):
        return "freigabe" if treffer.casefold() in self._f else None


def test_unveraenderter_originalaufruf_laeuft_nach_entscheid_durch():
    """Beweist: Nach dem Entscheid laeuft der UNVERAENDERTE Originalaufruf
    durch - das Blockieren vernichtet keinen Text (A9)."""
    original = {
        "model": "claude-opus-4-8",
        "messages": [{"role": "user", "content": "Wir haben mit Vogt gesprochen."}],
    }
    a = adapter.hole("anthropic")

    # Erster Anlauf: blockiert.
    erst = []
    for pfad, text in a.texte(original):
        b, _ = _erkenner().pruefe(text, feld=pfad)
        erst.extend(b)
    assert erkennung.blockiert(erst)

    # Nutzer entscheidet "Fehlalarm" -> Freigabe in der Mandantenliste.
    nach_entscheid = _erkenner(listen=_Liste({"Vogt"}))

    # Zweiter Anlauf mit exakt demselben Rumpf.
    zweit = []
    for pfad, text in a.texte(original):
        b, _ = nach_entscheid.pruefe(text, feld=pfad)
        zweit.extend(b)
    assert not erkennung.blockiert(zweit)
    assert original["messages"][0]["content"] == "Wir haben mit Vogt gesprochen."


def test_sichere_treffer_werden_ersetzt_und_zurueckgesetzt():
    """Beweist: Der Rundweg schliesst sich - sicher erkannter Klartext geht als
    Platzhalter hinaus und kommt als Klartext zurueck."""
    quelle = "Zustaendig ist Herr Buergi, erreichbar unter marc.buergi@be.ch."
    befunde, _ = _erkenner().pruefe(quelle, feld="messages[0].content")
    assert not erkennung.blockiert(befunde)

    speicher = SpeicherImArbeitsspeicher()
    hinweg, verwendet = ersetze(quelle, befunde, speicher)
    assert "Buergi" not in hinweg
    assert "marc.buergi@be.ch" not in hinweg

    antwort = "Wie besprochen wird {{P1}} informiert."
    zurueck, r = rueckersetze(antwort, verwendet)
    assert "Buergi" in zurueck
    assert not r.unbekannt


def test_antwort_mit_platzhalter_rest_wird_nicht_ausgeliefert():
    """Beweist: Eine Antwort mit unaufgeloestem Platzhalter-Rest wird nicht
    ausgeliefert - lieber ein Fehler als ein still falscher Text."""
    zurueck, r = rueckersetze("Laut {{P99}} ist es so.", {3: "Marc Buergi"})
    with pytest.raises(Leck):
        pruefe(zurueck, r, nie_gesendet=[])


def test_unerwarteter_klartext_in_der_antwort_wird_gemeldet():
    """Beweist: Taucht ein Klartextwert auf, den wir nie gesendet haben, wird
    die Antwort nicht ausgeliefert."""
    zurueck, r = rueckersetze("Alles in Ordnung, sagt Anna Steiner.", {})
    with pytest.raises(Leck):
        pruefe(zurueck, r, nie_gesendet=["Anna Steiner"])


def test_in_produktion_keine_ausnahme():
    """Beweist: In Produktion laesst sich keine Ausnahme aktivieren."""
    morgen = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)
    with pytest.raises(abschaltung.AusnahmeVerweigert):
        abschaltung.pruefe_antrag("main", True, "Testlauf", morgen)
    for umgebung in ("develop", "test"):
        assert abschaltung.pruefe_antrag(umgebung, True, "Testlauf", morgen)


def test_ausnahme_ohne_frist_oder_begruendung_wird_verweigert():
    """Beweist: Eine Abschaltung ist immer befristet und immer begruendet."""
    morgen = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)
    with pytest.raises(abschaltung.AusnahmeVerweigert):
        abschaltung.pruefe_antrag("develop", True, "", morgen)
    with pytest.raises(abschaltung.AusnahmeVerweigert):
        abschaltung.pruefe_antrag("develop", True, "Testlauf", None)
    with pytest.raises(abschaltung.AusnahmeVerweigert):
        abschaltung.pruefe_antrag("develop", False, "Testlauf", morgen)
