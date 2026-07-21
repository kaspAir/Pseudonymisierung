"""Datenmodell (KONZEPT 6).

Grundsaetze, die sich hier niederschlagen:
  - Der Schluessel fuer Zuordnungen und Listen ist immer das BLATT
    (anwendung, mandant) - nie eine hoehere Ebene.
  - vorgang/befund enthalten KEINEN Klartext und KEINE Prompts, nur Zaehler
    und Hashes. Sonst bauten wir uns eine zweite Halde.
  - Klartext liegt ausschliesslich verschluesselt in zuordnung.klartext_chiffre.
"""
import datetime as _dt

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _jetzt():
    return _dt.datetime.now(_dt.timezone.utc)


class Anwendung(Base):
    __tablename__ = "anwendung"
    id = Column(Integer, primary_key=True)
    schluessel = Column(String(64), unique=True, nullable=False)  # "hermes-pia"
    bezeichnung = Column(String(200), nullable=False)
    aktiv = Column(Boolean, default=True, nullable=False)


class Mandant(Base):
    __tablename__ = "mandant"
    id = Column(Integer, primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    externe_id = Column(String(120), nullable=False)  # org_id der Anwendung
    bezeichnung = Column(String(200))
    __table_args__ = (UniqueConstraint("anwendung_id", "externe_id"),)

    anwendung = relationship("Anwendung")


class Projekt(Base):
    __tablename__ = "projekt"
    id = Column(Integer, primary_key=True)
    mandant_id = Column(Integer, ForeignKey("mandant.id"), nullable=False)
    externe_id = Column(String(120), nullable=False)
    __table_args__ = (UniqueConstraint("mandant_id", "externe_id"),)


class Zuordnung(Base):
    """Klartext <-> Platzhalter. Das ist die heikelste Tabelle des Dienstes.

    Sie konzentriert genau die Personendaten, die wir schuetzen wollen, an
    einem Ort. Das ist der bewusst bezahlte Preis fuer A7 (Konsistenz ueber
    Projekt und Zeit); die Alternative - rein fluechtige Zuordnung je Aufruf -
    haette kein Kronjuwel, aber auch keine Konsistenz zwischen zwei Aufrufen
    desselben Interviews.
    """
    __tablename__ = "zuordnung"
    id = Column(Integer, primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    mandant_id = Column(Integer, ForeignKey("mandant.id"), nullable=False)
    projekt_id = Column(Integer, ForeignKey("projekt.id"), nullable=False)
    kategorie = Column(String(40), nullable=False)
    # KEINE Klartextspalte. Eine "normalisierte Oberflaeche" waere bequem zum
    # Nachschauen und stuende doch im Klartext in genau der Tabelle, die
    # ausschliesslich verschluesselt speichern soll. Gesucht wird ueber den
    # HMAC, gelesen ueber die Chiffre.
    oberflaeche_hash = Column(String(64), nullable=False, index=True)
    klartext_chiffre = Column(Text, nullable=False)   # verschluesselt at rest
    nummer = Column(Integer, nullable=False)
    erstellt_am = Column(DateTime, default=_jetzt, nullable=False)
    letzte_nutzung = Column(DateTime, default=_jetzt, nullable=False)

    __table_args__ = (
        UniqueConstraint("anwendung_id", "mandant_id", "projekt_id",
                         "kategorie", "oberflaeche_hash"),
        UniqueConstraint("anwendung_id", "mandant_id", "projekt_id", "nummer"),
    )


class ZuordnungVariante(Base):
    """Schreibvarianten derselben Person: "Buergi" / "M. Buergi" / "Marc Buergi"."""
    __tablename__ = "zuordnung_variante"
    id = Column(Integer, primary_key=True)
    zuordnung_id = Column(Integer, ForeignKey("zuordnung.id"), nullable=False)
    oberflaeche_hash = Column(String(64), nullable=False, index=True)


class Listeneintrag(Base):
    __tablename__ = "listeneintrag"
    id = Column(Integer, primary_key=True)
    bereich = Column(String(20), nullable=False)      # betrieb|anwendung|mandant
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"))
    mandant_id = Column(Integer, ForeignKey("mandant.id"))
    art = Column(String(20), nullable=False)          # freigabe|sperre
    muster = Column(String(300), nullable=False)
    mustertyp = Column(String(20), default="woertlich", nullable=False)
    kategorie = Column(String(40))
    begruendung = Column(Text)
    urheber = Column(String(200))
    gueltig_ab = Column(DateTime, default=_jetzt, nullable=False)
    widerrufen_am = Column(DateTime)
    widerrufen_durch = Column(String(200))


class Nummernmuster(Base):
    """Mandantenspezifische Geschaefts- und Verfahrensnummern.

    Bewusst konfigurierbar und nicht fest verdrahtet: die Formate der Justiz
    sind kantonal verschieden. Ein festes Muster waere entweder zu eng (findet
    nichts) oder zu weit (blockiert alles).
    """
    __tablename__ = "nummernmuster"
    id = Column(Integer, primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    mandant_id = Column(Integer, ForeignKey("mandant.id"), nullable=False)
    kategorie = Column(String(40), nullable=False)
    regex = Column(String(300), nullable=False)
    bezeichnung = Column(String(200))
    widerrufen_am = Column(DateTime)


class Vorgang(Base):
    """Protokoll eines Prueflaufs. Bewusst ohne Klartext und ohne Prompt."""
    __tablename__ = "vorgang"
    id = Column(String(40), primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    mandant_id = Column(Integer, ForeignKey("mandant.id"), nullable=False)
    projekt_id = Column(Integer, ForeignKey("projekt.id"))
    weg = Column(String(20), nullable=False)          # chat|embedding
    entscheid = Column(String(20), nullable=False)    # durchgelassen|blockiert|abgeschaltet
    anzahl_ersetzungen = Column(Integer, default=0, nullable=False)
    anzahl_befunde = Column(Integer, default=0, nullable=False)
    modell = Column(String(120))
    dauer_ms = Column(Integer)
    erstellt_am = Column(DateTime, default=_jetzt, nullable=False)


class Befund(Base):
    __tablename__ = "befund"
    id = Column(String(40), primary_key=True)
    vorgang_id = Column(String(40), ForeignKey("vorgang.id"), nullable=False)
    kategorie = Column(String(40), nullable=False)
    band = Column(String(20), nullable=False)
    sicherheit = Column(Float)
    treffer_hash = Column(String(64), nullable=False)  # kein Klartext
    grund = Column(String(300))
    entschieden_als = Column(String(20))               # ersetzen|freigeben
    entschieden_am = Column(DateTime)
    entschieden_durch = Column(String(200))


class Ausnahme(Base):
    """Abschaltung zu Testzwecken (A6). In Produktion serverseitig verweigert."""
    __tablename__ = "ausnahme"
    id = Column(Integer, primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    mandant_id = Column(Integer, ForeignKey("mandant.id"))
    umgebung = Column(String(20), nullable=False)
    beantragt_von = Column(String(200), nullable=False)
    begruendung = Column(Text, nullable=False)
    gueltig_bis = Column(DateTime, nullable=False)
    widerrufen_am = Column(DateTime)


class Anbieterschluessel(Base):
    """Zentrale Schluesselhaltung (KONZEPT 6.4).

    Weil die Anwendungen keinen eigenen Schluessel mehr besitzen, ist das
    Umgehen der Schicht nicht mehr verboten, sondern unmoeglich.
    """
    __tablename__ = "anbieterschluessel"
    id = Column(Integer, primary_key=True)
    anwendung_id = Column(Integer, ForeignKey("anwendung.id"), nullable=False)
    mandant_id = Column(Integer, ForeignKey("mandant.id"))   # NULL = Standard
    anbieter = Column(String(40), nullable=False)            # anthropic|voyage
    chiffre = Column(Text, nullable=False)
    gueltig_ab = Column(DateTime, default=_jetzt, nullable=False)
    widerrufen_am = Column(DateTime)
