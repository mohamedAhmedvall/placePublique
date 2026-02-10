import os
from datetime import datetime

from app.web import create_app
from app.db import db
from app.models import Camera, Detection


def test_db_insert(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "test.db")
    os.environ["DATA_DIR"] = str(tmp_path)
    app = create_app()
    with app.app_context():
        cam = db.session.get(Camera, "abbey")
        assert cam is not None
        d = Detection(camera_id=cam.id, ts=datetime.utcnow(), counts_json='{"person": 3}', total_persons=3, snapshot_ok=True, infer_ms=12.3, model_name="yolov8n")
        db.session.add(d)
        db.session.commit()
        assert Detection.query.count() >= 1
