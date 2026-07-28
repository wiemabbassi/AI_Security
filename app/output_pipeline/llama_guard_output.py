from typing import Dict, Any
from app.input_pipeline.llama_guard import llama_guard

class LlamaGuardOutputScanner:
    """
    Output Safety Scanner using Meta Llama Guard 3.
    Ensures final generated responses do not contain emergent harmful content.
    """
    def scan(self, response_text: str) -> Dict[str, Any]:
        return llama_guard.classify(response_text)

llama_guard_output = LlamaGuardOutputScanner()
