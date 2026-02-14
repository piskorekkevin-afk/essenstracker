# EssenTracker

Ein moderner, KI-gestützter Ernährungstracker mit automatischer Mahlzeitenerkennung.

## Features

- **KI-Mahlzeitenerkennung**: Foto hochladen, die KI erkennt automatisch die Mahlzeit und schätzt alle Nährwerte
- **Nährwert-Tracking**: Kalorien, Protein, Kohlenhydrate, Fett, Ballaststoffe, Zucker, Natrium und mehr
- **Tägliche Limits**: Empfohlene Tageseinnahmen konfigurieren und Fortschritt verfolgen
- **Wochenplan**: Übersicht aller Mahlzeiten der Woche mit Durchschnittswerten
- **Ziele setzen**: Persönliche Ernährungsziele erstellen und tracken
- **Personalisierte Vorschläge**: KI-generierte Mahlzeitenvorschläge basierend auf dem bisherigen Essensverlauf
- **Fortschritt teilen**: Share-Link für Freunde und Familie

## Setup

```bash
# Repository klonen und in das Verzeichnis wechseln
cd essenstracker

# Virtuelle Umgebung erstellen
python -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# .env Datei erstellen
cp .env.example .env
# ANTHROPIC_API_KEY in .env eintragen

# App starten
python app.py
```

Die App läuft dann unter `http://localhost:5000`.

## Technologie-Stack

- **Backend**: Python / Flask
- **Datenbank**: SQLite (via SQLAlchemy)
- **KI**: Claude API (Anthropic) für Bilderkennung und Vorschläge
- **Frontend**: Modernes Dark-Theme UI mit Chart.js
