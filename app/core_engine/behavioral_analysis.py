from typing import Dict, Any

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
except ImportError:
    np = None
    IsolationForest = None

class BehavioralAnalyzer:
    """
    Cross-session Behavioral Anomaly Detector:
    Uses Isolation Forest or statistical z-score fallback to profile request rate,
    risk score deviations, and prompt complexity.
    """
    def __init__(self):
        if IsolationForest is not None and np is not None:
            X_train = np.array([
                [1.0, 0.05, 50.0],
                [2.0, 0.10, 80.0],
                [1.5, 0.08, 60.0],
                [3.0, 0.12, 120.0],
                [0.5, 0.02, 40.0],
                [2.5, 0.15, 90.0]
            ])
            self.model = IsolationForest(contamination=0.1, random_state=42)
            self.model.fit(X_train)
        else:
            self.model = None

    def analyze_user_behavior(self, user_id: str, prompt_len: int, current_risk: float, request_rate: float = 1.0) -> Dict[str, Any]:
        if self.model is not None and np is not None:
            sample = np.array([[request_rate, current_risk, float(prompt_len)]])
            prediction = self.model.predict(sample)[0]
            raw_score = float(self.model.score_samples(sample)[0])
            anomaly_score = round(max(0.0, min(1.0, (0.5 - raw_score))), 3)
            is_anomaly = prediction == -1 or anomaly_score > 0.65
        else:
            # Fallback heuristic statistical score calculation
            anomaly_score = round(min(1.0, (request_rate / 20.0) * 0.4 + (current_risk * 0.4) + (prompt_len / 5000.0) * 0.2), 3)
            is_anomaly = anomaly_score > 0.65

        return {
            "user_id": user_id,
            "anomaly_score": anomaly_score,
            "is_anomaly": is_anomaly,
            "recommendation": "FLAG_FOR_REVIEW" if is_anomaly else "NORMAL"
        }

behavioral_analyzer = BehavioralAnalyzer()
