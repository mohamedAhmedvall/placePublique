"""
Tests du module inference/detector.py

Vérifie :
  - La détection sur une image locale (crowd.jpg)
  - Le comportement en cas d'URL invalide (fallback gracieux)
  - Le seuil de confiance (>= 0.4)
"""
import logging
import os
import sys
from pathlib import Path

import pytest

# Ajout du répertoire racine au sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Chemin vers l'image de test
CROWD_IMAGE = ROOT / "tests" / "fixtures" / "crowd.jpg"


@pytest.fixture(scope="session", autouse=True)
def ensure_crowd_image():
    """Crée l'image de test si elle n'existe pas."""
    CROWD_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    if not CROWD_IMAGE.exists():
        _create_test_image(str(CROWD_IMAGE))
    yield


def _create_test_image(path: str):
    """Génère une image de test avec des silhouettes humaines."""
    try:
        import cv2
        import numpy as np

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (45, 50, 55)

        # Quelques silhouettes simplifiées
        for x in [100, 200, 300, 400, 500]:
            cv2.circle(img, (x, 150), 20, (200, 180, 160), -1)
            cv2.rectangle(img, (x - 15, 170), (x + 15, 260), (150, 150, 150), -1)

        cv2.imwrite(path, img)
    except Exception as exc:
        # Si cv2 n'est pas disponible, créer un fichier JPEG minimal valide
        import struct
        # JPEG minimal 1x1 pixel blanc
        minimal_jpg = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD2, 0x8A, 0x28, 0x03, 0xFF, 0xD9,
        ])
        with open(path, 'wb') as f:
            f.write(minimal_jpg)


class TestDetectWithLocalImage:
    """Tests de détection avec une image locale."""

    def test_detect_returns_required_keys(self):
        """Vérifie que detect() retourne un dict avec toutes les clés requises."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))

        assert isinstance(result, dict), "Le résultat doit être un dictionnaire"
        assert "camera_id" in result, "Clé 'camera_id' manquante"
        assert "timestamp" in result, "Clé 'timestamp' manquante"
        assert "count" in result, "Clé 'count' manquante"
        assert "annotated_image_b64" in result, "Clé 'annotated_image_b64' manquante"
        assert "detections" in result, "Clé 'detections' manquante"

    def test_detect_camera_id_preserved(self):
        """Vérifie que camera_id est correctement transmis dans le résultat."""
        from inference.detector import detect

        result = detect("abbey_road", str(CROWD_IMAGE))
        assert result["camera_id"] == "abbey_road"

    def test_detect_count_non_negative(self):
        """Vérifie que count est un entier >= 0."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))
        assert isinstance(result["count"], int), "count doit être un entier"
        assert result["count"] >= 0, "count doit être >= 0"

    def test_detect_annotated_image_is_non_empty_string(self):
        """Vérifie que annotated_image_b64 est une chaîne non vide (si pas d'erreur)."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))
        # Si pas d'erreur critique, l'image annotée doit être une string
        assert isinstance(result["annotated_image_b64"], str), \
            "annotated_image_b64 doit être une string"
        # La string peut être vide en cas d'erreur d'encodage, mais doit exister
        if not result.get("error"):
            assert len(result["annotated_image_b64"]) > 0, \
                "annotated_image_b64 ne doit pas être vide si pas d'erreur"

    def test_detect_timestamp_is_iso_format(self):
        """Vérifie que le timestamp est au format ISO 8601."""
        from inference.detector import detect
        from datetime import datetime

        result = detect("test_cam", str(CROWD_IMAGE))
        ts = result["timestamp"]
        assert isinstance(ts, str), "timestamp doit être une string"

        try:
            datetime.fromisoformat(ts)
        except ValueError:
            pytest.fail(f"Le timestamp '{ts}' n'est pas au format ISO 8601")

    def test_detect_detections_is_list(self):
        """Vérifie que detections est une liste."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))
        assert isinstance(result["detections"], list), "detections doit être une liste"


class TestDetectFallbackOnBadUrl:
    """Tests du comportement en cas d'URL invalide."""

    def test_no_exception_on_bad_url(self):
        """detect() ne doit pas lever d'exception avec une URL invalide."""
        from inference.detector import detect

        # URL invalide — ne doit pas crasher
        try:
            result = detect("test_cam", "https://url-qui-nexiste-pas-du-tout-xyz.invalid/image.jpg")
        except Exception as exc:
            pytest.fail(f"detect() a levé une exception avec une URL invalide : {exc}")

    def test_count_zero_on_bad_url(self):
        """count == 0 quand l'URL est invalide."""
        from inference.detector import detect

        result = detect("test_cam", "https://url-qui-nexiste-pas.invalid/cam.jpg")
        assert result["count"] == 0, "count doit être 0 si l'image est inaccessible"

    def test_no_exception_on_nonexistent_file(self):
        """detect() ne doit pas lever d'exception avec un fichier inexistant."""
        from inference.detector import detect

        try:
            result = detect("test_cam", "/chemin/qui/nexiste/pas/image.jpg")
        except Exception as exc:
            pytest.fail(f"detect() a levé une exception avec un fichier inexistant : {exc}")

    def test_count_zero_on_nonexistent_file(self):
        """count == 0 si le fichier local n'existe pas."""
        from inference.detector import detect

        result = detect("test_cam", "/chemin/qui/nexiste/pas/image.jpg")
        assert result["count"] == 0

    def test_error_message_logged_on_bad_url(self, caplog):
        """Un message d'erreur doit être loggé en cas d'URL invalide."""
        from inference.detector import detect

        with caplog.at_level(logging.ERROR, logger="inference.detector"):
            result = detect("test_cam", "https://url-invalide-xyz.invalid/cam.jpg")

        # Vérifier qu'il y a eu au moins un log d'erreur ou warning
        assert len(caplog.records) > 0 or result.get("error"), \
            "Une erreur doit être loggée ou reportée dans le résultat"


class TestConfidenceThreshold:
    """Tests du seuil de confiance."""

    def test_detections_confidence_above_threshold(self):
        """Toutes les détections doivent avoir confidence >= 0.4."""
        from inference.detector import detect, CONFIDENCE_THRESHOLD

        result = detect("test_cam", str(CROWD_IMAGE))

        for i, det in enumerate(result["detections"]):
            assert "confidence" in det, f"Clé 'confidence' manquante dans detections[{i}]"
            assert det["confidence"] >= CONFIDENCE_THRESHOLD, (
                f"Detection [{i}] a confidence={det['confidence']} < {CONFIDENCE_THRESHOLD}"
            )

    def test_detections_have_bbox(self):
        """Toutes les détections doivent avoir un bbox valide."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))

        for i, det in enumerate(result["detections"]):
            assert "bbox" in det, f"Clé 'bbox' manquante dans detections[{i}]"
            bbox = det["bbox"]
            assert len(bbox) == 4, f"bbox doit avoir 4 valeurs, reçu : {bbox}"
            x1, y1, x2, y2 = bbox
            assert x2 > x1, f"x2 ({x2}) doit être > x1 ({x1})"
            assert y2 > y1, f"y2 ({y2}) doit être > y1 ({y1})"

    def test_count_matches_detections_length(self):
        """count doit correspondre au nombre d'éléments dans detections."""
        from inference.detector import detect

        result = detect("test_cam", str(CROWD_IMAGE))
        assert result["count"] == len(result["detections"]), \
            f"count={result['count']} != len(detections)={len(result['detections'])}"
