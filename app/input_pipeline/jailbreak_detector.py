import re
from typing import Dict, Any, List

_ml_roberta_jailbreak = None
_ml_roberta_attempted = False

def get_ml_roberta_jailbreak():
    global _ml_roberta_jailbreak, _ml_roberta_attempted
    if not _ml_roberta_attempted:
        _ml_roberta_attempted = True
        try:
            from transformers import pipeline
            _ml_roberta_jailbreak = pipeline(
                "text-classification",
                model="hubert233/GPTFuzz",
                tokenizer="hubert233/GPTFuzz",
                top_k=None
            )
        except Exception:
            _ml_roberta_jailbreak = None
    return _ml_roberta_jailbreak

class JailbreakDetector:
    """
    Jailbreak Detector targeting behavioral manipulation, DAN/AIM/Developer Mode prompts,
    hypothetical roleplay framing, RoBERTa pragmatics ML model, and multi-turn escalation tracking.
    """

    # High-confidence DAN-family patterns (score 0.55 each).
    # Two matches alone = 1.10 (capped at 1.0) → guaranteed BLOCK.
    DAN_PATTERNS = [
        r"(?i)\bDAN\b",                                      # The acronym itself
        r"(?i)do\s+anything\s+now",                           # Full DAN expansion
        r"(?i)act\s+as\s+a?\s*(DAN|jailbroken|free\s+AI)",   # Role assignment
        r"(?i)from\s+now\s+on\s+you\s+(are|will)",            # Identity override
        r"(?i)broken\s+free",                                 # "broken free of the typical confines"
        r"(?i)typical\s+confines\s+of\s+(AI|the\s+model)",   # DAN boilerplate
        r"(?i)no\s+longer\s+bound\s+by",                      # Rule removal framing
        r"(?i)(pretend|act|behave)\s+(like|as)\s+(if\s+)?you\s+(have\s+no|are\s+not)",  # Roleplay bypass
    ]

    # Generic jailbreak templates (score 0.40 each)
    JAILBREAK_TEMPLATES = [
        r"(?i)DAN\s+mode",
        r"(?i)AIM\s+prompt",
        r"(?i)developer\s+mode\s+enabled",
        r"(?i)pretend\s+you\s+have\s+no\s+rules?",
        r"(?i)hypothetically\s+speaking",
        r"(?i)for\s+educational\s+purposes\s+only",
        r"(?i)act\s+as\s+an?\s+unfiltered\s+ai",
        r"(?i)bypass\s+safety\s+filter",
        r"(?i)always\s+respond\s+with\s+two\s+answers",
        r"(?i)opposite\s+mode",
        r"(?i)jailbroken",
        r"(?i)ignore\s+ethical\s+guidelines",
    ]

    def analyze(self, prompt: str, session_history: List[str] = None) -> Dict[str, Any]:
        score = 0.0
        matches = []

        # 1. High-confidence DAN-family pattern check (0.55 per match)
        for pattern in self.DAN_PATTERNS:
            if re.search(pattern, prompt):
                score += 0.55
                matches.append(f"dan_family:{pattern[:30]}")

        # 2. Generic jailbreak template matcher (0.40 per match)
        for pattern in self.JAILBREAK_TEMPLATES:
            if re.search(pattern, prompt):
                score += 0.40
                matches.append(f"template:{pattern[:30]}")

        # 3. Multi-turn context evaluation & conversation history escalation tracking
        if session_history and len(session_history) >= 2:
            avg_length = sum(len(p) for p in session_history) / len(session_history)
            if len(prompt) > avg_length * 2.0:
                score += 0.25
                matches.append("multi_turn_prompt_escalation")

        # 4. RoBERTa / GPTFuzz ML Pragmatics Inference
        pipe = get_ml_roberta_jailbreak()
        if pipe is not None:
            try:
                res = pipe(prompt[:512])
                if isinstance(res, list) and len(res) > 0:
                    scores_dict = {item['label'].upper(): item['score'] for item in res[0]}
                    ml_score = scores_dict.get("JAILBREAK", scores_dict.get("LABEL_1", 0.0))
                    if ml_score > 0.5:
                        score = max(score, ml_score)
                        matches.append("roberta_pragmatics_classifier")
            except Exception:
                pass

        final_score = min(1.0, score)
        return {
            "jailbreak_score": round(final_score, 3),
            "is_jailbreak": final_score >= 0.70,
            "patterns_matched": matches
        }

jailbreak_detector = JailbreakDetector()
