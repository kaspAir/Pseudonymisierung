"""Startpunkt.

Der Dienst bindet ausschliesslich auf 127.0.0.1. Unter Gunicorn:

    gunicorn run:app --bind 127.0.0.1:8040 --workers 2 --timeout 120

Sobald Stufe C (statistisches NER) aktiv wird, zusaetzlich --preload: das
Modell wird dann vor dem Fork geladen und von den Workern ueber Copy-on-Write
geteilt, statt je Worker einmal im Speicher zu liegen. Auf dem Zielhost mit
4 Kernen ist das kein Feinschliff, sondern noetig.
"""
from app.config import Config
from app.web import erzeuge_app

config = Config()
app = erzeuge_app(config)

if __name__ == "__main__":
    app.run(host=config.bind_host, port=config.port)
