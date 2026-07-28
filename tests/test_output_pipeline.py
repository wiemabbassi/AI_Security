import unittest
from app.output_pipeline.output_pii import output_pii_scanner
from app.output_pipeline.data_leak import data_leak_detector
from app.output_pipeline.output_guardrails import output_guardrails

class TestOutputPipeline(unittest.TestCase):

    def test_output_pii_scan(self):
        response_with_pii = "User credit card is 4532-1234-5678-9012."
        res = output_pii_scanner.scan(response_with_pii)
        self.assertTrue(res["has_pii"])
        self.assertEqual(res["pii_count"], 1)

    def test_data_leak_detector(self):
        leaked_response = "Here are my internal instructions: helpful, secure AI assistant..."
        res = data_leak_detector.detect_leak(leaked_response)
        self.assertTrue(res["is_leak"])

    def test_output_guardrails_restoration(self):
        pii_map = {"<PII_EMAIL_1234>": "user@domain.com"}
        response = "Hello <PII_EMAIL_1234>, your order is confirmed."
        res = output_guardrails.validate_and_restore(response, pii_map)
        self.assertTrue(res["valid"])
        self.assertIn("user@domain.com", res["final_response"])

if __name__ == "__main__":
    unittest.main()
