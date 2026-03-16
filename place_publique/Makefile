# Makefile — Place Publique / FlowView
# Usage : make <cible>

.PHONY: build up down logs shell demo test trigger restart dev fixtures

## Construire l'image Docker
build:
	docker compose build

## Démarrer les services en arrière-plan
up:
	docker compose up -d

## Arrêter les services
down:
	docker compose down

## Afficher les logs en temps réel
logs:
	docker compose logs -f web

## Ouvrir un shell dans le conteneur web
shell:
	docker compose exec web bash

## Lancer le mode démo (sans internet, données simulées sur 24h)
demo:
	docker compose run --rm web python demo_mode.py

## Exécuter les tests pytest
test:
	docker compose run --rm web pytest tests/ -v

## Déclencher manuellement une détection sur toutes les caméras
trigger:
	curl -X POST http://localhost:5000/api/trigger

## Redémarrer le conteneur web
restart:
	docker compose restart web

## Mode développement Flask avec rechargement automatique
dev:
	flask --app app run --host 0.0.0.0 --port 5000 --debug

## Capturer des frames réelles depuis les webcams YouTube pour les fixtures de test
fixtures:
	docker compose run --rm web python -c "\
import sys; sys.path.insert(0,'.');\
from inference.detector import _fetch_frame_from_youtube;\
import cv2;\
cams = {'abbey_road':'https://www.youtube.com/live/M3EYAY2MftI','shibuya':'https://www.youtube.com/live/dfVK7ld38Ys'};\
[cv2.imwrite(f'tests/fixtures/{k}.jpg', f, [cv2.IMWRITE_JPEG_QUALITY,92]) or print(f'✓ {k}') for k,u in cams.items() if (f:=_fetch_frame_from_youtube(u)) is not None]\
"
