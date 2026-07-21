"""Pseudonymisierung - Vorschalt-Dienst fuer KI-Aufrufe.

Der Dienst ist von aussen NICHT erreichbar: er bindet auf 127.0.0.1 und hat
keine oeffentliche Site, keinen PHP-Proxy und keine Subdomain. Alle Aufrufer
laufen auf demselben Host. Damit liegen weder der Schluesseltresor noch die
Zuordnungstabelle je an einer oeffentlichen Adresse.
"""
__version__ = "0.0.1"
