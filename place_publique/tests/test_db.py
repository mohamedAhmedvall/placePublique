"""
Tests du module db/models.py

Vérifie :
  - L'insertion et la récupération d'une détection
  - L'agrégation des données sur les 24 dernières heures
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Ajout du répertoire racine au sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Fixture qui isole chaque test avec sa propre base de données temporaire.
    Réinitialise le moteur SQLAlchemy après chaque test.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))

    # Réinitialiser les variables globales du module db.models
    import db.models as db_module
    db_module._engine = None
    db_module._SessionLocal = None

    # Initialisation de la base avec une config cameras de test
    db_module.init_db.__wrapped__ = getattr(db_module.init_db, "__wrapped__", db_module.init_db)
    db_module._engine = db_module.get_engine()
    from sqlalchemy.orm import sessionmaker
    db_module._SessionLocal = sessionmaker(bind=db_module._engine)
    db_module.Base.metadata.create_all(db_module._engine)

    # Insérer une caméra de test
    with db_module._get_session() as session:
        from db.models import Camera
        cam = Camera(
            id="test_cam",
            name="Caméra de test",
            location="Test City",
            url="https://example.com/cam",
            active=True,
            classes=["person"],
        )
        session.add(cam)
        session.commit()

    yield

    # Nettoyage : reset du moteur après le test
    if db_module._engine:
        db_module._engine.dispose()
    db_module._engine = None
    db_module._SessionLocal = None


class TestInsertAndRetrieve:
    """Tests d'insertion et de récupération."""

    def test_insert_and_retrieve_latest(self):
        """
        Insère une Detection et vérifie qu'on peut la récupérer
        avec get_latest_detection().
        """
        from db.models import insert_detection, get_latest_detection

        # Insertion
        insert_detection(
            camera_id="test_cam",
            count=7,
            snapshot_path="static/snapshots/test_cam_latest.jpg",
        )

        # Récupération
        result = get_latest_detection("test_cam")

        assert result is not None, "get_latest_detection() ne doit pas retourner None"
        assert result["camera_id"] == "test_cam"
        assert result["count"] == 7
        assert result["class_name"] == "person"

    def test_latest_detection_returns_none_for_unknown_camera(self):
        """get_latest_detection() retourne None pour une caméra inconnue."""
        from db.models import get_latest_detection

        result = get_latest_detection("camera_inconnue_xyz")
        assert result is None

    def test_insert_multiple_returns_latest(self):
        """Après plusieurs insertions, get_latest_detection() retourne la dernière."""
        from db.models import insert_detection, get_latest_detection

        # Insérer plusieurs détections à des timestamps différents
        older_ts = datetime.utcnow() - timedelta(hours=2)
        newer_ts = datetime.utcnow() - timedelta(minutes=5)

        insert_detection("test_cam", count=3, timestamp=older_ts)
        insert_detection("test_cam", count=12, timestamp=newer_ts)
        insert_detection("test_cam", count=8, timestamp=older_ts - timedelta(hours=1))

        result = get_latest_detection("test_cam")
        assert result is not None
        assert result["count"] == 12, "Doit retourner la détection la plus récente (count=12)"

    def test_insert_preserves_timestamp(self):
        """Le timestamp inséré doit être récupéré correctement."""
        from db.models import insert_detection, get_latest_detection

        ts = datetime(2025, 6, 15, 14, 30, 0)
        insert_detection("test_cam", count=5, timestamp=ts)

        result = get_latest_detection("test_cam")
        assert result is not None

        retrieved_ts = datetime.fromisoformat(result["timestamp"])
        assert retrieved_ts.year == ts.year
        assert retrieved_ts.month == ts.month
        assert retrieved_ts.day == ts.day
        assert retrieved_ts.hour == ts.hour
        assert retrieved_ts.minute == ts.minute


class TestAggregationLast24h:
    """Tests d'agrégation des données sur les 24 dernières heures."""

    def test_aggregation_returns_non_empty_list(self):
        """
        Après insertion de 10 détections, get_counts_last_24h()
        doit retourner une liste non vide.
        """
        from db.models import insert_detection, get_counts_last_24h

        # Insérer 10 détections à des timestamps différents sur les dernières 24h
        now = datetime.utcnow()
        for i in range(10):
            ts = now - timedelta(hours=i, minutes=i * 7)
            insert_detection("test_cam", count=i + 1, timestamp=ts)

        result = get_counts_last_24h("test_cam")

        assert isinstance(result, list), "Doit retourner une liste"
        assert len(result) > 0, "La liste ne doit pas être vide après insertions"

    def test_aggregation_returns_correct_format(self):
        """
        Chaque item de get_counts_last_24h() doit avoir
        les clés 'timestamp' et 'count'.
        """
        from db.models import insert_detection, get_counts_last_24h

        now = datetime.utcnow()
        for i in range(5):
            insert_detection(
                "test_cam",
                count=i + 2,
                timestamp=now - timedelta(hours=i),
            )

        result = get_counts_last_24h("test_cam")
        assert len(result) > 0

        for item in result:
            assert "timestamp" in item, f"Clé 'timestamp' manquante dans {item}"
            assert "count" in item, f"Clé 'count' manquante dans {item}"
            assert isinstance(item["count"], int), "count doit être un entier"
            assert isinstance(item["timestamp"], str), "timestamp doit être une string"

    def test_aggregation_excludes_old_detections(self):
        """
        Les détections de plus de 24h ne doivent pas apparaître
        dans get_counts_last_24h().
        """
        from db.models import insert_detection, get_counts_last_24h

        now = datetime.utcnow()

        # Détection récente (dans les 24h)
        insert_detection("test_cam", count=10, timestamp=now - timedelta(hours=2))
        # Détection ancienne (> 24h)
        insert_detection("test_cam", count=999, timestamp=now - timedelta(hours=30))

        result = get_counts_last_24h("test_cam")

        # Vérifier qu'aucun count=999 n'est dans les résultats
        counts = [item["count"] for item in result]
        assert 999 not in counts, "Les détections > 24h ne doivent pas apparaître"

    def test_aggregation_ordered_by_timestamp(self):
        """Les résultats doivent être triés par timestamp croissant."""
        from db.models import insert_detection, get_counts_last_24h

        now = datetime.utcnow()
        timestamps = [
            now - timedelta(hours=5),
            now - timedelta(hours=1),
            now - timedelta(hours=3),
        ]
        for ts in timestamps:
            insert_detection("test_cam", count=1, timestamp=ts)

        result = get_counts_last_24h("test_cam")
        if len(result) >= 2:
            ts_values = [datetime.fromisoformat(r["timestamp"]) for r in result]
            assert ts_values == sorted(ts_values), "Les résultats doivent être triés par timestamp"

    def test_aggregation_empty_for_unknown_camera(self):
        """get_counts_last_24h() doit retourner une liste vide pour une caméra inconnue."""
        from db.models import get_counts_last_24h

        result = get_counts_last_24h("camera_inconnue_xyz")
        assert result == [], "Doit retourner une liste vide pour une caméra inconnue"


class TestGetAllCameras:
    """Tests de la fonction get_all_cameras."""

    def test_returns_list(self):
        """get_all_cameras() doit retourner une liste."""
        from db.models import get_all_cameras

        result = get_all_cameras()
        assert isinstance(result, list)

    def test_returns_active_cameras_only(self):
        """Seules les caméras actives doivent être retournées."""
        from db.models import get_all_cameras, Camera
        import db.models as db_module

        # Ajouter une caméra inactive
        with db_module._get_session() as session:
            cam = Camera(
                id="inactive_cam",
                name="Caméra inactive",
                location="Nowhere",
                url="https://example.com",
                active=False,
                classes=["person"],
            )
            session.add(cam)
            session.commit()

        cameras = get_all_cameras()
        ids = [c["id"] for c in cameras]
        assert "test_cam" in ids, "La caméra active doit être retournée"
        assert "inactive_cam" not in ids, "La caméra inactive ne doit pas être retournée"
