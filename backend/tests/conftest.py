import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from video_analysis.adapters.fake import FakeEmbedAdapter
from video_analysis.api import app, get_embedder, get_storage
from video_analysis.db import get_session
from video_analysis.models import Base
from video_analysis.storage import LocalStorage


@pytest.fixture(autouse=True)
def _fast_indexing_retries(monkeypatch):
    monkeypatch.setattr("video_analysis.indexing.retry_sleep", lambda _delay: None)


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://va:va@localhost:5432/video_analysis_test",
    )
    eng = create_engine(url)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE analysis_jobs, segments, videos RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db_session, tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path)

    def override_session():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedAdapter()
    monkeypatch.setattr("video_analysis.api.enqueue_analyze", lambda *a, **k: None)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
