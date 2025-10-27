<img width="984" height="645" alt="image" src="https://github.com/user-attachments/assets/95da779b-64da-4b07-be34-801207b4c027" />
<<<<<<< HEAD
# rheinpegel-python-app
=======
# Rheinpegel App

Eine moderne FastAPI-Anwendung, die den aktuellen Rheinpegel (Köln) abruft, zwischenspeichert und visuell aufbereitet. Die Anwendung kombiniert serverseitiges Polling mit einem reaktiven Frontend (AJAX, Countdown, Sparkline) und liefert zusätzlich Status- sowie Prometheus-Kennzahlen.

## Hauptfunktionen

- **Asynchrones Polling** der offiziellen Quelle via `httpx` mit Timeout (8&nbsp;s) und exponentiellem Backoff (4 Versuche).
- **Automatische Format-Erkennung** für JSON oder XML und robuste Feldzuordnung.
- **Trend-Berechnung** aus Rohdaten oder anhand der letzten Messwerte (Δ > 2 cm ⇒ ↑, Δ < −2 ⇒ ↓).
- **Mehrstufiges Caching**: In-Memory-Ringpuffer (48 Werte) + JSON-Persistenz unter `data/cache.json`.
- **Demo-Modus** bei Netzwerkfehlern oder via `?demo=1` mit synthetischen, plausiblen Messwerten.
- **FastAPI + Jinja2** Dashboard mit responsive Karte, Warnstufen, Sparkline (Inline-SVG) sowie Auto-Refresh-Toggle und Countdown.
- **Prometheus-Metriken**: letzte Latenz, Erfolgs-/Fehlerzähler, Datenalter und Health-Endpoint.

## Voraussetzungen

- Python 3.11+
- Optional: [uv](https://github.com/astral-sh/uv) für schnelle virtuelle Umgebungen

## Installation & Setup

### Variante A: uv

```bash
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e .
cp .env.example .env
```

### Variante B: pip / venv

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -e .
copy .env.example .env  # Windows
```

> **Hinweis:** Die Umgebungsvariablen (.env) steuern u.a. den Polling-Intervall (`REFRESH_SECONDS`), die Quelle (`SOURCE_URL`) und die Zeitzone (`TZ`).

## Starten der Anwendung

```bash
uvicorn app.main:app --reload
# oder
python -m app.main
```

Die Oberfläche ist anschließend unter http://127.0.0.1:8000 erreichbar.

## Wichtige Endpunkte

| Route           | Beschreibung                                   |
|-----------------|-------------------------------------------------|
| `/`             | Dashboard mit Live-Karte, Trend, Sparkline      |
| `/api/latest`   | Neueste Messung (JSON) + komplette Historie     |
| `/api/history`  | Maximal 48 Messpunkte aus dem Ringpuffer        |
| `/healthz`      | 200 OK, wenn der Hintergrund-Task aktiv ist     |
| `/metrics`      | Prometheus-kompatible Kennzahlen                |

### Demo-Modus

Alle Endpunkte akzeptieren `?demo=1`, um synthetische Daten zu liefern und das UI als „Demo“ zu markieren.

## Tests

```bash
pytest
```

Die Tests decken das Parsing (JSON/XML) sowie zentrale FastAPI-Endpunkte ab.

## Docker

```bash
docker build -t rheinpegel-app .
docker run -p 8000:8000 --env-file .env rheinpegel-app
```

Oder via Compose:

```bash
docker-compose up --build
```

Der Container läuft als Non-Root-User, besitzt einen Healthcheck (`/healthz`) und bindet `./data` für persistente Caches ein.

## Beispiel systemd Unit (optional)

```ini
[Unit]
Description=Rheinpegel App
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/rheinpegel-app
EnvironmentFile=/opt/rheinpegel-app/.env
ExecStart=/opt/rheinpegel-app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## Weiterentwicklung

- UI-Optimierungen, z. B. zusätzliche Karten oder historische Auswertungen
- Export in weitere Formate (CSV/ICS)
- Alarm-Benachrichtigungen (E-Mail, Webhooks) basierend auf Warnstufen

Viel Spaß beim Ausprobieren der Rheinpegel-App!
>>>>>>> 6c0a1e2 (Initial commit)

