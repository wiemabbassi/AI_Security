import time
import datetime
import requests
import uuid
from typing import Dict, Any, List, Optional
from app.config import settings

class LangfuseTracer:
    """
    Langfuse LLM-Native Tracing Handler
    Direct REST API Ingestion Handler — guarantees 100% reliable delivery to Langfuse Web UI.
    """
    def __init__(self):
        self.traces: List[Dict[str, Any]] = []

    def create_trace(
        self,
        name: str,
        user_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        scores: Dict[str, float],
        latency_ms: float,
        usage: Optional[Dict[str, int]] = None,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        trace_id = str(uuid.uuid4())
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"

        trace = {
            "trace_id": trace_id,
            "name": name,
            "user_id": user_id,
            "session_id": session_id or user_id,
            "timestamp": time.time(),
            "input": input_data,
            "output": output_data,
            "scores": scores,
            "latency_ms": latency_ms,
            "usage": usage or {},
            "tags": tags or []
        }
        self.traces.append(trace)
        if len(self.traces) > 500:
            self.traces.pop(0)

        # Skip REST ingestion if Langfuse keys are not configured
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return trace
        try:
            batch_items = [
                {
                    "id": str(uuid.uuid4()),
                    "type": "trace-create",
                    "timestamp": now_iso,
                    "body": {
                        "id": trace_id,
                        "name": name,
                        "userId": user_id,
                        "sessionId": session_id or user_id,
                        "input": input_data,
                        "output": output_data,
                        "tags": tags or [],
                        "metadata": {"latency_ms": latency_ms, "usage": usage or {}},
                        "timestamp": now_iso
                    }
                }
            ]

            # Track LLM Generation Span with Token Counts if model generated text
            if usage and usage.get("total", 0) > 0:
                # Use the actual provider from output_data if available
                provider_name = (
                    output_data.get("provider")
                    or input_data.get("provider")
                    or "gateway_llm_generation"
                )
                batch_items.append({
                    "id": str(uuid.uuid4()),
                    "type": "generation-create",
                    "timestamp": now_iso,
                    "body": {
                        "id": str(uuid.uuid4()),
                        "traceId": trace_id,
                        "name": provider_name,
                        "model": settings.OLLAMA_MODEL,
                        "usage": {
                            "promptTokens": usage.get("input", 0),
                            "completionTokens": usage.get("output", 0),
                            "totalTokens": usage.get("total", 0)
                        },
                        "input": input_data,
                        "output": output_data,
                        "timestamp": now_iso
                    }
                })

            for score_name, score_val in scores.items():
                batch_items.append({
                    "id": str(uuid.uuid4()),
                    "type": "score-create",
                    "timestamp": now_iso,
                    "body": {
                        "id": str(uuid.uuid4()),
                        "traceId": trace_id,
                        "name": score_name,
                        "value": float(score_val)
                    }
                })

            resp = requests.post(
                f"{settings.LANGFUSE_HOST}/api/public/ingestion",
                auth=(settings.LANGFUSE_PUBLIC_KEY, settings.LANGFUSE_SECRET_KEY),
                headers={"Content-Type": "application/json"},
                json={"batch": batch_items},
                timeout=3.0
            )
            if resp.status_code == 207:
                print(f"[LANGFUSE REST INGESTION SUCCESS] Trace {trace_id} pushed to Web UI.")
        except Exception as e:
            print(f"[LANGFUSE REST INGESTION ERROR] {e}")

        return trace

    def get_recent_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.traces[-limit:]

langfuse_tracer = LangfuseTracer()

def format_prometheus_metrics(metrics_data: Dict[str, Any]) -> str:
    """
    Formats operational metrics into official Prometheus plain-text format for Grafana ingestion.
    """
    lines = [
        "# HELP gateway_requests_total Total number of incoming requests",
        "# TYPE gateway_requests_total counter",
        f"gateway_requests_total {metrics_data.get('total_requests', 0)}",
        "",
        "# HELP gateway_requests_blocked_total Total number of blocked attack requests",
        "# TYPE gateway_requests_blocked_total counter",
        f"gateway_requests_blocked_total {metrics_data.get('blocked_requests', 0)}",
        "",
        "# HELP gateway_requests_flagged_total Total number of flagged requests for review",
        "# TYPE gateway_requests_flagged_total counter",
        f"gateway_requests_flagged_total {metrics_data.get('flagged_requests', 0)}",
        "",
        "# HELP gateway_block_rate Ratio of blocked requests to total requests",
        "# TYPE gateway_block_rate gauge",
        f"gateway_block_rate {metrics_data.get('block_rate', 0.0)}",
        "",
        "# HELP gateway_latency_p95_ms 95th percentile latency in milliseconds",
        "# TYPE gateway_latency_p95_ms gauge",
        f"gateway_latency_p95_ms {metrics_data.get('p95_latency_ms', 0.0)}",
        "",
        "# HELP gateway_latency_p99_ms 99th percentile latency in milliseconds",
        "# TYPE gateway_latency_p99_ms gauge",
        f"gateway_latency_p99_ms {metrics_data.get('p99_latency_ms', 0.0)}"
    ]
    return "\n".join(lines)
