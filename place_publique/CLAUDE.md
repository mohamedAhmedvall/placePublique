# CLAUDE.md — Place Publique / FlowView

Documentation technique pour les ingénieurs et agents IA travaillant sur ce projet.

---

## Architecture technique

```
┌─────────────────────────────────────────────────────────┐
│                  PIPELINE COMPLET                       │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │  Abbey Road  │    │   Shibuya    │  ← Webcams HTTP  │
│  │  (Londres)   │    │   (Tokyo)    │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                  │                            │
│         └────────┬─────────┘                            │
│                  ▼                                       │
│  ┌──────────────────────────┐                           │
│  │  inference/scheduler.py  │  ← APScheduler (5 min)   │
│  │  BackgroundScheduler     │                           │
│  └──────────────┬───────────┘                           │
│                 ▼                                        │
│  ┌──────────────────────────┐                           │
│  │  inference/detector.py   │  ← YOLOv8n COCO          │
│  │  detect(camera_id, url)  │    conf >= 0.4            │
│  └──────┬───────────────────┘    class: person (0)      │
│         │                                               │
│    ┌────┴────────────────────┐                          │
│    │         Résultats       │                          │
│    │  - count: int           │                          │
│    │  - detections: list     │                          │
│    │  - annotated_image_b64  │                          │
│    └────┬────────────────────┘                          │
│         │                                               │
│    ┌────▼────────────────────┐                          │
│    │  db/models.py (SQLite)  │  ← SQLAlchemy 2.0        │
│    │  - Camera               │                          │
│    │  - Detection            │                          │
│    └────┬────────────────────┘                          │
│         │                                               │
│  ┌──────▼───────────────────────────────────────────┐  │
│  │  Flask API (app/routes.py)                       │  │
│  │  GET /            → Dashboard index.html         │  │
│  │  GET /camera/<id> → Détail camera.html           │  │
│  │  GET /api/counts  → JSON 24h                     │  │
│  │  POST /api/trigger→ Détection manuelle           │  │
│  │  GET /health      → Healthcheck                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │  Frontend (Bootstrap 5 + Chart.js)             │    │
│  │  - Dashboard : 2 cartes + graphique comparatif │    │
│  │  - Détail caméra : snapshot + barres horaires  │    │
│  │  - Auto-refresh 60s via fetch(/api/counts)     │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## Choix de YOLOv8n

**Pourquoi YOLOv8n (nano) ?**

| Critère | YOLOv8n | YOLOv8s | YOLOv8m |
|---------|---------|---------|---------|
| Taille  | 6 MB    | 22 MB   | 52 MB   |
| Vitesse CPU | ~50ms | ~120ms | ~250ms |
| mAP50-95 | 37.3   | 44.9   | 50.2   |

- **CPU-only** : YOLOv8n est suffisant pour des images statiques (non-temps réel)
- **Pré-entraîné COCO** : contient déjà la classe `person` (class_id=0)
- **Pas de fine-tuning** : évite toute dépendance à des données propriétaires
- **Légèreté** : idéal pour un conteneur Docker sans GPU

---

## Schéma de la base de données

```sql
-- Table cameras
cameras (
    id          TEXT PRIMARY KEY,     -- ex: "abbey_road"
    name        TEXT NOT NULL,
    location    TEXT,
    url         TEXT,
    active      BOOLEAN DEFAULT TRUE,
    classes     JSON                  -- ex: ["person"]
)

-- Table detections
detections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id     TEXT REFERENCES cameras(id),
    timestamp     DATETIME NOT NULL,
    class_name    TEXT DEFAULT "person",
    count         INTEGER NOT NULL,
    snapshot_path TEXT
)
```

---

## Ajouter une nouvelle caméra

1. Éditer `config/cameras.yaml` :

```yaml
cameras:
  - id: new_cam_id          # Identifiant unique (snake_case)
    name: "Nom affiché"
    location: "Ville, Pays"
    url: "https://url-de-la-webcam"
    scrape_selector: "img"  # Sélecteur CSS pour scraper l'image
    active: true
    classes: ["person"]
    interval_minutes: 5
```

2. Redémarrer l'application : `make restart`

La caméra sera automatiquement ajoutée en base et détectée par le scheduler.

---

## Changer le modèle YOLO

Pour passer de nano → small → medium :

1. Via variable d'environnement :

```bash
# Dans docker-compose.yml ou .env
YOLO_MODEL=yolov8s.pt   # small
YOLO_MODEL=yolov8m.pt   # medium
```

2. Le modèle sera téléchargé automatiquement lors du premier lancement.

3. Pour pré-télécharger au build time, modifier `Dockerfile` :

```dockerfile
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"
```

---

## Mode Fallback

Le système est conçu pour **ne jamais crasher** à cause d'une caméra inaccessible :

```
Requête HTTP → Timeout 10s → ERREUR
                                 ↓
                    Log WARNING + count = 0
                                 ↓
                    Continue vers caméra suivante
```

**Niveaux de fallback :**
1. URL principale inaccessible → log + count=0
2. Modèle YOLO indisponible → log + count=0
3. Erreur d'encodage image → log + annotated_image_b64=""

Aucune de ces erreurs ne fait planter le scheduler ni le serveur Flask.

---

## Commandes de développement fréquentes

```bash
# Démarrer en développement (rechargement automatique)
make dev

# Voir les logs en temps réel
make logs

# Déclencher manuellement une détection
make trigger
# ou :
curl -X POST http://localhost:5000/api/trigger \
  -H "Content-Type: application/json" \
  -d '{"camera_id": "abbey_road"}'

# Ouvrir un shell dans le conteneur
make shell

# Lancer les tests
make test

# Mode démo sans internet
make demo

# Reconstruire après modification des dépendances
make down && make build && make up
```

---

## Structure des fichiers clés

```
place_publique/
├── config/cameras.yaml     ← Configuration des caméras
├── inference/
│   ├── detector.py         ← detect(camera_id, url) → dict
│   └── scheduler.py        ← APScheduler BackgroundScheduler
├── db/
│   └── models.py           ← SQLAlchemy models + fonctions utilitaires
├── app/
│   ├── routes.py           ← Flask factory + routes
│   └── templates/
│       ├── base.html       ← Layout Bootstrap 5 thème sombre
│       ├── index.html      ← Dashboard principal
│       └── camera.html     ← Page détail caméra
├── static/
│   ├── js/charts.js        ← Chart.js comparatif + horaire
│   └── snapshots/          ← Snapshots annotés (runtime)
├── demo_mode.py            ← Démonstration sans internet
└── tests/
    ├── test_detector.py
    └── test_db.py
```
