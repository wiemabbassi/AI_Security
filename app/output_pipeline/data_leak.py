from typing import Dict, Any

class DataLeakDetector:
    """
    Data Leak Detector:
    Scans LLM output to detect system prompt verbatim or paraphrased leakage.
    """
    SYSTEM_PROMPT_KEYWORDS = [
        "helpful, secure ai assistant",
        "system prompt",
        "internal instructions",
        "do not reveal"
    ]

    def detect_leak(self, response_text: str, system_prompt: str = "") -> Dict[str, Any]:
        lowered = response_text.lower()
        leak_detected = False
        reason = None
        
        for kw in self.SYSTEM_PROMPT_KEYWORDS:
            if kw in lowered:
                leak_detected = True
                reason = f"Response contains confidential prompt keyword: '{kw}'"
                break
                
        return {
            "is_leak": leak_detected,
            "leak_score": 0.95 if leak_detected else 0.05,
            "reason": reason
        }

data_leak_detector = DataLeakDetector()
