"""Regressionstests der Rueckersetzung - das technisch heikelste Stueck."""
from app.kern import platzhalter
from app.kern.rueckersetzung import Rueckersetzer, rueckersetze

ZUORDNUNG = {3: "Marc Buergi", 7: "Anna Steiner"}


def test_beugungssuffix_bleibt_am_namen():
    """Beweist: Ein Platzhalter mit deutschem Beugungssuffix wird korrekt
    rueckersetzt und behaelt das Suffix."""
    text, _ = rueckersetze("Das Anliegen des {{P3}}s wurde geprueft.", ZUORDNUNG)
    assert text == "Das Anliegen des Marc Buergis wurde geprueft."


def test_beugung_genitiv_mit_apostroph_und_dativ_n():
    """Beweist: Auch andere Beugungsformen bleiben erhalten, ohne dass der
    Rueckersetzer sie kennen muss."""
    text, _ = rueckersetze("mit {{P7}}n und {{P3}}s Team", ZUORDNUNG)
    assert text == "mit Anna Steinern und Marc Buergis Team"


def test_zeilenumbruch_innerhalb_des_platzhalters():
    """Beweist: Ein durch einen Zeilenumbruch zerteilter Platzhalter wird
    erkannt."""
    text, _ = rueckersetze("Zustaendig ist {{P\n3}} heute.", ZUORDNUNG)
    assert text == "Zustaendig ist Marc Buergi heute."


def test_markdown_um_den_platzhalter_herum():
    """Beweist: Markdown-Auszeichnung um einen Platzhalter herum stoert die
    Rueckersetzung nicht."""
    text, _ = rueckersetze("**{{P3}}** hat zugestimmt.", ZUORDNUNG)
    assert text == "**Marc Buergi** hat zugestimmt."


def test_kleinschreibung_und_leerzeichen():
    """Beweist: Der Rueckersetzer ist toleranter als die Vergabeform."""
    text, _ = rueckersetze("{{ p3 }} und {{P 7}}", ZUORDNUNG)
    assert text == "Marc Buergi und Anna Steiner"


def test_platzhalter_ueber_chunk_grenze_zerschnitten():
    """Beweist: Ein ueber Chunk-Grenzen zerschnittener Platzhalter wird im
    Stream korrekt zusammengesetzt - der Fall, an dem str.replace scheitert."""
    r = Rueckersetzer(ZUORDNUNG)
    ausgabe = ""
    for chunk in ["Zustaendig ist ", "{{P", "3", "}}", " seit Mai."]:
        ausgabe += r.schreibe(chunk)
    ausgabe += r.schluss()
    assert ausgabe == "Zustaendig ist Marc Buergi seit Mai."


def test_stream_haelt_nichts_unnoetig_zurueck():
    """Beweist: Text ohne Platzhalter wird sofort freigegeben und nicht bis
    zum Schluss gepuffert."""
    r = Rueckersetzer(ZUORDNUNG)
    erste = r.schreibe("Ein ganz gewoehnlicher Satz. ")
    assert erste == "Ein ganz gewoehnlicher Satz. "


def test_geschweifte_klammer_ohne_platzhalter_wird_freigegeben():
    """Beweist: Eine geschweifte Klammer, aus der kein Platzhalter mehr werden
    kann, blockiert den Strom nicht dauerhaft."""
    r = Rueckersetzer(ZUORDNUNG)
    ausgabe = r.schreibe("Wert {x} im JSON")
    ausgabe += r.schluss()
    assert ausgabe == "Wert {x} im JSON"


def test_unbekannter_platzhalter_wird_nicht_geraten():
    """Beweist: Einen nie vergebenen Platzhalter loest der Dienst nicht auf,
    sondern merkt ihn als Leck-Verdacht vor."""
    text, r = rueckersetze("Laut {{P99}} ist es so.", ZUORDNUNG)
    assert 99 in r.unbekannt
    assert "{{P99}}" in text


def test_bestandsplatzhalter_bleibt_unangetastet():
    """Beweist: Bestandsplatzhalter [Person_099] aus dem Seed-Korpus kollidieren
    nicht mit der eigenen Platzhalterform."""
    quelle = "Im Korpus steht [Person_099] neben {{P3}}."
    text, r = rueckersetze(quelle, ZUORDNUNG)
    assert text == "Im Korpus steht [Person_099] neben Marc Buergi."
    assert not r.unbekannt
    assert platzhalter.RE_BESTAND.search(text)
