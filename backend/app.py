import hashlib
import json
import os
import pickle
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, features, model

THRESHOLD = 0.5   # risk above this counts as a suspicious window
STREAK = 3        # this many suspicious windows in a row -> re-authenticate
ADMINS = set(os.environ.get("BCA_ADMINS", "admin").split(","))

app = FastAPI(title="Behavioral Continuous Authentication")
con = db.connect()
# All endpoints are `async def` so they run on the event loop thread: one shared sqlite connection is safe.


class Creds(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)


class Password(BaseModel):
    password: str = Field(max_length=128)


class Window(BaseModel):
    keys: list[tuple[float, float]] = Field(default_factory=list, max_length=2000)          # [down_ms, up_ms]
    moves: list[tuple[float, float, float]] = Field(default_factory=list, max_length=6000)  # [t_ms, x, y]
    clicks: list[tuple[float, float]] = Field(default_factory=list, max_length=500)        # [down_ms, up_ms]
    scrolls: int = Field(0, ge=0, le=10000)
    impostor: bool = False  # experiment flag: someone other than the owner is using this session


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def _check_password(user, password):
    return secrets.compare_digest(_hash(password, user["salt"]), user["pw_hash"])


def current(x_token: str = Header()):
    row = con.execute(  "SELECT s.token, s.locked, s.streak, u.* " \
                        "FROM sessions s " \
                        "JOIN users u ON u.id = s.user_id "
                        "WHERE s.token = ?", (x_token,)).fetchone()
    if not row:
        raise HTTPException(401, "Not logged in")
    
    return row


def _count(user_id, label):
    return con.execute("SELECT COUNT(*) " \
                       "FROM samples " \
                       "WHERE user_id=? AND label=?", (user_id, label)).fetchone()[0]


def _enroll_counts(user_id):
    """Enrollment windows collected per modality, e.g. {"keys": 7, "mouse": 3}."""
    return {mod: con.execute(f"SELECT COUNT(*) FROM samples WHERE user_id=? AND label='enroll' AND has_{mod}=1",
                             (user_id,)).fetchone()[0] for mod in model.MIN_ENROLL}


def _save_sample(s, label, raw, feats):
    con.execute("INSERT INTO samples (user_id, token, t, label, has_keys, has_mouse, raw) VALUES (?,?,?,?,?,?,?)",
                (s["id"], s["token"], time.time(), label, int("keys" in feats), int("mouse" in feats), json.dumps(raw)))


def _status(s):
    return {"username": s["username"], "enrolled": s["model"] is not None, "locked": bool(s["locked"]),
            "enroll_count": _enroll_counts(s["id"]), "enroll_needed": model.MIN_ENROLL,
            "admin": s["username"] in ADMINS}


@app.post("/api/register")
async def register(c: Creds):
    salt = secrets.token_bytes(16)
    try:
        con.execute("INSERT INTO users (username, salt, pw_hash, created) VALUES (?,?,?,?)",
                    (c.username, salt, _hash(c.password, salt), time.time()))
    except db.sqlite3.IntegrityError:
        raise HTTPException(409, "Username taken")
    return {"ok": True}


@app.post("/api/login")
async def login(c: Creds):
    user = con.execute("SELECT * FROM users WHERE username=?", (c.username,)).fetchone()
    if not user or not _check_password(user, c.password):
        raise HTTPException(401, "Wrong username or password")
    token = secrets.token_hex(24)
    con.execute("INSERT INTO sessions (token, user_id, created) VALUES (?,?,?)", (token, user["id"], time.time()))
    return {"token": token}


@app.post("/api/logout")
async def logout(s=Depends(current)):
    con.execute("DELETE FROM sessions WHERE token=?", (s["token"],))
    return {"ok": True}


@app.get("/api/me")
async def me(s=Depends(current)):
    return _status(s)


@app.post("/api/events")
async def events(w: Window, s=Depends(current)):
    raw = w.model_dump(exclude={"impostor"})
    f = features.extract(raw)
    if not f:
        return {"status": "idle"}
    if s["model"] is None:
        _save_sample(s, "enroll", raw, f)
        return {"status": "enrolling", "count": _enroll_counts(s["id"]), "needed": model.MIN_ENROLL}
    if s["locked"]:
        return {"status": "locked"}

    _save_sample(s, "impostor" if w.impostor else "live", raw, f)
    # recent windows of this session (including this one), only since the last lock, so an
    # impostor's windows are not pooled with the owner's after re-authentication
    recent = con.execute("SELECT raw FROM (SELECT raw, t FROM samples WHERE token=? AND label!='enroll' "
                         "AND t > COALESCE((SELECT MAX(t) FROM scores WHERE token=? AND locked=1), 0) "
                         "ORDER BY t DESC LIMIT 20) ORDER BY t", (s["token"], s["token"])).fetchall()
    pooled = features.rolling([json.loads(row["raw"]) for row in recent])[-1]
    r, parts = model.window_risk(pickle.loads(s["model"]), pooled)
    streak = s["streak"] + 1 if r > THRESHOLD else 0
    locked = streak >= STREAK
    con.execute("UPDATE sessions SET streak=?, locked=? WHERE token=?", (streak, int(locked), s["token"]))
    con.execute("INSERT INTO scores (token, t, risk, key_risk, mouse_risk, locked) VALUES (?,?,?,?,?,?)",
                (s["token"], time.time(), r, parts.get("keys"), parts.get("mouse"), int(locked)))
    return {"status": "locked" if locked else "ok", "risk": r, "parts": parts,
            "streak": streak, "streak_limit": STREAK}


@app.post("/api/enroll/finish")
async def enroll_finish(s=Depends(current)):
    counts = _enroll_counts(s["id"])
    missing = [f"{need - counts[mod]} more {mod} windows" for mod, need in model.MIN_ENROLL.items() if counts[mod] < need]
    if missing:
        raise HTTPException(400, "Need " + " and ".join(missing))
    rows = con.execute("SELECT raw FROM samples WHERE user_id=? AND label='enroll' ORDER BY t", (s["id"],)).fetchall()
    m = model.train_user([json.loads(r["raw"]) for r in rows])
    con.execute("UPDATE users SET model=? WHERE id=?", (pickle.dumps(m), s["id"]))
    return {"enrolled": True}


@app.post("/api/reauth")
async def reauth(p: Password, s=Depends(current)):
    if not _check_password(s, p.password):
        raise HTTPException(401, "Wrong password")
    con.execute("UPDATE sessions SET locked=0, streak=0 WHERE token=?", (s["token"],))
    return {"ok": True}


@app.get("/api/admin")
async def admin(s=Depends(current)):
    if s["username"] not in ADMINS:
        raise HTTPException(403, "Admins only")
    if s["locked"]:
        raise HTTPException(423, "Session locked: re-authenticate first")
    users = [{"username": u["username"], "enrolled": u["model"] is not None,
              **{lbl: _count(u["id"], lbl) for lbl in ("enroll", "live", "impostor")}}
             for u in con.execute("SELECT * FROM users ORDER BY id")]
    sessions = []
    for row in con.execute("SELECT s.token, s.created, s.locked, u.username FROM sessions s JOIN users u "
                           "ON u.id = s.user_id ORDER BY s.created DESC LIMIT 20").fetchall():
        pts = con.execute("SELECT t, risk, key_risk AS keys, mouse_risk AS mouse, locked FROM scores "
                          "WHERE token=? ORDER BY t", (row["token"],)).fetchall()
        if pts:
            sessions.append({"username": row["username"], "id": row["token"][:8], "created": row["created"],
                             "locked": bool(row["locked"]), "scores": [dict(p) for p in pts]})
    return {"threshold": THRESHOLD, "users": users, "sessions": sessions}


@app.middleware("http")
async def no_stale_pages(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"  # browser re-checks files, so code updates show on refresh
    return response


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True))
