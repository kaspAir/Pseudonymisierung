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


def _menge(werte):
    return set(w.casefold() for w in (werte or ()))


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

# Was unmittelbar auf eine Strassenangabe folgen darf, damit die Adresse als
# EINE Einheit ersetzt wird statt "{{P1}}, 3011 Bern" stehen zu lassen.
_RE_PLZ_ORT = re.compile(r"\s*,?\s*(\d{4})\s+([A-ZÄÖÜ][\wäöüéèàç-]+(?:[ -][A-ZÄÖÜ][\wäöüéèàç-]+)?)")


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

# Jedes grossgeschriebene Wort. Im Deutschen ist das FAST KEIN Namenssignal:
# alle Substantive und jedes Satzanfangswort sind gross. Gemessen an einem
# HERMES-nahen Probetext trafen 12% der verschiedenen grossgeschriebenen
# Woerter die BfS-Nachnamenliste - darunter "Der", "Die", "Das" (es gibt in
# der Schweiz Personen dieses Nachnamens) sowie "Kosten", "Recht", "Bau".
_RE_WORT = re.compile(r"\b[A-ZÄÖÜ][\wäöüéèàáâêîôûëïüç-]{1,}\b")

# Nur diese Zeichen erzwingen im Deutschen Grossschreibung; danach ist sie als
# Namenssignal wertlos.
#
# Bewusst NICHT enthalten: Doppelpunkt, Strichpunkt, Zeilenumbruch und
# Aufzaehlungszeichen. Nach ihnen geht es im Deutschen klein weiter - ein
# grosses Wort ist dort also sehr wohl ein Signal. Genau dort stehen in
# Projektdokumenten die Namen: "Projektleitung: Steiner", "- Steiner, Anna".
_SATZENDE = set(".!?")


def _ist_satzanfang(text, pos):
    """Steht das Wort an einer Stelle, an der Grossschreibung erzwungen ist?

    Ein WEICHER Zeilenumbruch (Umbruch mitten im Satz) zaehlt nicht - sonst
    gaelte in umbrochenem Text jedes Zeilenanfangswort als erzwungen und die
    Erkennung verloere halbe Saetze. Ein Absatz (Leerzeile) zaehlt.
    """
    i = pos - 1
    umbrueche = 0
    while i >= 0 and text[i] in " \t\r\n-–—\"'«»([":
        if text[i] == "\n":
            umbrueche += 1
            if umbrueche >= 2:
                return True          # Absatzwechsel
        i -= 1
    if i < 0:
        return True                  # Textanfang
    return text[i] in _SATZENDE


class Erkenner:
    """Fuehrt die Erkennung fuer einen Mandanten durch.

    listen:        aufgeloeste Listen dieses Mandanten (kern.listen.Listen)
    zusatzmuster:  mandantenspezifische Geschaefts-/Verfahrensnummern-Muster
                   als Liste von (regex, kategorie, grund). Die Formate der
                   Justiz sind kantonal verschieden - deshalb konfigurierbar
                   und nicht fest verdrahtet.
    namenslexikon: Menge bekannter Vor-/Nachnamen (kann leer sein)
    """

    def __init__(self, listen=None, zusatzmuster=None, namenslexikon=None,
                 nachnamen=None, vornamen=None, wortliste=None, orte=None):
        self._listen = listen
        self._zusatz = list(zusatzmuster or [])
        # namenslexikon bleibt als einfache Form bestehen und zaehlt als
        # Nachnamenliste.
        self._nachnamen = _menge(nachnamen) | _menge(namenslexikon)
        self._vornamen = _menge(vornamen)
        self._orte = _menge(orte)
        # Was fuer sich genommen KEINE Person meint:
        #  - Alltagswortschatz ("Kosten", "Recht", "Bau", "Der")
        #  - Schweizer Ortschaften; 359 davon sind zugleich Nachnamen
        #    (Basel, Baden, Arbon, Arosa, Bellinzona, Cham ...)
        # Beides unterdrueckt NUR den alleinstehenden Lexikontreffer. Mit
        # Anrede ("Frau Basel") oder als Vorname+Nachname ("Anna Basel") wird
        # weiterhin erkannt und ersetzt - es entsteht also kein Loch.
        self._nicht_person = _menge(wortliste) | self._orte

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
                anfang, ende = m.start(), m.end()
                if pruefer and not pruefer(m.group(0)):
                    continue
                if kategorie == K_ADRESSE:
                    ende, grund = self._adresse_erweitern(text, ende, grund)
                if not _frei(anfang, ende):
                    continue
                treffer = text[anfang:ende]
                if self._freigegeben(treffer, kategorie):
                    continue
                belegt.append((anfang, ende))
                befunde.append(
                    Befund(kategorie, treffer, anfang, ende, 0.99,
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
            # Die ganze Fundstelle sperren, nicht nur den Namen: das Anredewort
            # selbst ist teils ebenfalls ein Nachname ("Herr", "Frau" stehen in
            # der BfS-Liste) und wuerde sonst als eigener Befund blockieren.
            belegt.append((m.start(), m.end()))
            befunde.append(
                Befund(K_PERSON_NAME, name, a, b, 0.93, BAND_SICHER,
                       "erkannt_kontextanker_anrede", feld)
            )

        # Stufe B2: Vorname unmittelbar vor Nachname -> sicher.
        # Das ist das staerkste Signal ohne Anrede: zwei benachbarte
        # Lexikontreffer in genau dieser Rollenfolge.
        woerter = [m for m in _RE_WORT.finditer(text)]
        uebersprungen = set()
        if self._vornamen and self._nachnamen:
            for i in range(len(woerter) - 1):
                links, rechts = woerter[i], woerter[i + 1]
                if text[links.end():rechts.start()].strip():
                    continue          # nicht unmittelbar benachbart
                if links.group(0).casefold() not in self._vornamen:
                    continue
                if rechts.group(0).casefold() not in self._nachnamen:
                    continue
                voll = text[links.start():rechts.end()]
                if not _frei(links.start(), rechts.end()) \
                        or self._freigegeben(voll, K_PERSON_NAME):
                    continue
                belegt.append((links.start(), rechts.end()))
                uebersprungen.update({i, i + 1})
                befunde.append(
                    Befund(K_PERSON_NAME, voll, links.start(), rechts.end(), 0.95,
                           BAND_SICHER, "erkannt_vorname_und_nachname", feld)
                )

        # Stufe B3: einzelner Lexikontreffer -> unsicher, blockiert.
        for i, m in enumerate(woerter):
            if i in uebersprungen:
                continue
            wort = m.group(0)
            klein = wort.casefold()
            if not _frei(m.start(), m.end()):
                continue

            ist_nachname = klein in self._nachnamen
            ist_vorname = klein in self._vornamen
            if not (ist_nachname or ist_vorname):
                continue

            # Eine ausdrueckliche Sperre des Mandanten geht allem vor.
            if self._gesperrt(wort, K_PERSON_NAME):
                belegt.append((m.start(), m.end()))
                befunde.append(
                    Befund(K_PERSON_NAME, wort, m.start(), m.end(), 0.99,
                           BAND_SICHER, "gesperrt_durch_mandantenliste", feld)
                )
                continue

            if self._freigegeben(wort, K_PERSON_NAME):
                continue

            # Alltagswort oder Ortschaft: allein genommen keine Person.
            if klein in self._nicht_person:
                continue

            # Am Satzanfang ist Grossschreibung erzwungen und damit kein
            # Namenssignal. Ohne weiteres Signal wird hier nicht blockiert.
            if _ist_satzanfang(text, m.start()):
                continue

            belegt.append((m.start(), m.end()))
            befunde.append(
                Befund(K_PERSON_NAME, wort, m.start(), m.end(), 0.61,
                       BAND_UNSICHER,
                       "erkannt_lexikon_%s; kein_kontextanker_anrede"
                       % ("nachname" if ist_nachname else "vorname"), feld)
            )

        befunde.sort(key=lambda b: b.von)
        return befunde, bestand

    def _adresse_erweitern(self, text, ende, grund):
        """Zieht ein unmittelbar folgendes "PLZ Ortschaft" in die Adresse.

        Sonst bliebe nach der Ersetzung "{{P1}}, 3011 Bern" stehen - die
        Adresse waere zerrissen und der Rest lesbar. Erweitert wird nur, wenn
        die Ortschaft im amtlichen Verzeichnis steht; ohne Verzeichnis bleibt
        es bei der Strassenangabe.
        """
        if not self._orte:
            return ende, grund
        m = _RE_PLZ_ORT.match(text, ende)
        if not m:
            return ende, grund
        if m.group(2).casefold() not in self._orte:
            return ende, grund
        return m.end(), grund + "; plz_ortschaft_amtlich"

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
