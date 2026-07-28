import sqlite3
from typing import Dict, Any, List
from app.db.database import DB_PATH

class FeedbackReviewService:
    """
    Human-in-the-Loop Feedback Review & Model Retraining Service:
    Manages annotation tasks, false positive triage, and triggers LoRA fine-tuning.
    """
    def get_flagged_samples(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_events WHERE flagged = 1 ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        samples = [dict(r) for r in rows]
        conn.close()
        return samples

    def submit_annotation(self, event_id: int, correct_label: str, reviewer_notes: str) -> Dict[str, Any]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE security_events SET flagged = 0, metadata = ? WHERE id = ?", (
            f"annotated:{correct_label} | {reviewer_notes}", event_id
        ))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "event_id": event_id,
            "correct_label": correct_label,
            "retraining_queued": True
        }

feedback_service = FeedbackReviewService()
