from __future__ import annotations

from dataclasses import asdict

import numpy as np
from sklearn.linear_model import LogisticRegression

from .data import WardFeatureRow, month_to_seasonality


FEATURE_KEYS = [
    "rainfall_mm",
    "flood_indicator",
    "historical_cases",
    "month",
    "seasonality",
    "population_proxy",
]


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
            ]
        )
        if row.label is not None:
            y.append(row.label)

    x_array = np.array(x, dtype=float)
    y_array = np.array(y, dtype=int) if y else None
    return x_array, y_array


def train_baseline_model(rows: list[WardFeatureRow]) -> LogisticRegression:
    x_train, y_train = rows_to_matrix(rows)
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(x_train, y_train)
    return model


def evaluate_baseline_model(model: LogisticRegression, rows: list[WardFeatureRow]) -> dict:
    x_train, y_train = rows_to_matrix(rows)
    score = float(model.score(x_train, y_train))
    return {
        "training_accuracy": round(score, 4),
        "training_row_count": len(rows),
    }


def predict_probabilities(model: LogisticRegression, rows: list[WardFeatureRow]) -> list[dict]:
    x_test, _ = rows_to_matrix(rows)
    probabilities = model.predict_proba(x_test)[:, 1]

    results = []
    for row, probability in zip(rows, probabilities):
        record = asdict(row)
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
