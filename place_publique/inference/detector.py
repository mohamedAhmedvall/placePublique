"""
Module de détection de piétons avec YOLOv8n.

Utilise le modèle pré-entraîné COCO (sans fine-tuning).
Classe cible : "person" (class_id = 0).
Seuil de confiance : 0.4.
"""
import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Seuil de confiance pour la détection
CONFIDENCE_THRESHOLD = 0.4

# Répertoire de sauvegarde des snapshots annotés
SNAPSHOTS_DIR = Path(__file__).parent.parent / "static" / "snapshots"

# Instance globale du modèle YOLO (chargée une seule fois)
_yolo_model = None


def _get_yolo_model():
    """
    Charge et met en cache le modèle YOLOv8n.
    Retourne None en cas d'erreur de chargement.
    """
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model

    try:
        from ultralytics import YOLO
        model_name = os.getenv("YOLO_MODEL", "yolov8n.pt")
        _yolo_model = YOLO(model_name)
        logger.info("Modèle YOLO chargé : %s", model_name)
    except Exception as exc:
        logger.error("Impossible de charger le modèle YOLO : %s", exc)
        _yolo_model = None

    return _yolo_model


def _is_youtube_url(url: str) -> bool:
    """Détermine si l'URL est un lien YouTube (live ou vidéo)."""
    return any(domain in url for domain in ["youtube.com", "youtu.be"])


def _fetch_frame_from_youtube(url: str) -> Optional[np.ndarray]:
    """
    Extrait une frame d'un flux YouTube live via yt-dlp + OpenCV.
    Retourne None en cas d'échec.
    """
    try:
        import yt_dlp

        ydl_opts = {
            "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
            "quiet": True,
            "no_warnings": True,
            # Pas de téléchargement, seulement extraction des métadonnées
            "skip_download": True,
        }

        logger.info("Résolution du flux YouTube : %s", url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Récupérer l'URL du flux direct
        stream_url = None
        if "url" in info:
            stream_url = info["url"]
        elif "formats" in info:
            # Choisir le meilleur format vidéo ≤ 720p
            for fmt in reversed(info["formats"]):
                if fmt.get("vcodec") != "none" and fmt.get("height", 9999) <= 720:
                    stream_url = fmt["url"]
                    break
            if not stream_url:
                stream_url = info["formats"][-1]["url"]

        if not stream_url:
            logger.error("Aucun flux vidéo trouvé pour : %s", url)
            return None

        logger.info("Capture d'une frame depuis le flux live...")
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Lire quelques frames pour dépasser le buffer et avoir une frame récente
        frame = None
        for _ in range(5):
            ok, f = cap.read()
            if ok:
                frame = f
        cap.release()

        if frame is None:
            logger.error("Impossible de lire une frame depuis le flux : %s", stream_url[:80])
        return frame

    except ImportError:
        logger.error("yt-dlp non installé. Lancez : pip install yt-dlp")
        return None
    except Exception as exc:
        logger.error("Erreur lors de la capture YouTube %s : %s", url, exc)
        return None


def _fetch_image_from_url(url: str) -> Optional[np.ndarray]:
    """
    Télécharge une image depuis une URL HTTP.
    - URLs YouTube → yt-dlp + OpenCV VideoCapture
    - Image directe → requests
    - Page HTML     → scraping BeautifulSoup
    Timeout : 10 secondes. Retourne None en cas d'échec.
    """
    # Cas YouTube live / vidéo
    if _is_youtube_url(url):
        return _fetch_frame_from_youtube(url)

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")

        # Si c'est une image directe
        if any(ct in content_type for ct in ["image/jpeg", "image/png", "image/webp", "image/gif"]):
            arr = np.frombuffer(resp.content, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                return frame

        # Si c'est une page HTML, tenter de scraper l'image de la webcam
        if "text/html" in content_type:
            return _scrape_image_from_page(url, resp.text, headers)

        # Tenter le décodage direct même si Content-Type inconnu
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            return frame

        logger.warning("Impossible de décoder l'image depuis : %s", url)
        return None

    except requests.Timeout:
        logger.error("Timeout (10s) lors du téléchargement de : %s", url)
        return None
    except requests.RequestException as exc:
        logger.error("Erreur HTTP pour %s : %s", url, exc)
        return None
    except Exception as exc:
        logger.error("Erreur inattendue lors du téléchargement de %s : %s", url, exc)
        return None


def _scrape_image_from_page(page_url: str, html_content: str, headers: dict) -> Optional[np.ndarray]:
    """
    Tente de scraper l'image de webcam depuis une page HTML.
    Retourne None en cas d'échec.
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Sélecteurs spécifiques à Abbey Road
        selectors = [
            "img.crossing-cam",
            "img[class*='crossing']",
            "img[class*='webcam']",
            "img[class*='camera']",
            "img[class*='live']",
            "img[id*='webcam']",
            "img[id*='camera']",
            "img[id*='cam']",
        ]

        img_url = None
        for selector in selectors:
            img_tag = soup.select_one(selector)
            if img_tag and img_tag.get("src"):
                img_url = img_tag["src"]
                break

        # Fallback : prendre la plus grande image de la page
        if not img_url:
            images = soup.find_all("img")
            for img in images:
                src = img.get("src", "")
                if any(kw in src.lower() for kw in ["cam", "live", "stream", "crossing", "shibuya", "abbey"]):
                    img_url = src
                    break

        if not img_url:
            logger.warning("Aucune image de webcam trouvée sur : %s", page_url)
            return None

        # Construire l'URL absolue si nécessaire
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(page_url)
            img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
        elif not img_url.startswith("http"):
            from urllib.parse import urljoin
            img_url = urljoin(page_url, img_url)

        logger.info("Image scrapée : %s", img_url)
        resp = requests.get(img_url, headers=headers, timeout=10)
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame

    except Exception as exc:
        logger.error("Erreur lors du scraping de %s : %s", page_url, exc)
        return None


def _load_image_from_file(file_path: str) -> Optional[np.ndarray]:
    """
    Charge une image depuis un fichier local.
    Retourne None si le fichier n'existe pas ou est illisible.
    """
    try:
        frame = cv2.imread(file_path)
        if frame is None:
            logger.error("Impossible de lire l'image locale : %s", file_path)
        return frame
    except Exception as exc:
        logger.error("Erreur lors de la lecture de %s : %s", file_path, exc)
        return None


def _annotate_frame(frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
    """
    Annote l'image avec les bounding boxes et le comptage total.
    - Bounding boxes en vert avec score de confiance
    - Comptage total en haut à gauche (grande police, fond noir)
    """
    annotated = frame.copy()
    count = len(detections)

    # Dessiner les bounding boxes
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        conf = det["confidence"]
        # Bounding box en vert
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        # Étiquette de confiance
        label = f"{conf:.2f}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - label_size[1] - 4), (x1 + label_size[0], y1), (0, 255, 0), -1)
        cv2.putText(
            annotated, label,
            (x1, y1 - 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (0, 0, 0), 1
        )

    # Comptage total en haut à gauche
    count_text = f"Personnes : {count}"
    font_scale = 1.5
    thickness = 3
    text_size, _ = cv2.getTextSize(count_text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness)
    padding = 10

    # Fond noir semi-transparent
    overlay = annotated.copy()
    cv2.rectangle(
        overlay,
        (0, 0),
        (text_size[0] + 2 * padding, text_size[1] + 2 * padding + 10),
        (0, 0, 0),
        -1
    )
    cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)

    # Texte blanc
    cv2.putText(
        annotated, count_text,
        (padding, text_size[1] + padding),
        cv2.FONT_HERSHEY_DUPLEX, font_scale,
        (255, 255, 255), thickness
    )

    return annotated


def _create_empty_result(camera_id: str, error_msg: str = "") -> Dict:
    """Retourne un résultat vide avec count=0 en cas d'erreur."""
    if error_msg:
        logger.warning("Détection échouée pour %s : %s", camera_id, error_msg)
    return {
        "camera_id": camera_id,
        "timestamp": datetime.utcnow().isoformat(),
        "count": 0,
        "annotated_image_b64": "",
        "detections": [],
        "error": error_msg,
    }


def detect(camera_id: str, image_source: str) -> Dict[str, Any]:
    """
    Détecte les piétons sur une image et retourne les résultats.

    Args:
        camera_id: Identifiant de la caméra (ex: "abbey_road")
        image_source: URL HTTP ou chemin fichier local vers l'image

    Returns:
        dict avec les clés :
            - camera_id: str
            - timestamp: str (ISO 8601)
            - count: int
            - annotated_image_b64: str (image annotée en base64)
            - detections: list[{confidence, bbox}]
            - error: str (vide si succès)
    """
    # Chargement de l'image depuis la source
    frame = None

    if image_source.startswith("http://") or image_source.startswith("https://"):
        frame = _fetch_image_from_url(image_source)
    else:
        frame = _load_image_from_file(image_source)

    if frame is None:
        return _create_empty_result(camera_id, f"Impossible de charger l'image depuis : {image_source}")

    # Chargement du modèle YOLO
    model = _get_yolo_model()
    if model is None:
        return _create_empty_result(camera_id, "Modèle YOLO indisponible")

    # Inférence
    try:
        results = model.predict(frame, conf=CONFIDENCE_THRESHOLD, classes=[0], verbose=False)
        result = results[0]

        detections = []
        if result.boxes is not None:
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < CONFIDENCE_THRESHOLD:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "confidence": round(conf, 4),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                })

    except Exception as exc:
        logger.error("Erreur lors de l'inférence YOLO pour %s : %s", camera_id, exc)
        return _create_empty_result(camera_id, f"Erreur d'inférence : {exc}")

    count = len(detections)

    # Annotation de l'image
    annotated = _annotate_frame(frame, detections)

    # Sauvegarde du snapshot annoté
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOTS_DIR / f"{camera_id}_latest.jpg"
    try:
        cv2.imwrite(str(snapshot_path), annotated)
    except Exception as exc:
        logger.warning("Impossible de sauvegarder le snapshot pour %s : %s", camera_id, exc)

    # Encodage base64 de l'image annotée
    try:
        _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
    except Exception as exc:
        logger.warning("Impossible d'encoder l'image en base64 : %s", exc)
        annotated_b64 = ""

    logger.info(
        "%s : %d piéton(s) détecté(s) à %s",
        camera_id,
        count,
        datetime.utcnow().strftime("%H:%M"),
    )

    return {
        "camera_id": camera_id,
        "timestamp": datetime.utcnow().isoformat(),
        "count": count,
        "annotated_image_b64": annotated_b64,
        "detections": detections,
        "error": "",
    }
