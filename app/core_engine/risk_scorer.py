try:
    import numpy as np
except ImportError:
    np = None

from typing import Dict, Any

class RiskScoringEngine:
    """
    Weighted Risk Aggregation Engine using NumPy or fallback weighted dot product.
    Aggregates multi-detector risk signals into a single standardized [0.0, 1.0] risk score.
    """
    
    WEIGHTS = {
        "injection": 0.35,
        "jailbreak": 0.30,
        "llama_guard": 0.20,
        "anomaly": 0.15
    }

    def calculate_risk(
        self,
        injection_score: float,
        jailbreak_score: float,
        llama_guard_status: str,
        anomaly_score: float
    ) -> float:
        lg_score = 1.0 if llama_guard_status == "UNSAFE" else 0.0
        
        if np is not None:
            scores = np.array([injection_score, jailbreak_score, lg_score, anomaly_score])
            weights = np.array([
                self.WEIGHTS["injection"],
                self.WEIGHTS["jailbreak"],
                self.WEIGHTS["llama_guard"],
                self.WEIGHTS["anomaly"]
            ])
            aggregated = float(np.dot(scores, weights))
        else:
            aggregated = (
                injection_score * self.WEIGHTS["injection"] +
                jailbreak_score * self.WEIGHTS["jailbreak"] +
                lg_score * self.WEIGHTS["llama_guard"] +
                anomaly_score * self.WEIGHTS["anomaly"]
            )
            
        return round(min(1.0, max(0.0, aggregated)), 3)

risk_scorer = RiskScoringEngine()
