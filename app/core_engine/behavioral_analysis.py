import time
import datetime
import json
from typing import Dict, Any, List, Tuple
from app.config import settings

try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
except ImportError:
    np = None
    IsolationForest = None

try:
    import redis
except ImportError:
    redis = None


class BehavioralAnalyzer:
    """
    Behavioral Anomaly Analysis Engine (scikit-learn Isolation Forest + Redis):
    Tracks 8 real-time & cross-session behavioral signals per user:
      1. Request Frequency (requests / min)
      2. Rolling Avg Risk Score (0.0 – 1.0)
      3. Prompt Length & Length Variance
      4. Failure / Block Rate (ratio of rejected requests)
      5. Time-of-Day Anomaly (off-hours access: 23:00 - 06:00)
      6. Session Velocity (inter-request arrival gaps < 1.0s)
      7. Topic Drift (word overlap divergence between consecutive prompts)
      8. Rapid Multi-turn Escalation (sudden prompt expansion)

    Stores state in Redis (DB 1, 24h TTL) and syncs user profiles to DB (`user_behavior`).
    """

    def __init__(self):
        self.user_sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.redis_client = None

        if redis is not None:
            try:
                self.redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=1,
                    socket_connect_timeout=0.5
                )
                self.redis_client.ping()
            except Exception:
                self.redis_client = None

        if IsolationForest is not None and np is not None:
            # Training baseline on 8-feature vector:
            # [frequency, avg_risk, prompt_len, failure_rate, time_anomaly, session_velocity, topic_drift, len_ratio]
            X_train = np.array([
                [1.0, 0.05,  50.0, 0.0, 0.1, 5.0, 0.8, 1.0],
                [2.0, 0.10,  80.0, 0.0, 0.2, 3.0, 0.7, 1.2],
                [1.5, 0.08,  60.0, 0.0, 0.1, 4.0, 0.8, 1.1],
                [3.0, 0.12, 120.0, 0.0, 0.3, 2.0, 0.6, 1.3],
                [0.5, 0.02,  40.0, 0.0, 0.0, 8.0, 0.9, 0.9],
                [2.5, 0.15,  90.0, 0.1, 0.2, 2.5, 0.75, 1.15]
            ])
            self.model = IsolationForest(contamination=0.1, random_state=42)
            self.model.fit(X_train)
        else:
            self.model = None

    def _get_user_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Loads session history from Redis first, then in-memory fallback."""
        if self.redis_client is not None:
            try:
                raw = self.redis_client.get(f"behavior:{user_id}")
                if raw:
                    history = json.loads(raw)
                    self.user_sessions[user_id] = history
                    return history
            except Exception:
                pass
        return self.user_sessions.get(user_id, [])

    def _save_user_history(self, user_id: str, history: List[Dict[str, Any]]):
        """Persists session history to Redis with a 24h TTL."""
        if self.redis_client is not None:
            try:
                self.redis_client.setex(
                    f"behavior:{user_id}",
                    86400,   # 24h TTL
                    json.dumps(history[-50:])  # keep last 50 entries
                )
            except Exception:
                pass

    def get_user_prompt_history(self, user_id: str) -> List[str]:
        """Returns the list of recent prompt texts for multi-turn jailbreak tracking."""
        history = self._get_user_history(user_id)
        return [h.get("prompt_text", "") for h in history if h.get("prompt_text")]

    def record_and_analyze(
        self,
        user_id: str,
        prompt_len: int,
        current_risk: float,
        prompt_text: str = "",
        is_blocked: bool = False
    ) -> Dict[str, Any]:
        now = time.time()
        hour_of_day = datetime.datetime.now().hour
        time_anomaly = 1.0 if (hour_of_day < 6 or hour_of_day > 23) else 0.0

        history = self._get_user_history(user_id)
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = history

        # Compute signal 6: Session Velocity (gap since last request)
        last_timestamp = history[-1]["timestamp"] if history else now - 10.0
        inter_request_gap = max(0.1, now - last_timestamp)
        velocity_anomaly = 1.0 if inter_request_gap < 0.5 else 0.0

        # Compute signal 7: Topic Drift (word overlap divergence with last prompt)
        if history and history[-1].get("prompt_text") and prompt_text:
            prev_words = set(history[-1]["prompt_text"].lower().split())
            curr_words = set(prompt_text.lower().split())
            overlap = len(prev_words.intersection(curr_words)) / max(1, len(prev_words))
            topic_drift = round(1.0 - overlap, 3)
        else:
            topic_drift = 0.0

        # Compute signal 8: Length Ratio (prompt expansion vs average)
        if history:
            avg_prev_len = sum(h.get("prompt_len", 50) for h in history) / len(history)
            len_ratio = round(prompt_len / max(1.0, avg_prev_len), 2)
        else:
            len_ratio = 1.0

        history.append({
            "timestamp": now,
            "prompt_len": prompt_len,
            "prompt_text": prompt_text[:200],   # store truncated prompt text
            "risk_score": current_risk,
            "is_blocked": is_blocked
        })

        if len(history) > 50:
            history.pop(0)

        self.user_sessions[user_id] = history
        self._save_user_history(user_id, history)

        # Compute rolling behavioral metrics (signals 1-5)
        recent_1min = [h for h in history if now - h["timestamp"] <= 60.0]
        request_frequency = float(len(recent_1min))
        avg_risk = sum(h["risk_score"] for h in history) / max(1, len(history))
        blocked_count = sum(1 for h in history if h["is_blocked"])
        failure_rate = float(blocked_count / max(1, len(history)))

        # Isolation Forest Anomaly Detection (8-feature vector)
        if self.model is not None and np is not None:
            sample = np.array([[
                request_frequency,
                current_risk,
                float(prompt_len),
                failure_rate,
                time_anomaly,
                inter_request_gap,
                topic_drift,
                len_ratio
            ]])
            prediction = self.model.predict(sample)[0]
            raw_score = float(self.model.score_samples(sample)[0])
            anomaly_score = round(max(0.0, min(1.0, (0.5 - raw_score))), 3)
            is_anomaly = prediction == -1 or anomaly_score > 0.65
        else:
            anomaly_score = round(min(1.0, (
                (request_frequency / 15.0) * 0.2 +
                (current_risk * 0.2) +
                (failure_rate * 0.2) +
                (time_anomaly * 0.1) +
                (velocity_anomaly * 0.15) +
                (topic_drift * 0.15)
            )), 3)
            is_anomaly = anomaly_score > 0.65

        # Action mapping
        if anomaly_score >= 0.80:
            action = "HIGH_ANOMALY_THROTTLE"
        elif is_anomaly:
            action = "MEDIUM_ANOMALY_FLAG"
        else:
            action = "NORMAL"

        # Persist aggregate behavioral stats to DB
        try:
            from app.db.database import upsert_user_behavior
            blocked_total = sum(1 for h in history if h["is_blocked"])
            upsert_user_behavior(
                user_id=user_id,
                request_count=len(history),
                blocked_count=blocked_total,
                avg_risk=round(avg_risk, 3)
            )
        except Exception:
            pass

        return {
            "user_id": user_id,
            "anomaly_score": anomaly_score,
            "is_anomaly": is_anomaly,
            "request_frequency": request_frequency,
            "failure_rate": round(failure_rate, 2),
            "session_velocity_gap": round(inter_request_gap, 2),
            "topic_drift": topic_drift,
            "recommendation": action
        }

    def analyze_user_behavior(
        self,
        user_id: str,
        prompt_len: int,
        current_risk: float,
        prompt_text: str = "",
        request_rate: float = 1.0
    ) -> Dict[str, Any]:
        return self.record_and_analyze(
            user_id=user_id,
            prompt_len=prompt_len,
            current_risk=current_risk,
            prompt_text=prompt_text
        )


behavioral_analyzer = BehavioralAnalyzer()
