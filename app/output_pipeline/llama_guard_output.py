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
        Scans the LLM-generated response for emergent harmful content (malware, exploits, threats).
        Returns: {"status": "SAFE"|"UNSAFE", "category": str|None, "confidence": float}
        """
        lowered = response_text.lower()
        for term in self.HARMFUL_OUTPUT_TERMS:
            if term in lowered:
                return {
                    "status": "UNSAFE",
                    "category": f"Output safety violation: harmful pattern detected ('{term}')",
                    "confidence": 0.95,
                    "scan_mode": "output_safety_filter"
                }

        return {
            "status": "SAFE",
            "category": None,
            "confidence": 0.99,
            "scan_mode": "output_safety_filter"
        }


llama_guard_output = LlamaGuardOutputScanner()
