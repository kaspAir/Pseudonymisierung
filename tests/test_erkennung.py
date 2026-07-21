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


def test_satzanfang_allein_blockiert_nicht():
    """Beweist: Am Satzanfang ist Grossschreibung erzwungen und taugt nicht als
    Namenssignal - "Der", "Die", "Das" sind zwar Schweizer Nachnamen, duerfen
    aber nicht jeden Satz blockieren."""
    lexikon = {"Der", "Die", "Das"}
    befunde, _ = _e(nachnamen=lexikon).pruefe(
        "Der Auftrag ist erteilt. Die Studie folgt. Das Vorgehen steht fest."
    )
    assert befunde == []


def test_nach_doppelpunkt_zaehlt_grossschreibung_als_signal():
    """Beweist: Nach einem Doppelpunkt geht es im Deutschen klein weiter - ein
    grosses Wort ist dort also ein Signal. Genau dort stehen in
    Projektdokumenten die Namen."""
    befunde, _ = _e(nachnamen={"Steiner"}).pruefe("Projektleitung: Steiner")
    assert [b.treffer for b in befunde] == ["Steiner"]
    assert befunde[0].band == erkennung.BAND_UNSICHER


def test_weicher_zeilenumbruch_ist_kein_satzanfang():
    """Beweist: Ein Umbruch mitten im Satz zaehlt nicht als Satzanfang - sonst
    verloere umbrochener Text halbe Saetze."""
    befunde, _ = _e(nachnamen={"Steiner"}).pruefe(
        "Die Leitung liegt bei\nSteiner und dem Team."
    )
    assert [b.treffer for b in befunde] == ["Steiner"]


def test_absatzwechsel_zaehlt_als_satzanfang():
    """Beweist: Eine Leerzeile trennt Absaetze - dort ist Grossschreibung
    wieder erzwungen."""
    befunde, _ = _e(nachnamen={"Der"}).pruefe("Erster Absatz.\n\nDer zweite folgt.")
    assert befunde == []


def test_vorname_und_nachname_nebeneinander_sind_sicher():
    """Beweist: Zwei benachbarte Lexikontreffer in der Rollenfolge Vorname +
    Nachname sind das staerkste Signal ohne Anrede - sie blockieren nicht,
    sondern werden ersetzt."""
    befunde, _ = _e(vornamen={"Marc"}, nachnamen={"Buergi"}).pruefe(
        "Die Leitung liegt bei Marc Buergi und dem Team."
    )
    assert [b.treffer for b in befunde] == ["Marc Buergi"]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_wortliste_verhindert_fehlalarme_auf_alltagswoertern():
    """Beweist: Ein Wort im Alltagswortschatz erzeugt keinen Befund, auch wenn
    es als Nachname vorkommt - "Kosten", "Recht" und "Bau" sind in der Schweiz
    Nachnamen und wuerden sonst jedes HERMES-Dokument blockieren."""
    text = "Der Bericht nennt die Kosten, das Recht und den Bau der Anlage."
    ohne, _ = _e(nachnamen={"Kosten", "Recht", "Bau"}).pruefe(text)
    mit, _ = _e(nachnamen={"Kosten", "Recht", "Bau"},
                wortliste={"Kosten", "Recht", "Bau"}).pruefe(text)
    assert len(ohne) == 3
    assert mit == []


def test_datum_und_version_sind_keine_telefonnummer():
    """Beweist: Versions- und Datumsangaben aus Dokumentkoepfen werden NICHT
    als Telefonnummer erkannt. Solche Treffer laegen im Band 'sicher' und
    wuerden still ersetzt - jedes Datum im Dokument wuerde zum Platzhalter."""
    for harmlos in ("Version 1.0 01.02.2024", "Stand 31.12.2023 14.30",
                    "V0.14 vom 7.11.2019", "Betrag 1 234 567.80"):
        befunde, _ = _e().pruefe(harmlos)
        assert befunde == [], "Fehlalarm bei %r" % harmlos


def test_echte_telefonnummern_werden_erkannt():
    """Beweist: Die strengere Fassung erkennt die ueblichen Schreibweisen
    weiterhin."""
    for nummer in ("031 633 11 22", "+41 31 633 11 22", "+41 79 123 45 67",
                   "0041 31 633 11 22", "079/123 45 67"):
        befunde, _ = _e().pruefe("Erreichbar unter %s heute." % nummer)
        assert [b.kategorie for b in befunde] == [erkennung.K_PERSON_KONTAKT], \
            "nicht erkannt: %r" % nummer


def test_funktionsanker_meldet_keine_organisation():
    """Beweist: Nach einer Rollenbezeichnung kann eine Organisation oder ein
    Ort stehen - "Projektleiter Informatik" ist kein Personenname, "Frau Basel"
    dagegen schon."""
    org, _ = _e(orte={"Bern"}, wortliste={"Informatik"}).pruefe(
        "Projektleiter Informatik meldet. Zustaendig ist Bern."
    )
    assert org == []
    person, _ = _e(orte={"Basel"}).pruefe("Zustaendig ist Frau Basel.")
    assert [b.treffer for b in person] == ["Basel"]


def test_normaler_text_gilt_nicht_als_diktat():
    """Beweist: Deutscher Fliesstext wird nicht faelschlich als Text ohne
    Grossschreibung eingestuft - sonst griffen dort die schwaecheren Regeln."""
    assert not erkennung.ohne_grossschreibung(
        "Der Steuerungsausschuss hat den Auftrag genehmigt. Die Studie zeigt, "
        "dass der Nutzen die Kosten uebersteigt."
    )
    assert erkennung.ohne_grossschreibung(
        "der steuerungsausschuss hat den auftrag genehmigt und die studie "
        "zeigt dass der nutzen die kosten uebersteigt"
    )


def test_ohne_grossschreibung_nur_ein_wort_nach_der_anrede():
    """Beweist: Ohne Grossschreibung wird nach der Anrede nur EIN Wort als
    Name genommen - sonst wuerde aus "herr buergi moechte" der Name
    "buergi moechte"."""
    befunde, _ = _e(nachnamen={"buergi"}).pruefe(
        "unser chef, herr buergi moechte dass wir die dienste migrieren und "
        "das projekt bald starten koennen"
    )
    assert [b.treffer for b in befunde] == ["buergi"]


def test_anredewort_blockiert_nicht_als_eigener_befund():
    """Beweist: Das Anredewort selbst erzeugt keinen Befund - "Herr" und "Frau"
    stehen ebenfalls in der BfS-Nachnamenliste und wuerden sonst jeden Satz mit
    Anrede blockieren."""
    befunde, _ = _e(nachnamen={"Herr", "Frau", "Buergi"}).pruefe(
        "Zustaendig ist Herr Buergi."
    )
    assert [b.treffer for b in befunde] == ["Buergi"]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_ortschaft_allein_blockiert_nicht():
    """Beweist: Eine Schweizer Ortschaft blockiert nicht, auch wenn sie
    zugleich ein Nachname ist - 359 der 4421 Ortsnamen sind das (Basel, Baden,
    Arbon, Arosa, Bellinzona, Cham)."""
    text = "Die Arbeiten in Basel und Arbon laufen; Baden folgt spaeter."
    ohne, _ = _e(nachnamen={"Basel", "Arbon", "Baden"}).pruefe(text)
    mit, _ = _e(nachnamen={"Basel", "Arbon", "Baden"},
                orte={"Basel", "Arbon", "Baden"}).pruefe(text)
    assert len(ohne) == 3
    assert mit == []


def test_ortschaft_mit_anrede_wird_trotzdem_erkannt():
    """Beweist: Die Ortschaftenliste oeffnet kein Loch - mit Anrede wird der
    Name weiterhin erkannt und ersetzt."""
    befunde, _ = _e(nachnamen={"Basel"}, orte={"Basel"}).pruefe(
        "Zustaendig ist Frau Basel."
    )
    assert [b.treffer for b in befunde] == ["Basel"]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_ortschaft_als_nachname_nach_vorname_wird_erkannt():
    """Beweist: Auch in der Folge Vorname + Nachname wird ein Name erkannt, der
    zugleich Ortschaft ist."""
    befunde, _ = _e(vornamen={"Anna"}, nachnamen={"Basel"}, orte={"Basel"}).pruefe(
        "Die Leitung liegt bei Anna Basel."
    )
    assert [b.treffer for b in befunde] == ["Anna Basel"]
    assert befunde[0].band == erkennung.BAND_SICHER


def test_adresse_wird_mit_plz_und_ort_als_einheit_erkannt():
    """Beweist: Eine Adresse wird samt PLZ und Ortschaft als EINE Fundstelle
    erfasst - sonst bliebe nach der Ersetzung "{{P1}}, 3011 Bern" stehen."""
    text = "Wohnhaft an der Musterstrasse 5, 3011 Bern."
    ohne, _ = _e().pruefe(text)
    mit, _ = _e(orte={"Bern"}).pruefe(text)
    assert ohne[0].treffer == "Musterstrasse 5"
    assert mit[0].treffer == "Musterstrasse 5, 3011 Bern"
    assert mit[0].kategorie == erkennung.K_ADRESSE


def test_unbekannte_ortschaft_erweitert_die_adresse_nicht():
    """Beweist: Erweitert wird nur mit einer Ortschaft aus dem amtlichen
    Verzeichnis - es wird nichts geraten."""
    befunde, _ = _e(orte={"Bern"}).pruefe("Musterstrasse 5, 9999 Irgendwo.")
    assert befunde[0].treffer == "Musterstrasse 5"


def test_bestandsplatzhalter_erzeugt_keinen_befund():
    """Beweist: Bereits pseudonymisierter Bestand wird durchgereicht und nicht
    als Fundstelle gemeldet."""
    befunde, bestand = _e(namenslexikon={"Buergi"}).pruefe(
        "Im Korpus steht [Person_099] als Projektleiter."
    )
    assert bestand
    assert not befunde
