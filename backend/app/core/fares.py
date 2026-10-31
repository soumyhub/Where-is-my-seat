"""Fare estimation.

This is a deliberately simple distance-based model so the app can compare options.
It is NOT the official Indian Railways fare table (which is telescopic, varies by
train type and includes dynamic pricing on some services). Every fare it produces is
labelled as an estimate.
"""

from __future__ import annotations

from .models import Train

FARE_BASIS = "Simplified distance-based estimate — not an official IRCTC fare"

_RATE_PER_KM = {
    "1A": 3.50, "2A": 2.10, "3A": 1.45, "3E": 1.35, "EC": 2.70, "CC": 1.30,
    "FC": 1.90, "SL": 0.55, "2S": 0.40, "UR": 0.30,
}
_MIN_FARE = {"1A": 300, "2A": 220, "3A": 180, "3E": 170, "EC": 250, "CC": 120, "FC": 150, "SL": 60, "2S": 30, "UR": 10}
_RESERVATION_FEE = {"1A": 60, "2A": 50, "3A": 40, "3E": 40, "EC": 60, "CC": 40, "FC": 50, "SL": 20, "2S": 15, "UR": 0}
_SUPERFAST_FEE = {"1A": 75, "2A": 45, "3A": 45, "3E": 45, "EC": 75, "CC": 45, "FC": 45, "SL": 30, "2S": 15, "UR": 15}
_AC_CLASSES = {"1A", "2A", "3A", "3E", "EC", "CC"}
_AC_TAX = 0.05
# Premium services price above ordinary express trains (catering, dynamic fares); Garib Rath below.
_CATEGORY_FACTOR = {
    "Rajdhani": 1.35, "Duronto": 1.25, "Shatabdi": 1.30, "Vande Bharat": 1.50, "Tejas": 1.45,
    "Humsafar": 1.15, "Garib Rath": 0.75, "Jan Shatabdi": 1.05,
}


class FareEstimator:
    basis = FARE_BASIS

    def estimate(self, train: Train, travel_class: str, km: int) -> int:
        if travel_class not in _RATE_PER_KM:
            raise ValueError(f"unknown class {travel_class}")
        fare = max(_MIN_FARE[travel_class], _RATE_PER_KM[travel_class] * max(km, 0))
        if travel_class != "UR":
            fare *= _CATEGORY_FACTOR.get(train.category, 1.0)
        fare += _RESERVATION_FEE[travel_class]
        if train.superfast:
            fare += _SUPERFAST_FEE[travel_class]
        if travel_class in _AC_CLASSES:
            fare *= 1 + _AC_TAX
        return int(5 * round(fare / 5))
