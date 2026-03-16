"""
Planificateur APScheduler pour la détection automatique.

Exécute detect() pour chaque caméra active selon l'intervalle
défini dans cameras.yaml (défaut : 5 minutes).
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Any

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# Instance globale du scheduler
_scheduler: BackgroundScheduler = None


def _load_cameras_config(config_path: str = None) -> List[Dict[str, Any]]:
    """Charge la configuration des caméras depuis cameras.yaml."""
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent / "config" / "cameras.yaml"
        )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("cameras", [])
    except Exception as exc:
        logger.error("Impossible de charger la configuration cameras.yaml : %s", exc)
        return []


def _run_detection_for_camera(camera_config: Dict[str, Any]) -> None:
    """
    Exécute la détection pour une caméra et sauvegarde le résultat en base.
    En cas d'erreur, log un WARNING et continue sans bloquer les autres caméras.
    """
    camera_id = camera_config.get("id", "unknown")
    camera_url = camera_config.get("url", "")

    if not camera_config.get("active", True):
        return

    try:
        # Import ici pour éviter les imports circulaires
        from inference.detector import detect
        from db.models import insert_detection

        result = detect(camera_id, camera_url)
        count = result.get("count", 0)
        timestamp_str = result.get("timestamp", "")

        # Chemin du snapshot
        snapshot_path = f"static/snapshots/{camera_id}_latest.jpg"

        # Sauvegarde en base de données
        insert_detection(
            camera_id=camera_id,
            count=count,
            snapshot_path=snapshot_path,
        )

        # Log lisible
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(timestamp_str)
            ts_fmt = ts.strftime("%H:%M")
        except Exception:
            ts_fmt = timestamp_str

        logger.info(
            "%s : %d piéton(s) détecté(s) à %s",
            camera_config.get("name", camera_id),
            count,
            ts_fmt,
        )

    except Exception as exc:
        logger.warning(
            "Détection échouée pour la caméra %s : %s",
            camera_id,
            exc,
        )


def _run_all_cameras(cameras: List[Dict[str, Any]]) -> None:
    """Exécute la détection pour toutes les caméras actives."""
    for camera_config in cameras:
        if camera_config.get("active", True):
            _run_detection_for_camera(camera_config)


def start_scheduler(config_path: str = None) -> BackgroundScheduler:
    """
    Démarre le scheduler APScheduler en arrière-plan.
    Crée un job par caméra active avec son intervalle configuré.
    Retourne l'instance du scheduler.
    """
    global _scheduler

    # Arrêter le scheduler existant si nécessaire
    if _scheduler is not None and _scheduler.running:
        logger.info("Arrêt du scheduler existant")
        _scheduler.shutdown(wait=False)

    cameras = _load_cameras_config(config_path)

    if not cameras:
        logger.warning("Aucune caméra trouvée dans la configuration")
        return None

    # Vérifier si le scheduler est activé via variable d'environnement
    if os.getenv("SCHEDULER_ENABLED", "true").lower() == "false":
        logger.info("Scheduler désactivé via SCHEDULER_ENABLED=false")
        return None

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Regrouper les caméras par intervalle pour optimiser les jobs
    intervals: Dict[int, List[Dict]] = {}
    for cam in cameras:
        if not cam.get("active", True):
            continue
        interval = cam.get("interval_minutes", 5)
        intervals.setdefault(interval, []).append(cam)

    for interval_minutes, cams in intervals.items():
        cam_ids = [c["id"] for c in cams]
        logger.info(
            "Planification de %d caméra(s) toutes les %d minutes : %s",
            len(cams),
            interval_minutes,
            ", ".join(cam_ids),
        )
        _scheduler.add_job(
            func=_run_all_cameras,
            args=[cams],
            trigger="interval",
            minutes=interval_minutes,
            id=f"detection_interval_{interval_minutes}min",
            max_instances=1,
            replace_existing=True,
        )

    _scheduler.start()
    logger.info("Scheduler démarré avec %d job(s)", len(intervals))

    return _scheduler


def run_now(camera_id: str = None, config_path: str = None) -> List[Dict]:
    """
    Déclenche manuellement une détection immédiate.
    Si camera_id est None, déclenche toutes les caméras actives.
    Retourne la liste des résultats.
    """
    cameras = _load_cameras_config(config_path)
    results = []

    for cam in cameras:
        if not cam.get("active", True):
            continue
        if camera_id is not None and cam["id"] != camera_id:
            continue

        try:
            from inference.detector import detect
            from db.models import insert_detection
            from datetime import datetime

            result = detect(cam["id"], cam["url"])
            snapshot_path = f"static/snapshots/{cam['id']}_latest.jpg"
            insert_detection(
                camera_id=cam["id"],
                count=result.get("count", 0),
                snapshot_path=snapshot_path,
            )
            results.append(result)

        except Exception as exc:
            logger.warning("Déclenchement manuel échoué pour %s : %s", cam["id"], exc)
            results.append({
                "camera_id": cam["id"],
                "count": 0,
                "error": str(exc),
            })

    return results


def stop_scheduler() -> None:
    """Arrête le scheduler proprement."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler arrêté")
