# LLM Security Gateway — Tools, Justification & Added Value

> For each component: **what tool**, **why this tool**, and **what value it adds** that nothing else in the pipeline provides.

---

## 1. 🔐 API Gateway

### Component: FastAPI Gateway
- **Tool**: FastAPI + Uvicorn + Pydantic
- **Why FastAPI?**: Native async support — critical for high-throughput concurrent inspection pipelines.
- **Added value**: OpenAPI schema validation, Pydantic request sanitization, streaming support.

### Component: Rate Limiter
- **Tool**: Redis + Token Bucket Algorithm
- **Why Redis?**: Sub-millisecond performance (~0.1ms per op) + distributed token counters.
- **Added value**: Multi-dimensional limiting (Per-user, Per-API-key, Per-IP).

---

## 2. 🔒 Input Security Pipeline

### Component: Preprocessor / Normalization
- **Tool**: Python `unicodedata` + `ftfy` + `regex`
- **Added value**: Fixes unicode obfuscation (`ℯ` vs `e`), mojibake, and mixed encodings before regex or ML models run.

### Component: Prompt Injection Detector
- **Tool**: Fine-tuned DeBERTa-v3 + Regex + Heuristic Rules
- **Added value**: Disentangled attention catches direct and indirect instruction smuggling.

### Component: Jailbreak Detector
- **Tool**: RoBERTa + Scenario Pattern Library + Conversation Context Tracker
- **Added value**: Multi-turn context awareness detecting gradual escalation and DAN/developer mode roleplay prompts.

### Component: PII / Sensitive Data Detector
- **Tool**: Microsoft Presidio + SpaCy NER + Custom Regex
- **Added value**: Bi-directional masking & unmasking. Real PII never reaches the downstream LLM.

### Component: Llama Guard (Content Safety)
- **Tool**: Meta Llama Guard 3 via Ollama
- **Added value**: Nuanced semantic safety classification across domain harm taxonomies.

### Component: Guardrails AI — Input Validation
- **Tool**: Guardrails AI + RAIL specifications
- **Added value**: Declarative business rule enforcement (topic scope, token length, structural contracts).

---

## 3. 🔎 Behavioral Analysis

- **Tool**: Custom Python + Redis + PostgreSQL + scikit-learn (Isolation Forest)
- **Added value**: Cross-session anomaly detection catching low-and-slow attacks, topic drift, and session velocity spikes.

---

## 4. ⚙️ Core Security Engine

- **Risk Scoring Engine**: Custom Python + NumPy weighted score aggregation.
- **Policy Engine**: YAML policy-as-code rule evaluator (ALLOW, FLAG, REVIEW, BLOCK).
- **ML Detection Engine**: Hugging Face Transformers + sentence-transformers semantic embeddings.
- **Security Event Logger**: structlog + PostgreSQL (JSONB) + TimescaleDB metrics.

---

## 5. 🤖 LLM Backend

- **Tool**: Ollama (Local) + LiteLLM smart router fallback.

---

## 6. 🔍 Output Security Pipeline

- **Output PII Scanner**: Presidio + regex.
- **Data Leak Detector**: sentence-transformers semantic similarity vs. System Prompt.
- **Llama Guard Output**: Output safety validation.
- **Guardrails AI Output**: Schema validation, groundedness verification, PII restoration.

---

## 7. 📊 Observability & Monitoring

- **Langfuse**: LLM-native tracing and prompt replay.
- **Prometheus + Grafana**: Infrastructure metrics & latency monitoring.
- **Streamlit Security Dashboard**: Interactive security insights & threat heatmaps.

---

## 8. 🗄️ Data Layer & 9. 🔄 Feedback Loop & 10. 🎯 Testing
- **Redis 7+**, **PostgreSQL 16 + TimescaleDB**, **Label Studio**, **Celery**, **HF PEFT (LoRA)**, **DVC**, **Giskard**, **Garak**.
