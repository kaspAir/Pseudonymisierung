"""Rueckersetzung der Platzhalter durch Klartext.

Das technisch heikelste Stueck des Dienstes (KONZEPT 5).

Bewusst als ZUSTANDSAUTOMAT UEBER EINEN ZEICHENSTROM gebaut, nicht als
str.replace ueber einen fertigen Text. Grund: beim Streaming (SSE, vom
KI-Technology-Radar genutzt) kommt {{P3}} ueber Chunk-Grenzen zerschnitten an -
etwa als "{{P" und "3}}". Nicht-Streaming ist hier schlicht der Sonderfall
"ein einziges grosses Chunk". Haetten wir es andersherum gebaut, muesste die
Rueckersetzung fuer den Radar vollstaendig neu geschrieben werden.

Deutsche Beugung braucht KEINE Sonderbehandlung: aus "des {{P3}}s" wird durch
blosses Ersetzen "des Marc Buergis" - das Suffix bleibt von selbst am Namen.
"""
import re

from . import platzhalter

# Faengt einen am Puffer-Ende ABGESCHNITTENEN Platzhalter ab. Jede Stufe ist
# optional, damit auch "{", "{{", "{{P", "{{P3", "{{P3}" als moegliche
# Fortsetzung erkannt werden.
_RE_ANGEFANGEN = re.compile(
    r"\{(\{(\s*([Pp](\s*(\d+(\s*(\})?)?)?)?)?)?)?$"
)


class Rueckersetzer:
    """Setzt Platzhalter im Antwortstrom wieder in Klartext um.

    zuordnung: {nummer (int): klartext (str)}
    """

    def __init__(self, zuordnung):
        self._zuordnung = {int(k): v for k, v in zuordnung.items()}
        self._puffer = ""
        # Platzhalter, die das Modell verwendet hat, die wir aber nie vergeben
        # haben. Das ist ein Leck-Verdacht, kein Schoenheitsfehler.
        self.unbekannt = set()
        self.ersetzt = 0

    def schreibe(self, chunk):
        """Nimmt ein Chunk entgegen, gibt den sicher freigebbaren Teil zurueck."""
        self._puffer += chunk or ""
        grenze = self._rueckhalt_ab(self._puffer)
        sicher = self._puffer[:grenze]
        self._puffer = self._puffer[grenze:]
        return self._ersetze(sicher)

    def schluss(self):
        """Gibt den Rest frei. Nach diesem Aufruf wird nichts mehr zurueckgehalten."""
        rest = self._puffer
        self._puffer = ""
        return self._ersetze(rest)

    # -- intern ---------------------------------------------------------

    def _rueckhalt_ab(self, text):
        """Index, ab dem zurueckgehalten werden muss (== Laenge, wenn gar nicht)."""
        treffer = _RE_ANGEFANGEN.search(text)
        if not treffer:
            return len(text)
        beginn = treffer.start()
        # Laenger als ein tolerierter Platzhalter je sein kann -> es wird keiner
        # mehr daraus, also freigeben statt endlos zurueckhalten.
        if len(text) - beginn > platzhalter.MAX_LAENGE:
            return len(text)
        return beginn

    def _ersetze(self, text):
        if not text:
            return ""

        def _auf(treffer):
            nummer = int(treffer.group(1))
            if nummer in self._zuordnung:
                self.ersetzt += 1
                return self._zuordnung[nummer]
            # Unbekannt: NICHT stillschweigend stehen lassen und auch nicht
            # raten. Der Platzhalter bleibt im Text und die Leckpruefung
            # verhindert die Auslieferung.
            self.unbekannt.add(nummer)
            return treffer.group(0)

        return platzhalter.RE_PLATZHALTER.sub(_auf, text)


def rueckersetze(text, zuordnung):
    """Bequemlichkeit fuer den Nicht-Streaming-Fall."""
    r = Rueckersetzer(zuordnung)
    ergebnis = r.schreibe(text) + r.schluss()
    return ergebnis, r
