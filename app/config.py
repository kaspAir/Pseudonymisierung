"""Konfiguration des Dienstes.

Grundsatz: der Dienst bindet ausschliesslich auf 127.0.0.1. Er ist von aussen
nicht erreichbar (siehe docs/KONZEPT.md, Abschnitt 8). Alle Aufrufer laufen auf
demselben Host.
"""
import os

UMGEBUNGEN = ("develop", "test", "integration", "main")

# Port je Umgebung. Der Block 8030-8033 ist fuer dieses Produkt reserviert.
PORTS = {
    "develop": 8030,
    "test": 8031,
    "integration": 8032,
    "main": 8033,
}


class Config:
    def __init__(self, env=None):
        self.umgebung = (env or os.environ.get("PSEUDO_UMGEBUNG") or "develop").strip()
        if self.umgebung not in UMGEBUNGEN:
            raise ValueError(
                "PSEUDO_UMGEBUNG muss eine von %s sein, war: %r"
                % (", ".join(UMGEBUNGEN), self.umgebung)
            )

        self.port = PORTS[self.umgebung]
        self.bind_host = "127.0.0.1"

        self.datenbank_url = os.environ.get(
            "PSEUDO_DB_URL", "sqlite:///data/pseudonymisierung-%s.db" % self.umgebung
        )

        # Schluesselmaterial fuer die Verschluesselung at rest. Kommt aus der
        # Umgebung, niemals aus der Datenbank.
        self.tresor_schluessel = os.environ.get("PSEUDO_TRESOR_SCHLUESSEL")

        # Modell fuer Stufe C. Leer = Stufe C ist nicht aktiv (Latenz auf dem
        # Zielhost noch nicht gemessen, siehe KONZEPT 8.3).
        self.ner_modell = os.environ.get("PSEUDO_NER_MODELL", "").strip()

        # Verzeichnis mit nachnamen.txt / vornamen.txt / wortliste.txt.
        self.lexikon_verzeichnis = os.environ.get(
            "PSEUDO_LEXIKON",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "lexikon"),
        )

    @property
    def ist_produktion(self):
        """Nur in dieser Umgebung darf niemals eine Ausnahme aktiv werden."""
        return self.umgebung == "main"
