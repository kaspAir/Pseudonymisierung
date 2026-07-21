"""Regressionstests der Mandantentrennung.

Das ist die Zusage, deren Bruch am teuersten waere: eine Freigabe darf niemals
bei einem anderen Mandanten wirken (Anforderung A5).
"""
import datetime as _dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.kern import listen
from app.models import Anwendung, Base, Listeneintrag, Mandant


@pytest.fixture()
def sitzung():
    maschine = create_engine("sqlite://")
    Base.metadata.create_all(maschine)
    s = sessionmaker(bind=maschine)()
    yield s
    s.close()


@pytest.fixture()
def welt(sitzung):
    anwendung = Anwendung(schluessel="hermes-pia", bezeichnung="HERMES PIA")
    sitzung.add(anwendung)
    sitzung.flush()
    a = Mandant(anwendung_id=anwendung.id, externe_id="42", bezeichnung="Amt A")
    b = Mandant(anwendung_id=anwendung.id, externe_id="43", bezeichnung="Amt B")
    sitzung.add_all([a, b])
    sitzung.flush()
    return anwendung, a, b


def test_freigabe_bei_a_wirkt_nicht_bei_b(sitzung, welt):
    """Beweist: Eine Freigabe bei Mandant A wirkt bei Mandant B nicht."""
    anwendung, a, b = welt
    sitzung.add(
        Listeneintrag(
            bereich=listen.BEREICH_MANDANT,
            anwendung_id=anwendung.id,
            mandant_id=a.id,
            art=listen.ART_FREIGABE,
            muster="Vogt",
            kategorie="person_name",
            begruendung="Systemname der Fachanwendung",
        )
    )
    sitzung.flush()

    bei_a = listen.lade(sitzung, Listeneintrag, anwendung.id, a.id)
    bei_b = listen.lade(sitzung, Listeneintrag, anwendung.id, b.id)

    assert bei_a.entscheid("Vogt", "person_name") == listen.ART_FREIGABE
    assert bei_b.entscheid("Vogt", "person_name") is None


def test_betriebsliste_wirkt_bei_allen_mandanten(sitzung, welt):
    """Beweist: Die kuratierte Betriebsliste gilt mandantenuebergreifend -
    aber nur fuer Freigaben, die der Betreiber selbst gepflegt hat."""
    anwendung, a, b = welt
    sitzung.add(
        Listeneintrag(
            bereich=listen.BEREICH_BETRIEB,
            art=listen.ART_FREIGABE,
            muster="SharePoint",
            kategorie="person_name",
            urheber="betrieb",
        )
    )
    sitzung.flush()
    for m in (a, b):
        aufgeloest = listen.lade(sitzung, Listeneintrag, anwendung.id, m.id)
        assert aufgeloest.entscheid("SharePoint", "person_name") == listen.ART_FREIGABE


def test_sperre_oberhalb_der_mandantenebene_ist_unmoeglich():
    """Beweist: Eine Sperre laesst sich nicht im Bereich betrieb oder anwendung
    ablegen - Nutzerentscheide steigen nie ueber den eigenen Mandanten auf."""
    for bereich in (listen.BEREICH_BETRIEB, listen.BEREICH_ANWENDUNG):
        with pytest.raises(listen.BereichVerletzt):
            listen.pruefe_zulaessig(bereich, listen.ART_SPERRE)
    assert listen.pruefe_zulaessig(listen.BEREICH_MANDANT, listen.ART_SPERRE)


def test_sperre_schlaegt_freigabe(sitzung, welt):
    """Beweist: Trifft eine Sperre auf eine Freigabe, gilt die Sperre - die
    vorsichtigere Aussage gewinnt."""
    anwendung, a, _ = welt
    sitzung.add_all([
        Listeneintrag(bereich=listen.BEREICH_BETRIEB, art=listen.ART_FREIGABE,
                      muster="Bern", kategorie="person_name"),
        Listeneintrag(bereich=listen.BEREICH_MANDANT, anwendung_id=anwendung.id,
                      mandant_id=a.id, art=listen.ART_SPERRE,
                      muster="Bern", kategorie="person_name"),
    ])
    sitzung.flush()
    aufgeloest = listen.lade(sitzung, Listeneintrag, anwendung.id, a.id)
    assert aufgeloest.entscheid("Bern", "person_name") == listen.ART_SPERRE


def test_widerrufener_eintrag_wirkt_nicht_mehr(sitzung, welt):
    """Beweist: Ein Listeneintrag ist rueckgaengig zu machen - Lernen bleibt
    umkehrbar (A5)."""
    anwendung, a, _ = welt
    sitzung.add(
        Listeneintrag(
            bereich=listen.BEREICH_MANDANT, anwendung_id=anwendung.id,
            mandant_id=a.id, art=listen.ART_FREIGABE, muster="Vogt",
            kategorie="person_name",
            widerrufen_am=_dt.datetime(2026, 7, 1),
        )
    )
    sitzung.flush()
    aufgeloest = listen.lade(sitzung, Listeneintrag, anwendung.id, a.id)
    assert aufgeloest.entscheid("Vogt", "person_name") is None


def test_ohne_mandant_kein_laden(sitzung, welt):
    """Beweist: Es gibt keinen Standard-Mandanten - fehlt er, wird nichts
    geladen, statt still auf einen Sammeltopf auszuweichen."""
    anwendung, _, _ = welt
    with pytest.raises(ValueError):
        listen.lade(sitzung, Listeneintrag, anwendung.id, None)
