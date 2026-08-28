"""
Demo Pre-flight Check
=====================
Run this BEFORE starting the recording to verify all services are up.
Usage: python demo_preflight.py
"""

import requests
import sys
import time

GATEWAY = "http://localhost:8000"
OLLAMA  = "http://localhost:11434"
DASH    = "http://localhost:8501"

def check(label, fn):
    try:
        ok, msg = fn()
        status = "✅" if ok else "❌"
        print(f"  {status}  {label}: {msg}")
        return ok
    except Exception as e:
        print(f"  ❌  {label}: ERROR — {e}")
        return False

print()
print("=" * 60)
print("  DEMO PRE-FLIGHT CHECK — LLM Security Gateway")
print("=" * 60)
print()

results = []

# 1. Gateway health
results.append(check("FastAPI Gateway (port 8000)", lambda: (
    (r := requests.get(f"{GATEWAY}/", timeout=3)).status_code == 200,
    f"online — {r.json().get('name')}"
)))

# 2. Ollama
results.append(check("Ollama LLM Server (port 11434)", lambda: (
    (r := requests.get(f"{OLLAMA}/api/tags", timeout=3)).status_code == 200,
    f"online — models: {[m['name'] for m in r.json().get('models', [])]}"
)))

# 3. Streamlit
results.append(check("Streamlit Dashboard (port 8501)", lambda: (
    requests.get(f"{DASH}/", timeout=3).status_code == 200,
    "online"
)))

# 4. Gateway metrics endpoint
results.append(check("Gateway metrics endpoint", lambda: (
    (r := requests.get(f"{GATEWAY}/metrics", timeout=3)).status_code == 200,
    f"total_requests={r.json().get('total_requests', 0)}"
)))

# 5. Gateway events endpoint
results.append(check("Event log endpoint", lambda: (
    requests.get(f"{GATEWAY}/events", timeout=3).status_code == 200,
    "accessible"
)))

# 6. Warm-up request (loads ML models into memory)
print()
print("  🔥  Warming up ML models (first request loads DeBERTa, Presidio, etc.)...")
try:
    r = requests.post(f"{GATEWAY}/v1/chat",
        json={"prompt": "hello warmup test", "user_id": "warmup"},
        timeout=120
    )
    if r.status_code in [200, 403]:
        print(f"  ✅  Warm-up complete (HTTP {r.status_code}) — all ML models loaded into memory")
        results.append(True)
    else:
        print(f"  ⚠️   Warm-up returned HTTP {r.status_code}: {r.text[:100]}")
        results.append(False)
except Exception as e:
    print(f"  ❌  Warm-up failed: {e}")
    results.append(False)

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 60)
passed = sum(results)
total = len(results)
if passed == total:
    print(f"  🟢  ALL CHECKS PASSED ({passed}/{total}) — YOU ARE READY TO RECORD!")
else:
    print(f"  🔴  {total - passed} CHECK(S) FAILED — Fix issues above before recording")
print("=" * 60)
print()

if passed < total:
    print("  HOW TO START MISSING SERVICES:")
    print()
    print("  1. Ollama:    Open a terminal → run:  ollama serve")
    print("                Then in another terminal: ollama pull llama3.2:latest")
    print()
    print("  2. Gateway:   Open a terminal in the project folder → run:")
    print("                uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    print()
    print("  3. Dashboard: Open a terminal in the project folder → run:")
    print("                streamlit run dashboard/app.py --server.port 8501")
    print()
    sys.exit(1)

sys.exit(0)
