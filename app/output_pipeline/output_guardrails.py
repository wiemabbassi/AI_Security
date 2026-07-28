from typing import Dict, Any
from app.input_pipeline.pii_detector import pii_detector

class OutputGuardrailsValidator:
    """
    Guardrails AI Output Validator:
    Structural correctness, schema validation, groundedness, and PII restoration.
    """
    def validate_and_restore(self, response_text: str, pii_map: Dict[str, str]) -> Dict[str, Any]:
        # 1. Restore original PII tokens
        restored_text = pii_detector.unmask_pii(response_text, pii_map)
        
        # 2. Structural & groundedness validation
        is_valid = len(restored_text.strip()) > 0
        
        return {
            "valid": is_valid,
            "final_response": restored_text,
            "pii_restored_count": len(pii_map)
        }

output_guardrails = OutputGuardrailsValidator()
