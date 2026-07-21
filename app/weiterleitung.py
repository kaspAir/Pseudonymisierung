"""Weiterleitung an den Anbieter.

Getrennt vom Ablauf (dienst.py), damit die Regressionstests den vollstaendigen
Weg ohne Netzzugriff belegen koennen.
"""
import requests


def echte_weiterleitung(zeitlimit=120):
    def _weiter(adapter, pfad, rumpf, schluessel):
        ziel = adapter.basis_url.rstrip("/") + "/" + pfad.lstrip("/")
        kopf = {"content-type": "application/json"}
        name = adapter.schluessel_kopfzeile()
        kopf[name] = ("Bearer %s" % schluessel) if name == "Authorization" else schluessel
        if adapter.name == "anthropic":
            kopf["anthropic-version"] = "2023-06-01"

        antwort = requests.post(ziel, json=rumpf, headers=kopf, timeout=zeitlimit)
        try:
            rumpf_zurueck = antwort.json()
        except ValueError:
            rumpf_zurueck = {"type": "error", "error": {"message": antwort.text[:500]}}
        return antwort.status_code, rumpf_zurueck

    return _weiter
