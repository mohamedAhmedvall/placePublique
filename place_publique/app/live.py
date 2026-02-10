import threading
import time
from typing import Dict, Optional

import cv2
import numpy as np
import requests

from .yolo_infer import yolo_service


class LiveCameraState:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame_cond = threading.Condition(self.lock)
        self.latest_jpeg: Optional[bytes] = None
        self.running = False
        self.clients = 0
        self.thread: Optional[threading.Thread] = None


_states: Dict[str, LiveCameraState] = {}
_global_lock = threading.Lock()


def _read_from_snapshot(url: str) -> Optional[np.ndarray]:
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


def _open_video_capture(url: str):
    cap = cv2.VideoCapture(url)
    return cap if cap.isOpened() else None


def _producer(state: LiveCameraState, camera_cfg: dict, fps: float):
    frame_period = 1.0 / max(fps, 0.2)
    stream_url = camera_cfg.get("resolved_stream_url")
    snapshot_url = camera_cfg.get("resolved_snapshot_url")
    cap = _open_video_capture(stream_url) if stream_url else None
    try:
        while True:
            with state.lock:
                if not state.running:
                    break
            t0 = time.time()

            frame = None
            if cap is not None:
                ok, fr = cap.read()
                if ok:
                    frame = fr
            if frame is None and snapshot_url:
                frame = _read_from_snapshot(snapshot_url)
            if frame is None:
                frame = np.zeros((480, 854, 3), dtype=np.uint8)
                cv2.putText(frame, "No camera frame", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            annotated, counts, _, _ = yolo_service.infer(frame)
            persons = counts.get("person", 0)
            cv2.rectangle(annotated, (10, 10), (300, 55), (20, 20, 20), -1)
            cv2.putText(annotated, f"persons: {persons}", (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            ok, buff = cv2.imencode(".jpg", annotated)
            if ok:
                with state.lock:
                    state.latest_jpeg = buff.tobytes()
                    state.frame_cond.notify_all()

            elapsed = time.time() - t0
            if elapsed < frame_period:
                time.sleep(frame_period - elapsed)
    finally:
        if cap is not None:
            cap.release()


def _get_state(camera_id: str) -> LiveCameraState:
    with _global_lock:
        if camera_id not in _states:
            _states[camera_id] = LiveCameraState()
        return _states[camera_id]


def mjpeg_stream(camera_cfg: dict, fps: float = 3.0):
    camera_id = camera_cfg["id"]
    state = _get_state(camera_id)
    with state.lock:
        state.clients += 1
        if not state.running:
            state.running = True
            state.thread = threading.Thread(target=_producer, args=(state, camera_cfg, fps), daemon=True)
            state.thread.start()

    try:
        while True:
            with state.lock:
                if state.latest_jpeg is None:
                    state.frame_cond.wait(timeout=2)
                frame = state.latest_jpeg
            if frame is None:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
    finally:
        with state.lock:
            state.clients -= 1
            if state.clients <= 0:
                state.running = False
                state.frame_cond.notify_all()
