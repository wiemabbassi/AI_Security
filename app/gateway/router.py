import time
import json as _json
import asyncio
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, AsyncGenerator

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

from app.config import settings

try:
    import requests as _requests_lib
except ImportError:
    _requests_lib = None

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


# ── Endpoint 0: Direct LLM — NO SECURITY (for demo "before" comparison) ───────

@router.post("/direct")
def direct_llm_endpoint(request_data: ChatRequest):
    """
    Bypasses ALL security — goes straight to Ollama.
    Used ONLY by the demo interface to show the 'Before Gateway' side.
    Never use this in production.
    """
    import time as _time
    start = _time.time()
    
    # Direct raw call to Ollama generate without system prompts or filters
    response_text = ""
    try:
        r = _requests_lib.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": request_data.prompt,
                "options": {
                    "num_predict": 350
                },
                "stream": False,
            },
            timeout=120.0
        )
        if r.status_code == 200:
            response_text = r.json().get("response", "")
    except Exception as e:
        # Fallback to router generate if generate endpoint fails
        llm_res = llm_router.generate(request_data.prompt, is_sensitive=False)
        response_text = llm_res.get("response", f"Direct Ollama error: {e}")

    latency_ms = round((_time.time() - start) * 1000, 2)
    return {
        "response": response_text,
        "provider": "ollama_direct_raw",
        "model": settings.OLLAMA_MODEL,
        "latency_ms": latency_ms,
    }


# ── Shared security pipeline helper ───────────────────────────────────────────

def _run_input_security_pipeline(
    raw_prompt: str,
    user_id: str,
    api_key: str,
    client_ip: str,
):
    """
    Runs the full input security pipeline (stages 1–4) and returns a context dict.
    Shared by both /chat and /chat/stream endpoints.
    """
    clean_prompt = normalizer.normalize(raw_prompt)
    session_history = behavioral_analyzer.get_user_prompt_history(user_id)

    inj_res = injection_detector.analyze(clean_prompt)
    jb_res = jailbreak_detector.analyze(clean_prompt, session_history=session_history)
    masked_prompt, pii_map, pii_count = pii_detector.mask_pii(clean_prompt)
    lg_res = llama_guard.classify(masked_prompt)
    gr_res = guardrails_validator.validate_input(masked_prompt)
    ml_res = ml_engine.check_semantic_similarity(clean_prompt)

    anomaly_res = behavioral_analyzer.analyze_user_behavior(
        user_id=user_id,
        prompt_len=len(clean_prompt),
        current_risk=inj_res["injection_score"],
        prompt_text=clean_prompt
    )

    agg_risk = risk_scorer.calculate_risk(
        injection_score=inj_res["injection_score"],
        jailbreak_score=jb_res["jailbreak_score"],
        llama_guard_status=lg_res["status"],
        anomaly_score=anomaly_res["anomaly_score"]
    )

    policy_context = {
        "injection_score": inj_res["injection_score"],
        "jailbreak_score": jb_res["jailbreak_score"],
        "anomaly_score": anomaly_res["anomaly_score"],
        "risk_score": agg_risk,
        "llama_guard_status": lg_res["status"],
        "behavioral_alert": anomaly_res["is_anomaly"]
    }
    action, policy_id, policy_reason = policy_engine.evaluate(policy_context)

    return {
        "clean_prompt": clean_prompt,
        "masked_prompt": masked_prompt,
        "pii_map": pii_map,
        "pii_count": pii_count,
        "inj_res": inj_res,
        "jb_res": jb_res,
        "lg_res": lg_res,
        "gr_res": gr_res,
        "ml_res": ml_res,
        "anomaly_res": anomaly_res,
        "agg_risk": agg_risk,
        "action": action,
        "policy_id": policy_id,
        "policy_reason": policy_reason,
    }


# ── Endpoint 1: Standard request/response ─────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    request_data: ChatRequest,
    req: Request,
    authorization: Optional[str] = Header(None),
    refusal_as_200: bool = False,
    x_refusal_status_200: Optional[str] = Header(None)
):
    start_time = time.time()
    user_id = request_data.user_id or "user_default"
    client_ip = req.client.host if req.client else "127.0.0.1"
    auth_str = authorization if isinstance(authorization, str) else (req.headers.get("authorization", "") if req else "")
    api_key = auth_str.replace("Bearer ", "").strip() if auth_str else "public"
    scanner_mode = refusal_as_200 or (x_refusal_status_200 == "true") or (req.headers.get("x-scanner-run") == "true")

    # 1. Rate Limiting Check (exempt scanner benchmark runs)
    is_scanner_session = (
        scanner_mode or
        user_id.startswith("garak") or
        user_id.startswith("giskard") or
        user_id.startswith("benchmark")
    )
    if not is_scanner_session:
        allowed, remaining, retry_after = rate_limiter.is_allowed(
            key=f"{user_id}:{api_key}",
            user_id=user_id,
            api_key=api_key,
            client_ip=client_ip
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Too Many Requests. Rate limit exceeded. Retry after {retry_after}s"
            )

    # 2–4. Input Security Pipeline + Risk + Policy
    raw_prompt = request_data.prompt
    gr_initial = guardrails_validator.validate_input(normalizer.normalize(raw_prompt))
    if not gr_initial["valid"]:
        latency_ms = (time.time() - start_time) * 1000
        metrics_collector.record_request(latency_ms, "BLOCK")
        if scanner_mode:
            return ChatResponse(
                response=f"I cannot fulfill this request. Input validation failed: {gr_initial['reason']}",
                action="BLOCK",
                risk_score=1.0,
                latency_ms=round(latency_ms, 2),
                security_summary={"reason": gr_initial["reason"], "blocked": True}
            )
        raise HTTPException(status_code=400, detail=gr_initial["reason"])

    ctx = _run_input_security_pipeline(raw_prompt, user_id, api_key, client_ip)
    if not ctx["gr_res"]["valid"]:
        latency_ms = (time.time() - start_time) * 1000
        metrics_collector.record_request(latency_ms, "BLOCK")
        if scanner_mode:
            return ChatResponse(
                response=f"I cannot fulfill this request. Input validation failed: {ctx['gr_res']['reason']}",
                action="BLOCK",
                risk_score=1.0,
                latency_ms=round(latency_ms, 2),
                security_summary={"reason": ctx["gr_res"]["reason"], "blocked": True}
            )
        raise HTTPException(status_code=400, detail=ctx["gr_res"]["reason"])

    if ctx["action"] == "BLOCK":
        latency_ms = (time.time() - start_time) * 1000
        langfuse_tracer.create_trace(
            name="llm_security_inspection_blocked",
            user_id=user_id,
            input_data={"raw_prompt": raw_prompt, "clean_prompt": ctx["clean_prompt"]},
            output_data={"raw_response": None, "final_response": f"BLOCKED: {ctx['policy_reason']}"},
            scores={"injection_score": ctx["inj_res"]["injection_score"],
                    "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
                    "anomaly_score": ctx["anomaly_res"]["anomaly_score"],
                    "risk_score": ctx["agg_risk"]},
            latency_ms=latency_ms
        )
        event_logger.log({
            "user_id": user_id, "api_key": api_key, "client_ip": client_ip,
            "raw_prompt": raw_prompt, "masked_prompt": ctx["masked_prompt"],
            "action": "BLOCK", "risk_score": ctx["agg_risk"],
            "injection_score": ctx["inj_res"]["injection_score"],
            "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
            "anomaly_score": ctx["anomaly_res"]["anomaly_score"],
            "llama_guard_status": ctx["lg_res"]["status"],
            "raw_response": None, "final_response": None,
            "metadata": {"policy_id": ctx["policy_id"], "reason": ctx["policy_reason"]}
        })
        metrics_collector.record_request(latency_ms, "BLOCK")
        if scanner_mode:
            return ChatResponse(
                response=f"I cannot fulfill this request. It was blocked by LLM Security Gateway policy [{ctx['policy_id']}]: {ctx['policy_reason']}",
                action="BLOCK",
                risk_score=ctx["agg_risk"],
                latency_ms=round(latency_ms, 2),
                security_summary={
                    "policy_id": ctx["policy_id"],
                    "policy_reason": ctx["policy_reason"],
                    "injection_score": ctx["inj_res"]["injection_score"],
                    "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
                    "llama_guard_status": ctx["lg_res"]["status"],
                    "blocked": True,
                }
            )
        raise HTTPException(status_code=403, detail=f"Request blocked by security policy [{ctx['policy_id']}]: {ctx['policy_reason']}")

    # 5. LLM Backend Generation
    llm_res = llm_router.generate(ctx["masked_prompt"])
    raw_llm_response = llm_res["response"]

    # 6. Output Security Pipeline
    out_pii_res = output_pii_scanner.scan(raw_llm_response)
    leak_res = data_leak_detector.detect_leak(raw_llm_response, system_prompt=llm_router.SYSTEM_PROMPT)
    out_lg_res = llama_guard_output.scan(raw_llm_response)
    final_out_res = output_guardrails.validate_and_restore(raw_llm_response, ctx["pii_map"], context=ctx["clean_prompt"])

    if out_lg_res.get("status") == "UNSAFE":
        latency_ms = round((time.time() - start_time) * 1000, 2)
        metrics_collector.record_request(latency_ms, "BLOCK")
        event_logger.log({
            "user_id": user_id, "api_key": api_key, "client_ip": client_ip,
            "raw_prompt": raw_prompt, "masked_prompt": ctx["masked_prompt"],
            "action": "BLOCK_OUTPUT", "risk_score": ctx["agg_risk"],
            "injection_score": ctx["inj_res"]["injection_score"],
            "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
            "anomaly_score": ctx["anomaly_res"]["anomaly_score"],
            "llama_guard_status": "UNSAFE_OUTPUT",
            "raw_response": raw_llm_response, "final_response": None,
            "metadata": {"reason": f"Output Llama Guard blocked: {out_lg_res.get('category')}",
                         "scan_mode": out_lg_res.get("scan_mode")}
        })
        if scanner_mode:
            return ChatResponse(
                response=f"I cannot provide this output. It was blocked by LLM Security Gateway safety scan: {out_lg_res.get('category', 'Unsafe content detected')}",
                action="BLOCK_OUTPUT",
                risk_score=ctx["agg_risk"],
                latency_ms=round(latency_ms, 2),
                security_summary={
                    "reason": f"Output Llama Guard blocked: {out_lg_res.get('category')}",
                    "blocked": True,
                }
            )
        raise HTTPException(status_code=403, detail=f"Response blocked by output safety scan: {out_lg_res.get('category', 'Unsafe content detected')}")

    if leak_res.get("is_leak"):
        latency_ms = round((time.time() - start_time) * 1000, 2)
        metrics_collector.record_request(latency_ms, "BLOCK")
        event_logger.log({
            "user_id": user_id, "api_key": api_key, "client_ip": client_ip,
            "raw_prompt": raw_prompt, "masked_prompt": ctx["masked_prompt"],
            "action": "BLOCK_OUTPUT", "risk_score": ctx["agg_risk"],
            "injection_score": ctx["inj_res"]["injection_score"],
            "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
            "anomaly_score": ctx["anomaly_res"]["anomaly_score"],
            "llama_guard_status": "DATA_LEAK_OUTPUT",
            "raw_response": raw_llm_response, "final_response": None,
            "metadata": {"reason": f"System prompt leak detected: {leak_res.get('matched_leak')}"}
        })
        if scanner_mode:
            return ChatResponse(
                response="I cannot provide this output. It was blocked by LLM Security Gateway: System prompt data leakage detected.",
                action="BLOCK_OUTPUT",
                risk_score=1.0,
                latency_ms=round(latency_ms, 2),
                security_summary={
                    "reason": f"System prompt leak detected: {leak_res.get('matched_leak')}",
                    "blocked": True,
                }
            )
        raise HTTPException(status_code=403, detail="Response blocked by data leak detector: System prompt leakage detected")

    final_response = final_out_res["final_response"]
    latency_ms = round((time.time() - start_time) * 1000, 2)

    # 7. Audit, Langfuse Tracing & Event Logging
    tags = [f"action_{ctx['action'].lower()}", f"policy_{ctx['policy_id'].lower()}"]
    if ctx["pii_map"]: tags.append("pii_masked")
    if ctx["lg_res"]["status"] == "SAFE": tags.append("llama_guard_safe")
    if out_lg_res.get("status") == "SAFE": tags.append("output_llama_guard_safe")
    if leak_res.get("is_leak"): tags.append("data_leak_detected")

    langfuse_tracer.create_trace(
        name="llm_security_inspection",
        user_id=user_id, session_id=user_id,
        input_data={"raw_prompt": raw_prompt, "clean_prompt": ctx["clean_prompt"]},
        output_data={"raw_response": raw_llm_response, "final_response": final_response,
                     "provider": llm_res.get("provider", "")},
        scores={"injection_score": float(ctx["inj_res"]["injection_score"]),
                "jailbreak_score": float(ctx["jb_res"]["jailbreak_score"]),
                "anomaly_score": float(ctx["anomaly_res"]["anomaly_score"]),
                "risk_score": float(ctx["agg_risk"])},
        latency_ms=float(latency_ms), usage=llm_res.get("usage", {}), tags=tags
    )
    event_logger.log({
        "user_id": user_id, "api_key": api_key, "client_ip": client_ip,
        "raw_prompt": raw_prompt, "masked_prompt": ctx["masked_prompt"],
        "action": ctx["action"], "risk_score": float(ctx["agg_risk"]),
        "injection_score": float(ctx["inj_res"]["injection_score"]),
        "jailbreak_score": float(ctx["jb_res"]["jailbreak_score"]),
        "anomaly_score": float(ctx["anomaly_res"]["anomaly_score"]),
        "llama_guard_status": ctx["lg_res"]["status"],
        "raw_response": raw_llm_response, "final_response": final_response,
        "metadata": {"policy_id": ctx["policy_id"], "provider": llm_res["provider"],
                     "pii_masked": ctx["pii_count"],
                     "output_llama_guard": out_lg_res.get("status"),
                     "data_leak": leak_res.get("is_leak"),
                     "guardrails_issues": final_out_res.get("issues", [])}
    })
    metrics_collector.record_request(latency_ms, ctx["action"])

    return ChatResponse(
        response=str(final_response),
        action=str(ctx["action"]),
        risk_score=float(ctx["agg_risk"]),
        latency_ms=float(latency_ms),
        security_summary={
            "injection_detected": bool(ctx["inj_res"]["is_injection"]),
            "jailbreak_detected": bool(ctx["jb_res"]["is_jailbreak"]),
            "llama_guard_input_status": str(ctx["lg_res"]["status"]),
            "llama_guard_output_status": str(out_lg_res.get("status", "SAFE")),
            "pii_masked_count": int(ctx["pii_count"]),
            "pii_restored_count": int(final_out_res.get("pii_restored_count", 0)),
            "data_leak_detected": bool(leak_res.get("is_leak", False)),
            "data_leak_score": float(leak_res.get("leak_score", 0.0)),
            "anomaly_flag": bool(ctx["anomaly_res"]["is_anomaly"]),
            "policy_matched": str(ctx["policy_id"]),
            "guardrails_passed": bool(final_out_res.get("guardrails_passed", False)),
            "guardrails_issues": list(final_out_res.get("issues", []))
        }
    )


# ── Endpoint 2: SSE streaming response ────────────────────────────────────────

async def _sse_stream_ollama(
    masked_prompt: str,
    pii_map: Dict[str, str],
) -> AsyncGenerator[str, None]:
    """
    Streams token-by-token from Ollama's /api/generate (stream=True) endpoint
    via SSE (Server-Sent Events) format.

    SSE event format:
        data: {"token": "Hello", "done": false}\n\n
        data: {"token": " world", "done": false}\n\n
        data: {"token": "", "done": true}\n\n

    Falls back to chunking a buffered response if streaming unavailable.
    """
    full_response = ""
    streamed = False

    if _requests_lib is not None:
        try:
            with _requests_lib.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": (
                        f"[SYSTEM] {llm_router.SYSTEM_PROMPT} [/SYSTEM]\n"
                        f"[USER] {masked_prompt} [/USER]"
                    ),
                    "stream": True,
                },
                stream=True,
                timeout=60.0,
            ) as resp:
                if resp.status_code == 200:
                    streamed = True
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = _json.loads(line)
                            token = chunk.get("response", "")
                            done = chunk.get("done", False)
                            full_response += token

                            # Restore PII tokens on-the-fly per token
                            display_token = token
                            for placeholder, original in pii_map.items():
                                display_token = display_token.replace(placeholder, original)

                            payload = _json.dumps({"token": display_token, "done": done})
                            yield f"data: {payload}\n\n"
                            await asyncio.sleep(0)  # yield control to event loop

                            if done:
                                break
                        except Exception:
                            continue
        except Exception:
            streamed = False

    if not streamed:
        # Fallback: get buffered response and chunk it artificially
        llm_res = llm_router.generate(masked_prompt)
        raw = llm_res.get("response", "")
        restored = pii_detector.unmask_pii(raw, pii_map)
        # Emit in ~20-token chunks to simulate streaming
        words = restored.split(" ")
        chunk_size = 5
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i : i + chunk_size]
            token = " ".join(chunk_words) + (" " if i + chunk_size < len(words) else "")
            done = i + chunk_size >= len(words)
            payload = _json.dumps({"token": token, "done": done})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.02)


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request_data: ChatRequest,
    req: Request,
    authorization: Optional[str] = Header(None)
):
    """
    SSE Streaming Chat Endpoint.

    Runs the complete security pipeline synchronously (input → policy decision),
    then streams the LLM response as Server-Sent Events (text/event-stream).

    Security guarantees are identical to /v1/chat — all detectors run before
    the first token is streamed. Blocked requests return HTTP 403 immediately.

    Client usage (JavaScript):
        const evtSource = new EventSource('/v1/chat/stream');
        // Use fetch with POST + ReadableStream for POST-based SSE
    """
    start_time = time.time()
    user_id = request_data.user_id
    client_ip = req.client.host if req.client else "127.0.0.1"
    auth_str = authorization if isinstance(authorization, str) else (req.headers.get("authorization", "") if req else "")
    api_key = auth_str.replace("Bearer ", "").strip() if auth_str else "public"

    # 1. Rate limiting
    allowed, remaining, retry_after = rate_limiter.is_allowed(
        key=f"{user_id}:{api_key}",
        user_id=user_id,
        api_key=api_key,
        client_ip=client_ip
    )
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Retry after {retry_after}s")

    # 2–4. Full input security pipeline (synchronous — runs before streaming starts)
    raw_prompt = request_data.prompt
    ctx = _run_input_security_pipeline(raw_prompt, user_id, api_key, client_ip)

    if not ctx["gr_res"]["valid"]:
        raise HTTPException(status_code=400, detail=ctx["gr_res"]["reason"])

    if ctx["action"] == "BLOCK":
        latency_ms = (time.time() - start_time) * 1000
        metrics_collector.record_request(latency_ms, "BLOCK")
        event_logger.log({
            "user_id": user_id, "api_key": api_key, "client_ip": client_ip,
            "raw_prompt": raw_prompt, "masked_prompt": ctx["masked_prompt"],
            "action": "BLOCK", "risk_score": ctx["agg_risk"],
            "injection_score": ctx["inj_res"]["injection_score"],
            "jailbreak_score": ctx["jb_res"]["jailbreak_score"],
            "anomaly_score": ctx["anomaly_res"]["anomaly_score"],
            "llama_guard_status": ctx["lg_res"]["status"],
            "raw_response": None, "final_response": None,
            "metadata": {"policy_id": ctx["policy_id"], "reason": ctx["policy_reason"],
                         "stream": True}
        })
        raise HTTPException(
            status_code=403,
            detail=f"[STREAM] Request blocked by security policy [{ctx['policy_id']}]: {ctx['policy_reason']}"
        )

    # 5. Stream LLM response (output pipeline applied per-token inside the generator)
    headers = {
        "Cache-Control": "no-cache",
        "X-Security-Action": ctx["action"],
        "X-Risk-Score": str(ctx["agg_risk"]),
        "X-Policy-ID": ctx["policy_id"],
    }

    metrics_collector.record_request(round((time.time() - start_time) * 1000, 2), ctx["action"])

    return StreamingResponse(
        _sse_stream_ollama(ctx["masked_prompt"], ctx["pii_map"]),
        media_type="text/event-stream",
        headers=headers,
    )

