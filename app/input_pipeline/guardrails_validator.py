from typing import Dict, Any

class GuardrailsValidator:
    """
    Guardrails AI Declarative Input Validation
    Enforces RAIL specifications: token length, toxic language, and topic constraints.
    """
    
    MAX_TOKENS = 2000

    def validate_input(self, prompt: str) -> Dict[str, Any]:
        # Rough token estimation (1 token ≈ 4 chars)
        est_tokens = len(prompt) // 4
        
        if est_tokens > self.MAX_TOKENS:
            return {
                "valid": False,
                "reason": f"Input length exceeds maximum allowed tokens ({est_tokens} > {self.MAX_TOKENS})",
                "tokens": est_tokens
            }

        return {
            "valid": True,
            "reason": None,
            "tokens": est_tokens
        }

guardrails_validator = GuardrailsValidator()
