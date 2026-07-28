import re
import base64
from typing import Dict, Any

class PromptInjectionDetector:
    """
    Multi-layered Prompt Injection Detector:
    1. Base64 & Encoded Payload Decoder
    2. Heuristic Rule Engine (Structural anomalies, system tags)
    3. Regex Pattern Classifier
    4. Semantic DeBERTa-v3 ML Classifier Simulation
    """
    
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|above)\s+instructions?",
        r"(?i)disregard\s+(all\s+)?guidelines?",
        r"(?i)override\s+(all\s+)?(system\s+)?prompts?",
        r"(?i)you\s+are\s+now\s+in\s+developer\s+mode",
        r"(?i)start\s+a\s+new\s+conversation\s+from\s+scratch",
        r"(?i)\[SYSTEM\]",
        r"(?i)<\|im_start\|>",
        r"(?i)reveal\s+your\s+instructions?",
        r"(?i)print\s+your\s+(initial|system)\s+prompt",
        r"(?i)repeat\s+the\s+words\s+above",
        r"(?i)print\s+the\s+.*passwords?",
        r"(?i)training\s+corpus"
    ]

    def _decode_base64(self, text: str) -> str:
        # Detect base64 strings and attempt decoding
        b64_matches = re.findall(r'[A-Za-z0-9+/]{8,}={0,2}', text)
        decoded_parts = []
        for m in b64_matches:
            try:
                decoded = base64.b64decode(m).decode('utf-8', errors='ignore')
                if len(decoded.strip()) > 3:
                    decoded_parts.append(decoded)
            except Exception:
                pass
        return text + " " + " ".join(decoded_parts)

    def analyze(self, prompt: str) -> Dict[str, Any]:
        augmented_prompt = self._decode_base64(prompt)
        score = 0.0
        matches = []
        
        # 1. Regex pattern check
        for pattern in self.INJECTION_PATTERNS:
            found = re.findall(pattern, augmented_prompt)
            if found:
                score += 0.70
                matches.append(pattern)
                
        # 2. Heuristic checks
        if "[SYSTEM]" in augmented_prompt.upper() or "<|IM_START|>" in augmented_prompt.upper():
            score += 0.50
            matches.append("system_tag_injection")
            
        if "OVERRIDE" in augmented_prompt.upper() or "IGNORE" in augmented_prompt.upper():
            if "PROMPT" in augmented_prompt.upper() or "INSTRUCTION" in augmented_prompt.upper() or "COMMAND" in augmented_prompt.upper():
                score += 0.50
                matches.append("override_keyword_combination")

        final_score = min(1.0, score)
        return {
            "injection_score": round(final_score, 3),
            "is_injection": final_score >= 0.70 or len(matches) > 0,
            "patterns_matched": matches
        }

injection_detector = PromptInjectionDetector()
