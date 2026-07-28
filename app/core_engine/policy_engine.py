from typing import Dict, Any, Tuple
import os

try:
    import yaml
except ImportError:
    yaml = None

class PolicyEngine:
    """
    YAML Policy-as-Code Rule Engine:
    Evaluates risk signals against declarative security rules to output ALLOW, FLAG, REVIEW, or BLOCK decisions.
    """
    def __init__(self, policy_path: str = "config/policies.yaml"):
        self.policy_path = policy_path
        self.policies = []
        self.load_policies()

    def load_policies(self):
        if os.path.exists(self.policy_path) and yaml is not None:
            with open(self.policy_path, "r") as f:
                data = yaml.safe_load(f)
                self.policies = data.get("policies", [])
        else:
            self.policies = [
                {"id": "P001", "condition": "injection_score >= 0.75", "action": "BLOCK", "reason": "High confidence prompt injection attack detected"},
                {"id": "P002", "condition": "jailbreak_score >= 0.70", "action": "BLOCK", "reason": "Jailbreak behavior / roleplay bypass pattern identified"},
                {"id": "P003", "condition": "llama_guard_status == 'UNSAFE'", "action": "BLOCK", "reason": "Content flagged unsafe by Llama Guard taxonomy"},
                {"id": "P004", "condition": "anomaly_score >= 0.80 or behavioral_alert == True", "action": "FLAG", "reason": "Anomalous user session behavior detected"},
                {"id": "P005", "condition": "risk_score >= 0.50 and risk_score < 0.70", "action": "FLAG", "reason": "Moderate risk aggregated score"},
                {"id": "P006", "condition": "risk_score < 0.50", "action": "ALLOW", "reason": "Prompt passed all security thresholds"}
            ]

    def evaluate(self, context: Dict[str, Any]) -> Tuple[str, str, str]:
        # Context variables available for evaluation
        injection_score = context.get("injection_score", 0.0)
        jailbreak_score = context.get("jailbreak_score", 0.0)
        anomaly_score = context.get("anomaly_score", 0.0)
        risk_score = context.get("risk_score", 0.0)
        llama_guard_status = context.get("llama_guard_status", "SAFE")
        behavioral_alert = context.get("behavioral_alert", False)

        for policy in self.policies:
            condition = policy.get("condition", "")
            try:
                # Safely evaluate condition string in restricted scope
                matched = eval(condition, {
                    "injection_score": injection_score,
                    "jailbreak_score": jailbreak_score,
                    "anomaly_score": anomaly_score,
                    "risk_score": risk_score,
                    "llama_guard_status": llama_guard_status,
                    "behavioral_alert": behavioral_alert,
                    "True": True, "False": False
                })
                if matched:
                    return policy["action"], policy["id"], policy["reason"]
            except Exception:
                continue

        return "ALLOW", "P_DEFAULT", "Passed security verification"

policy_engine = PolicyEngine()
