import re
from typing import Dict, Any, List

class JailbreakDetector:
    """
    Jailbreak Detector targeting behavioral manipulation, DAN prompts,
    hypothetical roleplay framing, and multi-turn escalation tracking.
    """
    JAILBREAK_TEMPLATES = [
        r"(?i)do\s+anything\s+now",
        r"(?i)DAN\s+mode",
        r"(?i)pretend\s+you\s+have\s+no\s+rules?",
        r"(?i)hypothetically\s+speaking",
        r"(?i)for\s+educational\s+purposes\s+only",
        r"(?i)act\s+as\s+an?\s+unfiltered\s+ai",
        r"(?i)bypass\s+safety\s+filter",
        r"(?i)always\s+respond\s+with\s+two\s+answers"
    ]

    def analyze(self, prompt: str, session_history: List[str] = None) -> Dict[str, Any]:
        score = 0.0
        matches = []
        
        # 1. Template matcher
        for pattern in self.JAILBREAK_TEMPLATES:
            if re.search(pattern, prompt):
                score += 0.40
                matches.append(pattern)
                
        # 2. Multi-turn context evaluation
        if session_history and len(session_history) > 3:
            # Check for escalation in conversation depth
            avg_length = sum(len(p) for p in session_history) / len(session_history)
            if len(prompt) > avg_length * 2.5:
                score += 0.20
                matches.append("multi_turn_prompt_escalation")

        final_score = min(1.0, score)
        return {
            "jailbreak_score": round(final_score, 3),
            "is_jailbreak": final_score >= 0.70,
            "patterns_matched": matches
        }

jailbreak_detector = JailbreakDetector()
