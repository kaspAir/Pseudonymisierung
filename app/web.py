"""Flask-Anwendung.

Bindet ausschliesslich auf 127.0.0.1 (siehe run.py). Es gibt keine Site, keine
Subdomain und keinen PHP-Proxy - der Dienst ist aus dem Internet nicht
erreichbar, und damit liegen weder der Schluesseltresor noch die
Zuordnungstabelle je an einer oeffentlichen Adresse.
"""
import os

from flask import Flask, g, jsonify

from . import __version__
from .api import anbieter as anbieter_api, pseudo as pseudo_api
from .config import Config
from .db import richte_ein
from .tresor import Tresor
from .weiterleitung import echte_weiterleitung


def lade_namenslexikon(pfad):
    """Laedt das Namenslexikon fuer Stufe B.

    Die Datei wird BEWUSST nicht mit erfundenen Namen ausgeliefert. Ohne
    gepflegte Quelle bleibt sie leer - dann erkennt Stufe B nur Namen MIT
    Anrede-Anker. Das ist eine ehrliche Luecke und kein stiller Ausfall:
    /pseudo/v1/health weist die Zahl der Eintraege aus.
    """
    if not pfad or not os.path.exists(pfad):
        return set()
    namen = set()
    with open(pfad, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#"):
                namen.add(zeile)
    return namen


def erzeuge_app(config=None, sitzungsfabrik=None, weiterleiter=None, tresor=None,
                namenslexikon=None):
    app = Flask(__name__)
    config = config or Config()

    if sitzungsfabrik is None:
        _, sitzungsfabrik = richte_ein(config.datenbank_url)

    app.extensions["pseudo"] = {
        "config": config,
        "tresor": tresor or Tresor(config.tresor_schluessel),
        "weiterleiter": weiterleiter or echte_weiterleitung(),
        "namenslexikon": (
            namenslexikon
            if namenslexikon is not None
            else lade_namenslexikon(os.environ.get("PSEUDO_NAMENSLEXIKON"))
        ),
        "version": __version__,
        "sitzungsfabrik": sitzungsfabrik,
    }

    @app.before_request
    def _oeffne_sitzung():
        g.sitzung = app.extensions["pseudo"]["sitzungsfabrik"]()

    @app.teardown_request
    def _schliesse_sitzung(fehler):
        sitzung = g.pop("sitzung", None)
        if sitzung is not None:
            if fehler is not None:
                sitzung.rollback()
            sitzung.close()

    app.register_blueprint(pseudo_api.blueprint, url_prefix="/pseudo/v1")
    app.register_blueprint(anbieter_api.blueprint)

    @app.errorhandler(404)
    def _nicht_gefunden(_):
        return jsonify({"type": "error",
                        "error": {"type": "not_found", "message": "Unbekannte Route."}}), 404

    return app
