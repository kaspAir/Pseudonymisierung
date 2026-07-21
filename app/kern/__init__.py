"""Kern des Dienstes: anbieterblind.

Kein Modul in diesem Paket darf ein Feld eines Anbieterprotokolls kennen.
Das Wissen darueber, wo in einer Anfrage Text steckt, gehoert ausschliesslich
in app/adapter/ (KONZEPT 3.1). Diese Trennung ist auch die Voraussetzung
dafuer, spaeter ein lokales Open-Weight-Modell als weiteren Adapter zu
ergaenzen - dort darf die Schicht bewusst durchreichen, weil kein Text das
Haus verlaesst.
"""
