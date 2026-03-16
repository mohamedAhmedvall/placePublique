"""
Routes Flask pour le dashboard Place Publique.

Routes disponibles :
  GET  /                    → Dashboard principal
  GET  /camera/<camera_id>  → Page détail caméra
  GET  /api/counts          → JSON des comptages
  POST /api/trigger         → Déclencher une détection manuelle
  GET  /health              → Healthcheck
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

logger = logging.getLogger(__name__)

# Chemin de configuration par défaut
DEFAULT_CAMERAS_CONFIG = str(
    Path(__file__).parent.parent / "config" / "cameras.yaml"
)


def _load_cameras_config(config_path: str = None) -> list:
    """Charge la liste des caméras depuis cameras.yaml."""
    path = config_path or os.getenv("CAMERAS_CONFIG", DEFAULT_CAMERAS_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("cameras", [])
    except Exception as exc:
        logger.error("Erreur de lecture des caméras : %s", exc)
        return []


def create_app() -> Flask:
    """
    Fabrique applicative Flask.
    Initialise la base de données, démarre le scheduler et enregistre les routes.
    """
    # Ajout du répertoire parent au sys.path pour les imports absolus
    project_root = str(Path(__file__).parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder=str(Path(__file__).parent.parent / "static"),
        static_url_path="/static",
    )

    # --- Initialisation de la base de données ---
    try:
        from db.models import init_db
        init_db(os.getenv("CAMERAS_CONFIG", DEFAULT_CAMERAS_CONFIG))
        logger.info("Base de données initialisée")
    except Exception as exc:
        logger.error("Erreur d'initialisation de la base de données : %s", exc)

    # --- Démarrage du scheduler ---
    try:
        from inference.scheduler import start_scheduler
        start_scheduler(os.getenv("CAMERAS_CONFIG", DEFAULT_CAMERAS_CONFIG))
    except Exception as exc:
        logger.error("Erreur de démarrage du scheduler : %s", exc)

    # ==================== ROUTES ====================

    @app.route("/health")
    def health():
        """Healthcheck : retourne {"status": "ok", "timestamp": "..."}"""
        return jsonify({
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
        })

    @app.route("/")
    def index():
        """
        Dashboard principal.
        Affiche les deux caméras côte à côte avec le dernier snapshot,
        le nombre de piétons et un graphique comparatif Chart.js.
        """
        try:
            from db.models import get_all_cameras, get_latest_detection, get_counts_last_24h
        except Exception as exc:
            logger.error("Erreur import modèles : %s", exc)
            return render_template("index.html", cameras=[], cameras_data={}, error=str(exc))

        cameras = get_all_cameras()
        cameras_data = {}

        for cam in cameras:
            cam_id = cam["id"]
            latest = get_latest_detection(cam_id)
            history = get_counts_last_24h(cam_id)
            snapshot_url = f"/static/snapshots/{cam_id}_latest.jpg"
            cameras_data[cam_id] = {
                "info": cam,
                "latest": latest,
                "history_24h": history,
                "snapshot_url": snapshot_url,
            }

        return render_template(
            "index.html",
            cameras=cameras,
            cameras_data=cameras_data,
        )

    @app.route("/camera/<camera_id>")
    def camera_detail(camera_id: str):
        """
        Page détail d'une caméra.
        Affiche le snapshot live annoté, un graphique par heure et les 20 dernières détections.
        """
        try:
            from db.models import get_latest_detection, get_counts_last_24h, get_counts_by_hour, get_recent_detections
        except Exception as exc:
            return f"Erreur : {exc}", 500

        cameras_cfg = _load_cameras_config()
        cam_info = next((c for c in cameras_cfg if c["id"] == camera_id), None)

        if not cam_info:
            return "Caméra introuvable", 404

        latest = get_latest_detection(camera_id)
        history_24h = get_counts_last_24h(camera_id)
        by_hour = get_counts_by_hour(camera_id)
        recent = get_recent_detections(camera_id, limit=20)
        snapshot_url = f"/static/snapshots/{camera_id}_latest.jpg"

        return render_template(
            "camera.html",
            camera=cam_info,
            latest=latest,
            history_24h=history_24h,
            by_hour=by_hour,
            recent_detections=recent,
            snapshot_url=snapshot_url,
        )

    @app.route("/api/counts")
    def api_counts():
        """
        Retourne les comptages JSON pour toutes les caméras actives.
        """
        try:
            from db.models import get_all_cameras, get_latest_detection, get_counts_last_24h
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        cameras = get_all_cameras()
        result = []

        for cam in cameras:
            cam_id = cam["id"]
            latest = get_latest_detection(cam_id)
            history = get_counts_last_24h(cam_id)

            result.append({
                "camera_id": cam_id,
                "name": cam["name"],
                "latest_count": latest["count"] if latest else 0,
                "latest_timestamp": latest["timestamp"] if latest else None,
                "snapshot_url": f"/static/snapshots/{cam_id}_latest.jpg",
                "history_24h": history,
            })

        return jsonify(result)

    @app.route("/api/trigger", methods=["POST"])
    def api_trigger():
        """
        Déclenche manuellement une détection immédiate.
        Body JSON optionnel : {"camera_id": "abbey_road"}
        Si absent : déclenche toutes les caméras.
        """
        try:
            from inference.scheduler import run_now
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

        data = request.get_json(silent=True) or {}
        camera_id = data.get("camera_id")

        try:
            results = run_now(camera_id=camera_id)
            return jsonify({
                "status": "ok",
                "results": [
                    {
                        "camera_id": r.get("camera_id"),
                        "count": r.get("count", 0),
                        "timestamp": r.get("timestamp"),
                        "error": r.get("error", ""),
                    }
                    for r in results
                ],
            })
        except Exception as exc:
            logger.error("Erreur lors du déclenchement manuel : %s", exc)
            return jsonify({"status": "error", "message": str(exc)}), 500

    return app
