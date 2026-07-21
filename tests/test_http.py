"""Regressionstests des vollstaendigen Wegs ueber die HTTP-Schicht.

Der Weiterleiter ist ausgetauscht: kein Netzzugriff, aber derselbe Ablauf.
Er merkt sich, WAS hinausgegangen waere - daran laesst sich beweisen, dass bei
einem blockierten Aufruf tatsaechlich nichts das Haus verlaesst.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.models import Anbieterschluessel, Anwendung, Base, Nummernmuster, Vorgang
from app.tresor import Tresor
from app.web import erzeuge_app

LEXIKON = {"Buergi", "Steiner", "Vogt"}

KOPF = {
    "X-Pseudo-Anwendung": "hermes-pia",
    "X-Pseudo-Mandant": "42",
    "X-Pseudo-Projekt": "P-2026-01",
}


class Postfach:
    """Steht fuer den Anbieter im Ausland. Haelt fest, was hinausging."""

    def __init__(self):
        self.gesendet = []
        self.antwort = {
            "type": "message",
            "content": [{"type": "text", "text": "Danke, verstanden."}],
        }

    def __call__(self, adapter, pfad, rumpf, schluessel):
        self.gesendet.append({"anbieter": adapter.name, "pfad": pfad, "rumpf": rumpf})
        if adapter.name == "voyage":
            return 200, {"data": [{"embedding": [0.1, 0.2]}]}
        return 200, self.antwort

    @property
    def gesendeter_text(self):
        import json
        return json.dumps(self.gesendet, ensure_ascii=False)


@pytest.fixture()
def welt():
    maschine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(maschine)
    fabrik = sessionmaker(bind=maschine, future=True)
    tresor = Tresor(Tresor.neuer_schluessel())

    s = fabrik()
    anwendung = Anwendung(schluessel="hermes-pia", bezeichnung="HERMES PIA")
    s.add(anwendung)
    s.flush()
    for anbieter in ("anthropic", "voyage"):
        s.add(Anbieterschluessel(
            anwendung_id=anwendung.id, anbieter=anbieter,
            chiffre=tresor.verschluessle("sk-test-%s" % anbieter),
        ))
    s.commit()

    postfach = Postfach()
    app = erzeuge_app(
        config=Config("develop"), sitzungsfabrik=fabrik, weiterleiter=postfach,
        tresor=tresor, namenslexikon=LEXIKON,
    )
    app.config["TESTING"] = True
    return app, app.test_client(), postfach, fabrik, tresor


def test_health_weist_die_luecke_aus(welt):
    """Beweist: Der Dienst weist seine Erkennungsluecken offen aus - Stufe C,
    Lexikongroessen und die fehlende Wortliste."""
    _, klient, _, _, _ = welt
    d = klient.get("/pseudo/v1/health").get_json()
    assert d["umgebung"] == "develop"
    assert d["stufe_c_aktiv"] is False
    assert d["lexikon"]["nachnamen"] == len(LEXIKON)
    assert d["wortliste_fehlt"] is True


def test_blockierter_aufruf_verlaesst_das_haus_nicht(welt):
    """Beweist: Bei einem blockierten Aufruf geht NICHTS an den Anbieter."""
    _, klient, postfach, _, _ = welt
    antwort = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]},
    )
    assert antwort.status_code == 409
    assert postfach.gesendet == []


def test_409_nennt_stelle_kategorie_und_grund(welt):
    """Beweist: Die 409-Antwort ist maschinenlesbar begruendet (A3)."""
    _, klient, _, _, _ = welt
    d = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]},
    ).get_json()

    assert d["error"]["type"] == "pseudonymisierung_blockiert"
    befund = d["error"]["pseudo"]["befunde"][0]
    assert befund["kategorie"] == "person_name"
    assert befund["band"] == "unsicher"
    assert befund["treffer"] == "Vogt"
    assert befund["ort"]["feld"] == "messages[0].content"
    assert befund["grund"]
    assert befund["befund_id"].startswith("bf_")


def test_entscheid_freigeben_laesst_originalaufruf_durch(welt):
    """Beweist: Nach 'Fehlalarm' laeuft der UNVERAENDERTE Originalaufruf durch
    und der Text ist unversehrt beim Anbieter (A9)."""
    _, klient, postfach, _, _ = welt
    original = {"model": "claude-opus-4-8",
                "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]}

    erst = klient.post("/anthropic/v1/messages", headers=KOPF, json=original)
    befund_id = erst.get_json()["error"]["pseudo"]["befunde"][0]["befund_id"]

    quittung = klient.post(
        "/pseudo/v1/befunde/%s/entscheid" % befund_id,
        json={"entscheid": "freigeben", "muster": "Vogt",
              "begruendung": "Systemname der Fachanwendung", "urheber": "kaspar"},
    )
    assert quittung.status_code == 200
    assert quittung.get_json()["geltungsbereich"] == "mandant"

    zweit = klient.post("/anthropic/v1/messages", headers=KOPF, json=original)
    assert zweit.status_code == 200
    assert postfach.gesendet[0]["rumpf"]["messages"][0]["content"] == \
        "Wir sprachen mit Vogt."


def test_entscheid_ersetzen_fuehrt_zur_ersetzung(welt):
    """Beweist: Nach 'echter Personenbezug' geht der Name beim naechsten Mal
    als Platzhalter hinaus - der Nutzerentscheid wirkt, ohne Nachtrainieren."""
    _, klient, postfach, _, _ = welt
    original = {"model": "claude-opus-4-8",
                "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]}

    erst = klient.post("/anthropic/v1/messages", headers=KOPF, json=original)
    befund_id = erst.get_json()["error"]["pseudo"]["befunde"][0]["befund_id"]

    klient.post("/pseudo/v1/befunde/%s/entscheid" % befund_id,
                json={"entscheid": "ersetzen", "muster": "Vogt", "urheber": "kaspar"})

    zweit = klient.post("/anthropic/v1/messages", headers=KOPF, json=original)
    assert zweit.status_code == 200
    hinaus = postfach.gesendet[0]["rumpf"]["messages"][0]["content"]
    assert "Vogt" not in hinaus
    assert "{{P1}}" in hinaus


def test_entscheid_ohne_passenden_klartext_wird_abgewiesen(welt):
    """Beweist: Einen Befund kann nur entscheiden, wer den Klartext kennt - der
    Dienst speichert ihn nicht, sondern prueft ihn gegen den HMAC."""
    _, klient, _, _, _ = welt
    erst = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]},
    )
    befund_id = erst.get_json()["error"]["pseudo"]["befunde"][0]["befund_id"]
    antwort = klient.post("/pseudo/v1/befunde/%s/entscheid" % befund_id,
                          json={"entscheid": "freigeben", "muster": "Steiner"})
    assert antwort.status_code == 400
    assert antwort.get_json()["error"]["type"] == "muster_passt_nicht"


def test_rundweg_ersetzt_und_setzt_zurueck(welt):
    """Beweist: Sicher erkannter Klartext geht als Platzhalter hinaus und die
    Anwendung bekommt Klartext zurueck."""
    _, klient, postfach, _, _ = welt
    postfach.antwort = {
        "type": "message",
        "content": [{"type": "text", "text": "Ich informiere {{P1}} umgehend."}],
    }
    antwort = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Zustaendig ist Herr Buergi."}]},
    )
    assert antwort.status_code == 200
    assert "Buergi" not in postfach.gesendet[0]["rumpf"]["messages"][0]["content"]
    assert antwort.get_json()["content"][0]["text"] == "Ich informiere Buergi umgehend."


def test_embedding_weg_wird_ebenso_bereinigt(welt):
    """Beweist: Auch der Embedding-Weg wird bereinigt - der Weg, der gern
    uebersehen wird."""
    _, klient, postfach, _, _ = welt
    antwort = klient.post(
        "/voyage/v1/embeddings", headers=KOPF,
        json={"model": "voyage-3",
              "input": ["Zustaendig ist Herr Buergi.", "harmloser Text"]},
    )
    assert antwort.status_code == 200
    hinaus = postfach.gesendet[0]["rumpf"]["input"]
    assert "Buergi" not in hinaus[0]
    assert "{{P1}}" in hinaus[0]
    assert hinaus[1] == "harmloser Text"


def test_streaming_wird_ehrlich_abgewiesen(welt):
    """Beweist: Streaming wird klar abgewiesen statt halb unterstuetzt - ein
    halb funktionierendes Streaming waere der Fehler, den niemand bemerkt."""
    _, klient, postfach, _, _ = welt
    antwort = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8", "stream": True,
              "messages": [{"role": "user", "content": "Hallo"}]},
    )
    assert antwort.status_code == 501
    assert antwort.get_json()["error"]["type"] == "streaming_nicht_unterstuetzt"
    assert postfach.gesendet == []


def test_fehlender_mandant_wird_abgewiesen(welt):
    """Beweist: Es gibt keinen Standard-Mandanten - fehlt die Kopfzeile, wird
    der Aufruf abgewiesen statt in einen Sammeltopf umgeleitet."""
    _, klient, postfach, _, _ = welt
    kopf = dict(KOPF)
    del kopf["X-Pseudo-Mandant"]
    antwort = klient.post("/anthropic/v1/messages", headers=kopf,
                          json={"model": "x", "messages": []})
    assert antwort.status_code == 400
    assert antwort.get_json()["error"]["type"] == "kontext_fehlt"
    assert postfach.gesendet == []


def test_freigabe_wirkt_nicht_beim_anderen_mandanten(welt):
    """Beweist: Ueber die HTTP-Schicht bleibt die Mandantentrennung erhalten -
    eine Freigabe bei Mandant 42 wirkt bei Mandant 43 nicht (A5)."""
    _, klient, _, _, _ = welt
    rumpf = {"model": "claude-opus-4-8",
             "messages": [{"role": "user", "content": "Wir sprachen mit Vogt."}]}

    erst = klient.post("/anthropic/v1/messages", headers=KOPF, json=rumpf)
    befund_id = erst.get_json()["error"]["pseudo"]["befunde"][0]["befund_id"]
    klient.post("/pseudo/v1/befunde/%s/entscheid" % befund_id,
                json={"entscheid": "freigeben", "muster": "Vogt"})

    anderer = dict(KOPF, **{"X-Pseudo-Mandant": "43"})
    assert klient.post("/anthropic/v1/messages", headers=anderer, json=rumpf) \
        .status_code == 409
    assert klient.post("/anthropic/v1/messages", headers=KOPF, json=rumpf) \
        .status_code == 200


def test_kein_klartext_im_protokoll(welt):
    """Beweist: Das Vorgangsprotokoll enthaelt weder Klartext noch Prompt -
    der Dienst legt keine zweite Halde an."""
    _, klient, _, fabrik, _ = welt
    klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Zustaendig ist Herr Buergi."}]},
    )
    s = fabrik()
    spalten = []
    for v in s.query(Vorgang).all():
        spalten.extend(str(getattr(v, c.name)) for c in Vorgang.__table__.columns)
    s.close()
    assert spalten
    assert not any("Buergi" in w for w in spalten)


def test_zuordnung_liegt_verschluesselt(welt):
    """Beweist: In der Zuordnungstabelle steht der Klarname in KEINER Spalte im
    Klartext - auch nicht kleingeschrieben in einer Suchspalte."""
    _, klient, _, fabrik, tresor = welt
    klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Zustaendig ist Herr Buergi."}]},
    )
    from app.models import Zuordnung
    s = fabrik()
    z = s.query(Zuordnung).one()
    spalten = [str(getattr(z, c.name)) for c in Zuordnung.__table__.columns]
    assert not any("buergi" in w.casefold() for w in spalten)
    assert tresor.entschluessle(z.klartext_chiffre) == "Buergi"
    s.close()


def test_ohne_anbieterschluessel_kein_aufruf(welt):
    """Beweist: Ohne hinterlegten Anbieterschluessel laeuft kein Aufruf - die
    Anwendungen koennen den Dienst nicht umgehen."""
    _, klient, postfach, fabrik, _ = welt
    s = fabrik()
    for k in s.query(Anbieterschluessel).all():
        s.delete(k)
    s.commit()
    s.close()

    antwort = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Hallo"}]},
    )
    assert antwort.status_code == 503
    assert antwort.get_json()["error"]["type"] == "kein_anbieterschluessel"
    assert postfach.gesendet == []


def test_mandantenmuster_wird_angewandt(welt):
    """Beweist: Ein mandantenspezifisches Geschaeftsnummern-Muster greift und
    die Nummer geht nicht hinaus."""
    app, klient, postfach, fabrik, _ = welt
    s = fabrik()
    anwendung = s.query(Anwendung).one()
    # Mandant 42 anlegen, indem ein erster Aufruf durchlaeuft.
    klient.post("/anthropic/v1/messages", headers=KOPF,
                json={"model": "x", "messages": [{"role": "user", "content": "Hallo"}]})
    from app.models import Mandant
    mandant = s.query(Mandant).filter(Mandant.externe_id == "42").one()
    s.add(Nummernmuster(anwendung_id=anwendung.id, mandant_id=mandant.id,
                        kategorie="geschaeftsnummer", regex=r"\bGS-\d{4}/\d{3}\b"))
    s.commit()
    s.close()

    postfach.gesendet.clear()
    antwort = klient.post(
        "/anthropic/v1/messages", headers=KOPF,
        json={"model": "claude-opus-4-8",
              "messages": [{"role": "user", "content": "Siehe GS-2026/017 im Dossier."}]},
    )
    assert antwort.status_code == 200
    assert "GS-2026/017" not in postfach.gesendet[0]["rumpf"]["messages"][0]["content"]
