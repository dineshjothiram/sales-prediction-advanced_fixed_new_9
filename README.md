# Sales Prediction — Advanced CI/CD Pipeline

A FastAPI service that predicts sales from advertising spend (TV, Radio,
Newspaper) using a scikit-learn linear regression model, with a
production-grade CI/CD pipeline built around six concepts the original
version didn't have.

## What changed from the simple version

| | Before | Now |
|---|---|---|
| Model training | `RUN python train_model.py` inside `docker build` | Trained once in CI; the image only ever `COPY`s the resulting `model.pkl` |
| Quality control | None — training just printed R²/MSE | `check_quality_gate.py` fails the build if R² drops below 0.85 or MSE exceeds 3.0 |
| Tests | None | 14 pytest tests: API behavior (`tests/test_api.py`) + model regression checks (`tests/test_model.py`) |
| CI → CD relationship | Two independent workflows, both triggered on push | `cd.yml` only runs via `workflow_run` after `ci.yml` succeeds |
| Image tags | `:latest` only | `:v<version>`, `:candidate-<sha>`, and `:latest` (only after manual approval) |
| Docker build | Raw `docker login`/`build`/`push`, single-stage image | Multi-stage build, non-root user, `HEALTHCHECK`, GitHub Actions layer cache |
| Security | None | `pip-audit` on dependencies (CI) + Trivy image scan **before** any push (CD) |
| Production deploys | Automatic, no gate | Requires a human to click **Approve** in GitHub's `production` Environment |

## Pipeline flow

```
git push origin main
        │
        ▼
┌─────────────────────────── ci.yml ───────────────────────────┐
│  lint ──┬──────────────────────► dependency-scan              │
│         │                        (pip-audit, runs in parallel)│
│         ▼                                                     │
│  train-and-evaluate                                           │
│    - python train_model.py         → model.pkl, metrics.json  │
│    - check_quality_gate.py         → fails if R²/MSE regress  │
│    - upload-artifact "trained-model"                          │
│         │                                                     │
│         ▼                                                     │
│  test (pytest -v)                                             │
│    - downloads the exact "trained-model" artifact             │
│    - 7 API tests + 7 model regression tests                   │
└─────────────────────────────────────────────────────────────┘
        │  (only if every job above succeeded)
        ▼
┌─────────────────────────── cd.yml ────────────────────────────┐
│  build-and-scan                                                │
│    - download the SAME "trained-model" artifact from that      │
│      specific CI run (by run-id) — never retrains              │
│    - docker build (load locally, do NOT push yet)              │
│    - Trivy scan — CRITICAL/HIGH vulns fail the job here,        │
│      before the image has touched any registry                 │
│    - only on success: push :v<version> and :candidate-<sha>    │
│         │                                                       │
│         ▼                                                       │
│  promote-to-production   (environment: production)              │
│    - blocked until a human clicks Approve in the GitHub UI      │
│    - `docker buildx imagetools create` re-tags the exact        │
│      already-scanned image as :latest — no rebuild, so what     │
│      gets approved is bit-for-bit what goes live                │
└─────────────────────────────────────────────────────────────┘
```

## One-time setup

1. **Add repository secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `DOCKERHUB_USERNAME` | Your Docker Hub username |
   | `DOCKERHUB_TOKEN` | A Docker Hub [access token](https://hub.docker.com/settings/security) |

2. **Create the `production` GitHub Environment** (Settings → Environments →
   New environment → name it `production`):
   - Check **Required reviewers** and add yourself/your team.
   - This is what makes `promote-to-production` pause and wait for approval.

3. **(Recommended) Protect `main`** (Settings → Branches → Add rule):
   - Require status checks: `lint`, `dependency-scan`, `train-and-evaluate`, `test`.

See `SETUP-COMMANDS.txt` for the exact copy-paste command sequence.

## Local development

```bash
pip install -r requirements.txt -r requirements-dev.txt

python train_model.py       # produces model.pkl + metrics.json
python check_quality_gate.py  # same gate CI enforces
pytest -v                   # 14 tests
ruff check .                 # lint
pip-audit -r requirements.txt --strict   # dependency vulnerability scan

uvicorn app:app --reload    # http://localhost:8000
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | HTML form |
| POST | `/predict_form` | Form submission → renders prediction in HTML |
| POST | `/predict/` | JSON API: `{"TV": .., "Radio": .., "Newspaper": ..}` → `{"predicted_sales": ..}` |
| GET | `/health` | Liveness check, used by the Docker `HEALTHCHECK` |
| GET | `/version` | Reports the running app's version and the exact model metrics it was built with |

## Why each concept matters here specifically

- **Training separated from the Docker build** means the model that gets
  deployed is *exactly* the one that passed the quality gate and the test
  suite — not a fresh, unvalidated retrain that happens to run during
  `docker build`.
- **The quality gate** (`metrics/baseline_metrics.json`) is what actually
  stops a worse model from ever becoming an image. Without it, `R2=0.40`
  would deploy just as happily as `R2=0.95`.
- **`workflow_run` gating** means a failing test, a lint error, or a
  dependency vulnerability physically prevents `cd.yml` from ever
  starting — there's no code path where a red CI run reaches Docker Hub.
- **Scan-before-push** (not scan-after) means a vulnerable image is never
  even reachable at `:candidate-<sha>`, let alone `:latest`.
- **Retagging instead of rebuilding** for production promotion guarantees
  the image a human approved is the identical digest that was scanned and
  tested — not a "close enough" rebuild that could differ.

## A note on `aquasecurity/trivy-action`'s pin

`cd.yml` pins Trivy to a full commit SHA
(`57a97c7e7821a5776cebc9bb87c984fa69cba8f1`) instead of a version tag like
`@v0.35.0`. This isn't paranoia for its own sake: on 2026-03-19,
`trivy-action` suffered a real supply chain attack
([CVE-2026-33634](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23))
in which attackers force-pushed 76 of its 77 version tags to malicious
commits that stole CI/CD secrets before running the real scan — with the
workflow still appearing to pass. Tags in any third-party action can be
silently repointed like this; a commit SHA cannot. Treat this as the
default for any security-sensitive action, not a one-off exception.

## A note on the base image pin and `ignore-unfixed`

`Dockerfile` pins `python:3.11-slim-bookworm` rather than the floating
`python:3.11-slim`. The unpinned tag now resolves to Debian 13 ("trixie"),
a release too new to have accumulated security backports — an actual scan
against it turned up ~20 HIGH/CRITICAL OS-level CVEs, most with no fix
available at all. Bookworm (Debian 12) has a much more mature patch
cadence. Revisit this pin periodically; eventually trixie will be the
better-patched choice and bookworm will age out.

Relatedly, `cd.yml` sets `ignore-unfixed: true` on the Trivy scan. The
gate still fails the build on any HIGH/CRITICAL vulnerability that *has* a
available fix (which is real signal — e.g. an outdated `setuptools` or
`openssl` you just haven't rebuilt against yet). It does not fail forever
on CVEs with no vendor patch published yet, since there is nothing
actionable to do about those until upstream ships one.

The Dockerfile also strips the base image's own system-level
`pip`/`setuptools`/`wheel`/`ensurepip` from the final stage. The app runs
exclusively via `/opt/venv/bin/python`, so this system copy is completely
unused at runtime (confirmed with `python -X importtime` and by exercising
the API end to end) — it was nonetheless shipping 4 HIGH CVEs (stale
vendored `jaraco.context`/`wheel` inside the system `setuptools`, and
`ensurepip`'s frozen seed wheels) that upgrading the venv's own
pip/setuptools/wheel never touches, since it's a second, separate copy.
