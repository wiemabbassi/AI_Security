"""
Giskard LLM Vulnerability Scan (Direct Ollama vs. LLM Security Gateway)
======================================================================
Runs Giskard's LLM Security Scanner comparing:
  1. Pathway A: Direct Ollama (Unprotected Baseline via /v1/direct)
  2. Pathway B: LLM Security Gateway (Protected via /v1/chat)

Outputs:
  - reports/giskard_direct_baseline.html
  - reports/giskard_gateway_protected.html
  - reports/giskard_comparison_summary.json
"""

import os
import sys
import json
import time
import requests
import pandas as pd

# Ensure UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)
GATEWAY_URL = "http://127.0.0.1:8000"

# Check Giskard availability
try:
    import giskard
except ImportError:
    print("[ERROR] Giskard not installed in current interpreter.")
    print("Please execute with: ..\\giskard\\giskard-env\\Scripts\\python.exe benchmark_giskard_comparison.py")
    sys.exit(1)

# Configure Giskard local Ollama judge
try:
    giskard.llm.set_llm_model("ollama/llama3.2:latest", disable_structured_output=True, api_base="http://localhost:11434")
except Exception as e:
    print(f"[WARN] Could not set Giskard Ollama judge model: {e}")

# ── Prediction functions ───────────────────────────────────────────────────────

def predict_direct(df: pd.DataFrame):
    """Pathway A: Direct Ollama (unprotected)"""
    outputs = []
    for question in df["question"]:
        try:
            r = requests.post(f"{GATEWAY_URL}/v1/direct", json={"prompt": str(question)}, timeout=60)
            if r.status_code == 200:
                outputs.append(r.json().get("response", ""))
            else:
                outputs.append(f"HTTP {r.status_code}")
        except Exception as e:
            outputs.append(f"Error: {e}")
    return outputs

def predict_gateway(df: pd.DataFrame):
    """Pathway B: LLM Security Gateway (protected)"""
    outputs = []
    for question in df["question"]:
        try:
            r = requests.post(
                f"{GATEWAY_URL}/v1/chat?refusal_as_200=true",
                headers={"X-Scanner-Run": "true"},
                json={"prompt": str(question), "user_id": "giskard_scan"},
                timeout=60
            )
            if r.status_code == 200:
                outputs.append(r.json().get("response", ""))
            else:
                outputs.append(f"HTTP {r.status_code}")
        except Exception as e:
            outputs.append(f"Error: {e}")
    return outputs


def run_giskard_benchmark():
    print("=" * 80)
    print("🛡️  STARTING GISKARD LLM SECURITY SCAN COMPARISON")
    print("=" * 80)

    # Wrap models
    direct_model = giskard.Model(
        model=predict_direct,
        model_type="text_generation",
        name="Direct-Ollama-Baseline",
        description="Direct raw local Ollama LLM without security controls.",
        feature_names=["question"],
    )

    gateway_model = giskard.Model(
        model=predict_gateway,
        model_type="text_generation",
        name="LLM-Security-Gateway-Protected",
        description="Enterprise LLM Security Gateway with multi-layered guardrails.",
        feature_names=["question"],
    )

    # 1. Scan Direct Baseline
    print("\n[1/2] Scanning Baseline (Direct Ollama)...", flush=True)
    t0 = time.time()
    try:
        report_direct = giskard.scan(direct_model, only=["prompt_injection"])
        direct_html = os.path.join(REPORT_DIR, "giskard_direct_baseline.html")
        report_direct.to_html(direct_html)
        direct_issues = len(report_direct.issues)
        print(f"  [DIRECT] Scan completed in {round(time.time() - t0, 1)}s. Issues found: {direct_issues}")
        print(f"  [DIRECT] Report saved: {direct_html}")
    except Exception as e:
        print(f"  [DIRECT] Scan failed or partial: {e}")
        direct_issues = -1

    # 2. Scan Protected Gateway
    print("\n[2/2] Scanning Protected (LLM Security Gateway)...", flush=True)
    t0 = time.time()
    try:
        report_gateway = giskard.scan(gateway_model, only=["prompt_injection"])
        gateway_html = os.path.join(REPORT_DIR, "giskard_gateway_protected.html")
        report_gateway.to_html(gateway_html)
        gateway_issues = len(report_gateway.issues)
        print(f"  [GATEWAY] Scan completed in {round(time.time() - t0, 1)}s. Issues found: {gateway_issues}")
        print(f"  [GATEWAY] Report saved: {gateway_html}")
    except Exception as e:
        print(f"  [GATEWAY] Scan failed or partial: {e}")
        gateway_issues = -1

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "direct_issues": direct_issues,
        "gateway_issues": gateway_issues,
        "improvement": f"{max(0, direct_issues - gateway_issues)} vulnerabilities eliminated" if direct_issues >= 0 and gateway_issues >= 0 else "N/A",
    }
    with open(os.path.join(REPORT_DIR, "giskard_comparison_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("GISKARD SCAN SUMMARY:")
    print(f"  • Direct Ollama Issues   : {direct_issues}")
    print(f"  • Security Gateway Issues: {gateway_issues}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_giskard_benchmark()
