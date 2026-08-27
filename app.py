import json
import pickle
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Sales Prediction API")

MODEL_PATH = Path("model.pkl")
METRICS_PATH = Path("metrics.json")
VERSION_PATH = Path("VERSION")
FEATURE_COLUMNS = ["TV", "Radio", "Newspaper"]

templates = Jinja2Templates(directory="templates")


def _to_features(tv: float, radio: float, newspaper: float) -> pd.DataFrame:
    """Builds a DataFrame with the same column names/order used at
    training time, so scikit-learn matches features by name instead of
    position - and doesn't warn about missing feature names."""
    return pd.DataFrame([[tv, radio, newspaper]], columns=FEATURE_COLUMNS)


def _load_model():
    """Load the trained model, failing loudly and clearly if it's missing.

    In this pipeline model.pkl is produced by train_model.py in CI and
    copied into the image at build time - it is never trained here.
    """
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"{MODEL_PATH} not found. Run `python train_model.py` first, "
            "or make sure the CI-trained artifact was copied into the image."
        )
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _load_json(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


model = _load_model()
metrics = _load_json(METRICS_PATH)
app_version = VERSION_PATH.read_text().strip() if VERSION_PATH.exists() else "unknown"


class InputData(BaseModel):
    TV: float
    Radio: float
    Newspaper: float


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"prediction": None})


@app.get("/health")
def health():
    """Used by the Docker HEALTHCHECK and by load balancers/orchestrators."""
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/version")
def version():
    """Reports exactly which code version and which trained model this
    running container is serving - useful when debugging "which build is
    actually live" across staging/production."""
    return {
        "app_version": app_version,
        "model_metrics": metrics,
    }


@app.post("/predict_form", response_class=HTMLResponse)
async def predict_form(request: Request, TV: float = Form(...), Radio: float = Form(...), Newspaper: float = Form(...)):
    features = _to_features(TV, Radio, Newspaper)
    prediction = model.predict(features)[0]
    return templates.TemplateResponse(request, "index.html", {"prediction": round(float(prediction), 2)})


@app.post("/predict/")
def predict(data: InputData):
    for field_name, value in data.model_dump().items():
        if value < 0:
            raise HTTPException(status_code=422, detail=f"{field_name} must be >= 0")

    features = _to_features(data.TV, data.Radio, data.Newspaper)
    prediction = model.predict(features)[0]
    return {"predicted_sales": round(float(prediction), 4)}
