"""
Quality gate: fails the CI job (non-zero exit) if the freshly trained
model regresses below the accepted baseline in metrics/baseline_metrics.json.

This is what actually stops a bad retrain from ever reaching the point
where an image could be built from it.
"""
import json
import os
import sys

METRICS_PATH = "metrics.json"
BASELINE_PATH = "metrics/baseline_metrics.json"


def main():
    with open(METRICS_PATH) as f:
        metrics = json.load(f)
    with open(BASELINE_PATH) as f:
        baseline = json.load(f)

    r2 = metrics["r2"]
    mse = metrics["mse"]
    min_r2 = baseline["min_r2"]
    max_mse = baseline["max_mse"]

    print(f"Trained model : R2={r2:.4f}  MSE={mse:.4f}")
    print(f"Required gate : R2>={min_r2}  MSE<={max_mse}")

    failed = False
    if r2 < min_r2:
        print(f"::error::Quality gate FAILED - R2 {r2:.4f} is below minimum {min_r2}")
        failed = True
    if mse > max_mse:
        print(f"::error::Quality gate FAILED - MSE {mse:.4f} exceeds maximum {max_mse}")
        failed = True

    if failed:
        sys.exit(1)

    print("Quality gate passed")

    # Expose r2/mse to later workflow steps when running in GitHub Actions.
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as fh:
            fh.write(f"r2={r2:.4f}\n")
            fh.write(f"mse={mse:.4f}\n")


if __name__ == "__main__":
    main()
