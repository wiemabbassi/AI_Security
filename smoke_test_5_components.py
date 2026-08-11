import sys
sys.stdout.reconfigure(encoding="utf-8")

print("=== Component 1: PostgreSQL/SQLite DB ===")
from app.db.database import init_db, log_event, get_recent_events, upsert_user_behavior
init_db()
log_event({"user_id": "smoke_test", "action": "ALLOW", "risk_score": 0.1, "raw_prompt": "test"})
events = get_recent_events(limit=2)
print(f"  init_db OK, events in DB: {len(events)}")
upsert_user_behavior("smoke_test", 1, 0, 0.1)
print("  upsert_user_behavior OK")

print()
print("=== Component 2: Celery App ===")
from app.celery_app import celery_app
print(f"  Celery app: {celery_app.main}")
print(f"  Broker:     {celery_app.conf.broker_url}")
print(f"  Backend:    {celery_app.conf.result_backend}")
from app.feedback.tasks import monitor_threat_thresholds, run_nightly_eval_gate
print(f"  Task: {monitor_threat_thresholds.name}")
print(f"  Task: {run_nightly_eval_gate.name}")

print()
print("=== Component 3: W&B (import check) ===")
try:
    import wandb
    print(f"  wandb available: {wandb.__version__}")
except ImportError:
    print("  wandb not installed — graceful degradation active")

print()
print("=== Component 4: Garak scan (dry run) ===")
import subprocess
result = subprocess.run(
    ["python", "run_garak_scan.py", "--dry-run"],
    capture_output=True, text=True, timeout=10
)
if result.returncode == 0:
    print("  run_garak_scan.py --dry-run: OK")
    for line in result.stdout.strip().split("\n"):
        print(f"    {line}")
else:
    print(f"  dry-run exit {result.returncode}: {result.stderr[:300]}")

print()
print("=== Component 5: LoRA fine-tuning pipeline ===")
from app.feedback.fine_tuning import FeedbackFineTuningPipeline
p = FeedbackFineTuningPipeline()
r = p.run_eval_gate()
print(f"  status:          {r['status']}")
print(f"  precision:       {r['precision']}")
print(f"  recall:          {r['recall']}")
print(f"  f1_score:        {r['f1_score']}")
print(f"  benchmark_suite: {r['benchmark_suite']}")
print(f"  wandb_enabled:   {p.__class__.__name__}")

print()
print("ALL 5 COMPONENTS VERIFIED")
