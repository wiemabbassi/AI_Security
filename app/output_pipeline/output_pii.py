from typing import Dict, Any
from app.input_pipeline.pii_detector import pii_detector

class OutputPIIScanner:
    """
    Output PII Scanner:
    Scans generated LLM output to catch memorized training data leakage or regurgitated PII.
    """
    def scan(self, response_text: str) -> Dict[str, Any]:
        masked_text, pii_map, count = pii_detector.mask_pii(response_text)
        return {
            "has_pii": count > 0,
            "pii_count": count,
            "sanitized_response": masked_text,
            "detected_pii_map": pii_map
        }

output_pii_scanner = OutputPIIScanner()
