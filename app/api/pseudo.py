"""Eigener Namensraum des Dienstes - ausserhalb jedes Anbieterprotokolls."""
import datetime as _dt

from flask import Blueprint, current_app, g, jsonify, request

from ..kern import abschaltung, listen as listen_modul
from ..models import Ausnahme, Befund, Listeneintrag, Vorgang

blueprint = Blueprint("pseudo", __name__)


@blueprint.get("/health")
def health():
    umgebung = current_app.extensions["pseudo"]
    lexika = umgebung["lexika"]
    return jsonify({
        "status": "bereit",
        "umgebung": umgebung["config"].umgebung,
        "version": umgebung["version"],
        "lexikon": {
            "nachnamen": len(lexika.get("nachnamen") or ()),
            "vornamen": len(lexika.get("vornamen") or ()),
            "wortliste": len(lexika.get("wortliste") or ()),
        },
        # Ohne Wortliste blockiert der Dienst auf gewoehnlichem
        # Verwaltungsdeutsch. Die Luecke wird ausgewiesen, nicht verschwiegen.
        "wortliste_fehlt": not (lexika.get("wortliste") or ()),
        "stufe_c_aktiv": bool(umgebung["config"].ner_modell),
    })


@blueprint.post("/befunde/<befund_id>/entscheid")
def entscheid(befund_id):
    """Der Nutzer entscheidet zur Fundstelle.

    Der Klartext der Fundstelle wird vom Aufrufer MITGESCHICKT und nicht beim
    Dienst nachgeschlagen - er liegt hier nie gespeichert. Zur Absicherung wird
    er gegen den gespeicherten HMAC geprueft; wer den Klartext nicht kennt,
    kann den Befund also nicht entscheiden.
    """
    umgebung = current_app.extensions["pseudo"]
    sitzung = g.sitzung
    daten = request.get_json(silent=True) or {}

    wahl = (daten.get("entscheid") or "").strip()
    muster = (daten.get("muster") or "").strip()
    if wahl not in ("ersetzen", "freigeben"):
        return _fehler("ungueltiger_entscheid",
                       "entscheid muss 'ersetzen' oder 'freigeben' sein.", 400)
    if not muster:
        return _fehler("muster_fehlt",
                       "Der Klartext der Fundstelle ist mitzuschicken.", 400)

    befund = sitzung.get(Befund, befund_id)
    if befund is None:
        return _fehler("unbekannter_befund", "Befund nicht gefunden.", 404)
    if befund.entschieden_als:
        return _fehler("bereits_entschieden", "Dieser Befund ist entschieden.", 409)

    if umgebung["tresor"].hash(muster) != befund.treffer_hash:
        return _fehler("muster_passt_nicht",
                       "Der uebergebene Klartext gehoert nicht zu diesem Befund.", 400)

    vorgang = sitzung.get(Vorgang, befund.vorgang_id)

    # "ersetzen" = das IST ein Personenbezug -> Sperre, damit die Stelle beim
    # naechsten Mal sicher (statt unsicher) erkannt und ersetzt wird.
    # "freigeben" = Fehlalarm -> Freigabe.
    art = listen_modul.ART_SPERRE if wahl == "ersetzen" else listen_modul.ART_FREIGABE
    listen_modul.pruefe_zulaessig(listen_modul.BEREICH_MANDANT, art)

    sitzung.add(
        Listeneintrag(
            bereich=listen_modul.BEREICH_MANDANT,
            anwendung_id=vorgang.anwendung_id,
            mandant_id=vorgang.mandant_id,
            art=art,
            muster=muster,
            mustertyp="woertlich",
            kategorie=befund.kategorie,
            begruendung=(daten.get("begruendung") or "").strip() or None,
            urheber=(daten.get("urheber") or "").strip() or None,
        )
    )
    befund.entschieden_als = wahl
    befund.entschieden_am = _dt.datetime.now(_dt.timezone.utc)
    befund.entschieden_durch = (daten.get("urheber") or "").strip() or None
    sitzung.commit()

    return jsonify({
        "befund_id": befund_id,
        "entscheid": wahl,
        "wirkt_ab": "sofort",
        "geltungsbereich": "mandant",
        "hinweis": "Den unveraenderten Originalaufruf wiederholen.",
    })


@blueprint.post("/ausnahme")
def ausnahme_beantragen():
    """Abschaltung zu Testzwecken (A6). In Produktion serverseitig verweigert."""
    umgebung = current_app.extensions["pseudo"]
    sitzung = g.sitzung
    daten = request.get_json(silent=True) or {}

    stunden = daten.get("stunden") or 0
    gueltig_bis = None
    if stunden:
        gueltig_bis = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=float(stunden))

    try:
        abschaltung.pruefe_antrag(
            umgebung["config"].umgebung,
            berechtigt=bool(daten.get("berechtigt")),
            begruendung=daten.get("begruendung"),
            gueltig_bis=gueltig_bis,
        )
    except abschaltung.AusnahmeVerweigert as f:
        return _fehler("ausnahme_verweigert", str(f), 403)

    from ..api.kontext import KontextFehler, loese_auf
    try:
        kontext = loese_auf(sitzung, request.headers)
    except KontextFehler as f:
        return _fehler("kontext_fehlt", f.meldung, 400)

    a = Ausnahme(
        anwendung_id=kontext["anwendung"].id,
        mandant_id=kontext["mandant"].id,
        umgebung=umgebung["config"].umgebung,
        beantragt_von=(daten.get("urheber") or "unbekannt"),
        begruendung=daten["begruendung"],
        gueltig_bis=gueltig_bis,
    )
    sitzung.add(a)
    sitzung.commit()
    return jsonify({
        "ausnahme_id": a.id,
        "umgebung": a.umgebung,
        "gueltig_bis": a.gueltig_bis.isoformat(),
        "hinweis": "Aufrufe laufen weiterhin durch den Dienst und werden protokolliert.",
    })


def _fehler(typ, meldung, status):
    return jsonify({"type": "error", "error": {"type": typ, "message": meldung}}), status
