from __future__ import annotations

from dataclasses import asdict

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from .data import WARD_RISK_FEATURE_KEYS, WardFeatureRow, month_to_seasonality


ALGORITHM_LOGISTIC_REGRESSION = "logistic_regression"
ALGORITHM_RANDOM_FOREST = "random_forest"
ALGORITHM_XGBOOST = "xgboost"
ALGORITHM_LIGHTGBM = "lightgbm"


FEATURE_KEYS = WARD_RISK_FEATURE_KEYS


MODEL_CATALOG = {
    ALGORITHM_LOGISTIC_REGRESSION: {
        "run_name": "logistic-regression-baseline",
        "readiness_state": "candidate_scoring_until_phase_4_promotion",
        "runnable": True,
        "family": "linear_classifier",
    },
    ALGORITHM_RANDOM_FOREST: {
        "run_name": "random-forest-benchmark",
        "readiness_state": "benchmark_ready",
        "runnable": True,
        "family": "tree_ensemble",
    },
    ALGORITHM_XGBOOST: {
        "run_name": "xgboost-candidate",
        "readiness_state": "candidate_only",
        "runnable": False,
        "family": "boosted_tree_ensemble",
    },
    ALGORITHM_LIGHTGBM: {
        "run_name": "lightgbm-candidate",
        "readiness_state": "candidate_only",
        "runnable": False,
        "family": "boosted_tree_ensemble",
    },
}


def rows_to_matrix(rows: list[WardFeatureRow]) -> tuple[np.ndarray, np.ndarray | None]:
    x = []
    y = []

    for row in rows:
        x.append(
            [
                row.rainfall_mm,
                row.flood_indicator,
                row.historical_cases,
                row.month,
                month_to_seasonality(row.month),
                row.population_proxy,
                float(row.population_density or 0.0),
                float(row.settlement_concentration or 0.0),
                float(row.floodplain_exposure or 0.0),
                float(row.water_body_proximity or 0.0),
                float(row.wash_vulnerability or 0.0),
                row.exposed_population_proxy_scaled,
                row.catchment_population_estimate_scaled,
            ]
        )
        if row.label is not None:
            y.append(row.label)

    x_array = np.array(x, dtype=float)
    y_array = np.array(y, dtype=int) if y else None
    return x_array, y_array


def algorithm_to_run_name(algorithm: str) -> str:
    return MODEL_CATALOG.get(algorithm, MODEL_CATALOG[ALGORITHM_LOGISTIC_REGRESSION])["run_name"]


def train_model(rows: list[WardFeatureRow], algorithm: str = ALGORITHM_LOGISTIC_REGRESSION):
    x_train, y_train = rows_to_matrix(rows)
    if algorithm == ALGORITHM_RANDOM_FOREST:
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=1,
            random_state=42,
        )
    else:
        model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(x_train, y_train)
    return model


def train_baseline_model(rows: list[WardFeatureRow]) -> LogisticRegression:
    return train_model(rows, algorithm=ALGORITHM_LOGISTIC_REGRESSION)


def evaluate_model(model, rows: list[WardFeatureRow], algorithm: str = ALGORITHM_LOGISTIC_REGRESSION) -> dict:
    x_train, y_train = rows_to_matrix(rows)
    score = float(model.score(x_train, y_train))
    metrics = {
        "algorithm": algorithm,
        "training_accuracy": round(score, 4),
        "training_row_count": len(rows),
    }
    if algorithm == ALGORITHM_RANDOM_FOREST and hasattr(model, "feature_importances_"):
        metrics["feature_importances"] = {
            key: float(round(value, 4))
            for key, value in zip(FEATURE_KEYS, model.feature_importances_)
        }
    return metrics


def evaluate_baseline_model(model: LogisticRegression, rows: list[WardFeatureRow]) -> dict:
    return evaluate_model(model, rows, algorithm=ALGORITHM_LOGISTIC_REGRESSION)


def predict_probabilities(model, rows: list[WardFeatureRow], algorithm: str = ALGORITHM_LOGISTIC_REGRESSION) -> list[dict]:
    x_test, _ = rows_to_matrix(rows)
    probabilities = model.predict_proba(x_test)[:, 1]

    results = []
    for row, probability in zip(rows, probabilities):
        record = asdict(row)
        record["algorithm"] = algorithm
        record["predicted_probability"] = float(round(probability, 4))
        results.append(record)
    return results


def probability_to_risk_level(probability: float) -> str:
    if probability >= 0.75:
        return "HIGH"
    if probability >= 0.45:
        return "MEDIUM"
    return "LOW"


def probability_to_predicted_cases(probability: float) -> int:
    return max(1, int(round(probability * 20)))
