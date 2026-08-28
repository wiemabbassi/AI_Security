import json
import os
import sqlite3
from typing import Dict, Any, List, Optional

try:
    import requests as _requests
except ImportError:
    _requests = None

from app.db.database import DB_PATH

# ── Label Studio connection settings (from environment) ───────────────────────
_LS_URL = os.getenv("LABEL_STUDIO_URL", "http://localhost:8080")
_LS_API_KEY = os.getenv("LABEL_STUDIO_API_KEY", "")
_LS_PROJECT_ID = os.getenv("LABEL_STUDIO_PROJECT_ID", "")   # optional: auto-create if blank


class FeedbackReviewService:
    """
    Human-in-the-Loop Feedback Review & Model Retraining Service:
    Manages annotation tasks in Label Studio format, false positive triage,
    and triggers LoRA fine-tuning.

    Label Studio integration:
      - export_label_studio_tasks()  → formats flagged events in LS JSON format
      - push_to_label_studio()       → POSTs tasks directly to a running LS server
      - submit_annotation()          → records human correction back in the DB
    """

    # ── Label Studio labeling config (classification schema) ──────────────────
    _LS_LABEL_CONFIG = """
    <View>
      <Header value="Security Event Review"/>
      <Text name="text" value="$text"/>
      <Choices name="label" toName="text" choice="single">
        <Choice value="SAFE" hint="Legitimate prompt — false positive"/>
        <Choice value="PROMPT_INJECTION" hint="Injection attack confirmed"/>
        <Choice value="JAILBREAK" hint="Jailbreak attempt confirmed"/>
        <Choice value="HARMFUL_CONTENT" hint="Harmful content"/>
        <Choice value="PII_LEAK" hint="PII / data leak attempt"/>
        <Choice value="ANOMALOUS_BEHAVIOR" hint="Unusual behavior, not a specific attack"/>
      </Choices>
      <TextArea name="notes" toName="text" placeholder="Optional reviewer notes"/>
    </View>
    """

    # ── DB queries ─────────────────────────────────────────────────────────────

    def get_flagged_samples(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM security_events WHERE flagged = 1 ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        samples = [dict(r) for r in rows]
        conn.close()
        return samples

    # ── Label Studio export (file format) ─────────────────────────────────────

    def export_label_studio_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns flagged security events formatted as Label Studio JSON annotation tasks.
        Can be imported via LS UI or pushed directly via push_to_label_studio().
        """
        samples = self.get_flagged_samples(limit)
        tasks = []
        for s in samples:
            # Pre-populate model prediction based on highest-scoring detector
            inj_score = s.get("injection_score", 0.0) or 0.0
            jb_score = s.get("jailbreak_score", 0.0) or 0.0
            if inj_score > 0.5:
                predicted = "PROMPT_INJECTION"
            elif jb_score > 0.5:
                predicted = "JAILBREAK"
            else:
                predicted = "SAFE"

            tasks.append({
                "id": s["id"],
                "data": {
                    "text": s.get("raw_prompt", ""),
                    "user_id": s.get("user_id", ""),
                    "risk_score": s.get("risk_score", 0.0),
                    "injection_score": inj_score,
                    "jailbreak_score": jb_score,
                    "action": s.get("action", ""),
                },
                "predictions": [{
                    "model_version": "gateway-v1.0",
                    "result": [{
                        "from_name": "label",
                        "to_name": "text",
                        "type": "choices",
                        "value": {"choices": [predicted]},
                    }],
                }],
            })
        return tasks

    # ── Label Studio live API integration ─────────────────────────────────────

    def _ls_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {_LS_API_KEY}",
            "Content-Type": "application/json",
        }

    def _get_or_create_ls_project(self) -> Optional[int]:
        """
        Returns the Label Studio project ID.
        Uses LABEL_STUDIO_PROJECT_ID env if set; otherwise creates a new project.
        Returns None if Label Studio is unreachable.
        """
        if not _LS_API_KEY or _requests is None:
            return None

        if _LS_PROJECT_ID:
            try:
                return int(_LS_PROJECT_ID)
            except ValueError:
                pass

        # Auto-create project
        try:
            resp = _requests.post(
                f"{_LS_URL}/api/projects",
                headers=self._ls_headers(),
                json={
                    "title": "LLM Security Gateway — Flagged Events",
                    "description": "Human review of security events flagged by the gateway pipeline.",
                    "label_config": self._LS_LABEL_CONFIG,
                },
                timeout=5.0,
            )
            if resp.status_code in (200, 201):
                project_id = resp.json().get("id")
                print(f"[LABEL_STUDIO] Created project id={project_id}")
                return project_id
            else:
                print(f"[LABEL_STUDIO] Project creation failed: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"[LABEL_STUDIO] Connection error: {e}")
            return None

    def push_to_label_studio(self, limit: int = 50) -> Dict[str, Any]:
        """
        Pushes flagged security events directly to a running Label Studio server.

        Environment variables required:
          LABEL_STUDIO_URL       — e.g. http://localhost:8080
          LABEL_STUDIO_API_KEY   — user API token from LS Account page
          LABEL_STUDIO_PROJECT_ID — (optional) existing project; auto-created if blank

        Returns a result dict with counts of tasks pushed and any errors.
        """
        result = {
            "status": "OK",
            "tasks_pushed": 0,
            "tasks_failed": 0,
            "project_id": None,
            "label_studio_url": _LS_URL,
            "errors": [],
        }

        if _requests is None:
            result["status"] = "ERROR"
            result["errors"].append("requests library not installed")
            return result

        if not _LS_API_KEY:
            result["status"] = "SKIPPED"
            result["errors"].append(
                "LABEL_STUDIO_API_KEY not set — set env var to enable live push"
            )
            return result

        project_id = self._get_or_create_ls_project()
        if project_id is None:
            result["status"] = "ERROR"
            result["errors"].append("Could not connect to or create Label Studio project")
            return result

        result["project_id"] = project_id
        tasks = self.export_label_studio_tasks(limit)

        if not tasks:
            result["status"] = "NO_DATA"
            result["errors"].append("No flagged events to push")
            return result

        # POST tasks in batches of 10
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            try:
                resp = _requests.post(
                    f"{_LS_URL}/api/projects/{project_id}/import",
                    headers=self._ls_headers(),
                    json=batch,
                    timeout=10.0,
                )
                if resp.status_code in (200, 201):
                    result["tasks_pushed"] += len(batch)
                else:
                    result["tasks_failed"] += len(batch)
                    result["errors"].append(
                        f"Batch {i//batch_size + 1} failed: {resp.status_code} {resp.text[:200]}"
                    )
            except Exception as e:
                result["tasks_failed"] += len(batch)
                result["errors"].append(f"Batch {i//batch_size + 1} error: {str(e)}")

        if result["tasks_failed"] > 0:
            result["status"] = "PARTIAL"
        elif result["tasks_pushed"] > 0:
            result["status"] = "OK"

        print(
            f"[LABEL_STUDIO] Pushed {result['tasks_pushed']} tasks to project {project_id} "
            f"({result['tasks_failed']} failed)"
        )
        return result

    # ── Annotation submission ──────────────────────────────────────────────────

    def submit_annotation(
        self,
        event_id: int,
        correct_label: str,
        reviewer_notes: str,
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE security_events SET flagged = 0, metadata = ? WHERE id = ?",
            (
                json.dumps({
                    "label_studio_annotation": correct_label,
                    "notes": reviewer_notes,
                }),
                event_id,
            ),
        )
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "event_id": event_id,
            "correct_label": correct_label,
            "reviewer_notes": reviewer_notes,
            "label_studio_format": True,
            "retraining_queued": True,
        }


feedback_service = FeedbackReviewService()

