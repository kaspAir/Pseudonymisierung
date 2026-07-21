"""Erkennung von Personendaten - ausschliesslich lokal (Anforderung A8).

Drei Stufen (KONZEPT 4.1):
  A  deterministische Muster    -> Band "sicher"
  B  Lexika + Kontextanker      -> "sicher" nur MIT Anker, sonst "unsicher"
  C  lokales statistisches NER  -> noch NICHT aktiv, siehe unten

Drei Baender (KONZEPT 4.2): sicher | unsicher | unauffaellig.
Ein einziger Treffer im Band "unsicher" blockiert den gesamten Aufruf (A2).

STUFE C ist bewusst nicht verdrahtet. Geprueft ist bisher nur, dass spaCy auf
dem Zielhost (Python 3.9.2) ueberhaupt laeuft und presidio-analyzer nicht.
Die LATENZ an einem echten Diktattext ist NICHT gemessen - deshalb wird sie
hier auch nicht unterstellt.
"""
import re

from . import platzhalter

BAND_SICHER = "sicher"
BAND_UNSICHER = "unsicher"
BAND_UNAUFFAELLIG = "unauffaellig"

# Kategorien. Organisationen fehlen hier ABSICHTLICH und dauerhaft: das Modell
# braucht den fachlichen Kontext (KONZEPT 1.1).
K_PERSON_NAME = "person_name"
K_PERSON_KONTAKT = "person_kontakt"
K_GESCHAEFTSNUMMER = "geschaeftsnummer"
K_VERFAHRENSNUMMER = "verfahrensnummer"
K_ADRESSE = "adresse"
K_AHV = "ahv"
K_FINANZKONTO = "finanzkonto"
K_DATUM_GEBURT = "datum_geburt"
K_BENUTZERKONTO = "benutzerkonto"
# Nicht ersetzend: Bestandsplatzhalter des Seed-Korpus.
K_BEREITS = "bereits_pseudonymisiert"


class Befund:
    def __init__(self, kategorie, treffer, von, bis, sicherheit, band, grund, feld=None):
        self.kategorie = kategorie
        self.treffer = treffer
        self.von = von
        self.bis = bis
        self.sicherheit = sicherheit
        self.band = band
        self.grund = grund
        self.feld = feld

    def als_dict(self, befund_id, auszug):
        return {
            "befund_id": befund_id,
            "kategorie": self.kategorie,
            "auszug": auszug,
            "treffer": self.treffer,
            "ort": {"feld": self.feld, "von": self.von, "bis": self.bis},
            "sicherheit": round(self.sicherheit, 2),
            "band": self.band,
            "grund": self.grund,
            "vorschlag": "ersetzen",
            "moegliche_entscheide": ["ersetzen", "freigeben"],
        }


# -- Stufe A: deterministische Muster ------------------------------------

_RE_EMAIL = re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_RE_AHV = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
_RE_IBAN = re.compile(r"\b(?:CH|LI)\d{2}[ ]?(?:[0-9A-Z]{4}[ ]?){4}[0-9A-Z]{1}\b")
_RE_TELEFON = re.compile(r"(?:\+41|\+423|0)(?:[ /.-]?\d){8,11}\b")
# Strasse mit Hausnummer - Hausnummer ist das tragende Signal.
_RE_ADRESSE = re.compile(
    r"\b[A-ZÄÖÜ][\wäöüéèà-]+(?:strasse|weg|gasse|platz|allee|str\.)\s+\d+[a-z]?\b",
    re.IGNORECASE,
)


def _ahv_gueltig(roh):
    """EAN-13-Pruefziffer der 13-stelligen AHV-Nummer."""
    ziffern = [int(c) for c in re.sub(r"\D", "", roh)]
    if len(ziffern) != 13:
        return False
    summe = 0
    for i, z in enumerate(ziffern[:12]):
        summe += z * (1 if i % 2 == 0 else 3)
    return (10 - summe % 10) % 10 == ziffern[12]


def _iban_gueltig(roh):
    """Mod-97-Pruefung nach ISO 13616."""
    s = re.sub(r"\s", "", roh).upper()
    if len(s) < 5:
        return False
    umgestellt = s[4:] + s[:4]
    zahl = ""
    for c in umgestellt:
        zahl += str(ord(c) - 55) if c.isalpha() else c
    try:
        return int(zahl) % 97 == 1
    except ValueError:
        return False


_STUFE_A = [
    (_RE_EMAIL, K_PERSON_KONTAKT, None, "muster_email"),
    (_RE_AHV, K_AHV, _ahv_gueltig, "muster_ahv_mit_pruefziffer"),
    (_RE_IBAN, K_FINANZKONTO, _iban_gueltig, "muster_iban_mod97"),
    (_RE_TELEFON, K_PERSON_KONTAKT, None, "muster_telefon"),
    (_RE_ADRESSE, K_ADRESSE, None, "muster_adresse_mit_hausnummer"),
]


# -- Stufe B: Lexika und Kontextanker ------------------------------------

# Anrede- und Funktionsanker. Das sind gewoehnliche deutsche Woerter, keine
# erfundenen Daten. Die NAMENSLEXIKA dagegen werden NICHT hier erfunden - sie
# werden aus einer gepflegten Datei geladen (lexikon.py) und sind anfangs leer.
_ANKER = (
    r"Herr|Frau|Hr\.|Fr\.|Dr\.|Prof\.|Regierungsrat|Regierungsraetin|"
    r"Gemeindepraesident|Gemeindepraesidentin|Stadtpraesident|Amtsleiter|"
    r"Amtsleiterin|Projektleiter|Projektleiterin|zustaendig ist|"
    r"verantwortlich ist|vertreten durch"
)
_RE_ANKER_NAME = re.compile(
    r"(?:%s)\s+([A-ZÄÖÜ][\wäöüéèà-]{1,}(?:\s+[A-ZÄÖÜ][\wäöüéèà-]{1,})?)" % _ANKER
)


class Erkenner:
    """Fuehrt die Erkennung fuer einen Mandanten durch.

    listen:        aufgeloeste Listen dieses Mandanten (kern.listen.Listen)
    zusatzmuster:  mandantenspezifische Geschaefts-/Verfahrensnummern-Muster
                   als Liste von (regex, kategorie, grund). Die Formate der
                   Justiz sind kantonal verschieden - deshalb konfigurierbar
                   und nicht fest verdrahtet.
    namenslexikon: Menge bekannter Vor-/Nachnamen (kann leer sein)
    """

    def __init__(self, listen=None, zusatzmuster=None, namenslexikon=None):
        self._listen = listen
        self._zusatz = list(zusatzmuster or [])
        self._namen = set(n.casefold() for n in (namenslexikon or ()))

    def pruefe(self, text, feld=None):
        """Liefert (befunde, bestandsstellen)."""
        befunde = []
        belegt = []

        # Bestandsplatzhalter zuerst: sie werden unangetastet durchgereicht und
        # nie gemeldet. Ihre Stellen werden gesperrt, damit keine andere Stufe
        # sie nochmals anfasst.
        bestand = [(m.start(), m.end()) for m in platzhalter.RE_BESTAND.finditer(text)]
        belegt.extend(bestand)

        def _frei(a, b):
            return not any(a < ende and beginn < b for beginn, ende in belegt)

        # Stufe A
        for regex, kategorie, pruefer, grund in _STUFE_A:
            for m in regex.finditer(text):
                if not _frei(m.start(), m.end()):
                    continue
                if pruefer and not pruefer(m.group(0)):
                    continue
                if self._freigegeben(m.group(0), kategorie):
                    continue
                belegt.append((m.start(), m.end()))
                befunde.append(
                    Befund(kategorie, m.group(0), m.start(), m.end(), 0.99,
                           BAND_SICHER, grund, feld)
                )

        # Mandantenspezifische Nummernmuster
        for regex, kategorie, grund in self._zusatz:
            for m in re.finditer(regex, text):
                if not _frei(m.start(), m.end()):
                    continue
                if self._freigegeben(m.group(0), kategorie):
                    continue
                belegt.append((m.start(), m.end()))
                befunde.append(
                    Befund(kategorie, m.group(0), m.start(), m.end(), 0.95,
                           BAND_SICHER, grund, feld)
                )

        # Stufe B: Name MIT Anker -> sicher
        for m in _RE_ANKER_NAME.finditer(text):
            name = m.group(1)
            a, b = m.start(1), m.end(1)
            if not _frei(a, b) or self._freigegeben(name, K_PERSON_NAME):
                continue
            belegt.append((a, b))
            befunde.append(
                Befund(K_PERSON_NAME, name, a, b, 0.93, BAND_SICHER,
                       "erkannt_kontextanker_anrede", feld)
            )

        # Stufe B: Lexikontreffer OHNE Anker -> unsicher, blockiert
        if self._namen:
            for m in re.finditer(r"\b[A-ZÄÖÜ][\wäöüéèà-]{1,}\b", text):
                wort = m.group(0)
                if not _frei(m.start(), m.end()):
                    continue
                if wort.casefold() not in self._namen:
                    continue
                if self._gesperrt(wort, K_PERSON_NAME):
                    belegt.append((m.start(), m.end()))
                    befunde.append(
                        Befund(K_PERSON_NAME, wort, m.start(), m.end(), 0.99,
                               BAND_SICHER, "gesperrt_durch_mandantenliste", feld)
                    )
                    continue
                if self._freigegeben(wort, K_PERSON_NAME):
                    continue
                belegt.append((m.start(), m.end()))
                befunde.append(
                    Befund(K_PERSON_NAME, wort, m.start(), m.end(), 0.61,
                           BAND_UNSICHER,
                           "erkannt_lexikon_nachname; kein_kontextanker_anrede", feld)
                )

        befunde.sort(key=lambda b: b.von)
        return befunde, bestand

    # -- Listen ---------------------------------------------------------

    def _freigegeben(self, treffer, kategorie):
        if not self._listen:
            return False
        return self._listen.entscheid(treffer, kategorie) == "freigabe"

    def _gesperrt(self, treffer, kategorie):
        if not self._listen:
            return False
        return self._listen.entscheid(treffer, kategorie) == "sperre"


def blockiert(befunde):
    """A2: ein einziger unsicherer Befund haelt den Aufruf an."""
    return any(b.band == BAND_UNSICHER for b in befunde)
