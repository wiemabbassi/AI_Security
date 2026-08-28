import json
import os
from typing import Dict, Any, List

try:
    import numpy as np
except ImportError:
    np = None

WEIGHTS_FILE_PATH = "config/risk_weights.json"

class RiskScoringEngine:
    """
    Weighted Risk Aggregation Engine using NumPy or fallback weighted dot product.
    Aggregates multi-detector risk signals into a single standardized [0.0, 1.0] risk score.

    Supports dynamic weight tuning & persistence:
    - Loads weights from config/risk_weights.json if present
    - Auto-tunes weights based on human feedback (annotations vs detector scores)
    """

    DEFAULT_WEIGHTS = {
        "injection": 0.35,
        "jailbreak": 0.30,
        "llama_guard": 0.20,
        "anomaly": 0.15
    }

    def __init__(self):
        self.WEIGHTS = dict(self.DEFAULT_WEIGHTS)
        self.load_weights()

    def load_weights(self):
        """Loads weights from JSON config file if present, ensuring normalization."""
        if os.path.exists(WEIGHTS_FILE_PATH):
            try:
                with open(WEIGHTS_FILE_PATH, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.update_weights(data, save=False)
                        print(f"[RISK SCORER] Loaded calibrated weights: {self.WEIGHTS}")
            except Exception as e:
                print(f"[RISK SCORER] Error loading weights file: {e}")

    def save_weights(self):
        """Saves current weights to JSON config file."""
        try:
            os.makedirs(os.path.dirname(WEIGHTS_FILE_PATH), exist_ok=True)
            with open(WEIGHTS_FILE_PATH, "w") as f:
                json.dump(self.WEIGHTS, f, indent=2)
            print(f"[RISK SCORER] Saved calibrated weights to {WEIGHTS_FILE_PATH}")
        except Exception as e:
            print(f"[RISK SCORER] Error saving weights file: {e}")

    def update_weights(self, new_weights: Dict[str, float], save: bool = True):
        """Validates and normalizes weights so they sum to 1.0."""
        valid_keys = {"injection", "jailbreak", "llama_guard", "anomaly"}
        filtered = {k: max(0.01, float(v)) for k, v in new_weights.items() if k in valid_keys}

        total = sum(filtered.values())
        if total <= 0:
            return

        # Normalize weights to sum to 1.0
        normalized = {k: round(v / total, 4) for k, v in filtered.items()}
        for k, v in normalized.items():
            self.WEIGHTS[k] = v

        if save:
            self.save_weights()

    def auto_tune_weights(self, annotated_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Auto-tunes detector weights based on historical annotated events.
        Measures false positive / false negative rates of each detector against
        human annotations and adjusts weights proportionally.
        """
        if not annotated_events or len(annotated_events) < 5:
            return {
                "status": "SKIPPED",
                "reason": "Not enough annotated events (minimum 5 required)",
                "current_weights": self.WEIGHTS
            }

        # Track accuracy / correlation for each detector
        detector_accuracy = {
            "injection": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "jailbreak": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "llama_guard": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "anomaly": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        }

        for ev in annotated_events:
            meta = ev.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            annot = meta.get("label_studio_annotation", "")
            is_true_attack = annot in ["PROMPT_INJECTION", "JAILBREAK", "HARMFUL_CONTENT", "UNSAFE", "BLOCK"]

            # Detector predictions
            inj_pred = (ev.get("injection_score", 0.0) or 0.0) >= 0.50
            jb_pred = (ev.get("jailbreak_score", 0.0) or 0.0) >= 0.50
            lg_pred = ev.get("llama_guard_status", "") == "UNSAFE"
            anom_pred = (ev.get("anomaly_score", 0.0) or 0.0) >= 0.50

            preds = {
                "injection": inj_pred,
                "jailbreak": jb_pred,
                "llama_guard": lg_pred,
                "anomaly": anom_pred
            }

            for det, pred in preds.items():
                if pred and is_true_attack:
                    detector_accuracy[det]["tp"] += 1
                elif pred and not is_true_attack:
                    detector_accuracy[det]["fp"] += 1
                elif not pred and not is_true_attack:
                    detector_accuracy[det]["tn"] += 1
                else:
                    detector_accuracy[det]["fn"] += 1

        # Calculate F1 score for each detector to derive new relative weight
        f1_scores = {}
        for det, counts in detector_accuracy.items():
            tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
            precision = tp / max(1, tp + fp)
            recall = tp / max(1, tp + fn)
            f1 = 2 * precision * recall / max(0.001, precision + recall)
            f1_scores[det] = max(0.1, f1)  # baseline minimum weight 0.1

        # Update and save weights
        self.update_weights(f1_scores, save=True)

        return {
            "status": "COMPLETED",
            "sample_count": len(annotated_events),
            "detector_f1_scores": {k: round(v, 3) for k, v in f1_scores.items()},
            "calibrated_weights": self.WEIGHTS
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
