"""Adapter-Schnittstelle.

Ein Adapter ist die EINZIGE Stelle im Dienst, die das Protokoll eines Anbieters
kennt: wo in der Anfrage Text steckt, wie die Antwort aussieht, wie Streaming
aufgebaut ist. Der Kern (app/kern/) bleibt anbieterblind.

Feldpfade sind Zeichenketten wie "messages[2].content[0].text". Sie erscheinen
unveraendert im 409-Fehlerformat, damit die aufrufende Anwendung die Stelle im
Diktattext punktgenau markieren kann (KONZEPT 3.4).
"""


class Adapter:
    name = None
    basis_url = None
    # Welche Wege der Adapter kennt: "chat" und/oder "embedding".
    wege = ()

    def weg(self, pfad):
        """Ordnet einen eingehenden Pfad einem Weg zu, oder None."""
        raise NotImplementedError

    def texte(self, rumpf):
        """Liefert [(feldpfad, text), ...] - alles, was hinausgehen wuerde."""
        raise NotImplementedError

    def setze_texte(self, rumpf, ersetzt):
        """Schreibt {feldpfad: neuer_text} zurueck in eine Kopie des Rumpfs."""
        raise NotImplementedError

    def antwort_texte(self, antwort):
        """Liefert [(feldpfad, text), ...] aus der Anbieterantwort."""
        raise NotImplementedError

    def setze_antwort_texte(self, antwort, ersetzt):
        raise NotImplementedError

    def schluessel_kopfzeile(self):
        """Wie der Anbieter den API-Schluessel erwartet."""
        raise NotImplementedError


_REGISTER = {}


def registriere(adapter):
    _REGISTER[adapter.name] = adapter
    return adapter


def hole(name):
    return _REGISTER.get(name)


def alle():
    return dict(_REGISTER)
