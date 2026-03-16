"""
Modèles SQLAlchemy 2.0 et fonctions utilitaires pour la base de données SQLite.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml
from sqlalchemy import (
    create_engine, Column, String, Boolean, Integer, DateTime,
    ForeignKey, JSON, func, inspect
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


# --- Configuration de la base de données ---

def get_db_path() -> str:
    """Retourne le chemin vers le fichier SQLite."""
    return os.getenv("DB_PATH", str(Path(__file__).parent.parent / "data" / "counts.db"))


def get_engine():
    """Crée et retourne le moteur SQLAlchemy."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


# Moteur global (initialisé à la demande)
_engine = None
_SessionLocal = None


def _get_session() -> Session:
    """Retourne une session de base de données."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = get_engine()
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


# --- Modèles ---

class Base(DeclarativeBase):
    pass


class Camera(Base):
    """Représente une caméra configurée dans le système."""
    __tablename__ = "cameras"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    location = Column(String(256))
    url = Column(String(1024))
    active = Column(Boolean, default=True, nullable=False)
    # JSON liste des classes détectées, ex: ["person"]
    classes = Column(JSON, default=["person"])


class Detection(Base):
    """Représente une détection effectuée sur une caméra à un instant donné."""
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    class_name = Column(String(64), nullable=False, default="person")
    count = Column(Integer, nullable=False, default=0)
    snapshot_path = Column(String(512))


# --- Fonctions utilitaires ---

def init_db(cameras_config_path: str = None) -> None:
    """
    Crée les tables et insère les caméras depuis cameras.yaml si elles n'existent pas.
    """
    global _engine, _SessionLocal
    _engine = get_engine()
    _SessionLocal = sessionmaker(bind=_engine)

    Base.metadata.create_all(_engine)

    # Chargement de la configuration des caméras
    if cameras_config_path is None:
        cameras_config_path = str(
            Path(__file__).parent.parent / "config" / "cameras.yaml"
        )

    if os.path.exists(cameras_config_path):
        with open(cameras_config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        cameras_cfg = config.get("cameras", [])

        with _get_session() as session:
            for cam_cfg in cameras_cfg:
                cam_id = cam_cfg.get("id")
                if not cam_id:
                    continue
                existing = session.get(Camera, cam_id)
                if not existing:
                    camera = Camera(
                        id=cam_id,
                        name=cam_cfg.get("name", cam_id),
                        location=cam_cfg.get("location", ""),
                        url=cam_cfg.get("url", ""),
                        active=cam_cfg.get("active", True),
                        classes=cam_cfg.get("classes", ["person"]),
                    )
                    session.add(camera)
            session.commit()


def get_counts_last_24h(camera_id: str) -> List[Dict[str, Any]]:
    """
    Retourne les comptages des 24 dernières heures pour une caméra donnée.
    Retourne une liste de dicts {timestamp: str, count: int}.
    """
    since = datetime.utcnow() - timedelta(hours=24)
    with _get_session() as session:
        rows = (
            session.query(Detection)
            .filter(
                Detection.camera_id == camera_id,
                Detection.timestamp >= since,
                Detection.class_name == "person",
            )
            .order_by(Detection.timestamp.asc())
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "count": r.count,
            }
            for r in rows
        ]


def get_counts_by_hour(camera_id: str, date: datetime = None) -> List[Dict[str, Any]]:
    """
    Retourne une agrégation horaire des comptages pour une date donnée.
    Retourne une liste de dicts {hour: int, count: float}.
    """
    if date is None:
        date = datetime.utcnow().date()

    start = datetime(date.year, date.month, date.day, 0, 0, 0)
    end = start + timedelta(days=1)

    with _get_session() as session:
        rows = (
            session.query(
                func.strftime("%H", Detection.timestamp).label("hour"),
                func.avg(Detection.count).label("avg_count"),
            )
            .filter(
                Detection.camera_id == camera_id,
                Detection.timestamp >= start,
                Detection.timestamp < end,
                Detection.class_name == "person",
            )
            .group_by(func.strftime("%H", Detection.timestamp))
            .order_by(func.strftime("%H", Detection.timestamp))
            .all()
        )
        return [
            {
                "hour": int(r.hour),
                "count": round(float(r.avg_count), 2),
            }
            for r in rows
        ]


def get_latest_detection(camera_id: str) -> Optional[Dict[str, Any]]:
    """
    Retourne la dernière détection pour une caméra donnée.
    Retourne None si aucune détection n'existe.
    """
    with _get_session() as session:
        row = (
            session.query(Detection)
            .filter(
                Detection.camera_id == camera_id,
                Detection.class_name == "person",
            )
            .order_by(Detection.timestamp.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "camera_id": row.camera_id,
            "timestamp": row.timestamp.isoformat(),
            "class_name": row.class_name,
            "count": row.count,
            "snapshot_path": row.snapshot_path,
        }


def get_all_cameras() -> List[Dict[str, Any]]:
    """
    Retourne la liste de toutes les caméras actives.
    """
    with _get_session() as session:
        cameras = session.query(Camera).filter(Camera.active.is_(True)).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "url": c.url,
                "active": c.active,
                "classes": c.classes,
            }
            for c in cameras
        ]


def insert_detection(
    camera_id: str,
    count: int,
    snapshot_path: str = None,
    timestamp: datetime = None,
    class_name: str = "person",
) -> Detection:
    """
    Insère une nouvelle détection en base de données.
    Retourne l'objet Detection créé.
    """
    if timestamp is None:
        timestamp = datetime.utcnow()

    with _get_session() as session:
        det = Detection(
            camera_id=camera_id,
            timestamp=timestamp,
            class_name=class_name,
            count=count,
            snapshot_path=snapshot_path,
        )
        session.add(det)
        session.commit()
        session.refresh(det)
        return det


def get_recent_detections(camera_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retourne les N dernières détections pour une caméra donnée.
    """
    with _get_session() as session:
        rows = (
            session.query(Detection)
            .filter(
                Detection.camera_id == camera_id,
                Detection.class_name == "person",
            )
            .order_by(Detection.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "camera_id": r.camera_id,
                "timestamp": r.timestamp.isoformat(),
                "count": r.count,
                "snapshot_path": r.snapshot_path,
            }
            for r in rows
        ]
