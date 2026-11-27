import os
import random
import tempfile

os.environ["BCA_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient

from backend import features, model
from backend.app import app
from eval.evaluate import evaluate

OWNER = {"dwell": 100, "flight": 150, "speed": 1.0}
OTHER = {"dwell": 220, "flight": 50, "speed": 3.5}


def window(rng, dwell=100, flight=150, speed=1.0, keys=20, moves=120):
    t, ks = 0.0, []
    for _ in range(keys):
        d = max(10, rng.gauss(dwell, dwell * 0.15))
        ks.append([t, t + d])
        t += d + rng.gauss(flight, flight * 0.2)
    mv, x = [], 0.0
    for i in range(moves):
        x += speed * 16 * rng.uniform(0.8, 1.2)
        mv.append([i * 16, x, 100 + rng.gauss(0, 2)])
    return {"keys": ks, "moves": mv, "clicks": [[0, rng.gauss(dwell, 10)]] if moves else [], "scrolls": 0}


def test_extract_splits_modalities():
    assert features.extract({"keys": [], "moves": []}) == {}
    keys = [[i * 200, i * 200 + 100] for i in range(10)]
    moves = [[i * 10, i * 5, 0] for i in range(100)]
    f = features.extract({"keys": keys, "moves": moves, "clicks": [[0, 80]], "scrolls": 2})
    assert f["keys"] == [100, 100, 100, 0, 200, 200, 0.0]
    assert abs(f["mouse"][0] - 0.5) < 1e-9 and f["mouse"][3] == 1.0 and f["mouse"][4] == 80
    assert set(features.extract({"keys": keys, "moves": moves[:50]})) == {"keys"}
    assert set(features.extract({"keys": keys[:3], "moves": moves})) == {"mouse"}


def test_rolling_pools_per_modality_without_cross_window_intervals():
    k1 = {"keys": [[i * 200, i * 200 + 100] for i in range(10)]}
    k2 = {"keys": [[i * 100, i * 100 + 50] for i in range(10)]}
    m = {"moves": [[i * 10, i * 5, 0] for i in range(100)]}
    out = features.rolling([k1, m, k2])
    assert set(out[1]) == {"mouse"} and set(out[2]) == {"keys"}
    assert out[2]["keys"][0] == 75
    assert min(out[2]["keys"][1:4]) >= 0


def test_model_separates_users_per_modality():
    rng = random.Random(1)
    models = model.train_user([window(rng, **OWNER) for _ in range(30)])
    for kind in ({"moves": 0}, {"keys": 0}, {}):
        own = [model.window_risk(models, d)[0] for d in features.rolling([window(rng, **OWNER, **kind) for _ in range(20)])]
        other = [model.window_risk(models, d)[0] for d in features.rolling([window(rng, **OTHER, **kind) for _ in range(20)])]
        assert sum(own) / 20 < 0.5 < sum(other) / 20, kind


def test_evaluate_metrics():
    rng = random.Random(2)
    users = {"a": OWNER, "b": {"dwell": 150, "flight": 80, "speed": 2.0}, "c": {"dwell": 70, "flight": 250, "speed": 0.6}}
    data = {u: {"enroll": [window(rng, **p) for _ in range(30)], "live": [window(rng, **p) for _ in range(10)], "impostor": []}
            for u, p in users.items()}
    for mods in (("keys",), ("mouse",), features.MODALITIES):
        r = evaluate(data, "iforest", mods)
        assert r["users"] == 3 and r["EER"] < 0.2 and r["detect_rate"] > 0.8, mods


def test_api_flow():
    c = TestClient(app)
    creds = {"username": "alice", "password": "secret123"}
    assert c.post("/api/register", json=creds).status_code == 200
    assert c.post("/api/register", json=creds).status_code == 409
    assert c.post("/api/login", json={**creds, "password": "nope12"}).status_code == 401
    h = {"X-Token": c.post("/api/login", json=creds).json()["token"]}

    rng = random.Random(3)
    for _ in range(model.MIN_ENROLL["keys"]):
        j = c.post("/api/events", headers=h, json=window(rng, **OWNER, moves=0)).json()
    assert j["count"] == {"keys": 15, "mouse": 0}
    assert "10 more mouse" in c.post("/api/enroll/finish", headers=h).json()["detail"]
    for _ in range(model.MIN_ENROLL["mouse"]):
        c.post("/api/events", headers=h, json=window(rng, **OWNER, keys=0))
    assert c.post("/api/enroll/finish", headers=h).json()["enrolled"]

    j = c.post("/api/events", headers=h, json=window(rng, **OWNER, moves=0)).json()
    assert set(j["parts"]) == {"keys"} and j["status"] == "ok"

    statuses = [c.post("/api/events", headers=h, json={**window(rng, **OTHER), "impostor": True}).json()["status"]
                for _ in range(5)]
    assert "locked" in statuses
    assert c.post("/api/reauth", headers=h, json={"password": "wrong!"}).status_code == 401
    assert c.post("/api/reauth", headers=h, json={"password": "secret123"}).status_code == 200
    assert c.get("/api/me", headers=h).json()["locked"] is False

    assert c.get("/api/admin", headers=h).status_code == 403
    assert c.get("/api/me", headers={"X-Token": "bad"}).status_code == 401

    assert c.post("/api/events", headers=h, json={"keys": [[1]]}).status_code == 422
    assert c.post("/api/events", headers=h, json={"moves": [[1, 2]]}).status_code == 422

    assert c.post("/api/logout", headers=h).status_code == 200
    assert c.get("/api/me", headers=h).status_code == 401


def test_locked_admin_session_cannot_read_dashboard():
    from backend.app import con
    c = TestClient(app)
    creds = {"username": "admin", "password": "123qwe456"}
    assert c.post("/api/register", json=creds).status_code == 409  # seeded, can't be claimed
    h = {"X-Token": c.post("/api/login", json=creds).json()["token"]}
    assert c.get("/api/me", headers=h).json()["admin"] is True
    assert c.get("/api/admin", headers=h).status_code == 200
    con.execute("UPDATE sessions SET locked=1 WHERE token=?", (h["X-Token"],))
    assert c.get("/api/admin", headers=h).status_code == 423
    assert c.post("/api/reauth", headers=h, json={"password": "123qwe456"}).status_code == 200
    assert c.get("/api/admin", headers=h).status_code == 200
