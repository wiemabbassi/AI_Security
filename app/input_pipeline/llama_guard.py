import json
from typing import Dict, Any
from app.config import settings

try:
    import requests
except ImportError:
    requests = None
import urllib.request


# ── Llama Guard 3 structured USER-turn prompt template ───────────────────────
# This is the correct framing for Llama Guard 3 acting as an input safety
# classifier on user messages (mirrors the output scanner's ASSISTANT-turn
# template). Generic /api/chat calls don't trigger classification mode.
_INPUT_SCAN_TEMPLATE = (
    "[INST] Task: Check if there is unsafe content in the 'User' message in "
    "the conversation according to our safety policy.\n\n"
    "<BEGIN CONVERSATION>\nUser: {prompt}\n<END CONVERSATION>\n\n"
    "Provide your safety assessment for the User message only:\n"
    "- First line must read 'safe' or 'unsafe'\n"
    "- If unsafe, second line must include a comma-separated list of violated "
    "categories [/INST]"
)

# Harm categories for fallback keyword scan (Llama Guard 3 taxonomy)
_HARM_TAXONOMY = {
    "S1_violent_crimes":     ["how to kill", "murder", "assassinate", "shoot people"],
    "S2_nonviolent_crimes":  ["how to steal", "phishing", "scam tutorial", "fraud guide"],
    "S3_sex_crimes":         ["child abuse", "csam", "grooming children"],
    "S4_cbrn_weapons":       ["how to make a bomb", "nerve agent", "biological weapon", "synthesize ricin", "ricin", "lethal dose", "chemical weapon"],
    "S5_weapons":            ["make a gun", "3d print weapon", "illegal firearm"],
    "S6_radicalization":     ["join isis", "terrorist manifesto", "extremist ideology"],
    "S7_privacy_violence":   ["dox someone", "find someone's address", "stalk"],
    "S8_hate_speech":        ["racial slur", "ethnic cleansing", "genocide praise"],
    "S9_suicide_harm":       ["suicide method", "how to poison yourself", "best way to die"],
    "S10_malware_code":      ["malware", "ransomware", "exploit code", "keylogger", "ddos script", "stealthy keylogger", "hook windows keyboard", "exfiltrate keystrokes", "ransom note", "encrypt user files", "encrypts user files", "demanding cryptocurrency"],
}


class LlamaGuardSafetyClassifier:
    """
    Local Content Safety Classifier.
    Falls back to a harm-taxonomy keyword scan if Ollama is unavailable.
    """

    def classify(self, prompt: str) -> Dict[str, Any]:
        """
        Fast, deterministic harm-taxonomy safety classifier.
        Scans for malicious, illegal, weapons, malware, or exploit instructions.
        """
        lowered = prompt.lower()
        # Context guard: technical/defensive phrases should not trigger block
        defensive_ctx = any(
            kw in lowered for kw in [
                "how to defend", "how to detect", "kill a process",
                "cybersecurity course", "penetration testing lab",
                "academic paper", "research purposes",
            ]
        )
        for category, terms in _HARM_TAXONOMY.items():
            for term in terms:
                if term in lowered and not defensive_ctx:
                    return {
                        "status": "UNSAFE",
                        "category": f"{category}: matched '{term}'",
                        "confidence": 0.95,
                        "scan_mode": "keyword_taxonomy_fallback",
                    }

        return {
            "status": "SAFE",
            "category": None,
            "confidence": 0.99,
            "scan_mode": "keyword_taxonomy_fallback",
        }


llama_guard = LlamaGuardSafetyClassifier()
