# Place Publique — FlowView

**Comptage automatique de piétons sur webcams publiques iconiques.**

| Abbey Road (Londres) | Shibuya (Tokyo) |
|---------------------|-----------------|
| YOLOv8n détection   | YOLOv8n détection |

## Démarrage rapide

```bash
# Construire et démarrer
make build && make up

# Dashboard disponible sur :
open http://localhost:5000

# Mode démo (sans internet, données simulées 24h)
make demo
```

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Détection | YOLOv8n (Ultralytics, COCO pré-entraîné) |
| Backend   | Flask 3.0 + SQLAlchemy 2.0 + APScheduler |
| Base de données | SQLite (léger, sans serveur) |
| Frontend  | Bootstrap 5 (thème sombre) + Chart.js |
| Conteneurisation | Docker + Gunicorn |

## Architecture

```
Webcam (HTTP) → detector.py (YOLOv8n) → SQLite → Flask API → Dashboard
                     ↑
              scheduler.py (APScheduler, 5 min)
```

## Routes disponibles

| Route | Description |
|-------|-------------|
| `GET /` | Dashboard principal |
| `GET /camera/<id>` | Page détail caméra |
| `GET /api/counts` | JSON des comptages 24h |
| `POST /api/trigger` | Déclencher une détection |
| `GET /health` | Healthcheck |

## Configuration

Modifier `config/cameras.yaml` pour ajouter/modifier des caméras :

```yaml
cameras:
  - id: abbey_road
    name: "Abbey Road Crossing"
    location: "Londres, UK"
    url: "https://www.abbeyroad.com/crossing"
    active: true
    interval_minutes: 5
```

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DB_PATH` | `data/counts.db` | Chemin SQLite |
| `CAMERAS_CONFIG` | `config/cameras.yaml` | Config caméras |
| `SCHEDULER_ENABLED` | `true` | Activer le scheduler |
| `YOLO_MODEL` | `yolov8n.pt` | Modèle YOLO |

## Commandes utiles

```bash
make build      # Construire l'image Docker
make up         # Démarrer en arrière-plan
make down       # Arrêter
make logs       # Voir les logs
make test       # Exécuter les tests
make demo       # Mode démo sans internet
make trigger    # Déclencher une détection manuelle
make dev        # Mode développement Flask
```

## Tests

```bash
make test
# ou localement :
pytest tests/ -v
```
