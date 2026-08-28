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
            # ── Training baseline: 30 realistic behavioural samples ─────────────
            # Feature vector: [frequency/min, avg_risk, prompt_len, failure_rate,
            #                  time_anomaly, inter_request_gap, topic_drift, len_ratio]
            #
            # Rows are grouped by profile:
            #   Rows  0-11: Normal users (varied usage patterns, low risk)
            #   Rows 12-17: Power users (higher frequency but legitimate)
            #   Rows 18-23: Suspicious patterns (high failure, off-hours, bursts)
            #   Rows 24-29: Active attack profiles (guaranteed anomaly zone)
            X_train = np.array([
                # ── Normal users (baseline) ───────────────────────────────────
                [1.0, 0.04,  55.0, 0.00, 0.0,  6.0, 0.80, 1.00],  # casual morning user
                [2.0, 0.08,  80.0, 0.00, 0.0,  4.0, 0.75, 1.10],  # regular mid-day
                [1.5, 0.06,  65.0, 0.00, 0.0,  5.0, 0.82, 1.05],  # steady afternoon
                [0.5, 0.03,  40.0, 0.00, 0.0,  9.0, 0.90, 0.95],  # infrequent user
                [3.0, 0.10, 120.0, 0.00, 0.0,  2.5, 0.65, 1.20],  # chatty but safe
                [1.0, 0.05,  50.0, 0.05, 0.0,  7.0, 0.78, 1.00],  # occasional block (normal FP rate)
                [2.5, 0.09,  90.0, 0.05, 0.0,  3.0, 0.70, 1.15],  # active normal user
                [1.2, 0.07,  70.0, 0.00, 0.0,  6.5, 0.85, 1.02],  # light usage
                [0.8, 0.04,  45.0, 0.00, 0.0,  8.0, 0.88, 0.98],  # very light user
                [2.0, 0.06,  75.0, 0.00, 0.0,  4.5, 0.72, 1.08],  # normal weekday
                [1.8, 0.08,  85.0, 0.05, 0.0,  4.0, 0.68, 1.12],  # normal with minor flags
                [3.0, 0.12, 100.0, 0.05, 0.0,  2.5, 0.60, 1.18],  # busy but legitimate

                # ── Power users (higher volume, still legitimate) ──────────────
                [5.0, 0.10, 150.0, 0.05, 0.0,  1.5, 0.55, 1.25],  # dev/power user
                [4.0, 0.08, 130.0, 0.05, 0.0,  2.0, 0.60, 1.20],  # API integration
                [6.0, 0.12, 200.0, 0.10, 0.0,  1.0, 0.50, 1.30],  # batch job user
                [4.5, 0.09, 140.0, 0.05, 0.0,  1.8, 0.58, 1.22],  # automation script
                [5.5, 0.11, 160.0, 0.05, 0.0,  1.2, 0.52, 1.28],  # high-freq legit
                [3.5, 0.10, 110.0, 0.08, 0.0,  2.2, 0.62, 1.16],  # power with some flags

                # ── Suspicious patterns (elevated risk, not yet attack) ─────────
                [2.0, 0.30,  90.0, 0.20, 1.0,  4.0, 0.85, 1.10],  # off-hours + medium risk
                [3.0, 0.25, 100.0, 0.25, 0.0,  3.0, 0.88, 1.20],  # high failure rate
                [1.0, 0.35,  60.0, 0.30, 1.0,  8.0, 0.90, 1.00],  # off-hours + high risk
                [4.0, 0.20, 120.0, 0.15, 0.0,  1.5, 0.92, 1.30],  # fast + topic drift
                [2.5, 0.40, 200.0, 0.20, 0.0,  3.5, 0.95, 2.00],  # escalating prompt length
                [3.5, 0.35, 150.0, 0.25, 1.0,  0.8, 0.88, 1.40],  # night burst + risk

                # ── Active attack profiles (should score as anomaly) ───────────
                [15.0, 0.80, 500.0, 0.70, 1.0,  0.1, 0.98, 3.50],  # rapid-fire injection
                [12.0, 0.75, 400.0, 0.65, 1.0,  0.2, 0.95, 4.00],  # DAN variant flood
                [10.0, 0.90, 300.0, 0.80, 0.0,  0.3, 0.99, 5.00],  # automated attack tool
                [20.0, 0.85, 600.0, 0.75, 1.0,  0.05, 0.97, 6.00], # high-freq scripted attack
                [ 8.0, 0.70, 350.0, 0.60, 1.0,  0.4, 0.96, 3.00],  # off-hours scanner
                [18.0, 0.95, 700.0, 0.90, 1.0,  0.08, 0.99, 7.00], # maximum threat signal
            ])
            self.model = IsolationForest(
                contamination=0.25,   # ~25% of training samples are attack-like
                n_estimators=150,     # more trees = more stable anomaly scores
                random_state=42,
            )
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

    def cluster_users(self) -> Dict[str, Any]:
        """
        Historical Layer User Clustering:
        Loads user behavioral profiles from the database and clusters users into
        4 behavioral profiles: NORMAL, POWER_USER, SUSPICIOUS, ATTACKER.
        Uses scikit-learn KMeans when available, or heuristic multi-factor rules.
        Saves assigned cluster labels back to user_behavior table in DB.
        """
        try:
            from app.db.database import get_all_user_behaviors, update_user_behavior_cluster
            users = get_all_user_behaviors()
        except Exception as e:
            return {"status": "ERROR", "error": f"Failed to fetch user profiles: {e}"}

        if not users:
            return {"status": "NO_DATA", "clustered_counts": {}}

        cluster_counts = {"NORMAL": 0, "POWER_USER": 0, "SUSPICIOUS": 0, "ATTACKER": 0}
        clustered_results = []

        # Use KMeans if sklearn and > 4 users available
        use_kmeans = False
        try:
            from sklearn.cluster import KMeans
            if np is not None and len(users) >= 4:
                use_kmeans = True
        except ImportError:
            use_kmeans = False

        if use_kmeans:
            try:
                feature_matrix = []
                for u in users:
                    req_cnt = float(u.get("request_count", 0) or 0)
                    blk_cnt = float(u.get("blocked_count", 0) or 0)
                    avg_r = float(u.get("avg_risk_score", 0.0) or 0.0)
                    blk_rate = blk_cnt / max(1.0, req_cnt)
                    feature_matrix.append([req_cnt, blk_rate, avg_r])

                X = np.array(feature_matrix)
                k = min(4, len(users))
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10).fit(X)
                labels = kmeans.labels_

                # Map cluster centers to profile names based on risk/block rate
                center_risks = [c[1] * 0.5 + c[2] * 0.5 for c in kmeans.cluster_centers_]
                sorted_center_indices = np.argsort(center_risks)

                cluster_names = ["NORMAL", "POWER_USER", "SUSPICIOUS", "ATTACKER"]
                cluster_map = {idx: cluster_names[min(i, 3)] for i, idx in enumerate(sorted_center_indices)}

                for u, label in zip(users, labels):
                    c_name = cluster_map[label]
                    user_id = u["user_id"]
                    update_user_behavior_cluster(user_id, c_name)
                    cluster_counts[c_name] = cluster_counts.get(c_name, 0) + 1
                    clustered_results.append({"user_id": user_id, "cluster": c_name})

            except Exception as e:
                use_kmeans = False  # Fall through to rule-based

        if not use_kmeans:
            # Rule-based segmentation fallback
            for u in users:
                user_id = u["user_id"]
                req_cnt = float(u.get("request_count", 0) or 0)
                blk_cnt = float(u.get("blocked_count", 0) or 0)
                avg_r = float(u.get("avg_risk_score", 0.0) or 0.0)
                blk_rate = blk_cnt / max(1.0, req_cnt)

                if blk_cnt >= 3 or blk_rate > 0.40 or avg_r >= 0.60:
                    c_name = "ATTACKER"
                elif blk_cnt >= 1 or blk_rate > 0.15 or avg_r >= 0.25:
                    c_name = "SUSPICIOUS"
                elif req_cnt >= 20:
                    c_name = "POWER_USER"
                else:
                    c_name = "NORMAL"

                update_user_behavior_cluster(user_id, c_name)
                cluster_counts[c_name] = cluster_counts.get(c_name, 0) + 1
                clustered_results.append({"user_id": user_id, "cluster": c_name})

        return {
            "status": "COMPLETED",
            "method": "KMeans" if use_kmeans else "RuleBasedThresholds",
            "total_users_clustered": len(users),
            "cluster_counts": cluster_counts,
            "clustered_users": clustered_results[:20]  # sample of up to 20
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
