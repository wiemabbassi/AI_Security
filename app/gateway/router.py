import time
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from app.gateway.rate_limiter import rate_limiter
from app.input_pipeline.normalizer import normalizer
from app.input_pipeline.prompt_injection import injection_detector
from app.input_pipeline.jailbreak_detector import jailbreak_detector
from app.input_pipeline.pii_detector import pii_detector
from app.input_pipeline.llama_guard import llama_guard
from app.input_pipeline.guardrails_validator import guardrails_validator

from app.core_engine.risk_scorer import risk_scorer
from app.core_engine.behavioral_analysis import behavioral_analyzer
from app.core_engine.policy_engine import policy_engine
from app.core_engine.ml_engine import ml_engine
from app.core_engine.event_logger import event_logger

from app.llm_backend.router import llm_router

from app.output_pipeline.output_pii import output_pii_scanner
from app.output_pipeline.data_leak import data_leak_detector
from app.output_pipeline.llama_guard_output import llama_guard_output
from app.output_pipeline.output_guardrails import output_guardrails

from app.observability.metrics import metrics_collector
from app.observability.tracing import langfuse_tracer

router = APIRouter()

class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User prompt text to inspect and process")
    user_id: Optional[str] = "user_default"
    session_id: Optional[str] = "sess_001"

class ChatResponse(BaseModel):
    response: str
    action: str
    risk_score: float
    latency_ms: float
    security_summary: Dict[str, Any]

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request_data: ChatRequest,
    req: Request,
    authorization: Optional[str] = Header(None)
):
    start_time = time.time()
    user_id = request_data.user_id
    client_ip = req.client.host if req.client else "127.0.0.1"
    api_key = authorization.replace("Bearer ", "") if authorization else "public"

    # 1. Rate Limiting Check
    allowed, remaining, retry_after = rate_limiter.is_allowed(key=f"{user_id}:{api_key}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too Many Requests. Rate limit exceeded. Retry after {retry_after}s"
        )

    # 2. Input Security Pipeline
    raw_prompt = request_data.prompt
    clean_prompt = normalizer.normalize(raw_prompt)
    
    inj_res = injection_detector.analyze(clean_prompt)
    jb_res = jailbreak_detector.analyze(clean_prompt)
    masked_prompt, pii_map, pii_count = pii_detector.mask_pii(clean_prompt)
    lg_res = llama_guard.classify(masked_prompt)
    gr_res = guardrails_validator.validate_input(masked_prompt)
    ml_res = ml_engine.check_semantic_similarity(clean_prompt)

    if not gr_res["valid"]:
        raise HTTPException(status_code=400, detail=gr_res["reason"])

    # 3. Risk & Behavioral Analysis
    anomaly_res = behavioral_analyzer.analyze_user_behavior(
        user_id=user_id,
        prompt_len=len(clean_prompt),
        current_risk=inj_res["injection_score"]
    )
    
    agg_risk = risk_scorer.calculate_risk(
        injection_score=inj_res["injection_score"],
        jailbreak_score=jb_res["jailbreak_score"],
        llama_guard_status=lg_res["status"],
        anomaly_score=anomaly_res["anomaly_score"]
    )

    # 4. Policy Engine Evaluation
    policy_context = {
        "injection_score": inj_res["injection_score"],
        "jailbreak_score": jb_res["jailbreak_score"],
        "anomaly_score": anomaly_res["anomaly_score"],
        "risk_score": agg_risk,
        "llama_guard_status": lg_res["status"],
        "behavioral_alert": anomaly_res["is_anomaly"]
    }
    
    action, policy_id, policy_reason = policy_engine.evaluate(policy_context)

    if action == "BLOCK":
        latency_ms = (time.time() - start_time) * 1000
        
        langfuse_tracer.create_trace(
            name="llm_security_inspection_blocked",
            user_id=user_id,
            input_data={"raw_prompt": raw_prompt, "clean_prompt": clean_prompt},
            output_data={"raw_response": None, "final_response": f"BLOCKED: {policy_reason}"},
            scores={
                "injection_score": inj_res["injection_score"],
                "jailbreak_score": jb_res["jailbreak_score"],
                "anomaly_score": anomaly_res["anomaly_score"],
                "risk_score": agg_risk
            },
            latency_ms=latency_ms
        )

        event_logger.log({
            "user_id": user_id,
            "api_key": api_key,
            "client_ip": client_ip,
            "raw_prompt": raw_prompt,
            "masked_prompt": masked_prompt,
            "action": "BLOCK",
            "risk_score": agg_risk,
            "injection_score": inj_res["injection_score"],
            "jailbreak_score": jb_res["jailbreak_score"],
            "anomaly_score": anomaly_res["anomaly_score"],
            "llama_guard_status": lg_res["status"],
            "raw_response": None,
            "final_response": None,
            "metadata": {"policy_id": policy_id, "reason": policy_reason}
        })
        metrics_collector.record_request(latency_ms, "BLOCK")
        raise HTTPException(status_code=403, detail=f"Request blocked by security policy [{policy_id}]: {policy_reason}")

    # 5. LLM Backend Generation (Local Ollama / Fallback)
    llm_res = llm_router.generate(masked_prompt)
    raw_llm_response = llm_res["response"]

    # 6. Output Security Pipeline
    out_pii_res = output_pii_scanner.scan(raw_llm_response)
    leak_res = data_leak_detector.detect_leak(raw_llm_response)
    out_lg_res = llama_guard_output.scan(raw_llm_response)
    final_out_res = output_guardrails.validate_and_restore(raw_llm_response, pii_map)

    final_response = final_out_res["final_response"]
    latency_ms = round((time.time() - start_time) * 1000, 2)

    # 7. Audit, Langfuse Tracing & Event Logging
    tags = [f"action_{action.lower()}", f"policy_{policy_id.lower()}"]
    if pii_map:
        tags.append("pii_masked")
    if lg_res["status"] == "SAFE":
        tags.append("llama_guard_safe")

    langfuse_tracer.create_trace(
        name="llm_security_inspection",
        user_id=user_id,
        session_id=user_id,
        input_data={"raw_prompt": raw_prompt, "clean_prompt": clean_prompt},
        output_data={"raw_response": raw_llm_response, "final_response": final_response},
        scores={
            "injection_score": inj_res["injection_score"],
            "jailbreak_score": jb_res["jailbreak_score"],
            "anomaly_score": anomaly_res["anomaly_score"],
            "risk_score": agg_risk
        },
        latency_ms=latency_ms,
        usage=llm_res.get("usage", {}),
        tags=tags
    )

    event_logger.log({
        "user_id": user_id,
        "api_key": api_key,
        "client_ip": client_ip,
        "raw_prompt": raw_prompt,
        "masked_prompt": masked_prompt,
        "action": action,
        "risk_score": agg_risk,
        "injection_score": inj_res["injection_score"],
        "jailbreak_score": jb_res["jailbreak_score"],
        "anomaly_score": anomaly_res["anomaly_score"],
        "llama_guard_status": lg_res["status"],
        "raw_response": raw_llm_response,
        "final_response": final_response,
        "metadata": {"policy_id": policy_id, "provider": llm_res["provider"], "pii_masked": pii_count}
    })
    metrics_collector.record_request(latency_ms, action)

    return ChatResponse(
        response=final_response,
        action=action,
        risk_score=agg_risk,
        latency_ms=latency_ms,
        security_summary={
            "injection_detected": inj_res["is_injection"],
            "jailbreak_detected": jb_res["is_jailbreak"],
            "llama_guard_status": lg_res["status"],
            "pii_masked_count": pii_count,
            "anomaly_flag": anomaly_res["is_anomaly"],
            "policy_matched": policy_id
        }
    )
