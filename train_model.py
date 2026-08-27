"""
Trains the sales-prediction model and writes two artifacts:
  - model.pkl     the fitted scikit-learn model
  - metrics.json  evaluation metrics + provenance, consumed by:
                     * check_quality_gate.py (CI quality gate)
                     * tests/test_model.py   (regression tests)
                     * app.py                (exposed via /version)

Training happens here, in CI, on its own — never inside `docker build`.
The Docker image only ever COPYs the model.pkl this script produces.
"""
import json
import os
import pickle
from datetime import datetime, timezone

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

DATA_PATH = "data/add.csv"
MODEL_PATH = "model.pkl"
METRICS_PATH = "metrics.json"


def main():
    data = pd.read_csv(DATA_PATH)
    X = data[["TV", "Radio", "Newspaper"]]
    y = data["Sales"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.4, random_state=42
    )

    model = LinearRegression()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)

    print("Model trained successfully")
    print(f"R2 Score: {r2:.4f}")
    print(f"MSE: {mse:.4f}")

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    metrics = {
        "r2": round(float(r2), 4),
        "mse": round(float(mse), 4),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA", "local"),
        "rows_trained_on": int(len(X_train)),
        "rows_tested_on": int(len(X_test)),
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Wrote {MODEL_PATH} and {METRICS_PATH}")


if __name__ == "__main__":
    main()
