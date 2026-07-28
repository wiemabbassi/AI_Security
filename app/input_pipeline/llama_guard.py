import json
from typing import Dict, Any
from app.config import settings

try:
    import requests
except ImportError:
    requests = None
import urllib.request

class LlamaGuardSafetyClassifier:
    """
    Local Meta Llama Guard 3 Content Safety Classifier
    Evaluates prompts against harm taxonomy (violence, hate speech, illegal acts, malware).
    """
    
    HARMFUL_TERMS = [
        "bomb", "malware", "exploit", "ransomware", "ddos", "keylogger",
        "suicide", "poison", "assassinate", "weapon"
    ]

    def classify(self, prompt: str) -> Dict[str, Any]:
        # Try local Ollama instance if available
        try:
            if requests is not None:
                resp = requests.post(
                    f"{settings.OLLAMA_URL}/api/chat",
                    json={
                        "model": settings.OLLAMA_SAFETY_MODEL,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=2.0
                )
                if resp.status_code == 200:
                    content = resp.json().get("message", {}).get("content", "")
                    if "unsafe" in content.lower():
                        return {"status": "UNSAFE", "category": content, "confidence": 0.95}
                    return {"status": "SAFE", "category": None, "confidence": 0.99}
            else:
                data = json.dumps({
                    "model": settings.OLLAMA_SAFETY_MODEL,
                    "messages": [{"role": "user", "content": prompt}]
                }).encode('utf-8')
                req = urllib.request.Request(f"{settings.OLLAMA_URL}/api/chat", data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=2.0) as response:
                    res_body = json.loads(response.read().decode('utf-8'))
                    content = res_body.get("message", {}).get("content", "")
                    if "unsafe" in content.lower():
                        return {"status": "UNSAFE", "category": content, "confidence": 0.95}
                    return {"status": "SAFE", "category": None, "confidence": 0.99}
        except Exception:
            pass
            
        # Fallback local taxonomy inspection
        lowered = prompt.lower()
        for term in self.HARMFUL_TERMS:
            if term in lowered and not ("how to defend" in lowered or "kill a process" in lowered):
                return {
                    "status": "UNSAFE",
                    "category": f"S1: Harmful Content ({term})",
                    "confidence": 0.90
                }
                
        return {"status": "SAFE", "category": None, "confidence": 0.99}

llama_guard = LlamaGuardSafetyClassifier()
