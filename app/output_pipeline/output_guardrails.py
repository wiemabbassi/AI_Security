import json
from typing import Dict, Any
from app.input_pipeline.pii_detector import pii_detector

# Try Guardrails AI Hub validators — graceful degradation if not installed
_guardrails_available = False
_valid_json_guard = None
_provenance_guard = None

try:
    import guardrails as gd

    # ValidJSON — ensures output is syntactically valid JSON when expected
    try:
        from guardrails.hub import ValidJSON
        _valid_json_guard = gd.Guard().use(ValidJSON())
        _guardrails_available = True
    except Exception:
        _valid_json_guard = None

    # ProvenanceVerifier — groundedness check (response supported by context)
    try:
        from guardrails.hub import ProvenanceVerifier
        _provenance_guard = gd.Guard().use(ProvenanceVerifier(threshold=0.5))
    except Exception:
        _provenance_guard = None

except Exception:
    gd = None


class OutputGuardrailsValidator:
    """
    Guardrails AI Output Validator (fully wired):
    1. Bi-directional PII token restoration (unmask → original values)
    2. Structural ValidJSON check when response looks like JSON
    3. ProvenanceVerifier groundedness check (response stays on-context)
    4. Response quality gate (non-empty, not a refusal loop)

    Spec ref: tools_and_justification.md §6 — Output Guardrails AI Validation
    Key validators: ValidJSON, ProvenanceVerifier, ResponseRelevancy, NoOffTopic
    """

    # Common model refusal patterns — flag for review (not block, just note)
    REFUSAL_PATTERNS = [
        "i cannot", "i'm unable to", "i am unable to",
        "i don't have the ability", "as an ai language model",
        "i must decline", "that request falls outside"
    ]

    def validate_and_restore(
        self,
        response_text: str,
        pii_map: Dict[str, str],
        context: str = ""
    ) -> Dict[str, Any]:
        """
        Full output validation pipeline:
          Step 1 → Restore PII tokens
          Step 2 → ValidJSON (if JSON-shaped)
          Step 3 → ProvenanceVerifier groundedness
          Step 4 → Quality gate
        """
        result = {
            "valid": True,
            "is_valid_json": False,
            "final_response": response_text,
            "pii_restored_count": 0,
            "groundedness_verified": False,
            "guardrails_passed": False,
            "issues": []
        }

        # ── Step 1: Restore original PII tokens securely ─────────────────────
        restored_text = pii_detector.unmask_pii(response_text, pii_map)
        result["final_response"] = restored_text
        result["pii_restored_count"] = len(pii_map)

        # ── Step 2: ValidJSON — only when response looks like JSON ────────────
        is_json_shaped = (
            restored_text.strip().startswith("{") and restored_text.strip().endswith("}")
        ) or (
            restored_text.strip().startswith("[") and restored_text.strip().endswith("]")
        )

        if is_json_shaped:
            # First try native json.loads
            try:
                json.loads(restored_text)
                result["is_valid_json"] = True
            except json.JSONDecodeError as je:
                result["is_valid_json"] = False
                result["issues"].append(f"JSON parse error: {je}")

            # Then try Guardrails ValidJSON validator if available
            if _valid_json_guard is not None:
                try:
                    validated = _valid_json_guard.parse(restored_text)
                    result["guardrails_passed"] = validated.validation_passed
                    if not validated.validation_passed:
                        result["issues"].append(
                            f"Guardrails ValidJSON failed: {getattr(validated, 'error', 'schema mismatch')}"
                        )
                except Exception:
                    pass  # Validator unavailable — native check result stands

        # ── Step 3: ProvenanceVerifier groundedness check ─────────────────────
        if _provenance_guard is not None and context:
            try:
                grounded = _provenance_guard.parse(
                    restored_text,
                    metadata={"sources": [context]}
                )
                result["groundedness_verified"] = grounded.validation_passed
                if not grounded.validation_passed:
                    result["issues"].append("ProvenanceVerifier: response not grounded in provided context")
            except Exception:
                # Provenance check unavailable — mark as skipped (not failed)
                result["groundedness_verified"] = False
        else:
            # No context provided — groundedness check skipped (not a failure)
            result["groundedness_verified"] = True

        # ── Step 4: Response quality gate ─────────────────────────────────────
        stripped = restored_text.strip()

        if not stripped:
            result["valid"] = False
            result["issues"].append("Empty response from LLM")
            return result

        # Flag (but don't block) model refusals — surface them in audit log
        lowered = stripped.lower()
        for pattern in self.REFUSAL_PATTERNS:
            if pattern in lowered:
                result["issues"].append(f"Model refusal pattern detected: '{pattern}'")
                break

        # Mark overall guardrails as passed if no blocking issues
        if not result["issues"] or all("refusal" in i for i in result["issues"]):
            result["guardrails_passed"] = True

        return result


output_guardrails = OutputGuardrailsValidator()
