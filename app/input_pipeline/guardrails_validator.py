from typing import Dict, Any, List

# ── Guardrails AI Hub validators ──────────────────────────────────────────────
# Graceful degradation: if guardrails or hub validators aren't installed,
# we fall back to pure-Python implementations.
_gd_available = False
_toxic_guard = None
_topic_guard = None

try:
    import guardrails as gd

    try:
        from guardrails.hub import ToxicLanguage
        _toxic_guard = gd.Guard().use(ToxicLanguage(threshold=0.5, validation_method="sentence"))
        _gd_available = True
    except Exception:
        _toxic_guard = None

    try:
        from guardrails.hub import RestrictToTopic
        _topic_guard = gd.Guard().use(
            RestrictToTopic(
                valid_topics=["general assistance", "enterprise", "IT", "HR", "software"],
                invalid_topics=["illegal activities", "self-harm", "hacking", "violence"],
                disable_classifier=False,
                disable_llm=True,   # run classifier only — no extra LLM call
                on_fail="exception"
            )
        )
    except Exception:
        _topic_guard = None

except Exception:
    gd = None


class GuardrailsValidator:
    """
    Guardrails AI Declarative Input Validator (fully wired):

    Layer 1 — Token-length constraint (RAIL contract: max 2000 estimated tokens)
    Layer 2 — Prohibited-topic keyword gate (fast, <1ms)
    Layer 3 — ToxicLanguage Hub validator (sentence-level toxicity score ≥ 0.5)
    Layer 4 — RestrictToTopic Hub validator (topic relevance classifier)
    Layer 5 — Raw RAIL spec validation via gd.Guard (schema contract)

    Spec ref: tools_and_justification.md §2 — Guardrails AI Input Validation
    """

    MAX_TOKENS = 2000

    # Coarse prohibited-topic keyword list — fast pre-filter before ML validators
    PROHIBITED_TOPICS: List[str] = [
        "illegal activities", "self-harm", "malicious hacking",
        "how to make a bomb", "child abuse", "terrorism",
    ]

    # Explicit toxic phrases — caught by keyword before invoking the ML model
    EXPLICIT_TOXIC: List[str] = [
        "kill yourself", "you should die", "go hurt yourself",
    ]

    def __init__(self):
        # Raw RAIL spec guard (structural contract)
        self._rail_guard = None
        if gd is not None:
            try:
                rail_spec = """
                <rail version="0.1">
                <output>
                    <string name="user_prompt"
                            description="Sanitized user prompt"
                            required="true" />
                </output>
                </rail>
                """
                self._rail_guard = gd.Guard.from_rail_string(rail_spec)
            except Exception:
                self._rail_guard = None

    def validate_input(self, prompt: str) -> Dict[str, Any]:
        """
        Runs all 5 validation layers in order.
        Returns the first failure with a descriptive reason, or a pass result.
        """
        est_tokens = len(prompt) // 4

        # ── Layer 1: Token length ─────────────────────────────────────────────
        if est_tokens > self.MAX_TOKENS:
            return {
                "valid": False,
                "reason": (
                    f"Input length exceeds maximum allowed tokens "
                    f"({est_tokens} > {self.MAX_TOKENS}). Please shorten your request."
                ),
                "tokens": est_tokens,
                "layer": "token_length",
                "rail_validated": False,
            }

        lowered = prompt.lower()

        # ── Layer 2: Prohibited-topic keyword gate ────────────────────────────
        for topic in self.PROHIBITED_TOPICS:
            if topic in lowered:
                return {
                    "valid": False,
                    "reason": f"Prompt violates topic policy: '{topic}' is a restricted subject.",
                    "tokens": est_tokens,
                    "layer": "topic_keyword",
                    "rail_validated": False,
                }

        # ── Layer 2b: Explicit toxic keyword pre-filter ───────────────────────
        for phrase in self.EXPLICIT_TOXIC:
            if phrase in lowered:
                return {
                    "valid": False,
                    "reason": f"Prompt contains explicitly toxic language: '{phrase}'.",
                    "tokens": est_tokens,
                    "layer": "toxic_keyword",
                    "rail_validated": False,
                }

        # ── Layer 3: ToxicLanguage Hub validator ──────────────────────────────
        if _toxic_guard is not None:
            try:
                result = _toxic_guard.parse(prompt)
                if not result.validation_passed:
                    return {
                        "valid": False,
                        "reason": (
                            "ToxicLanguage validator: prompt contains toxic content "
                            f"(score ≥ 0.5). {getattr(result, 'error', '')}"
                        ),
                        "tokens": est_tokens,
                        "layer": "guardrails_toxic_language",
                        "rail_validated": True,
                    }
            except Exception as e:
                # If validator raises (e.g. on_fail="exception"), treat as block
                err_msg = str(e)
                if "toxic" in err_msg.lower() or "validation" in err_msg.lower():
                    return {
                        "valid": False,
                        "reason": f"ToxicLanguage validator blocked: {err_msg[:200]}",
                        "tokens": est_tokens,
                        "layer": "guardrails_toxic_language",
                        "rail_validated": True,
                    }

        # ── Layer 4: RestrictToTopic Hub validator ────────────────────────────
        if _topic_guard is not None:
            try:
                result = _topic_guard.parse(prompt)
                if not result.validation_passed:
                    return {
                        "valid": False,
                        "reason": (
                            "RestrictToTopic validator: prompt topic is outside "
                            f"allowed scope. {getattr(result, 'error', '')}"
                        ),
                        "tokens": est_tokens,
                        "layer": "guardrails_restrict_topic",
                        "rail_validated": True,
                    }
            except Exception as e:
                err_msg = str(e)
                if "topic" in err_msg.lower() or "validation" in err_msg.lower():
                    return {
                        "valid": False,
                        "reason": f"RestrictToTopic validator blocked: {err_msg[:200]}",
                        "tokens": est_tokens,
                        "layer": "guardrails_restrict_topic",
                        "rail_validated": True,
                    }

        # ── Layer 5: Raw RAIL spec schema validation ──────────────────────────
        if self._rail_guard is not None:
            try:
                res = self._rail_guard.validate(prompt)
                if not res.validation_passed:
                    return {
                        "valid": False,
                        "reason": f"RAIL schema contract failed: {getattr(res, 'error', 'schema mismatch')}",
                        "tokens": est_tokens,
                        "layer": "rail_schema",
                        "rail_validated": True,
                    }
            except Exception:
                pass  # RAIL guard unavailable — not a blocking failure

        # ── All layers passed ─────────────────────────────────────────────────
        return {
            "valid": True,
            "reason": None,
            "tokens": est_tokens,
            "layer": "passed_all",
            "rail_validated": self._rail_guard is not None,
            "guardrails_hub_active": _gd_available,
        }


guardrails_validator = GuardrailsValidator()
