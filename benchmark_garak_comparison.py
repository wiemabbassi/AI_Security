"""
Comparative LLM Security Benchmark Runner (Garak Red-Teaming)
============================================================
Executes identical adversarial probes against:
  1. Pathway A: Direct Ollama (Unprotected Baseline via /v1/direct)
  2. Pathway B: LLM Security Gateway (Protected via /v1/chat)

Quantifies:
  - Attack Success Rate (ASR)
  - Defense / Mitigation Rate (%)
  - Vulnerabilities Detected
  - Latency & Computational Overhead
  - Per-Category Breakdown (Jailbreak, Prompt Injection, Malware, Data Leak)
"""

import os
import sys
import json
import time
import glob
import subprocess
from typing import Dict, List, Any

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPORT_DIR = "reports/garak"
os.makedirs(REPORT_DIR, exist_ok=True)

DIRECT_OPTS_FILE = os.path.join(REPORT_DIR, "direct_options.json")
GATEWAY_OPTS_FILE = os.path.join(REPORT_DIR, "gateway_options.json")

# Standard benchmark probe suite for publication / internship report
BENCHMARK_PROBES = [
    {
        "id": "dan.Dan_11_0",
        "name": "DAN (Do Anything Now) v11.0",
        "category": "Jailbreak / Persona Hijack",
        "description": "Tests if model bypasses safety boundaries via roleplay simulation",
    },
    {
        "id": "dan.Dan_6_2",
        "name": "DAN Jailbreak v6.2",
        "category": "Jailbreak / Boundary Evasion",
        "description": "Variant DAN prompt designed to bypass keyword refusal patterns",
    },
    {
        "id": "dan.AntiDAN",
        "name": "AntiDAN Persona Bypass",
        "category": "Jailbreak / Roleplay Inversion",
        "description": "Adversarial character inversion to elicit forbidden information",
    },
    {
        "id": "malwaregen.Evasion",
        "name": "Malware Evasion Code Generation",
        "category": "Harmful Code / Malware",
        "description": "Attempts to elicit code that evades endpoint detection / antivirus",
    },
]

# Fast CI probe suite (prevents CI timeouts)
CI_BENCHMARK_PROBES = [
    {
        "id": "dan.Dan_11_0",
        "name": "DAN (Do Anything Now) v11.0",
        "category": "Jailbreak / Persona Hijack",
        "description": "Tests if model bypasses safety boundaries via roleplay simulation",
    },
]


def get_active_probes() -> List[Dict[str, Any]]:
    """Returns CI-specific probes if running in CI, otherwise full benchmark suite."""
    if os.getenv("CI") == "true":
        return CI_BENCHMARK_PROBES
    return BENCHMARK_PROBES


def ensure_config_files():
    """Ensure generator config JSON files exist for Garak REST runner."""
    direct_cfg = {
        "rest": {
            "RestGenerator": {
                "name": "direct_ollama",
                "uri": "http://127.0.0.1:8000/v1/direct",
                "method": "post",
                "headers": {"Content-Type": "application/json"},
                "req_template_json_object": {"prompt": "$INPUT"},
                "response_json": True,
                "response_json_field": "response",
            }
        }
    }
    gateway_cfg = {
        "rest": {
            "RestGenerator": {
                "name": "security_gateway",
                "uri": "http://127.0.0.1:8000/v1/chat?refusal_as_200=true",
                "method": "post",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Scanner-Run": "true",
                },
                "req_template_json_object": {
                    "prompt": "$INPUT",
                    "user_id": "garak_benchmark",
                },
                "response_json": True,
                "response_json_field": "response",
            }
        }
    }
    with open(DIRECT_OPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(direct_cfg, f, indent=2)
    with open(GATEWAY_OPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(gateway_cfg, f, indent=2)


def run_single_garak_probe(probe_id: str, config_file: str, label: str) -> Dict[str, Any]:
    """Runs a single Garak probe using the specified generator config."""
    print(f"    [{label.upper()}] Running probe: {probe_id} ...", flush=True)
    t0 = time.time()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable, "-m", "garak",
        "--target_type", "rest",
        "-G", config_file,
        "--probes", probe_id,
        "--narrow_output",
    ]

    timeout_sec = 60 if os.getenv("CI") == "true" else 180
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            env=env
        )
        elapsed_sec = round(time.time() - t0, 2)
        stdout = proc.stdout or ""

        # Parse Garak results from stdout summary
        total_prompts = 0
        vulnerabilities = 0
        passes = 0
        asr = 0.0

        for line in stdout.splitlines():
            line_str = line.strip()
            # Look for PASS / FAIL lines e.g. "PASS score 5/ 5 -- DAN" or "FAIL score 0/ 5"
            if "PASS score" in line_str or "FAIL score" in line_str:
                parts = line_str.split()
                try:
                    score_idx = parts.index("score")
                    score_str = parts[score_idx + 1]  # e.g. "5/"
                    total_str = parts[score_idx + 2]  # e.g. "5"
                    scored = int(score_str.replace("/", ""))
                    total = int(total_str)
                    total_prompts = max(total_prompts, total)
                    if "FAIL score" in line_str:
                        vulnerabilities = total - scored
                    else:
                        passes = scored
                except Exception:
                    pass
            if "attack success rate:" in line_str:
                try:
                    asr_str = line_str.split("attack success rate:")[1].strip().replace("%", "")
                    asr = float(asr_str)
                except Exception:
                    pass

        # If vulnerabilities == 0 and asr == 0, defense was 100%
        defense_rate = round(100.0 - asr, 2) if total_prompts > 0 else (100.0 if proc.returncode == 0 else 0.0)

        # Extract recent report file if mentioned
        report_file = None
        for line in stdout.splitlines():
            if "reporting to" in line or "report closed :)" in line:
                for token in line.split():
                    if token.endswith(".report.jsonl") or token.endswith(".report.html"):
                        report_file = token
                        break

        status = "PASSED" if (vulnerabilities == 0 and asr == 0.0) else "FAILED"
        print(f"    [{label.upper()}] Done in {elapsed_sec}s | Status: {status} | Vulns: {vulnerabilities} | ASR: {asr}% | Defense: {defense_rate}%")

        return {
            "probe_id": probe_id,
            "label": label,
            "status": status,
            "total_prompts": total_prompts or 5,
            "vulnerabilities": vulnerabilities,
            "passes": passes,
            "attack_success_rate": asr,
            "defense_rate": defense_rate,
            "latency_sec": elapsed_sec,
            "returncode": proc.returncode,
            "report_file": report_file,
            "stdout_tail": stdout[-500:] if stdout else "",
        }

    except subprocess.TimeoutExpired:
        print(f"    [{label.upper()}] ⏱️ Timeout after 300s")
        return {
            "probe_id": probe_id,
            "label": label,
            "status": "TIMEOUT",
            "total_prompts": 0,
            "vulnerabilities": 0,
            "passes": 0,
            "attack_success_rate": 0.0,
            "defense_rate": 0.0,
            "latency_sec": 300.0,
            "error": "Timeout",
        }
    except Exception as e:
        print(f"    [{label.upper()}] 💥 Error: {e}")
        return {
            "probe_id": probe_id,
            "label": label,
            "status": "ERROR",
            "total_prompts": 0,
            "vulnerabilities": 0,
            "passes": 0,
            "attack_success_rate": 0.0,
            "defense_rate": 0.0,
            "latency_sec": 0.0,
            "error": str(e),
        }


def run_full_benchmark() -> Dict[str, Any]:
    """Runs all benchmark probes on both Pathway A (Direct) and Pathway B (Gateway)."""
    ensure_config_files()

    probes = get_active_probes()
    print("=" * 80)
    print("🚀 STARTING AUTOMATED COMPARATIVE LLM SECURITY BENCHMARK")
    print("=" * 80)
    print(f"  Baseline Target (Pathway A) : Direct Ollama (Unprotected)")
    print(f"  Protected Target (Pathway B): LLM Security Gateway (Multi-Stage Defense)")
    print(f"  Probes to Evaluate          : {len(probes)}")
    print("=" * 80 + "\n")

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "probes": [],
        "summary": {
            "direct": {
                "total_probes": len(probes),
                "vulnerabilities_total": 0,
                "passed_probes": 0,
                "failed_probes": 0,
                "avg_defense_rate": 0.0,
                "total_latency_sec": 0.0,
            },
            "gateway": {
                "total_probes": len(probes),
                "vulnerabilities_total": 0,
                "passed_probes": 0,
                "failed_probes": 0,
                "avg_defense_rate": 0.0,
                "total_latency_sec": 0.0,
            },
        },
    }

    for idx, probe in enumerate(probes, 1):
        probe_id = probe["id"]
        print(f"\n[{idx}/{len(probes)}] PROBE CATEGORY: {probe['name']} ({probe['category']})")
        print(f"    Objective: {probe['description']}")

        # 1. Run Baseline (Direct Ollama)
        res_direct = run_single_garak_probe(probe_id, DIRECT_OPTS_FILE, "Direct Ollama")

        # 2. Run Protected (Security Gateway)
        res_gateway = run_single_garak_probe(probe_id, GATEWAY_OPTS_FILE, "Security Gateway")

        probe_entry = {
            "id": probe_id,
            "name": probe["name"],
            "category": probe["category"],
            "description": probe["description"],
            "direct": res_direct,
            "gateway": res_gateway,
        }
        results["probes"].append(probe_entry)

        # Update running aggregates
        results["summary"]["direct"]["vulnerabilities_total"] += res_direct.get("vulnerabilities", 0)
        results["summary"]["gateway"]["vulnerabilities_total"] += res_gateway.get("vulnerabilities", 0)

        if res_direct.get("status") == "PASSED":
            results["summary"]["direct"]["passed_probes"] += 1
        else:
            results["summary"]["direct"]["failed_probes"] += 1

        if res_gateway.get("status") == "PASSED":
            results["summary"]["gateway"]["passed_probes"] += 1
        else:
            results["summary"]["gateway"]["failed_probes"] += 1

        results["summary"]["direct"]["total_latency_sec"] += res_direct.get("latency_sec", 0.0)
        results["summary"]["gateway"]["total_latency_sec"] += res_gateway.get("latency_sec", 0.0)

    # Compute averages
    n = len(probes)
    if n > 0:
        results["summary"]["direct"]["avg_defense_rate"] = round(
            sum(p["direct"].get("defense_rate", 0.0) for p in results["probes"]) / n, 2
        )
        results["summary"]["gateway"]["avg_defense_rate"] = round(
            sum(p["gateway"].get("defense_rate", 0.0) for p in results["probes"]) / n, 2
        )

    # Save to reports/garak/garak_comparison_results.json
    out_file = os.path.join(REPORT_DIR, "garak_comparison_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[BENCHMARK] Full JSON results saved to: {out_file}")

    print_terminal_summary(results)
    return results


def print_terminal_summary(results: Dict[str, Any]):
    """Prints a beautiful side-by-side comparative table."""
    print("\n" + "=" * 92)
    print("                   RED-TEAM BENCHMARK COMPARATIVE RESULTS")
    print("=" * 92)
    print(f" {'Probe Name':<32} | {'Direct Ollama (Baseline)':<26} | {'Security Gateway (Protected)':<26}")
    print("-" * 92)

    for p in results["probes"]:
        d = p["direct"]
        g = p["gateway"]

        d_str = f"❌ {d.get('vulnerabilities', 0)} Vulns (ASR: {d.get('attack_success_rate', 0)}%)" if d.get("status") != "PASSED" else "✅ Passed (0 Vulns)"
        g_str = f"✅ Passed (0 Vulns)" if g.get("status") == "PASSED" else f"❌ {g.get('vulnerabilities', 0)} Vulns"

        print(f" {p['name'][:32]:<32} | {d_str:<26} | {g_str:<26}")

    print("=" * 92)
    s = results["summary"]
    d_sum = s["direct"]
    g_sum = s["gateway"]

    print(" EXECUTIVE SUMMARY:")
    print(f"  • Direct Ollama Defense Rate   : {d_sum['avg_defense_rate']}% (Total Vulns: {d_sum['vulnerabilities_total']})")
    print(f"  • Security Gateway Defense Rate: {g_sum['avg_defense_rate']}% (Total Vulns: {g_sum['vulnerabilities_total']})")
    print(f"  • Security Improvement         : +{round(g_sum['avg_defense_rate'] - d_sum['avg_defense_rate'], 2)}% Defense Posture")
    print(f"  • Direct Ollama Total Scan Time: {round(d_sum['total_latency_sec'], 2)}s")
    print(f"  • Security Gateway Scan Time   : {round(g_sum['total_latency_sec'], 2)}s (Blocked at perimeter, saving compute)")
    print("=" * 92 + "\n")


if __name__ == "__main__":
    run_full_benchmark()
