import unittest
from app.core_engine.risk_scorer import risk_scorer
from app.core_engine.policy_engine import policy_engine
from app.core_engine.behavioral_analysis import behavioral_analyzer

class TestCoreEngine(unittest.TestCase):

    def test_risk_scoring(self):
        score = risk_scorer.calculate_risk(
            injection_score=0.8,
            jailbreak_score=0.7,
            llama_guard_status="UNSAFE",
            anomaly_score=0.5
        )
        self.assertGreater(score, 0.70)

    def test_policy_engine_block(self):
        context = {
            "injection_score": 0.85,
            "jailbreak_score": 0.2,
            "anomaly_score": 0.1,
            "risk_score": 0.75,
            "llama_guard_status": "SAFE",
            "behavioral_alert": False
        }
        action, policy_id, reason = policy_engine.evaluate(context)
        self.assertEqual(action, "BLOCK")

    def test_behavioral_analysis_outlier(self):
        res = behavioral_analyzer.analyze_user_behavior(
            user_id="user_spike",
            prompt_len=1500,
            current_risk=0.9,
            request_rate=25.0
        )
        self.assertIn("anomaly_score", res)

if __name__ == "__main__":
    unittest.main()
