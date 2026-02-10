import os
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def db_uri() -> str:
    path = os.getenv("DB_PATH", "/data/app.db")
    return f"sqlite:///{path}"
