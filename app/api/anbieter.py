"""Anbieterkompatible Routen.

Die Anwendung setzt nur ihre base_url auf http://127.0.0.1:8040/<anbieter>;
das SDK haengt /v1/messages bzw. /v1/embeddings selbst an.
"""
from flask import Blueprint, current_app, g, jsonify, request

from ..dienst import Dienst, DienstFehler
from .kontext import KontextFehler, loese_auf

blueprint = Blueprint("anbieter", __name__)


@blueprint.route("/<anbieter>/<path:rest>", methods=["POST"])
def weiterleiten(anbieter, rest):
    umgebung = current_app.extensions["pseudo"]
    sitzung = g.sitzung

    try:
        kontext = loese_auf(sitzung, request.headers)
    except KontextFehler as f:
        return jsonify({"type": "error",
                        "error": {"type": "kontext_fehlt", "message": f.meldung}}), 400

    rumpf = request.get_json(silent=True)
    if not isinstance(rumpf, dict):
        return jsonify({"type": "error",
                        "error": {"type": "invalid_request_error",
                                  "message": "JSON-Rumpf erwartet."}}), 400

    dienst = Dienst(
        sitzung=sitzung,
        config=umgebung["config"],
        tresor=umgebung["tresor"],
        weiterleiter=umgebung["weiterleiter"],
        lexika=umgebung["lexika"],
    )

    try:
        antwort, kopf = dienst.verarbeite(anbieter, "/" + rest, rumpf, kontext)
    except DienstFehler as f:
        sitzung.commit()          # Vorgang und Befunde bleiben protokolliert
        return jsonify(f.als_rumpf()), f.status

    sitzung.commit()
    ergebnis = jsonify(antwort)
    for k, v in kopf.items():
        ergebnis.headers[k] = v
    return ergebnis, 200
