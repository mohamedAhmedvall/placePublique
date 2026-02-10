import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask

from .db import db, db_uri
from .models import Camera, Detection
from .providers import resolve_camera
from .web import load_cameras_config
from .yolo_infer import yolo_service


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("worker")


def create_worker_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["CAMERAS_CONFIG"] = os.getenv("CAMERAS_CONFIG", "config/cameras.yaml")
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


def get_snapshot(cam: Camera) -> np.ndarray:
    if not cam.resolved_snapshot_url and cam.resolved_stream_url:
        cap = cv2.VideoCapture(cam.resolved_stream_url)
        try:
            ok, frame = cap.read()
            if ok:
                return frame
        finally:
            cap.release()
    if cam.resolved_snapshot_url:
        resp = requests.get(cam.resolved_snapshot_url, timeout=10)
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            return frame
    raise RuntimeError("No snapshot source available")


def refresh_resolved_urls(config_path: str):
    cfg = {c["id"]: c for c in load_cameras_config(config_path)}
    for cam in Camera.query.all():
        c = cfg.get(cam.id)
        if not c:
            continue
        res = resolve_camera(c)
        cam.resolved_stream_url = res.stream_url
        cam.resolved_snapshot_url = res.snapshot_url
    db.session.commit()


def process_one(cam: Camera):
    start = time.perf_counter()
    ok = False
    err = None
    counts = {"person": 0}
    model_name = yolo_service.model_name

    try:
        frame = get_snapshot(cam)
        annotated, counts, infer_ms, model_name = yolo_service.infer(frame)
        out = Path(os.getenv("DATA_DIR", "/data")) / "annotated" / f"{cam.id}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), annotated)
        ok = True
    except Exception as exc:
        infer_ms = (time.perf_counter() - start) * 1000
        err = str(exc)
        logger.error("camera %s failed: %s", cam.id, exc)

    det = Detection(
        camera_id=cam.id,
        ts=datetime.utcnow(),
        counts_json=json.dumps(counts),
        total_persons=counts.get("person", 0),
        snapshot_ok=ok,
        error_message=err,
        infer_ms=infer_ms,
        model_name=model_name,
    )
    db.session.add(det)
    db.session.commit()


def run_cycle(app: Flask):
    with app.app_context():
        refresh_resolved_urls(app.config["CAMERAS_CONFIG"])
        for cam in Camera.query.filter_by(enabled=True).all():
            retries = 2
            for i in range(retries + 1):
                try:
                    process_one(cam)
                    break
                except Exception as exc:
                    logger.error("retry %s cam=%s err=%s", i, cam.id, exc)
                    time.sleep(2 * (i + 1))


def main():
    app = create_worker_app()
    with app.app_context():
        if Camera.query.count() == 0:
            for c in load_cameras_config(app.config["CAMERAS_CONFIG"]):
                db.session.add(Camera(id=c["id"], name=c["name"], page_url=c["page_url"], enabled=True))
            db.session.commit()

    sched = BlockingScheduler()
    interval = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "60"))
    sched.add_job(lambda: run_cycle(app), "interval", seconds=interval, max_instances=1)
    logger.info("worker started interval=%ss", interval)
    run_cycle(app)
    sched.start()


if __name__ == "__main__":
    main()
