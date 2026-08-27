"""
API-level tests. These exercise the actual FastAPI app the way a real
client would - unlike the original pipeline, which had zero tests and
treated "training printed a number" as the test suite.

Requires model.pkl and metrics.json to already exist (train_model.py
must have been run first) - the CI workflow guarantees this ordering.
"""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True


def test_version_endpoint_reports_model_metrics():
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert "app_version" in body
    assert body["model_metrics"] is not None
    assert "r2" in body["model_metrics"]


def test_predict_endpoint_returns_a_number():
    response = client.post(
        "/predict/", json={"TV": 230.1, "Radio": 37.8, "Newspaper": 69.2}
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["predicted_sales"], float)
    # Sanity range for this dataset - sales are never negative or in the
    # thousands, so a wildly out-of-range number indicates something is
    # broken (wrong feature order, corrupted model, unit mismatch, etc.)
    assert 0 <= body["predicted_sales"] <= 50


def test_predict_endpoint_rejects_missing_field():
    response = client.post("/predict/", json={"TV": 100.0, "Radio": 20.0})
    assert response.status_code == 422


def test_predict_endpoint_rejects_negative_budget():
    response = client.post(
        "/predict/", json={"TV": -10.0, "Radio": 20.0, "Newspaper": 5.0}
    )
    assert response.status_code == 422


def test_predict_form_endpoint_renders_prediction():
    response = client.post(
        "/predict_form",
        data={"TV": "230.1", "Radio": "37.8", "Newspaper": "69.2"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
