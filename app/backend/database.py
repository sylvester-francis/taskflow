import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import Base

# Use data directory for persistence in containers
db_path = os.getenv("DATABASE_PATH", "./taskflow.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
