"""Regressionstests der Erkennung (Stufe A und B)."""
from app.kern import erkennung


def _e(**kw):
    return erkennung.Erkenner(**kw)


def test_ahv_nummer_nur_mit_gueltiger_pruefziffer():
    """Beweist: Die AHV-Nummer wird ueber ihre Pruefziffer erkannt, nicht ueber
    das blosse Zahlenmuster - eine erfundene Nummer erzeugt keinen Befund."""
    echt = "756.9217.0769.85"          # Pruefziffer stimmt
    falsch = "756.9217.0769.84"        # dieselbe Nummer, falsche Pruefziffer
    assert erkennung._ahv_gueltig(echt)
    assert not erkennung._ahv_gueltig(falsch)

    befunde, _ = _e().pruefe("AHV %s" % echt)
    assert [b.kategorie for b in befunde] == [erkennung.K_AHV]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_iban_wird_ueber_mod97_geprueft():
    """Beweist: Eine IBAN wird nur bei gueltiger Mod-97-Pruefsumme erkannt."""
    assert erkennung._iban_gueltig("CH93 0076 2011 6238 5295 7")
    assert not erkennung._iban_gueltig("CH93 0076 2011 6238 5295 8")


def test_organisationsnamen_haben_keine_kategorie():
    """Beweist: Organisationen werden bewusst nicht ersetzt - es gibt gar keine
    Kategorie dafuer, nicht bloss eine abgeschaltete Regel."""
    kategorien = {
        v for k, v in vars(erkennung).items()
        if k.startswith("K_") and isinstance(v, str)
    }
    assert not any("org" in k for k in kategorien)


def test_name_mit_anrede_ist_sicher_ohne_anrede_unsicher():
    """Beweist: Der Kontextanker hebt die Sicherheit - derselbe Name ist mit
    Anrede sicher und ohne Anrede nur unsicher."""
    mit, _ = _e(namenslexikon={"Buergi"}).pruefe("Zustaendig ist Herr Buergi.")
    ohne, _ = _e(namenslexikon={"Buergi"}).pruefe("Das hat Buergi entschieden.")
    assert mit[0].band == erkennung.BAND_SICHER
    assert ohne[0].band == erkennung.BAND_UNSICHER


def test_mandantenspezifisches_nummernmuster():
    """Beweist: Geschaeftsnummern sind pro Mandant konfigurierbar - die Formate
    der Justiz sind kantonal verschieden."""
    muster = [(r"\bGS-\d{4}/\d{3}\b", erkennung.K_GESCHAEFTSNUMMER, "muster_mandant")]
    befunde, _ = _e(zusatzmuster=muster).pruefe("Siehe GS-2026/017 im Dossier.")
    assert [b.treffer for b in befunde] == ["GS-2026/017"]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_bestandsplatzhalter_erzeugt_keinen_befund():
    """Beweist: Bereits pseudonymisierter Bestand wird durchgereicht und nicht
    als Fundstelle gemeldet."""
    befunde, bestand = _e(namenslexikon={"Buergi"}).pruefe(
        "Im Korpus steht [Person_099] als Projektleiter."
    )
    assert bestand
    assert not befunde
