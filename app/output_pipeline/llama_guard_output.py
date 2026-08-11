import json
from typing import Dict, Any
from app.config import settings

try:
    import requests as _requests
except ImportError:
    _requests = None

import urllib.request


class LlamaGuardOutputScanner:
    """
    Output Safety Scanner using Meta Llama Guard 3 (8B).
    Uses the ASSISTANT turn framing — specifically scans the LLM *response*
    for emergent harmful content that passed input filtering.

    This is the LAST safety net before the response reaches the user.
    It catches:
      - Emergent harmful content from seemingly-safe prompts
      - Jailbreak outputs that slipped through input scanning
      - Creative/fictional tasks that produced unexpected unsafe content
    """

    # Llama Guard 3 output-scan prompt template (scan the assistant's response)
    OUTPUT_SCAN_TEMPLATE = (
        "[INST] Task: Check if there is unsafe content in the 'Agent' messages in the "
        "conversation according to our safety policy.\n\n"
        "<BEGIN CONVERSATION>\nUser: [input not evaluated]\nAgent: {response}\n"
        "<END CONVERSATION>\n\n"
        "Provide your safety assessment for the Agent message only:\n"
        "- First line must read 'safe' or 'unsafe'\n"
        "- If unsafe, second line must include a comma-separated list of violated categories [/INST]"
    )

    HARMFUL_OUTPUT_TERMS = [
        "here is how to make", "step-by-step instructions",
        "to build a bomb", "to create malware", "exploit code",
        "how to hack", "steal credentials", "bypass security",
    ]

    def scan(self, response_text: str) -> Dict[str, Any]:
        """
        Scans the LLM-generated response for harmful content.
        Returns: {"status": "SAFE"|"UNSAFE", "category": str|None, "confidence": float}
        """
        # 1. Try Ollama Llama Guard with output-mode framing
        scan_prompt = self.OUTPUT_SCAN_TEMPLATE.format(
            response=response_text[:2000]  # cap to avoid token overflow
        )
        try:
            if _requests is not None:
                resp = _requests.post(
                    f"{settings.OLLAMA_URL}/api/generate",
                    json={
                        "model": settings.OLLAMA_SAFETY_MODEL,
                        "prompt": scan_prompt,
                        "stream": False
                    },
                    timeout=8.0
                )
                if resp.status_code == 200:
                    content = resp.json().get("response", "").strip().lower()
                    first_line = content.split("\n")[0].strip()
                    if "unsafe" in first_line:
                        lines = content.split("\n")
                        category = lines[1].strip() if len(lines) > 1 else "Unknown category"
                        return {
                            "status": "UNSAFE",
                            "category": f"Output scan: {category}",
                            "confidence": 0.93,
                            "scan_mode": "llama_guard_output_turn"
                        }
                    return {
                        "status": "SAFE",
                        "category": None,
                        "confidence": 0.98,
                        "scan_mode": "llama_guard_output_turn"
                    }
        except Exception as e:
            pass  # Fall through to heuristic fallback

        # 2. Heuristic fallback — keyword scan of response content
        lowered = response_text.lower()
        for term in self.HARMFUL_OUTPUT_TERMS:
            if term in lowered:
                return {
                    "status": "UNSAFE",
                    "category": f"Output heuristic: harmful instruction pattern detected ('{term}')",
                    "confidence": 0.85,
                    "scan_mode": "heuristic_fallback"
                }

        return {
            "status": "SAFE",
            "category": None,
            "confidence": 0.95,
            "scan_mode": "heuristic_fallback"
        }


llama_guard_output = LlamaGuardOutputScanner()
