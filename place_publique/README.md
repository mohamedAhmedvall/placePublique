# Place Publique (MVP)

Application Flask pour compter et visualiser la fréquentation de webcams publiques (Abbey Road + Shibuya) via détection YOLO.

## Stack
- Python 3.11+
- Flask + Jinja2 + Chart.js
- SQLite + SQLAlchemy
- Ultralytics YOLOv8n (CPU)
- APScheduler (worker séparé)

## Lancer en local
```bash
docker compose -f compose.yaml up --build
```

Web: `http://localhost:8000`

## Variables d'override (prioritaires)
Si le resolver ne trouve pas de lien média direct depuis la page HTML:
```bash
CAM_ABBEY_SNAPSHOT_URL=...
CAM_ABBEY_STREAM_URL=...
CAM_SHIBUYA_SNAPSHOT_URL=...
CAM_SHIBUYA_STREAM_URL=...
```

## Architecture
- `web` (gunicorn): UI + APIs + endpoint Live MJPEG `/live/<camera_id>.mjpg`
- `worker` (APScheduler): snapshot -> inférence -> SQLite + image annotée
- DB: `/data/app.db`
- images annotées: `/data/annotated/<camera_id>.jpg`

## Endpoints
- `GET /health`
- `GET /api/kpis?range=24h|7d`
- `GET /api/counts?camera_id=&from=&to=&granularity=minute|hour|day`

## Déploiement Dokploy
1. Build depuis le repo.
2. Exposer le port `8000`.
3. Monter un volume persistant sur `/data`.
4. Configurer un healthcheck sur `/health`.
5. Déployer `web` et `worker` séparément (recommandé) pour éviter la duplication du scheduler.

## Notes resolver
Le module providers implémente une extraction simple (regex + BeautifulSoup) des URLs `m3u8/mp4/jpg/png` présentes dans le HTML EarthCam/Skyline.
Si aucun lien n'est détecté, l'application continue de fonctionner et l'UI Settings affiche `needs override`.
