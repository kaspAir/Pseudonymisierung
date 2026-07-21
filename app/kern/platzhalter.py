"""Form und Vergabe der Platzhalter.

FORMWAHL (bewusst, mit Begruendung):

Im Entwurf stand zunaechst die Guillemet-Form «P3». Sie ist VERWORFEN: im
Schweizer Deutsch sind « » die normalen Anfuehrungszeichen. Ein Modell, das
Schweizer Verwaltungstext schreibt, setzt und normalisiert diese Zeichen
staendig - genau das Gegenteil von dem, was ein Marker braucht.

Gewaehlt: {{P3}}

  - reines ASCII (ueberlebt cp1252-Exporte, JSON, SQLite)
  - kommt in deutscher Prosa praktisch nicht vor
  - hat in Markdown keine Bedeutung, wird also nicht umformatiert
  - kollisionsfrei zu den Bestandsplatzhaltern [Person_099] / [Org_148]
    aus dem Seed-Korpus (einfache Klammern, anderes Innenmuster)

OFFEN, nicht behauptet: ob gaengige Tokenizer {{P3}} stabil zusammenhalten,
ist NICHT gemessen. Die Form ist deshalb an genau dieser Stelle gekapselt und
austauschbar; die Rueckersetzung arbeitet ausschliesslich ueber die hier
definierten Ausdruecke.
"""
import re

# Vergabeform.
def bilde(nummer):
    """Erzeugt die kanonische Platzhalterform zu einer Nummer."""
    return "{{P%d}}" % int(nummer)


# Erkennungsform auf dem Rueckweg - absichtlich toleranter als die Vergabeform.
# Toleriert: Leerzeichen und Zeilenumbrueche innerhalb, Kleinschreibung.
# NICHT toleriert (und das ist Absicht): fehlende Klammern - dann ist es kein
# Platzhalter mehr, sondern ein Leck (siehe leckpruefung.py).
RE_PLATZHALTER = re.compile(r"\{\{\s*[Pp]\s*(\d+)\s*\}\}")

# Groesste Zeichenzahl, die ein toleriert geschriebener Platzhalter belegen
# kann. Begrenzt den Rueckhalt im Stromautomaten (rueckersetzung.py).
MAX_LAENGE = 32

# Bestandsplatzhalter aus dem Seed-Korpus: werden erkannt, unangetastet
# durchgereicht und NIE als Befund gemeldet (Kategorie bereits_pseudonymisiert).
RE_BESTAND = re.compile(r"\[(?:Person|Org)_\d+\]")


def naechste_nummer(vergebene):
    """Kleinste noch freie Nummer. Nummern werden je (Mandant, Projekt) vergeben."""
    belegt = set(int(n) for n in vergebene)
    n = 1
    while n in belegt:
        n += 1
    return n
