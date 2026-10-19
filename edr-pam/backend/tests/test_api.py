import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from edr_pam.api import app
from edr_pam.db import get_session
from edr_pam.models import Base
from edr_pam.seed import seed_if_empty


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_session():
        session = SessionLocal()
        try:
            seed_if_empty(session)
            session.commit()
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["service"] == "edr-pam"


def test_overview(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["today_alerts"] == 5
    assert len(data["trend"]) == 7
    assert len(data["latest_alerts"]) == 5


def test_alerts_filter(client):
    r = client.get("/api/alerts", params={"level": "high"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["level"] == "high" for i in items)


def test_alert_detail(client):
    r = client.get("/api/alerts/A-20260827-017")
    assert r.status_code == 200
    data = r.json()
    assert data["account"] == "zhang_wj"
    assert len(data["timeline"]) >= 4


def test_dispose(client):
    r = client.post(
        "/api/alerts/A-20260827-017/dispose",
        json={"action": "增强认证"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "processing"


def test_models(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()) == 4


def test_generate_report(client):
    r = client.post(
        "/api/evidence/report",
        json={
            "date_from": "2026-08-27",
            "date_to": "2026-08-27",
            "account": "zhang_wj",
            "asset": "BSS-DB-01",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["account"] == "zhang_wj"
    assert data["alert_id"] == "A-20260827-017"
    assert len(data["timeline"]) >= 2


def test_generate_report_not_found(client):
    r = client.post(
        "/api/evidence/report",
        json={"account": "nobody", "asset": "NOWHERE"},
    )
    assert r.status_code == 404


def test_export_report_pdf(client):
    r = client.post(
        "/api/evidence/report/pdf",
        json={
            "date_from": "2026-08-27",
            "date_to": "2026-08-27",
            "account": "zhang_wj",
            "asset": "BSS-DB-01",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000
