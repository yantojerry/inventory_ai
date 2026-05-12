"""Scikit-Learn assisted inventory analytics."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from app.ai.anomaly_detection import detect_anomalies
from app.models import InventoryItem
from config import get_industry_config, validate_industry


class InventoryAI:
    """Advisory AI layer for demand, reorder, anomaly, and expiry risk analysis."""

    def __init__(self, industry: str = "retail") -> None:
        self.industry = validate_industry(industry)
        self.config = get_industry_config(self.industry)

    def _sales_frame(self, sales_history: List[Dict[str, Any]]) -> pd.DataFrame:
        if not sales_history:
            return pd.DataFrame(columns=["date", "quantity"])

        frame = pd.DataFrame(sales_history)
        if "transaction_date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["transaction_date"]).dt.date
        elif "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"]).dt.date
        else:
            raise ValueError("Sales history must include 'transaction_date' or 'date'.")

        if "quantity" not in frame.columns:
            raise ValueError("Sales history must include 'quantity'.")

        daily = (
            frame.groupby("date", as_index=False)["quantity"]
            .sum()
            .sort_values("date")
            .reset_index(drop=True)
        )
        daily["day_index"] = np.arange(len(daily), dtype=float)
        return daily

    def forecast_demand(
        self,
        sales_history: List[Dict[str, Any]],
        forecast_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Forecast demand with LinearRegression over daily sales totals."""
        days = forecast_days or self.config["forecast"]["default_forecast_days"]
        daily = self._sales_frame(sales_history)

        if daily.empty:
            return {
                "method": "LinearRegression",
                "daily_forecast": [0 for _ in range(days)],
                "total_forecast": 0,
                "trend_per_day": 0.0,
                "confidence_note": "No sales history available; forecast is neutral.",
            }

        x = daily[["day_index"]].to_numpy()
        y = daily["quantity"].to_numpy(dtype=float)
        model = LinearRegression()
        model.fit(x, y)

        future_x = np.arange(len(daily), len(daily) + days, dtype=float).reshape(-1, 1)
        raw_forecast = model.predict(future_x)
        adjusted = raw_forecast * float(self.config["forecast"]["seasonality_weight"])
        clipped = np.maximum(0, np.round(adjusted)).astype(int)

        return {
            "method": "LinearRegression",
            "daily_forecast": clipped.tolist(),
            "total_forecast": int(clipped.sum()),
            "trend_per_day": round(float(model.coef_[0]), 3),
            "confidence_note": (
                "Advisory forecast based on historical transactions; "
                "human review is required before purchasing decisions."
            ),
        }

    def recommend_reorder(
        self,
        item: InventoryItem,
        sales_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Recommend, but do not execute, reorder decisions."""
        item_ai = InventoryAI(item.industry)
        reorder_config = item_ai.config["reorder"]
        lead_time_days = int(reorder_config["lead_time_days"])
        forecast = item_ai.forecast_demand(sales_history, forecast_days=lead_time_days)

        expected_lead_time_demand = forecast["total_forecast"]
        safety_stock = int(
            np.ceil(
                max(1, expected_lead_time_demand)
                * float(reorder_config["safety_stock_multiplier"])
                * 0.25
            )
        )
        target_stock = expected_lead_time_demand + safety_stock
        suggested_quantity = max(0, target_stock - item.stock_quantity)
        minimum_order = int(reorder_config["minimum_order_quantity"])

        if suggested_quantity > 0:
            suggested_quantity = max(suggested_quantity, minimum_order)

        return {
            "sku": item.sku,
            "method": "LinearRegression forecast + profile reorder policy",
            "current_stock": item.stock_quantity,
            "lead_time_days": lead_time_days,
            "expected_lead_time_demand": expected_lead_time_demand,
            "safety_stock": safety_stock,
            "target_stock": target_stock,
            "suggested_order_quantity": int(suggested_quantity),
            "decision": "review_reorder" if suggested_quantity else "no_reorder_needed",
            "advisory_note": "AI assists the decision; it does not automatically place orders.",
        }

    def anomaly_detection(self, sales_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect unusual sales days using a LinearRegression trend residual."""
        daily = self._sales_frame(sales_history)
        minimum_points = int(self.config["anomaly"]["minimum_points"])
        threshold = float(self.config["anomaly"]["z_score_threshold"])
        return detect_anomalies(daily, minimum_points, threshold)

    def expiry_risk(
        self,
        item: InventoryItem,
        sales_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Score expiry risk using a small LinearRegression risk curve."""
        item_ai = InventoryAI(item.industry)
        expiry_config = item_ai.config["expiry"]

        if not expiry_config["enabled"] or item.expiry_date is None:
            return {
                "sku": item.sku,
                "method": "LinearRegression expiry risk curve",
                "risk_score": 0,
                "risk_level": "not_applicable",
                "days_to_expiry": item.days_to_expiry,
                "advisory_note": "Expiry tracking is not required for this profile or item.",
            }

        warning_days = int(expiry_config["warning_days"])
        critical_days = int(expiry_config["critical_days"])
        days_to_expiry = (item.expiry_date - date.today()).days

        x_train = np.array([[0], [critical_days], [warning_days], [warning_days * 2]], dtype=float)
        y_train = np.array([100, 85, 55, 10], dtype=float)
        model = LinearRegression()
        model.fit(x_train, y_train)
        predicted = float(model.predict(np.array([[max(days_to_expiry, 0)]], dtype=float))[0])

        if days_to_expiry < 0:
            risk_score = 100
        else:
            risk_score = int(np.clip(round(predicted), 0, 100))

        if risk_score >= 80:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "warning"
        elif risk_score >= 20:
            risk_level = "watch"
        else:
            risk_level = "low"

        return {
            "sku": item.sku,
            "method": "LinearRegression expiry risk curve",
            "risk_score": risk_score,
            "risk_level": risk_level,
            "days_to_expiry": days_to_expiry,
            "advisory_note": "Review soon-to-expire stock before discounting, transferring, or disposing.",
        }
