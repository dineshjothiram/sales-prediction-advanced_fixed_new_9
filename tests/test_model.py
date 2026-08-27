"""
Model regression tests. These check properties of the *trained artifact*
itself, separate from the API that serves it - catching cases where the
API tests would still pass (model loads, returns a float) but the model
itself has quietly gotten worse or behaves nonsensically.
"""
import json
import pickle

import numpy as np
import pandas as pd
import pytest

with open("model.pkl", "rb") as f:
    model = pickle.load(f)

with open("metrics.json") as f:
    metrics = json.load(f)

with open("metrics/baseline_metrics.json") as f:
    baseline = json.load(f)

FEATURE_COLUMNS = ["TV", "Radio", "Newspaper"]


def _features(tv, radio, newspaper):
    return pd.DataFrame([[tv, radio, newspaper]], columns=FEATURE_COLUMNS)


def test_metrics_meet_baseline():
    """Belt-and-suspenders: the CI quality gate already enforces this, but
    keeping it as a test too means `pytest` alone always tells the truth
    about whether the current model.pkl is deployable."""
    assert metrics["r2"] >= baseline["min_r2"]
    assert metrics["mse"] <= baseline["max_mse"]


def test_prediction_on_known_input_is_reasonable():
    # This exact row exists in data/add.csv with a known Sales value of
    # 22.1 - the model should land in the same ballpark, not just "a
    # number".
    prediction = model.predict(_features(230.1, 37.8, 69.2))[0]
    assert 15 <= prediction <= 30


def test_prediction_with_zero_budget_is_near_intercept():
    prediction = model.predict(_features(0.0, 0.0, 0.0))[0]
    # Should be close to the model's intercept, and not something wild
    # like a negative number or a value larger than any real budget could
    # justify.
    assert -5 <= prediction <= 15


def test_prediction_is_monotonic_in_tv_spend():
    """More TV spend, all else equal, should never predict lower sales for
    this dataset - a flipped sign here usually means a feature-order bug."""
    low = model.predict(_features(50.0, 20.0, 20.0))[0]
    high = model.predict(_features(250.0, 20.0, 20.0))[0]
    assert high > low


@pytest.mark.parametrize(
    "tv,radio,newspaper",
    [
        (0.0, 0.0, 0.0),
        (500.0, 500.0, 500.0),
        (230.1, 37.8, 69.2),
    ],
)
def test_predict_never_returns_nan_or_inf(tv, radio, newspaper):
    prediction = model.predict(_features(tv, radio, newspaper))[0]
    assert np.isfinite(prediction)
