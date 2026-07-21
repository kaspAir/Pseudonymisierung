"""Verschluesselung at rest und Hashbildung.

Das Schluesselmaterial kommt ausschliesslich aus der Umgebung, nie aus der
Datenbank. Fehlt es, verweigert der Dienst den Start - ein stiller Rueckfall
auf Klartextspeicherung waere der schlimmste denkbare Ausgang, weil niemand
ihn bemerkt.
"""
import base64
import hashlib
import hmac

from cryptography.fernet import Fernet


class TresorFehlt(Exception):
    pass


class Tresor:
    def __init__(self, schluessel):
        if not schluessel:
            raise TresorFehlt(
                "PSEUDO_TRESOR_SCHLUESSEL ist nicht gesetzt. Der Dienst "
                "speichert ohne Schluessel nichts - auch nicht im Klartext."
            )
        roh = schluessel.encode("utf-8") if isinstance(schluessel, str) else schluessel
        self._fernet = Fernet(roh)
        # Eigener, abgeleiteter Schluessel fuer Hashes - damit ein Hash nicht
        # mit demselben Material gebildet wird wie die Verschluesselung.
        self._hmac_schluessel = hashlib.sha256(b"hash:" + roh).digest()

    def verschluessle(self, klartext):
        return self._fernet.encrypt(klartext.encode("utf-8")).decode("ascii")

    def entschluessle(self, chiffre):
        return self._fernet.decrypt(chiffre.encode("ascii")).decode("utf-8")

    def hash(self, wert):
        """HMAC statt blossem SHA-256.

        Ein blosser Hash eines kurzen Namens waere durch Ausprobieren sofort
        aufzuloesen und damit kein Schutz. Mit dem HMAC-Schluessel ist das
        ohne Kenntnis des Schluessels nicht moeglich.
        """
        return hmac.new(
            self._hmac_schluessel, wert.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def neuer_schluessel():
        """Erzeugt ein gueltiges Schluesselmaterial (fuer die Einrichtung)."""
        return Fernet.generate_key().decode("ascii")


def normiere(s):
    """Vergleichsform einer Oberflaeche: Mehrfachleerzeichen weg, klein."""
    return " ".join((s or "").split()).casefold()
