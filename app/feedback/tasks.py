"""
Celery Tasks — LLM Security Gateway
=====================================
Real async tasks dispatched by the feedback loop and beat scheduler.

Task list:
  1. trigger_fine_tuning_run      — kicks off LoRA adapter training from annotations
  2. monitor_threat_thresholds    — checks rolling metrics, alerts on spikes (beat: every 15min)
  3. run_nightly_eval_gate        — precision/recall evaluation gate (beat: 02:00 UTC)
  4. export_dataset_version       — DVC dataset commit + push
"""

import json
import time
import os
from typing import List, Dict, Any

from app.celery_app import celery_app
from app.db.database import get_recent_events, upsert_user_behavior


# ── Task 1: Fine-tuning trigger ───────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.feedback.tasks.trigger_fine_tuning_run",
    max_retries=3,
    default_retry_delay=120,
)
def trigger_fine_tuning_run(self, annotations: List[Dict[str, Any]], model_name: str = "DeBERTa-v3") -> Dict[str, Any]:
    """
    Triggers a real LoRA fine-tuning run on the annotated dataset.
    Called by FeedbackFineTuningPipeline.process_annotation_batch().

    Steps:
      1. Build training dataset from annotations
      2. Run DVC dataset versioning
      3. Launch HuggingFace Trainer + LoRA adapter training
      4. Log metrics to W&B
      5. Return eval gate result
    """
    try:
        from app.feedback.fine_tuning import FeedbackFineTuningPipeline
        pipeline = FeedbackFineTuningPipeline()

        # Step 1: Prepare dataset
        dataset = pipeline._prepare_dataset(annotations)

        # Step 2: DVC versioning
        dvc_result = pipeline._dvc_version_dataset(dataset)

        # Step 3: LoRA training
        train_result = pipeline._run_lora_training(dataset, model_name)

        # Step 4: Eval gate
        eval_result = pipeline.run_eval_gate()

        return {
            "status": "COMPLETED",
            "task_id": self.request.id,
            "annotation_count": len(annotations),
            "dvc_version": dvc_result.get("version"),
            "train_loss": train_result.get("train_loss"),
            "eval_precision": eval_result.get("precision"),
            "eval_recall": eval_result.get("recall"),
            "eval_f1": eval_result.get("f1_score"),
            "deployment_ready": eval_result.get("deployment_ready", False),
        }

    except Exception as exc:
        raise self.retry(exc=exc)


# ── Task 2: Threshold monitor (runs every 15 min via beat) ───────────────────

@celery_app.task(
    name="app.feedback.tasks.monitor_threat_thresholds",
    ignore_result=False,
)
def monitor_threat_thresholds() -> Dict[str, Any]:
    """
    Pulls the last 100 security events and checks rolling threat metrics.
    Fires an alert if:
      - Block rate > 30% in the last 15 min
      - Injection score average > 0.60
      - Any UNSAFE Llama Guard output detections
    """
    events = get_recent_events(limit=100)
    if not events:
        return {"status": "NO_DATA", "alerts": []}

    total = len(events)
    blocked = sum(1 for e in events if e.get("action") == "BLOCK")
    block_rate = round(blocked / max(1, total), 3)

    avg_injection = round(
        sum(e.get("injection_score", 0.0) for e in events) / max(1, total), 3
    )

    unsafe_outputs = sum(
        1 for e in events
        if isinstance(e.get("metadata"), dict)
        and e["metadata"].get("output_llama_guard") == "UNSAFE"
    )

    alerts = []
    if block_rate > 0.30:
        alerts.append(f"HIGH block rate: {block_rate:.1%} of last {total} requests blocked")
    if avg_injection > 0.60:
        alerts.append(f"HIGH avg injection score: {avg_injection} (threshold 0.60)")
    if unsafe_outputs > 0:
        alerts.append(f"{unsafe_outputs} output Llama Guard UNSAFE detections in last {total} requests")

    result = {
        "status": "ALERT" if alerts else "OK",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_events_checked": total,
        "block_rate": block_rate,
        "avg_injection_score": avg_injection,
        "unsafe_output_count": unsafe_outputs,
        "alerts": alerts,
    }

    if alerts:
        print(f"[THRESHOLD MONITOR] ALERTS: {alerts}")

    return result


# ── Task 3: Nightly eval gate (runs at 02:00 UTC via beat) ───────────────────

@celery_app.task(
    name="app.feedback.tasks.run_nightly_eval_gate",
    ignore_result=False,
)
def run_nightly_eval_gate() -> Dict[str, Any]:
    """
    Runs a held-out benchmark evaluation on the current production detector.
    Blocks deployment if precision < 0.95 or recall < 0.90.
    """
    from app.feedback.fine_tuning import FeedbackFineTuningPipeline
    pipeline = FeedbackFineTuningPipeline()
    result = pipeline.run_eval_gate()
    result["run_type"] = "nightly_scheduled"
    result["run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result


# ── Task 4: DVC dataset export ────────────────────────────────────────────────

@celery_app.task(
    name="app.feedback.tasks.export_dataset_version",
    ignore_result=False,
)
def export_dataset_version(dataset_name: str = "security_events_dataset") -> Dict[str, Any]:
    """
    Exports current flagged events to a versioned DVC dataset.
    Runs `dvc add` + `dvc push` to commit the new version.
    """
    import subprocess

    events = get_recent_events(limit=5000)
    flagged = [e for e in events if e.get("flagged")]

    # Write to jsonl for DVC tracking
    dataset_path = f"data/{dataset_name}.jsonl"
    os.makedirs("data", exist_ok=True)
    with open(dataset_path, "w") as f:
        for event in flagged:
            f.write(json.dumps(event) + "\n")

    dvc_out = {"dataset_path": dataset_path, "record_count": len(flagged)}

    # Run DVC commands
    for cmd in [f"dvc add {dataset_path}", "dvc push"]:
        try:
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=120
            )
            dvc_out[cmd.split()[0]] = result.returncode == 0
            if result.returncode != 0:
                dvc_out[f"{cmd.split()[0]}_error"] = result.stderr[:200]
        except Exception as e:
            dvc_out[f"{cmd.split()[0]}_error"] = str(e)

    return {"status": "COMPLETED", **dvc_out}
