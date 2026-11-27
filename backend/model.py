import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import KFold
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from . import features

ALGOS = {
    "iforest": lambda: IsolationForest(n_estimators=200, random_state=0),
    "ocsvm": lambda: OneClassSVM(nu=0.1, gamma="scale"),
    "lof": lambda: LocalOutlierFactor(n_neighbors=5, novelty=True),
}
MIN_ENROLL = {"keys": 15, "mouse": 10}


def _fit(X, algo):
    return make_pipeline(StandardScaler(), ALGOS[algo]()).fit(X)


def train(X, algo="iforest"):
    X = np.asarray(X, float)
    folds = KFold(5, shuffle=True, random_state=0).split(X)
    oof = np.concatenate([_fit(X[tr], algo).decision_function(X[te]) for tr, te in folds])
    return {"algo": algo, "pipe": _fit(X, algo),
            "median": float(np.median(oof)), "p5": float(np.percentile(oof, 5))}


def train_user(windows, algo="iforest", modalities=MIN_ENROLL):
    pooled = features.rolling(windows)
    return {mod: train([d[mod] for d in pooled if mod in d], algo) for mod in modalities}


def risk(m, x):
    s = m["pipe"].decision_function(np.asarray([x], float))[0]
    span = max(m["median"] - m["p5"], 1e-9)
    return float(np.clip((m["median"] - s) / span / 2, 0, 1))


def window_risk(models, feats):
    parts = {mod: risk(models[mod], x) for mod, x in feats.items() if mod in models}
    return (sum(parts.values()) / len(parts) if parts else None), parts
