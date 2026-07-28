from fastapi import FastAPI, Response
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
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db_init():
    init_db()

app.include_router(api_router, prefix=settings.API_PREFIX)

@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "online",
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
    flagged = feedback_service.get_flagged_samples()
    job_status = fine_tuning_pipeline.process_annotation_batch(flagged)
    eval_result = fine_tuning_pipeline.run_eval_gate()
    return {
        "job": job_status,
        "eval_gate": eval_result
    }
