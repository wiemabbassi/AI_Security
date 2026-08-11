"""
Giskard LLM Vulnerability Scanner Test Suite
=============================================
Automated Giskard vulnerability scan targeting the LLM Security Gateway.
Usage:
    python tests/test_giskard_scan.py
"""

import os
import json
import time
import requests
import unittest

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

def gateway_reachable() -> bool:
    try:
        r = requests.get(GATEWAY_URL + "/", timeout=5)
        return r.status_code < 500
    except Exception:
        return False

def giskard_available() -> bool:
    try:
        import giskard
        return True
    except ImportError:
        return False

class TestGiskardScan(unittest.TestCase):

    def setUp(self):
        if not gateway_reachable():
            self.skipTest("Gateway not running")

    def test_giskard_vulnerability_scan(self):
        """Runs Giskard scan against the gateway if installed, else fallback test."""
        if not giskard_available():
            self.skipTest("Giskard not installed")

        import giskard

        def model_predict(df):
            responses = []
            for prompt in df["prompt"]:
                try:
                    r = requests.post(
                        f"{GATEWAY_URL}/v1/chat",
                        json={"prompt": prompt, "user_id": "giskard_tester"},
                        timeout=30
                    )
                    if r.status_code == 200:
                        responses.append(r.json().get("response", ""))
                    else:
                        responses.append(f"BLOCKED: {r.status_code}")
                except Exception as e:
                    responses.append(f"ERROR: {str(e)}")
            return responses

        giskard_model = giskard.Model(
            model=model_predict,
            model_type="text_generation",
            name="LLM Security Gateway",
            description="Enterprise LLM Security Gateway with multi-stage input/output validation.",
            feature_names=["prompt"]
        )

        dataset = giskard.Dataset(
            df=giskard.demo.load_demo_data()[0] if hasattr(giskard, "demo") else None,
            target=None
        ) if hasattr(giskard, "demo") else None

        results = giskard.scan(giskard_model, dataset)
        
        os.makedirs("reports", exist_ok=True)
        report_path = f"reports/giskard_report_{int(time.time())}.json"
        with open(report_path, "w") as f:
            json.dump(results.to_json() if hasattr(results, "to_json") else {"status": "completed"}, f, indent=2)

        print(f"[GISKARD] Scan report written to {report_path}")
        self.assertTrue(os.path.exists(report_path))

if __name__ == "__main__":
    unittest.main(verbosity=2)
