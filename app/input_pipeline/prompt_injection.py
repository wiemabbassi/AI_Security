import re
import base64
from typing import Dict, Any

_ml_injection_pipeline = None
_ml_injection_attempted = False

def get_ml_injection_pipeline():
    global _ml_injection_pipeline, _ml_injection_attempted
    if not _ml_injection_attempted:
        _ml_injection_attempted = True
        try:
            from transformers import pipeline
            _ml_injection_pipeline = pipeline(
                "text-classification",
                model="protectai/deberta-v3-base-prompt-injection-v2",
                tokenizer="protectai/deberta-v3-base-prompt-injection-v2",
                top_k=None
            )
        except Exception:
            _ml_injection_pipeline = None
    return _ml_injection_pipeline


class PromptInjectionDetector:
    """
    Multi-layered Prompt Injection Detector:
    1. Base64 & Encoded Payload Decoder
    2. Heuristic Rule Engine (Structural anomalies, system tags)
    3. Regex Pattern Classifier
    4. Fine-tuned DeBERTa-v3 ML Classifier (Hugging Face Transformers)
    """

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|above)\s+instructions?",
        r"(?i)disregard\s+(all\s+)?(customer\s+review|guidelines?|instructions?|rules?)",
        r"(?i)override\s+(all\s+)?(system\s+)?prompts?",
        r"(?i)you\s+are\s+now\s+in\s+developer\s+mode",
        r"(?i)start\s+a\s+new\s+conversation\s+from\s+scratch",
        r"(?i)\[SYSTEM(\s*(NOTE|TAG|DIRECTIVE))?\]",
        r"(?i)<\|im_start\|>",
        r"(?i)reveal\s+your\s+instructions?",
        r"(?i)print\s+your\s+(initial|system)\s+prompt",
        r"(?i)repeat\s+(verbatim\s+)?(all\s+)?instructions?",
        r"(?i)repeat\s+the\s+words\s+above",
        r"(?i)print\s+(the\s+)?.*passwords?",
        r"(?i)print\s+(secret\s+)?api\s*key",
        r"(?i)starting\s+with\s+['\"]?you\s+are\s+a",
        r"(?i)training\s+corpus",
        r"(?i)print\s+(the\s+values\s+of\s+)?.*environment\s+variables?",
        r"(?i)OPENAI_API_KEY",
        r"(?i)DATABASE_URL",
        r"(?i)SECRET_KEY",
        r"(?i)tracking\s+pixel",
        r"(?i)!\[.*\]\(https?://"
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

        # 3. Fine-tuned DeBERTa-v3 ML Classifier Inference
        pipe = get_ml_injection_pipeline()
        if pipe is not None:
            try:
                res = pipe(augmented_prompt[:512])
                if isinstance(res, list) and len(res) > 0:
                    scores_dict = {item['label'].upper(): item['score'] for item in res[0]}
                    ml_score = scores_dict.get("INJECTION", scores_dict.get("LABEL_1", 0.0))
                    if ml_score > 0.5:
                        # KEY FIX: ML classifier alone is not sufficient to BLOCK.
                        # Known issue: DeBERTa-v3 gives false positives on PII-heavy queries
                        # (structured data like emails/phones confuses the model).
                        # Require at least one regex/heuristic pattern to reach BLOCK threshold.
                        # ML-only signals cap at 0.65 (FLAG range), not 0.75+ (BLOCK range).
                        if len(matches) == 0:
                            # No structural evidence — ML alone, cap below BLOCK threshold
                            score = max(score, min(ml_score, 0.65))
                        else:
                            # Structural + ML corroboration — full score
                            score = max(score, ml_score)
                        matches.append("deberta_v3_ml_classifier")
            except Exception:
                pass

        final_score = min(1.0, score)
        return {
            "injection_score": round(final_score, 3),
            # is_injection requires score >= 0.70 (not just any match)
            "is_injection": final_score >= 0.70,
            "patterns_matched": matches
        }

injection_detector = PromptInjectionDetector()

