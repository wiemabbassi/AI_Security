"""
Garak Red-Team Vulnerability Scanner
======================================
Real Garak LLM red-team scan targeting the local Ollama gateway.

Probes executed:
  - dan.Dan_11_0          — DAN (Do Anything Now) jailbreak variants
  - promptinject          — Prompt injection attack corpus
  - leakreplay            — System prompt / training data leakage
  - malwaregen            — Malware generation elicitation
  - knownbadsignatures    — Known bad prompt signatures
  - continuation          — Harmful continuation elicitation

Usage:
    python run_garak_scan.py                  # full scan against gateway
    python run_garak_scan.py --dry-run        # print probe list, do not run
    python run_garak_scan.py --probe dan      # run only DAN probes
    python run_garak_scan.py --direct         # scan Ollama directly (bypass gateway)
    python run_garak_scan.py --format json    # output JSON report

Exit codes:
    0 = all probes passed (no successful attacks)
    1 = one or more probes found vulnerabilities
    2 = scan could not run (Garak not installed, target unreachable)
"""

import argparse
import json
import subprocess
import sys
import os
import time
from typing import List, Dict

GATEWAY_URL  = "http://localhost:8000"
OLLAMA_URL   = "http://localhost:11434"
REPORT_DIR   = "reports/garak"

# Probes to run in a full scan (ordered by severity)
FULL_PROBE_SET = [
    "dan.Dan_11_0",
    "dan.Dan_6_2",
    "promptinject",
    "leakreplay",
    "malwaregen.Evasion",
    "knownbadsignatures",
    "continuation.ContinueSlursReclaimedSlurs50",
]

# Lighter probe set for CI (faster, still meaningful)
CI_PROBE_SET = [
    "dan.Dan_11_0",
    "promptinject",
    "leakreplay",
]


def check_garak_installed() -> bool:
    """Returns True if garak is importable."""
    try:
        import garak
        return True
    except ImportError:
        try:
            result = subprocess.run(
                ["python", "-m", "garak", "--version"],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False


def check_target_reachable(url: str) -> bool:
    """Returns True if the target URL responds."""
    try:
        import requests
        r = requests.get(url + "/", timeout=5)
        return r.status_code < 500
    except Exception:
        return False


def run_garak_scan(
    probes: List[str],
    target_url: str,
    model_name: str = "llama3.2:latest",
    output_format: str = "text",
    report_dir: str = REPORT_DIR,
) -> Dict:
    """
    Invokes Garak via subprocess using the REST generator pointing at Ollama or gateway.
    Returns a result dict with pass/fail per probe.
    """
    os.makedirs(report_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"garak_report_{timestamp}.json")

    results = {
        "scan_start": timestamp,
        "target_url": target_url,
        "probes_run": probes,
        "probe_results": {},
        "overall_pass": True,
        "vulnerabilities_found": 0,
    }

    for probe in probes:
        probe_short = probe.split(".")[-1] if "." in probe else probe
        print(f"\n  [GARAK] Running probe: {probe} ...", flush=True)

        cmd = [
            "python", "-m", "garak",
            "--model_type", "rest",
            "--model_name", model_name,
            "--probes", probe,
            "--format", "json",
            "--report_prefix", os.path.join(report_dir, f"{probe_short}_{timestamp}"),
            "--rest_uri", f"{target_url}/v1/chat",
            "--rest_json",
            json.dumps({
                "prompt": "{prompt}",
                "user_id": "garak_redteam",
                "session_id": "garak_scan"
            }),
            "--rest_response_json", "response",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min per probe
            )

            # Parse garak output
            passed = proc.returncode == 0
            vulnerabilities = 0

            # Look for vulnerability count in stdout
            for line in proc.stdout.split("\n"):
                if "passed" in line.lower() and "failed" in line.lower():
                    # e.g. "5 passed, 2 failed"
                    parts = line.split(",")
                    for part in parts:
                        if "failed" in part:
                            try:
                                vulnerabilities = int(part.strip().split()[0])
                            except Exception:
                                pass

            if vulnerabilities > 0:
                passed = False
                results["overall_pass"] = False
                results["vulnerabilities_found"] += vulnerabilities

            results["probe_results"][probe] = {
                "passed": passed,
                "vulnerabilities": vulnerabilities,
                "return_code": proc.returncode,
                "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
                "stderr_tail": proc.stderr[-200:] if proc.stderr else "",
            }

            status = "✅ PASSED" if passed else f"❌ FAILED ({vulnerabilities} vulnerabilities)"
            print(f"  [GARAK] {probe}: {status}")

        except subprocess.TimeoutExpired:
            results["probe_results"][probe] = {
                "passed": False,
                "vulnerabilities": 0,
                "error": "TIMEOUT after 300s"
            }
            print(f"  [GARAK] {probe}: ⏱️ TIMEOUT")

        except Exception as e:
            results["probe_results"][probe] = {
                "passed": False,
                "vulnerabilities": 0,
                "error": str(e)
            }
            print(f"  [GARAK] {probe}: 💥 ERROR — {e}")

    results["scan_end"] = time.strftime("%Y%m%d_%H%M%S")

    # Save JSON report
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  [GARAK] Report saved: {report_path}")

    return results


def print_summary(results: Dict):
    """Prints a coloured summary table."""
    print("\n" + "=" * 60)
    print("  GARAK RED-TEAM SCAN SUMMARY")
    print("=" * 60)
    print(f"  Target:       {results['target_url']}")
    print(f"  Probes run:   {len(results['probes_run'])}")
    print(f"  Vulns found:  {results['vulnerabilities_found']}")
    print(f"  Overall:      {'✅ PASS' if results['overall_pass'] else '❌ FAIL'}")
    print("-" * 60)
    for probe, r in results.get("probe_results", {}).items():
        icon = "✅" if r.get("passed") else "❌"
        vuln = r.get("vulnerabilities", 0)
        err  = f" [{r['error']}]" if "error" in r else ""
        print(f"  {icon} {probe:<45} vulns={vuln}{err}")
    print("=" * 60)



def main():
    parser = argparse.ArgumentParser(description="Garak LLM Red-Team Scanner")
    parser.add_argument("--dry-run",  action="store_true", help="Print probe list and exit")
    parser.add_argument("--probe",    default=None,        help="Run only this probe (e.g. dan.Dan_11_0)")
    parser.add_argument("--direct",   action="store_true", help="Scan Ollama directly (bypass gateway)")
    parser.add_argument("--ci",       action="store_true", help="Use CI probe set (faster)")
    parser.add_argument("--format",   default="text",      choices=["text", "json"])
    args = parser.parse_args()

    # Select probes
    if args.probe:
        probes = [args.probe]
    elif args.ci:
        probes = CI_PROBE_SET
    else:
        probes = FULL_PROBE_SET

    target_url = OLLAMA_URL if args.direct else GATEWAY_URL

    # Dry run
    if args.dry_run:
        print(f"\nGarak Red-Team Scan — DRY RUN")
        print(f"Target:  {target_url}")
        print(f"Probes:  {len(probes)}")
        for p in probes:
            print(f"  - {p}")
        sys.exit(0)

    # Pre-flight checks
    if not check_garak_installed():
        if args.format == "json":
            print(json.dumps({"error": "Garak not installed", "vulnerabilities_found": 0, "probes_run": []}))
        else:
            print("❌ Garak not installed. Run: pip install garak")
        sys.exit(2)

    if not check_target_reachable(target_url):
        if args.format == "json":
            print(json.dumps({"error": f"Target not reachable: {target_url}", "vulnerabilities_found": 0, "probes_run": []}))
        else:
            print(f"❌ Target not reachable: {target_url}")
        sys.exit(2)

    if args.format != "json":
        print(f"\n🔴 Starting Garak red-team scan")
        print(f"   Target: {target_url}")
        print(f"   Probes: {len(probes)}")

    results = run_garak_scan(
        probes=probes,
        target_url=target_url,
        output_format=args.format,
    )

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print_summary(results)

    sys.exit(0 if results["overall_pass"] else 1)


if __name__ == "__main__":
    main()
