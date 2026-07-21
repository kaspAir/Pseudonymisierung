"""Abschaltung zu Testzwecken (Anforderung A6).

Eng begrenzt: nur dev/test, nur mit Berechtigung, befristet, sichtbar und auch
dann laeuft der Aufruf durch den Dienst und wird protokolliert.

Die Sperre fuer die Produktion ist ABSICHTLICH hier im Code und nicht in einer
Konfiguration. Eine Konfiguration kann man versehentlich setzen.
"""
import datetime as _dt

UMGEBUNGEN_MIT_AUSNAHME = ("develop", "test")


class AusnahmeVerweigert(Exception):
    pass


def darf_beantragt_werden(umgebung):
    return umgebung in UMGEBUNGEN_MIT_AUSNAHME


def pruefe_antrag(umgebung, berechtigt, begruendung, gueltig_bis, jetzt=None):
    """Wirft AusnahmeVerweigert, wenn der Antrag nicht zulaessig ist."""
    if not darf_beantragt_werden(umgebung):
        raise AusnahmeVerweigert(
            "In der Umgebung %r ist keine Abschaltung moeglich." % umgebung
        )
    if not berechtigt:
        raise AusnahmeVerweigert("Fehlende Berechtigung.")
    if not (begruendung or "").strip():
        raise AusnahmeVerweigert("Begruendung ist zwingend.")
    jetzt = jetzt or _dt.datetime.now(_dt.timezone.utc)
    if gueltig_bis is None or gueltig_bis <= jetzt:
        raise AusnahmeVerweigert("Eine Ausnahme muss befristet sein.")
    return True


def ist_aktiv(ausnahme, umgebung, jetzt=None):
    """Auch eine gespeicherte Ausnahme wirkt in der Produktion nie."""
    if not darf_beantragt_werden(umgebung):
        return False
    if ausnahme is None or ausnahme.widerrufen_am is not None:
        return False
    jetzt = jetzt or _dt.datetime.now(_dt.timezone.utc)
    bis = ausnahme.gueltig_bis
    if bis is not None and bis.tzinfo is None:
        bis = bis.replace(tzinfo=_dt.timezone.utc)
    return bis is not None and bis > jetzt
