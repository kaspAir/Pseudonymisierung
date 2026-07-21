"""Ablauf eines Aufrufs (KONZEPT 7).

    Erkennung -> (blockieren | ersetzen) -> Anbieter -> Rueckersetzung
    -> Leckpruefung -> Auslieferung

Der Dienst speichert den blockierten Text NICHT. Die aufrufende Anwendung haelt
ihn und wiederholt den unveraenderten Originalaufruf, sobald der Entscheid
gefallen ist (A9). Andernfalls legte der Dienst ausgerechnet von den heikelsten
Texten eine Zwischenhalde an.
"""
import time
import uuid

from . import adapter as adapter_paket
from .kern import abschaltung, erkennung, listen as listen_modul
from .kern.ersetzung import ersetze
from .kern.leckpruefung import Leck, pruefe as pruefe_leck
from .kern.rueckersetzung import Rueckersetzer
from .kern.speicher import DatenbankSpeicher
from .models import (
    Anbieterschluessel, Ausnahme, Befund, Listeneintrag, Nummernmuster, Vorgang,
)


class DienstFehler(Exception):
    def __init__(self, status, typ, meldung, zusatz=None):
        super().__init__(meldung)
        self.status = status
        self.typ = typ
        self.meldung = meldung
        self.zusatz = zusatz or {}

    def als_rumpf(self):
        fehler = {"type": self.typ, "message": self.meldung}
        fehler.update(self.zusatz)
        return {"type": "error", "error": fehler}


def _id(praefix):
    return "%s_%s" % (praefix, uuid.uuid4().hex[:22])


class Dienst:
    """weiterleiter: aufrufbar (anbieter, pfad, rumpf, schluessel) -> (status, dict).

    Als Abhaengigkeit hereingereicht, damit die Regressionstests den ganzen
    Ablauf ohne Netzzugriff belegen koennen.
    """

    def __init__(self, sitzung, config, tresor, weiterleiter, namenslexikon=None):
        self._s = sitzung
        self._c = config
        self._t = tresor
        self._weiterleiten = weiterleiter
        self._lexikon = set(namenslexikon or ())

    # -- oeffentlich ----------------------------------------------------

    def verarbeite(self, anbieter_name, pfad, rumpf, kontext):
        begonnen = time.time()
        adapter = adapter_paket.hole(anbieter_name)
        if adapter is None:
            raise DienstFehler(404, "not_found", "Unbekannter Anbieter: %s" % anbieter_name)

        weg = adapter.weg(pfad)
        if weg is None:
            raise DienstFehler(404, "not_found", "Unbekannter Pfad: %s" % pfad)

        if rumpf.get("stream"):
            # Ehrlich abweisen statt halb koennen. Die Rueckersetzung ist als
            # Stromautomat gebaut, aber der Weiterleitungsweg fuer SSE ist noch
            # nicht belegt - und ein halb funktionierendes Streaming waere
            # genau die Art Fehler, die niemand bemerkt.
            raise DienstFehler(
                501, "streaming_nicht_unterstuetzt",
                "Streaming ist in dieser Fassung nicht unterstuetzt.",
            )

        abgeschaltet = self._ist_abgeschaltet(kontext)
        speicher = DatenbankSpeicher(
            self._s, self._t, kontext["anwendung"].id, kontext["mandant"].id,
            kontext["projekt"].id,
        )

        if abgeschaltet:
            # Auch abgeschaltet laeuft der Aufruf durch den Dienst und wird
            # protokolliert (A6).
            antwort = self._hinaus(adapter, pfad, rumpf, kontext)
            self._protokolliere(kontext, weg, "abgeschaltet", 0, 0, rumpf, begonnen)
            return antwort, {"X-Pseudo-Status": "abgeschaltet"}

        befunde = self._erkenne(adapter, rumpf, kontext)

        if erkennung.blockiert(befunde):
            vorgang_id = self._protokolliere(
                kontext, weg, "blockiert", 0, len(befunde), rumpf, begonnen
            )
            raise self._blockiert_fehler(vorgang_id, befunde, adapter, rumpf)

        bereinigt, verwendet = self._ersetze_alles(adapter, rumpf, befunde, speicher)
        antwort = self._hinaus(adapter, pfad, bereinigt, kontext)
        antwort = self._zurueck(adapter, antwort, verwendet, speicher)

        self._protokolliere(
            kontext, weg, "durchgelassen", len(verwendet), len(befunde), rumpf, begonnen
        )
        return antwort, {"X-Pseudo-Status": "aktiv"}

    # -- Erkennung ------------------------------------------------------

    def _erkenner(self, kontext):
        aufgeloest = listen_modul.lade(
            self._s, Listeneintrag, kontext["anwendung"].id, kontext["mandant"].id
        )
        muster = [
            (m.regex, m.kategorie, "muster_mandant")
            for m in self._s.query(Nummernmuster)
            .filter(
                Nummernmuster.anwendung_id == kontext["anwendung"].id,
                Nummernmuster.mandant_id == kontext["mandant"].id,
                Nummernmuster.widerrufen_am.is_(None),
            )
            .all()
        ]
        return erkennung.Erkenner(
            listen=aufgeloest, zusatzmuster=muster, namenslexikon=self._lexikon
        )

    def _erkenne(self, adapter, rumpf, kontext):
        erkenner = self._erkenner(kontext)
        alle = []
        for feld, text in adapter.texte(rumpf):
            befunde, _ = erkenner.pruefe(text, feld=feld)
            alle.extend(befunde)
        return alle

    def _ersetze_alles(self, adapter, rumpf, befunde, speicher):
        nach_feld = {}
        for b in befunde:
            nach_feld.setdefault(b.feld, []).append(b)

        neue_texte = {}
        verwendet = {}
        for feld, text in adapter.texte(rumpf):
            if feld not in nach_feld:
                continue
            neu, teil = ersetze(text, nach_feld[feld], speicher)
            neue_texte[feld] = neu
            verwendet.update(teil)
        return adapter.setze_texte(rumpf, neue_texte), verwendet

    # -- Anbieter -------------------------------------------------------

    def _schluessel(self, anbieter, kontext):
        q = self._s.query(Anbieterschluessel).filter(
            Anbieterschluessel.anwendung_id == kontext["anwendung"].id,
            Anbieterschluessel.anbieter == anbieter,
            Anbieterschluessel.widerrufen_am.is_(None),
        )
        eigener = q.filter(
            Anbieterschluessel.mandant_id == kontext["mandant"].id
        ).one_or_none()
        gewaehlt = eigener or q.filter(
            Anbieterschluessel.mandant_id.is_(None)
        ).one_or_none()
        if gewaehlt is None:
            raise DienstFehler(
                503, "kein_anbieterschluessel",
                "Fuer %s ist kein Schluessel hinterlegt." % anbieter,
            )
        return self._t.entschluessle(gewaehlt.chiffre)

    def _hinaus(self, adapter, pfad, rumpf, kontext):
        schluessel = self._schluessel(adapter.name, kontext)
        status, antwort = self._weiterleiten(adapter, pfad, rumpf, schluessel)
        if status >= 400:
            raise DienstFehler(
                status, "anbieter_fehler",
                "Der Anbieter hat den Aufruf abgelehnt.",
                {"anbieter_antwort": antwort},
            )
        return antwort

    # -- Rueckweg -------------------------------------------------------

    def _zurueck(self, adapter, antwort, verwendet, speicher):
        texte = adapter.antwort_texte(antwort)
        if not texte:
            return antwort          # Embeddings: Vektoren, kein Text

        gesendet = set(verwendet.values())
        nie_gesendet = [w for w in speicher.alle_klartexte() if w not in gesendet]

        neu = {}
        for feld, text in texte:
            r = Rueckersetzer(verwendet)
            fertig = r.schreibe(text) + r.schluss()
            try:
                pruefe_leck(fertig, r, nie_gesendet)
            except Leck as leck:
                raise DienstFehler(
                    502, "rueckersetzung_unvollstaendig",
                    "Die Antwort wurde nicht ausgeliefert: %s" % leck.hinweis,
                    {"pseudo": {"art": leck.art, "feld": feld}},
                )
            neu[feld] = fertig
        return adapter.setze_antwort_texte(antwort, neu)

    # -- Blockieren -----------------------------------------------------

    def _blockiert_fehler(self, vorgang_id, befunde, adapter, rumpf):
        texte = dict(adapter.texte(rumpf))
        eintraege = []
        for b in befunde:
            if b.band != erkennung.BAND_UNSICHER:
                continue
            befund_id = _id("bf")
            self._s.add(
                Befund(
                    id=befund_id,
                    vorgang_id=vorgang_id,
                    kategorie=b.kategorie,
                    band=b.band,
                    sicherheit=b.sicherheit,
                    treffer_hash=self._t.hash(b.treffer),
                    grund=b.grund,
                )
            )
            eintraege.append(b.als_dict(befund_id, _auszug(texte.get(b.feld, ""), b)))
        self._s.flush()

        return DienstFehler(
            409, "pseudonymisierung_blockiert",
            "%d Fundstelle(n) erfordern eine Entscheidung." % len(eintraege),
            {"pseudo": {"vorgang_id": vorgang_id, "schema": "1.0", "befunde": eintraege}},
        )

    # -- Protokoll ------------------------------------------------------

    def _protokolliere(self, kontext, weg, entscheid, ersetzungen, befunde, rumpf, seit):
        vorgang_id = _id("vg")
        self._s.add(
            Vorgang(
                id=vorgang_id,
                anwendung_id=kontext["anwendung"].id,
                mandant_id=kontext["mandant"].id,
                projekt_id=kontext["projekt"].id,
                weg=weg,
                entscheid=entscheid,
                anzahl_ersetzungen=ersetzungen,
                anzahl_befunde=befunde,
                modell=rumpf.get("model"),
                dauer_ms=int((time.time() - seit) * 1000),
            )
        )
        self._s.flush()
        return vorgang_id

    def _ist_abgeschaltet(self, kontext):
        if not abschaltung.darf_beantragt_werden(self._c.umgebung):
            return False
        a = (
            self._s.query(Ausnahme)
            .filter(
                Ausnahme.anwendung_id == kontext["anwendung"].id,
                Ausnahme.widerrufen_am.is_(None),
            )
            .order_by(Ausnahme.gueltig_bis.desc())
            .first()
        )
        return abschaltung.ist_aktiv(a, self._c.umgebung)


def _auszug(text, befund, rand=40):
    """Kurzer Textausschnitt um die Fundstelle, damit der Nutzer sie einordnen kann."""
    if not text:
        return befund.treffer
    a = max(0, befund.von - rand)
    b = min(len(text), befund.bis + rand)
    stueck = text[a:b]
    return ("…" if a > 0 else "") + stueck + ("…" if b < len(text) else "")
