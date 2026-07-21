"""Adapter fuer Voyage-Embeddings.

Dieser Weg wird gern uebersehen (KONZEPT 1.2): der Wissenskorpus schickt
denselben Text ins Ausland wie der Chat, nur ohne Antworttext. Es gibt hier
KEINE Rueckersetzung - zurueck kommt ein Vektor. Der Hinweg ist trotzdem
vollstaendig pflichtig, und der erzeugte Vektor ist der Vektor des
PSEUDONYMISIERTEN Texts. Das muss dokumentiert bleiben, sonst wundert sich
spaeter jemand ueber die Trefferqualitaet.
"""
import copy

from .basis import Adapter, registriere


class VoyageAdapter(Adapter):
    name = "voyage"
    basis_url = "https://api.voyageai.com"
    wege = ("embedding",)

    def weg(self, pfad):
        if pfad.rstrip("/").endswith("/v1/embeddings"):
            return "embedding"
        return None

    def texte(self, rumpf):
        eingabe = rumpf.get("input")
        if isinstance(eingabe, str):
            return [("input", eingabe)]
        if isinstance(eingabe, list):
            return [
                ("input[%d]" % i, t) for i, t in enumerate(eingabe)
                if isinstance(t, str)
            ]
        return []

    def setze_texte(self, rumpf, ersetzt):
        neu = copy.deepcopy(rumpf)
        for pfad, text in ersetzt.items():
            if pfad == "input":
                neu["input"] = text
            else:
                i = int(pfad[len("input["):-1])
                neu["input"][i] = text
        return neu

    def antwort_texte(self, antwort):
        return []          # Vektoren, kein Text

    def setze_antwort_texte(self, antwort, ersetzt):
        return antwort

    def schluessel_kopfzeile(self):
        return "Authorization"


registriere(VoyageAdapter())
