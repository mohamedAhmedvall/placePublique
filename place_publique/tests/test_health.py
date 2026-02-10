import os
from app.web import create_app


def test_health(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "test.db")
    os.environ["DATA_DIR"] = str(tmp_path)
    app = create_app()
    client = app.test_client()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
