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


def _lies_liste(pfad):
    if not pfad or not os.path.exists(pfad):
        return set()
    werte = set()
    with open(pfad, "r", encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#"):
                werte.add(zeile)
    return werte


def lade_lexika(verzeichnis):
    """Laedt Nachnamen, Vornamen und den Alltagswortschatz.

    Nachnamen und Vornamen stammen aus den offenen Daten des Bundesamts fuer
    Statistik (siehe scripts/importiere_namen.py). Nichts davon ist erfunden.

    Die WORTLISTE ist der Gegenspieler: Woerter, die zwar als Nachname
    vorkommen, im laufenden Text aber praktisch nie eine Person meinen -
    "Kosten", "Recht", "Bau". Fehlt sie, blockiert der Dienst auf gewoehnlichem
    Verwaltungsdeutsch. /pseudo/v1/health weist alle drei Zahlen aus, damit die
    Luecke sichtbar bleibt.
    """
    verzeichnis = verzeichnis or ""
    return {
        "nachnamen": _lies_liste(os.path.join(verzeichnis, "nachnamen.txt")),
        "vornamen": _lies_liste(os.path.join(verzeichnis, "vornamen.txt")),
        "wortliste": _lies_liste(os.path.join(verzeichnis, "wortliste.txt")),
    }


def erzeuge_app(config=None, sitzungsfabrik=None, weiterleiter=None, tresor=None,
                namenslexikon=None, lexika=None):
    app = Flask(__name__)
    config = config or Config()

    if sitzungsfabrik is None:
        _, sitzungsfabrik = richte_ein(config.datenbank_url)

    if lexika is None:
        if namenslexikon is not None:
            # Einfache Form: eine Liste, als Nachnamen gewertet.
            lexika = {"nachnamen": set(namenslexikon), "vornamen": set(),
                      "wortliste": set()}
        else:
            lexika = lade_lexika(config.lexikon_verzeichnis)

    app.extensions["pseudo"] = {
        "config": config,
        "tresor": tresor or Tresor(config.tresor_schluessel),
        "weiterleiter": weiterleiter or echte_weiterleitung(),
        "lexika": lexika,
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
