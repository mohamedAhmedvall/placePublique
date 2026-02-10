from datetime import datetime
from .db import db


class Camera(db.Model):
    __tablename__ = "cameras"

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    page_url = db.Column(db.String(1024), nullable=False)
    resolved_stream_url = db.Column(db.String(1024))
    resolved_snapshot_url = db.Column(db.String(1024))
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Detection(db.Model):
    __tablename__ = "detections"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    camera_id = db.Column(db.String(64), db.ForeignKey("cameras.id"), nullable=False, index=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    counts_json = db.Column(db.Text, nullable=False)
    total_persons = db.Column(db.Integer, nullable=False, default=0)
    snapshot_ok = db.Column(db.Boolean, nullable=False, default=False)
    error_message = db.Column(db.Text)
    infer_ms = db.Column(db.Float, nullable=False, default=0)
    model_name = db.Column(db.String(128), nullable=False, default="yolov8n")


class LiveSession(db.Model):
    __tablename__ = "live_sessions"

    camera_id = db.Column(db.String(64), db.ForeignKey("cameras.id"), primary_key=True)
    active_count = db.Column(db.Integer, nullable=False, default=0)
    last_client_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
