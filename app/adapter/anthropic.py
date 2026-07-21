"""Adapter fuer die Anthropic Messages API.

Route: /anthropic/v1/messages - die Anwendung setzt nur ihre base_url auf
http://127.0.0.1:8030/anthropic, das SDK haengt /v1/messages selbst an.
"""
import copy

from .basis import Adapter, registriere


class AnthropicAdapter(Adapter):
    name = "anthropic"
    basis_url = "https://api.anthropic.com"
    wege = ("chat",)

    def weg(self, pfad):
        if pfad.rstrip("/").endswith("/v1/messages"):
            return "chat"
        return None

    def texte(self, rumpf):
        gefunden = []

        # Systemanweisung: String oder Bloecke.
        system = rumpf.get("system")
        if isinstance(system, str):
            gefunden.append(("system", system))
        elif isinstance(system, list):
            for i, block in enumerate(system):
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    gefunden.append(("system[%d].text" % i, block["text"]))

        for mi, nachricht in enumerate(rumpf.get("messages") or []):
            inhalt = nachricht.get("content")
            if isinstance(inhalt, str):
                gefunden.append(("messages[%d].content" % mi, inhalt))
            elif isinstance(inhalt, list):
                for bi, block in enumerate(inhalt):
                    if not isinstance(block, dict):
                        continue
                    if isinstance(block.get("text"), str):
                        gefunden.append(
                            ("messages[%d].content[%d].text" % (mi, bi), block["text"])
                        )
                    # Werkzeug-Ergebnisse tragen ebenfalls Text hinaus.
                    if isinstance(block.get("content"), str):
                        gefunden.append(
                            ("messages[%d].content[%d].content" % (mi, bi),
                             block["content"])
                        )
        return gefunden

    def setze_texte(self, rumpf, ersetzt):
        neu = copy.deepcopy(rumpf)
        for pfad, text in ersetzt.items():
            _setze(neu, pfad, text)
        return neu

    def antwort_texte(self, antwort):
        gefunden = []
        for bi, block in enumerate(antwort.get("content") or []):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                gefunden.append(("content[%d].text" % bi, block["text"]))
        return gefunden

    def setze_antwort_texte(self, antwort, ersetzt):
        neu = copy.deepcopy(antwort)
        for pfad, text in ersetzt.items():
            _setze(neu, pfad, text)
        return neu

    def schluessel_kopfzeile(self):
        return "x-api-key"


def _setze(wurzel, pfad, wert):
    """Schreibt einen Wert an einen Feldpfad wie messages[2].content[0].text."""
    teile = pfad.replace("]", "").replace("[", ".").split(".")
    ziel = wurzel
    for t in teile[:-1]:
        ziel = ziel[int(t)] if t.isdigit() else ziel[t]
    letzt = teile[-1]
    if letzt.isdigit():
        ziel[int(letzt)] = wert
    else:
        ziel[letzt] = wert


registriere(AnthropicAdapter())
