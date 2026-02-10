import os
import time
from typing import Dict, Tuple

import cv2
import numpy as np


class YOLOService:
    def __init__(self):
        self.model_name = os.getenv("YOLO_MODEL", "yolov8n.pt")
        self.conf = float(os.getenv("YOLO_CONF", "0.3"))
        self._model = None
        self._load_error = None

    def _ensure_model(self):
        if self._model is not None or self._load_error is not None:
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(self.model_name)
        except Exception as exc:
            self._load_error = str(exc)

    def infer(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, int], float, str]:
        start = time.perf_counter()
        self._ensure_model()

        if self._model is None:
            counts = {"person": 0}
            annotated = frame.copy()
            cv2.putText(annotated, "YOLO unavailable", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            infer_ms = (time.perf_counter() - start) * 1000
            return annotated, counts, infer_ms, f"fallback:{self._load_error or 'not_loaded'}"

        result = self._model.predict(frame, conf=self.conf, verbose=False)[0]
        annotated = result.plot()

        counts: Dict[str, int] = {}
        names = result.names
        for cls_id in result.boxes.cls.tolist() if result.boxes is not None else []:
            name = names.get(int(cls_id), str(int(cls_id)))
            counts[name] = counts.get(name, 0) + 1
        counts.setdefault("person", 0)

        infer_ms = (time.perf_counter() - start) * 1000
        return annotated, counts, infer_ms, self.model_name


yolo_service = YOLOService()
