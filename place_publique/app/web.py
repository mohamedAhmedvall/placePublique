import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request, Response, send_from_directory
from sqlalchemy import func

from .db import db, db_uri
from .live import mjpeg_stream
from .models import Camera, Detection
from .providers import resolve_camera


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def load_cameras_config(path: str = "config/cameras.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("cameras", [])


def bootstrap_cameras(app: Flask):
    cfg_cameras = load_cameras_config(app.config["CAMERAS_CONFIG"])
    for c in cfg_cameras:
        row = db.session.get(Camera, c["id"])
        if not row:
            row = Camera(id=c["id"], name=c["name"], page_url=c["page_url"], enabled=True)
            db.session.add(row)
            db.session.flush()
        res = resolve_camera(c)
        row.resolved_stream_url = res.stream_url
        row.resolved_snapshot_url = res.snapshot_url
    db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["CAMERAS_CONFIG"] = os.getenv("CAMERAS_CONFIG", "config/cameras.yaml")
    app.config["LIVE_FPS"] = float(os.getenv("LIVE_FPS", "3"))

    data_path = Path(os.getenv("DATA_DIR", "/data"))
    (data_path / "annotated").mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        bootstrap_cameras(app)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

    @app.route("/")
    def dashboard():
        now = datetime.utcnow()
        since = now - timedelta(hours=24)
        q = Detection.query.filter(Detection.ts >= since)
        total = q.with_entities(func.coalesce(func.sum(Detection.total_persons), 0)).scalar() or 0
        avg = q.with_entities(func.coalesce(func.avg(Detection.total_persons), 0)).scalar() or 0
        peak = q.with_entities(func.coalesce(func.max(Detection.total_persons), 0)).scalar() or 0
        ok_count = q.filter(Detection.snapshot_ok.is_(True)).count()
        all_count = q.count() or 1
        availability = round(ok_count * 100 / all_count, 1)

        points = (
            db.session.query(Camera.id, func.strftime("%Y-%m-%d %H:%M", Detection.ts), func.avg(Detection.total_persons))
            .join(Detection, Detection.camera_id == Camera.id)
            .filter(Detection.ts >= since)
            .group_by(Camera.id, func.strftime("%Y-%m-%d %H:%M", Detection.ts))
            .order_by(func.strftime("%Y-%m-%d %H:%M", Detection.ts))
            .all()
        )

        if not points:
            labels = [(now - timedelta(hours=i)).strftime("%H:%M") for i in range(12, -1, -1)]
            abbey_vals = [0] * len(labels)
            shibuya_vals = [0] * len(labels)
        else:
            labels = sorted(set(p[1] for p in points))
            abbey_map = {p[1]: round(p[2], 2) for p in points if p[0] == "abbey"}
            shibuya_map = {p[1]: round(p[2], 2) for p in points if p[0] == "shibuya"}
            abbey_vals = [abbey_map.get(l, 0) for l in labels]
            shibuya_vals = [shibuya_map.get(l, 0) for l in labels]

        peaks = Detection.query.order_by(Detection.total_persons.desc()).limit(10).all()
        return render_template(
            "dashboard.html",
            total=total,
            avg=round(avg, 2),
            peak=peak,
            availability=availability,
            labels=labels,
            abbey_vals=abbey_vals,
            shibuya_vals=shibuya_vals,
            peaks=peaks,
        )

    @app.route("/cameras")
    def cameras():
        cams = Camera.query.all()
        latest = {}
        for c in cams:
            d = Detection.query.filter_by(camera_id=c.id).order_by(Detection.ts.desc()).first()
            latest[c.id] = d
        return render_template("cameras.html", cameras=cams, latest=latest)

    @app.route("/cameras/<camera_id>")
    def camera_detail(camera_id):
        cam = db.session.get(Camera, camera_id)
        if not cam:
            return "not found", 404
        now = datetime.utcnow()
        since = now - timedelta(hours=24)
        rows = (
            Detection.query.filter_by(camera_id=camera_id)
            .filter(Detection.ts >= since)
            .order_by(Detection.ts.asc())
            .all()
        )
        labels = [r.ts.strftime("%H:%M") for r in rows]
        values = [r.total_persons for r in rows]
        by_hour = [0] * 24
        for r in rows:
            by_hour[r.ts.hour] += r.total_persons
        return render_template("camera_detail.html", camera=cam, labels=labels, values=values, by_hour=by_hour)

    @app.route("/liveview")
    def liveview():
        cams = Camera.query.all()
        return render_template("liveview.html", cameras=cams)

    @app.route("/settings")
    def settings():
        cams = Camera.query.all()
        return render_template("settings.html", cameras=cams)

    @app.route("/live/<camera_id>.mjpg")
    def live(camera_id):
        cam = db.session.get(Camera, camera_id)
        if not cam:
            return "not found", 404
        cfg = {
            "id": cam.id,
            "resolved_stream_url": cam.resolved_stream_url,
            "resolved_snapshot_url": cam.resolved_snapshot_url,
        }
        fps = float(request.args.get("fps", app.config["LIVE_FPS"]))
        return Response(mjpeg_stream(cfg, fps=fps), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/data/annotated/<path:filename>")
    def annotated_file(filename):
        data_path = Path(os.getenv("DATA_DIR", "/data")) / "annotated"
        return send_from_directory(data_path, filename)

    @app.route("/api/kpis")
    def api_kpis():
        rng = request.args.get("range", "24h")
        since = datetime.utcnow() - (timedelta(days=7) if rng == "7d" else timedelta(hours=24))
        q = Detection.query.filter(Detection.ts >= since)
        payload = {
            "total_persons": q.with_entities(func.coalesce(func.sum(Detection.total_persons), 0)).scalar() or 0,
            "avg_persons": q.with_entities(func.coalesce(func.avg(Detection.total_persons), 0)).scalar() or 0,
            "peak": q.with_entities(func.coalesce(func.max(Detection.total_persons), 0)).scalar() or 0,
            "availability": round((q.filter(Detection.snapshot_ok.is_(True)).count() * 100 / (q.count() or 1)), 2),
        }
        return jsonify(payload)

    @app.route("/api/counts")
    def api_counts():
        camera_id = request.args.get("camera_id")
        granularity = request.args.get("granularity", "minute")
        fmt = "%Y-%m-%d %H:%M"
        if granularity == "hour":
            fmt = "%Y-%m-%d %H"
        elif granularity == "day":
            fmt = "%Y-%m-%d"

        q = Detection.query
        if camera_id:
            q = q.filter_by(camera_id=camera_id)
        from_ts = request.args.get("from")
        to_ts = request.args.get("to")
        if from_ts:
            q = q.filter(Detection.ts >= datetime.fromisoformat(from_ts))
        if to_ts:
            q = q.filter(Detection.ts <= datetime.fromisoformat(to_ts))

        rows = (
            q.with_entities(Detection.camera_id, func.strftime(fmt, Detection.ts).label("bucket"), func.avg(Detection.total_persons).label("v"))
            .group_by(Detection.camera_id, "bucket")
            .order_by("bucket")
            .all()
        )
        return jsonify([{"camera_id": r[0], "bucket": r[1], "value": round(r[2], 2)} for r in rows])

    return app
