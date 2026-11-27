# Behavioral Continuous Authentication (keystroke + mouse dynamics)

CSCI 408 Senior Project I prototype. After login, the system keeps checking that the same person is using the
session. Every 10 s the browser sends **timings only** (key hold and between-key times, mouse path, clicks,
scrolls; never which keys were pressed). Typing (7 robust rhythm features) and mouse (5 features) are scored by separate per-user one-class
models trained on that user's enrollment data, each score pooling the last 2 windows (~20 s). Three suspicious windows in a row (risk > 0.5) lock the session
and ask for the password again.

```
backend/features.py   raw windows -> typing and mouse features, pooled over 2 windows
backend/model.py      IsolationForest / One-Class SVM / LOF per user, risk score 0..1
backend/app.py        FastAPI: register, login, events, enroll, re-auth, admin API; serves frontend/
backend/db.py         SQLite (data/bca.db)
frontend/             index.html (login), app.html (tasks + live risk), admin.html (dashboard)
eval/evaluate.py      FAR, FRR, EER, detection delay; model comparison; ROC plot
tests/                pytest suite (features, model, evaluation, API flow)
```

## Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn backend.app:app --port 8000 --timeout-graceful-shutdown 2
```

Open http://localhost:8000. Log in as `admin` / `123qwe456` to see the dashboard (the account is seeded on startup; override the password with env `BCA_ADMIN_PASSWORD`).

## Data collection protocol (for the evaluation)
1. Each person registers and does both tasks until the typing bar (15 windows) and the mouse bar (10 windows) are full, about 5 min, then clicks **Finish enrollment**. Typing and mouse get separate models; a window is scored by whichever it has enough activity for.
2. Keep using it for 3-5 min as yourself (these are the genuine "live" windows).
3. Swap seats: use a teammate's session with **Experiment mode** ticked (impostor windows).
4. `.venv\Scripts\python -m eval.evaluate` writes `eval/results.md` and `eval/roc.png`.

## Tests

```powershell
.venv\Scripts\python -m pytest -q tests
```
