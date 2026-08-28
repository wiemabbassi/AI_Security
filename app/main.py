import os
from fastapi import FastAPI, Response, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.gateway.router import router as api_router
from app.db.database import init_db, get_recent_events, get_timescaledb_hourly_aggregates
from app.observability.metrics import metrics_collector
from app.observability.tracing import format_prometheus_metrics, langfuse_tracer
from app.feedback.review_service import feedback_service
from app.feedback.fine_tuning import fine_tuning_pipeline
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Production LLM Security Gateway API with Input/Output pipelines, risk scoring, behavioral analysis, and observability."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db_init():
    init_db()

app.include_router(api_router, prefix=settings.API_PREFIX)

# Serve demo UI directly
DEMO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo", "index.html")

@app.get("/demo", response_class=HTMLResponse)
def get_demo_ui():
    if os.path.exists(DEMO_PATH):
        return FileResponse(DEMO_PATH, media_type="text/html")
    return HTMLResponse("<h1>Demo UI not found</h1>", status_code=404)

@app.get("/")
def root(request: Request):
    # If opened in a web browser, serve the ChatGPT-like demo interface
    accept = request.headers.get("accept", "")
    if "text/html" in accept and os.path.exists(DEMO_PATH):
        return FileResponse(DEMO_PATH, media_type="text/html")
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "online",
        "chat_ui": "/demo",
        "docs": "/docs"
    }

@app.get("/metrics")
def get_metrics():
    return metrics_collector.get_metrics()

@app.get("/metrics/prometheus")
def get_prometheus_metrics():
    metrics = metrics_collector.get_metrics()
    formatted = format_prometheus_metrics(metrics)
    return Response(content=formatted, media_type="text/plain")

@app.get("/observability/langfuse/traces")
def get_langfuse_traces(limit: int = 20):
    return langfuse_tracer.get_recent_traces(limit)

@app.get("/events")
def get_events(limit: int = 50):
    return get_recent_events(limit)

@app.get("/analytics/timescaledb/hourly")
def get_hourly_aggregates():
    return get_timescaledb_hourly_aggregates()

class AnnotationRequest(BaseModel):
    event_id: int
    correct_label: str
    reviewer_notes: str

@app.post("/feedback/annotate")
def submit_annotation(annotation: AnnotationRequest):
    return feedback_service.submit_annotation(
        event_id=annotation.event_id,
        correct_label=annotation.correct_label,
        reviewer_notes=annotation.reviewer_notes
    )

@app.post("/feedback/retrain")
def trigger_retraining_job():
    """
    Dispatches a LoRA fine-tuning job to Celery and returns immediately.
    The job runs asynchronously — poll /feedback/retrain/{task_id} for status.
    """
    flagged = feedback_service.get_flagged_samples()
    # process_annotation_batch() dispatches to Celery internally and returns metadata+task_id
    job_status = fine_tuning_pipeline.process_annotation_batch(flagged)
    return {
        "status": "DISPATCHED",
        "celery_task_id": job_status.get("celery_task_id"),
        "annotation_count": job_status.get("annotation_count"),
        "dvc_dataset_version": job_status.get("dvc_dataset_version"),
        "note": "Fine-tuning job queued. Eval gate runs inside the Celery task. Check W&B for results.",
    }


@app.post("/feedback/push-label-studio")
def push_to_label_studio(limit: int = 50):
    """Pushes the latest flagged events to a running Label Studio instance."""
    return feedback_service.push_to_label_studio(limit=limit)
