"""Anomaly detection logic for inventory sales history."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from sklearn.linear_model import LinearRegression


def detect_anomalies(daily_sales: Any, minimum_points: int, threshold: float) -> Dict[str, Any]:
    """Detect unusual sales days using a LinearRegression trend residual."""
    if len(daily_sales) < minimum_points:
        return {
            "method": "LinearRegression residual z-score",
            "anomalies": [],
            "summary": f"Need at least {minimum_points} daily points for anomaly detection.",
        }

    x = daily_sales[["day_index"]].to_numpy()
    y = daily_sales["quantity"].to_numpy(dtype=float)
    model = LinearRegression()
    model.fit(x, y)
    expected = model.predict(x)
    residuals = y - expected
    residual_std = float(np.std(residuals)) or 1.0
    z_scores = residuals / residual_std

    anomalies: List[Dict[str, Any]] = []
    for row, expected_value, z_score in zip(daily_sales.to_dict("records"), expected, z_scores):
        if abs(float(z_score)) >= threshold:
            anomalies.append(
                {
                    "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
                    "actual_quantity": int(row["quantity"]),
                    "expected_quantity": round(float(expected_value), 2),
                    "z_score": round(float(z_score), 2),
                }
            )

    return {
        "method": "LinearRegression residual z-score",
        "anomalies": anomalies,
        "summary": f"{len(anomalies)} anomalous sales day(s) found.",
    }

