"""Datenbankanbindung."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def maschine_fuer(url):
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        pfad = url.replace("sqlite:///", "")
        if pfad and pfad != ":memory:":
            verzeichnis = os.path.dirname(os.path.abspath(pfad))
            if verzeichnis:
                os.makedirs(verzeichnis, exist_ok=True)
    return create_engine(url, **kwargs)


def richte_ein(url):
    """Erzeugt Maschine und Sitzungsfabrik und legt fehlende Tabellen an."""
    maschine = maschine_fuer(url)
    Base.metadata.create_all(maschine)
    return maschine, sessionmaker(bind=maschine, future=True)
