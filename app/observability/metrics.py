import time
from typing import Dict, Any

try:
    import numpy as np
except ImportError:
    np = None

class MetricsCollector:
    """
    Prometheus & Langfuse Observability Metrics Collector
    Tracks p95/p99 latency, request throughput, risk scores, and block rates.
    """
    def __init__(self):
        self.total_requests = 0
        self.blocked_requests = 0
        self.flagged_requests = 0
        self.latencies = []

    def record_request(self, latency_ms: float, action: str):
        self.total_requests += 1
        self.latencies.append(latency_ms)
        if len(self.latencies) > 1000:
            self.latencies.pop(0)
            
        if action == "BLOCK":
            self.blocked_requests += 1
        elif action == "FLAG":
            self.flagged_requests += 1

    def get_metrics(self) -> Dict[str, Any]:
        if self.latencies:
            if np is not None:
                p95 = float(np.percentile(self.latencies, 95))
                p99 = float(np.percentile(self.latencies, 99))
            else:
                sorted_lat = sorted(self.latencies)
                p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
                p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        else:
            p95 = 0.0
            p99 = 0.0
        
        return {
            "total_requests": self.total_requests,
            "blocked_requests": self.blocked_requests,
            "flagged_requests": self.flagged_requests,
            "block_rate": round(self.blocked_requests / max(1, self.total_requests), 4),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2)
        }

metrics_collector = MetricsCollector()
