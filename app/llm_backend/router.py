import requests
import json
import os
from typing import Dict, Any
from app.config import settings

try:
    import litellm
    # Configure LiteLLM options
    litellm.drop_params = True
except Exception:
    litellm = None

class LiteLLMRouter:
    """
    LiteLLM Unified Router:
    Provides a single API interface to 100+ LLM providers (Ollama, OpenAI, Azure, Anthropic).
    Routes requests based on data sensitivity:
    - Sensitive / Masked PII prompts -> Ollama (Local)
    - High-reasoning general queries -> OpenAI API (Cloud)
    """
    SYSTEM_PROMPT = "You are a helpful, secure AI assistant for enterprise queries."

    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", None)

    def generate(self, prompt: str, target_provider: str = "auto", is_sensitive: bool = True) -> Dict[str, Any]:
        # 1. LiteLLM Unified Completion call if available
        if litellm is not None and not is_sensitive and self.openai_api_key:
            try:
                response = litellm.completion(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=10.0
                )
                content = response.choices[0].message.content
                return {
                    "response": content,
                    "provider": "litellm_openai_cloud",
                    "model": settings.OPENAI_MODEL,
                    "usage": {
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens
                    }
                }
            except Exception:
                pass

        # 2. Local Ollama Execution (Zero-data exposure)
        if target_provider in ["ollama", "auto"]:
            try:
                resp = requests.post(
                    f"{settings.OLLAMA_URL}/api/chat",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        "options": {
                            "num_predict": 350
                        },
                        "stream": False
                    },
                    timeout=180.0
                )
                if resp.status_code == 200:
                    res_json = resp.json()
                    content = res_json.get("message", {}).get("content", "")
                    prompt_tokens = res_json.get("prompt_eval_count", len(prompt.split()))
                    completion_tokens = res_json.get("eval_count", len(content.split()))
                    if content:
                        return {
                            "response": content,
                            "provider": "ollama_local",
                            "model": settings.OLLAMA_MODEL,
                            "usage": {
                                "input": prompt_tokens,
                                "output": completion_tokens,
                                "total": prompt_tokens + completion_tokens
                            }
                        }
            except Exception as e:
                print(f"[OLLAMA ROUTER ERROR] {e}")

        # 3. Direct OpenAI Fallback if key available
        if self.openai_api_key:
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": settings.OPENAI_MODEL,
                        "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ]
                    },
                    timeout=5.0
                )
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    return {
                        "response": content,
                        "provider": "openai_cloud",
                        "model": settings.OPENAI_MODEL
                    }
            except Exception:
                pass

        # 4. Gateway Local Security Execution Engine Fallback
        # NOTE: never echo the prompt back — it may contain masked PII tokens
        # that would be restored by the output pipeline, leaking real PII.
        return {
            "response": (
                "Your request has been received and processed securely through the "
                "LLM Security Gateway. The language model is temporarily unavailable "
                "(Ollama not reachable). Please ensure Ollama is running and try again."
            ),
            "provider": "gateway_fallback_engine",
            "model": "local-security-v1",
            "usage": {
                "input": len(prompt.split()),
                "output": 30,
                "total": len(prompt.split()) + 30
            }
        }

llm_router = LiteLLMRouter()

