# LLM Security Gateway — Tools, Justification & Added Value

> For each component: **what tool**, **why this tool**, and **what value it adds** that nothing else in the pipeline provides.

---

## 1. 🔐 API Gateway

### Component: FastAPI Gateway

| | Detail |
|:--|:-------|
| **Tool** | **FastAPI** + **Uvicorn** (ASGI server) + **Pydantic** (validation) |
| **Why FastAPI?** | Native **async support** — critical for an LLM gateway where you're making multiple concurrent calls to detectors, models, and databases. Synchronous frameworks (Flask, Django) would bottleneck under load. |
| **Why not Express/Node?** | Python ecosystem is where all the ML/AI tools live (Presidio, SpaCy, Transformers, Giskard, Guardrails AI). Using Python end-to-end avoids cross-language serialization overhead. |
| **Added value** | Auto-generated OpenAPI docs, type-safe request/response validation via Pydantic (catches malformed requests before they touch the pipeline), and native WebSocket support for streaming LLM responses. |


### Component: Rate Limiter

| | Detail |
|:--|:-------|
| **Tool** | **Redis** + **Token Bucket algorithm** (custom implementation) |
| **Why Redis?** | In-memory speed (~0.1ms per operation) + distributed state. Multiple gateway instances share the same rate limit counters without conflicts. |
| **Why Token Bucket over Fixed Window?** | Token bucket allows **bursts** within reason (a user can send 5 quick requests) while still enforcing a sustained rate limit. Fixed window causes edge-case bursts at window boundaries. |
| **Added value** | Per-user, per-API-key, AND per-IP rate limiting simultaneously. A compromised API key can be throttled without affecting the entire IP. |

---

## 2. 🔒 Input Security Pipeline

### Component: Preprocessor / Normalization

| | Detail |
|:--|:-------|
| **Tool** | **Python unicodedata** (stdlib) + **ftfy** (fixes text encoding) + **regex** (advanced regex) |
| **Why ftfy?** | Standard Python can normalize unicode, but ftfy handles **real-world encoding chaos** — mojibake, mixed encodings, HTML entities, curly quotes. It's battle-tested on billions of web documents. |
| **Why not just regex?** | Regex alone can't handle semantic equivalence between unicode characters (`ℯ` vs `e`, `𝐇` vs `H`). Unicode normalization (NFKC) collapses these before regex even runs. |
| **Added value** | **The invisible shield.** Every downstream detector sees clean, normalized text. Without this, an attacker writing `ⅰgnore prev𝐢ous 𝑖nstructions` bypasses every pattern-based detector. |

### Component: Prompt Injection Detector

| | Detail |
|:--|:-------|
| **Tool** | **Custom fine-tuned DeBERTa-v3** (ML classifier) + **regex patterns** + **heuristic rules** |
| **Why DeBERTa-v3?** | State-of-the-art on text classification benchmarks. Its **disentangled attention** mechanism understands the relationship between content and position — critical for detecting when instruction-like text appears in data fields where it shouldn't. |
| **Why not just a keyword list?** | Attackers use **infinite paraphrasing**. "Ignore previous instructions" can be rephrased as "Disregard the above", "Override your guidelines", "Start a new conversation from scratch", etc. Only an ML model trained on thousands of variants catches novel phrasings. |
| **Why also keep regex + heuristics?** | Defense in depth. ML models have latency (~50ms). Simple regex catches the obvious attacks in <1ms. Heuristics catch structural anomalies (e.g., `[SYSTEM]` tags appearing in user input). The three layers complement each other. |
| **Added value** | Catches both **direct injection** (user types the attack) AND **indirect injection** (attack is hidden in documents/data the app processes). The ML model understands context, not just keywords. |

### Component: Jailbreak Detector

| | Detail |
|:--|:-------|
| **Tool** | **Custom fine-tuned classifier** (based on RoBERTa) + **scenario pattern library** + **conversation context tracker** |
| **Why a separate model from injection?** | Different training data, different attack surface. Jailbreaks target **model behavior** (role-play, hypothetical framing), while injections target **application logic** (instruction smuggling). A single model trying to do both loses accuracy on each. |
| **Why RoBERTa?** | Excellent at understanding **pragmatic intent** — distinguishing between a user genuinely asking about a hypothetical scenario vs. using hypothetical framing to bypass safety. |
| **The scenario pattern library** | A curated, regularly updated database of known jailbreak templates: DAN prompts, AIM prompts, Developer Mode prompts, etc. New templates are added weekly from threat intelligence feeds and manual red teaming. |
| **Added value** | **Multi-turn awareness.** Unlike single-turn detectors, this tracks conversation history and flags **gradual escalation** — where each individual message looks safe but the conversation trajectory is clearly building toward a jailbreak. |

### Component: PII / Sensitive Data Detector

| | Detail |
|:--|:-------|
| **Tool** | **Microsoft Presidio** (primary) + **SpaCy NER** (supporting) + **custom regex patterns** |
| **Why Presidio?** | Built specifically for PII detection — supports **40+ entity types** out of the box, handles multi-language PII, and provides built-in **anonymization operators** (mask, hash, redact, replace). Open-source and actively maintained by Microsoft. |
| **Why SpaCy alongside Presidio?** | SpaCy's NER catches **contextual entities** that Presidio misses — organization names, locations mentioned conversationally, product names that could be confidential. SpaCy understands grammar; Presidio understands data formats. |
| **Why custom regex too?** | Company-specific patterns: employee IDs (`EMP-XXXXX`), internal project codes (`PROJ-XXX-XXXX`), custom account formats. No off-the-shelf tool knows your internal ID formats. |
| **Added value** | **Bi-directional PII handling.** Masks PII before the LLM sees it, stores the mapping securely, then de-masks the response so the user sees the original names/values. The LLM never touches real PII. |

### Component: Llama Guard (Content Safety)

| | Detail |
|:--|:-------|
| **Tool** | **Meta Llama Guard 3** (8B parameter safety classifier) via **Ollama** (local inference) |
| **Why Llama Guard?** | Purpose-built for LLM safety classification. Unlike general classifiers, it understands **LLM-specific harm categories** and rates content on a nuanced scale, not just safe/unsafe binary. |
| **Why run it locally via Ollama?** | **Data sovereignty.** Sending every user prompt to a cloud safety API (like OpenAI Moderation) means your users' data leaves your infrastructure. With Ollama, Llama Guard runs entirely on your GPU — zero external data exposure. |
| **Why not just OpenAI Moderation API?** | Three reasons: (1) data never leaves your infra, (2) customizable taxonomy — you can fine-tune categories for your domain, (3) no per-call cost at scale. |
| **Added value** | **Deep semantic safety understanding.** Catches nuanced harmful intent that keyword filters miss entirely. Understands context — "how to kill a process" (safe, technical) vs. harmful requests. |

### Component: 🆕 Guardrails AI — Input Validation

| | Detail |
|:--|:-------|
| **Tool** | **Guardrails AI** (open-source framework) + **RAIL specifications** + **Guardrails Hub validators** |
| **Why Guardrails AI?** | The other detectors catch **attacks**. Guardrails AI catches **misuse** — valid, safe prompts that are simply outside the system's intended scope. It fills the gap between "is this prompt dangerous?" and "is this prompt appropriate for our system?" |
| **What's a RAIL spec?** | A declarative XML/JSON specification that defines exactly what inputs are acceptable — topics, formats, length constraints, required fields. Think of it as a **contract** between the user and the system. |
| **Guardrails Hub** | Pre-built validators you can plug in: `ToxicLanguage`, `DetectPII`, `RestrictToTopic`, `ReadingTime`, `ValidURL`, etc. No need to build everything from scratch. |
| **Added value** | **Programmable guardrails** that go beyond ML detection. You can enforce business rules declaratively: "Only allow prompts about customer support topics", "Reject any prompt over 2000 tokens", "Ensure the input language is French or English". |

---

## 3. 🔎 Analyse Comportementale (Behavioral Analysis)

> [!IMPORTANT]
> This is a **cross-cutting component** that spans the entire pipeline — it monitors user behavior patterns over time, not individual requests in isolation.

| | Detail |
|:--|:-------|
| **Tool** | **Custom Python service** + **Redis** (real-time session state) + **PostgreSQL** (historical patterns) + **scikit-learn** (anomaly models) + **Celery** (async processing) |
| **What it does** | Profiles each user's behavior over time and flags **anomalous deviations** from their normal patterns. |

### What It Monitors

| Signal | What It Catches | Example |
|:-------|:----------------|:--------|
| **Request frequency patterns** | Sudden spike in request volume from a normally low-usage user | A compromised API key being exploited |
| **Topic drift across sessions** | User who always asks about HR topics suddenly starts asking about network infrastructure | Potential lateral movement or social engineering |
| **Failure rate anomalies** | Abnormally high rate of blocked/flagged requests from one user | Active attack probing — trying different injection variants |
| **Time-of-day patterns** | Requests at 3 AM from a user who normally works 9-5 | Compromised account or automated scripting |
| **Prompt complexity escalation** | Prompts getting progressively more complex, longer, or more technical over a session | Multi-turn jailbreak attempt building up gradually |
| **Session velocity** | Many short sessions in rapid succession instead of normal conversation flow | Automated attack tooling |
| **Detector score trends** | Risk scores gradually increasing across a session, even if none hit the block threshold | Slow-burn attack that stays just under detection thresholds |
| **Response usage patterns** | User consistently ignores LLM responses (not reading them) | Likely probing for information extraction, not genuine use |

### How It Works

```
Real-time Layer (Redis):
  → Track per-session: request count, avg risk score, topic vector, timing
  → Compare against user's rolling baseline (last 30 days)
  → If deviation > threshold → raise behavioral alert

Historical Layer (PostgreSQL):
  → Build user behavior profiles over time
  → Cluster users by behavior type (normal, power user, suspicious)
  → Train anomaly detection model (Isolation Forest) on historical patterns

Alert Actions:
  → Low anomaly  → Log + increase monitoring sensitivity
  → Medium       → Flag for human review + temporarily lower risk thresholds
  → High         → Throttle user + notify security team + require re-auth
```

### Why scikit-learn?

| | Detail |
|:--|:-------|
| **Algorithm** | **Isolation Forest** for anomaly detection |
| **Why?** | Lightweight, fast inference (<1ms), doesn't need labeled attack data (unsupervised). It learns what "normal" looks like and flags anything that doesn't fit. |
| **Why not deep learning?** | Overkill for tabular behavioral features. Isolation Forest outperforms neural nets on this type of structured anomaly detection with far less compute. |

### Added Value

> **The other detectors analyze one request at a time. Behavioral analysis sees the bigger picture.**

A sophisticated attacker who keeps each individual request just below detection thresholds would slip past every single-request detector. Behavioral analysis catches them because the **pattern of many "barely safe" requests** is itself anomalous. This is the difference between checking each tree and seeing the forest.

---

## 4. ⚙️ Core Security Engine

### Component: Risk Scoring Engine

| | Detail |
|:--|:-------|
| **Tool** | **Custom Python** + **NumPy** (fast weighted aggregation) |
| **Why custom over an off-the-shelf scoring tool?** | Every LLM security deployment has different priorities. A healthcare app weights PII detection 3x higher. A code assistant weights injection detection 3x higher. Generic scoring tools don't allow this granularity. |
| **Added value** | **Unified risk score** from 5+ independent detectors. Without aggregation, you'd have 5 separate yes/no decisions with no way to weigh trade-offs. The risk score enables graduated responses (allow → flag → review → block). |

### Component: Policy Engine

| | Detail |
|:--|:-------|
| **Tool** | **Custom YAML-based rule engine** + **Python** |
| **Why YAML policy-as-code?** | Security rules change faster than code. A new attack pattern emerges? Add a YAML rule in minutes, no redeployment needed. Compliance requirement changes? Update the policy file. |
| **Why not OPA (Open Policy Agent)?** | OPA is powerful but uses Rego — a custom policy language. YAML is readable by security analysts, not just engineers. This lowers the barrier for the security team to own their rules. |
| **Added value** | **Decouples security logic from code.** Non-engineers can read, write, and audit security policies. Version-controlled in Git for full change history and review. |

### Component: ML Detection Engine

| | Detail |
|:--|:-------|
| **Tool** | **Hugging Face Transformers** + **sentence-transformers** (semantic similarity) + **custom trained models** |
| **Why sentence-transformers?** | Embeds prompts into vector space where **semantically similar attacks cluster together**. Even if an attacker completely rewords a known attack, its embedding will be close to known attack embeddings. |
| **Added value** | **Catches zero-day prompt attacks.** A novel attack phrasing that no rule or pattern has ever seen will still be flagged if its semantic meaning is similar to known attacks. This is the ML layer that makes the system future-proof. |

### Component: Security Event Logger

| | Detail |
|:--|:-------|
| **Tool** | **structlog** (structured logging) + **PostgreSQL** (JSONB storage) + **TimescaleDB** (time-series extension) |
| **Why structlog?** | Produces machine-parseable JSON logs (not human-readable text). Every log entry is a structured object that can be queried, aggregated, and analyzed. |
| **Why TimescaleDB?** | Security events are time-series data. TimescaleDB gives automatic partitioning, compression, and fast time-range queries on top of PostgreSQL. "Show me all blocked requests in the last 24 hours" runs in milliseconds even on millions of events. |
| **Added value** | **Complete audit trail** for compliance (EU AI Act, NIST AI RMF). Every decision is traceable: who asked what, what was detected, what action was taken, and why. |

---

## 5. 🤖 LLM Backend

### Component: LLM Router

| | Detail |
|:--|:-------|
| **Tool** | **Custom Python router** + **LiteLLM** (unified LLM API) |
| **Why LiteLLM?** | Provides a **single API interface** to 100+ LLM providers (OpenAI, Anthropic, Ollama, Azure, etc.). Switch models or add providers without changing application code. |
| **Added value** | **Smart routing based on data sensitivity.** Requests containing masked PII → route to Ollama (local). General queries → route to OpenAI (better quality). Cost optimization by routing simple tasks to cheaper models. |

### Component: Ollama (Local)

| | Detail |
|:--|:-------|
| **Tool** | **Ollama** (local model runtime) |
| **Why Ollama?** | Simplest way to run open-source models locally. One command to download and serve any model. Built-in model management, GPU optimization, and API compatibility. |
| **Added value** | **Zero data exposure.** Everything runs on your GPU. No API calls to external servers. Required for compliance in regulated industries (healthcare, finance, government). |

### Component: OpenAI API (Cloud)

| | Detail |
|:--|:-------|
| **Tool** | **OpenAI API** (GPT-4o, o1 series) |
| **Why OpenAI?** | When you need maximum reasoning capability — complex analysis, nuanced generation, multi-step reasoning. Local models are good but frontier models are better for hard tasks. |
| **Added value** | **Best-in-class quality** for non-sensitive tasks. The router ensures sensitive data never reaches this endpoint. |

---

## 6. 🔍 Output Security Pipeline

### Component: Output PII Scanner

| | Detail |
|:--|:-------|
| **Tool** | **Microsoft Presidio** (same as input) + **regex** |
| **Why reuse Presidio?** | Consistency — same entity types detected on both input and output. If we masked `John Smith` on input, we need to catch it if the model hallucinates it on output. |
| **Added value** | Catches **training data leakage** — real PII the model memorized during pre-training and might regurgitate. |

### Component: Data Leak Detector

| | Detail |
|:--|:-------|
| **Tool** | **Custom Python** + **sentence-transformers** (semantic similarity) + **regex** |
| **Why semantic similarity?** | The model won't leak the system prompt verbatim — it'll paraphrase it. Regex catches exact matches; semantic similarity catches paraphrased leaks ("My instructions say..." → flagged because it's semantically similar to the actual system prompt). |
| **Added value** | **Protects your intellectual property.** System prompts often contain proprietary business logic, custom instructions, and API configurations. This detector prevents the model from exposing them. |

### Component: Llama Guard — Output

| | Detail |
|:--|:-------|
| **Tool** | **Meta Llama Guard 3** via **Ollama** (same as input) |
| **Why scan output too?** | A subtle jailbreak might pass input scanning but produce harmful output. The input looked safe; the output isn't. This is the **last safety net** before the response reaches the user. |
| **Added value** | Catches **emergent harmful content** — the model sometimes produces unsafe content even from safe-looking prompts, especially with creative/fictional tasks. |

### Component: 🆕 Guardrails AI — Output Validation

| | Detail |
|:--|:-------|
| **Tool** | **Guardrails AI** + **Guardrails Hub validators** |
| **Key validators used** | `ValidJSON`, `CorrectSchema`, `ProvenanceVerifier` (groundedness check), `ResponseRelevancy`, `NoOffTopic` |
| **Added value** | **Structural correctness + factual grounding.** Ensures the LLM's response actually conforms to expected format, stays on topic, and doesn't confidently assert ungrounded claims. The other output detectors check safety; this checks quality. |

---

## 7. 📊 Observability & Monitoring

### Component: Langfuse

| | Detail |
|:--|:-------|
| **Tool** | **Langfuse** (open-source LLM observability) |
| **Why Langfuse over Datadog/New Relic?** | Traditional APM tools don't understand LLMs. Langfuse provides **LLM-native tracing** — it tracks prompt templates, model responses, token counts, costs per call, and quality scores. It's built specifically for AI applications. |
| **Why not Arize/Weights & Biases?** | Langfuse is **self-hostable** (no data leaves your infra) and **open-source**. W&B and Arize are primarily cloud SaaS. |
| **Added value** | **Replay any request end-to-end.** See the exact prompt sent, every detector's score, the model's raw response, and the final sanitized output. Critical for debugging false positives and investigating incidents. |

### Component: Grafana + Prometheus

| | Detail |
|:--|:-------|
| **Tool** | **Grafana** (dashboards) + **Prometheus** (metrics collection) + **Alertmanager** (alerting) |
| **Why this stack?** | Industry standard for infrastructure monitoring. Massive ecosystem of pre-built dashboards, exporters, and integrations. Your ops team already knows it. |
| **Added value** | **Real-time operational visibility:** request throughput, p95/p99 latency per detector, error rates, queue depths, memory/CPU usage. Alerts when any detector's latency degrades or error rate spikes. |

### Component: Security Dashboard (Streamlit)

| | Detail |
|:--|:-------|
| **Tool** | **Streamlit** (Python web app framework) |
| **Why Streamlit?** | Build interactive dashboards in pure Python — no frontend skills needed. Since the entire pipeline is Python, the dashboard can directly query the same PostgreSQL database and render charts with Plotly. |
| **Why not Grafana for security dashboards too?** | Grafana excels at time-series metrics but is limited for **custom interactive analysis** — filtering by attack type, drilling into specific users, replaying flagged conversations. Streamlit handles these interactive workflows naturally. |
| **Added value** | **Security-specific insights:** attack trend heatmaps, threat category breakdowns, top targeted users, detector accuracy metrics, compliance status reports. Designed for the security team, not the ops team. |

---

## 8. 🗄️ Data Layer

### Component: Redis

| | Detail |
|:--|:-------|
| **Tool** | **Redis 7+** (in-memory data store) |
| **Why Redis?** | Sub-millisecond read/write. Rate limiting requires checking and incrementing counters on every single request — any database with disk I/O is too slow. |
| **Used for** | Rate limit counters, session state, behavioral analysis real-time signals, temporary IP/user block lists, feature flags |
| **Added value** | **Real-time state** that enables instant blocking. When behavioral analysis detects an active attack, it writes to Redis and the next request from that user is blocked within milliseconds. |

### Component: PostgreSQL

| | Detail |
|:--|:-------|
| **Tool** | **PostgreSQL 16** + **TimescaleDB** (time-series) + **JSONB** columns |
| **Why PostgreSQL over MongoDB?** | Security events have relational structure (users → sessions → requests → events). JSONB gives you document flexibility where needed (detector outputs vary in structure), while joins and transactions keep data consistent. |
| **Why TimescaleDB?** | Security events are inherently time-series. TimescaleDB gives automatic time-based partitioning, compression (10-20x), and continuous aggregates — "blocked requests per hour for the last 30 days" runs in milliseconds. |
| **Added value** | **Single source of truth** for audit, compliance, and retraining. All security events, feedback data, and policy configurations live here with full ACID guarantees. |

---

## 9. 🔄 Feedback Loop — Human-in-the-Loop

### Component: Human Review Interface

| | Detail |
|:--|:-------|
| **Tool** | **Streamlit** (review dashboard) + **Label Studio** (annotation tool) |
| **Why Label Studio?** | Purpose-built for **data annotation**. Supports custom labeling schemas, multi-annotator workflows, agreement metrics, and export to training formats. It's the industry standard for building ML training datasets from human feedback. |
| **Why Streamlit for the review part?** | Quick triage interface — reviewers see flagged response, context, detector scores, and can approve/reject/correct with one click. More focused than Label Studio's general-purpose interface. |
| **Added value** | **Human oversight at scale.** Not every response goes through human review — only flagged ones (medium-risk) and random samples. This keeps the workload manageable while ensuring quality. |

### Component: Feedback Store

| | Detail |
|:--|:-------|
| **Tool** | **PostgreSQL** + **DVC** (Data Version Control) |
| **Why DVC?** | Training datasets need **versioning** just like code. DVC tracks which data was used to train which model version. If a new model performs worse, you can trace back to the exact dataset and diff it. |
| **Added value** | **Reproducible retraining.** Every model version can be traced to the exact set of human corrections that produced it. Required for auditing and debugging. |

### Component: Threshold Monitor

| | Detail |
|:--|:-------|
| **Tool** | **Celery** (task queue) + **Redis** (broker) + **Cron schedule** |
| **Why Celery?** | Async task execution — the threshold check runs periodically without blocking the main pipeline. When N samples accumulate, it dispatches the fine-tuning job to a GPU worker. |
| **Added value** | **Automated trigger.** No human needs to remember to check if there's enough data for retraining. The system watches and triggers automatically. |

### Component: Fine-tuning Pipeline — Detection Models

> [!IMPORTANT]
> The feedback loop retrains the **security detection classifiers** (DeBERTa, RoBERTa, Isolation Forest), **NOT the LLM itself**. The LLM is either a 3rd-party service (OpenAI) or a large model whose alignment is the provider's job. What you control — and what benefits most from real-world feedback — are your detection models.

| | Detail |
|:--|:-------|
| **Tool** | **Hugging Face Transformers Trainer** + **LoRA/PEFT** (for classifier adapters) + **Weights & Biases** (experiment tracking) + **scikit-learn** (for Isolation Forest refit) |
| **What gets retrained** | **DeBERTa-v3** (prompt injection) — learns from false positives/negatives · **RoBERTa** (jailbreak) — learns new attack patterns · **Isolation Forest** (behavioral analysis) — updated baseline profiles · **Risk score weights** — adjusted based on which detectors over/under-trigger |
| **Why retrain detectors, not the LLM?** | (1) Detectors are small (~350M params) → retrain in **minutes** on a single GPU. (2) Feedback data is "was this correctly classified?" → directly maps to classifier training. (3) A bad detector update can be rolled back **instantly** — a bad LLM fine-tune can degrade all capabilities. (4) Far cheaper and lower risk. |
| **Why LoRA for classifiers?** | Even for smaller models, LoRA reduces training cost further. Freeze the base DeBERTa/RoBERTa weights, only train adapter layers — keeps the model's general text understanding intact while specializing its detection capability. |
| **Why W&B?** | Fine-tuning experiments need detailed tracking: loss curves, precision/recall per attack category, confusion matrices. W&B is the best tool for experiment tracking, even though we use Langfuse for production observability. |
| **The Eval Gate** | After retraining, each updated detector runs against a **held-out benchmark suite** — if precision or recall drops on any attack category, the update is **rejected** and the team is alerted. No automatic deployment of degraded detectors. |
| **Added value** | **Your defenses improve from real-world attacks.** A novel injection that slips through → human catches it → becomes training data → detector learns it → blocks it next time. This creates a **virtuous cycle**: attack → human catch → retrain detector → defend. |

---

## 10. 🎯 Testing & Validation — Giskard & Garak

### Component: Giskard Scan

| | Detail |
|:--|:-------|
| **Tool** | **giskard-scan** (vulnerability scanner) |
| **Why Giskard?** | Pre-built validation suites covering both safety (hallucinations, bias, toxicity) and functional quality. Unlike static fuzzers, Giskard utilizes conversational LLM-as-a-judge patterns to evaluate complex model behaviors. |
| **Added value** | **Shift-left quality & safety testing.** Ideal for CI/CD gates, evaluating if a model change degrades outputs or introduces subtle functional regressions. |

### Component: Giskard Checks

| | Detail |
|:--|:-------|
| **Tool** | **giskard-checks** (evaluation framework) |
| **Why?** | Allows you to write declarative regression tests and behavior checks. You define expected behavior guidelines, and it checks if updates maintain these guidelines. |
| **Added value** | Automated QA. Ensures that prompt tuning or classifier retraining doesn't cause functional drift. |

### Component: Garak Scan

| | Detail |
|:--|:-------|
| **Tool** | **garak** (Generative AI Red-teaming & Assessment Kit) |
| **Why Garak?** | Garak acts as the **Nmap for LLMs**. It has a massive, structured static corpus of pre-built attacks, jailbreaks, prompt injections, and data extraction patterns. It is incredibly fast and comprehensive at finding vulnerability edges. |
| **Added value** | **Automated vulnerability detection.** Instantly tells you if a model is vulnerable to known public attack sets (e.g. DAN roleplay, token smuggling, base64 payloads) without manual scripting. |

### Component: CI/CD Gate

| | Detail |
|:--|:-------|
| **Tool** | **GitHub Actions** + **Giskard / Garak CLIs** |
| **Why?** | Automates regression blocking. Prevents any updates to system prompts, policy rules, or classifier models from going live if they fail safety or quality thresholds. |
| **Added value** | Ensures continuous protection. A developer cannot accidentally weaken security via a bad commit. |

---

## 🛠️ The "Before vs. After Proxy" Demonstration Setup

To showcase the concrete value of your security proxy, use this comparison setup:

1. **Pathway A (Direct Access):** Configure Garak and manual red team attacks directly against the underlying LLM endpoint (e.g., raw OpenAI API or unprotected Ollama instance).
2. **Pathway B (Proxy Protected):** Configure the exact same Garak suites and manual attacks to route through your FastAPI LLM Security Gateway.
3. **Outcome Comparison:** Generate and compare side-by-side reports. Pathway A will show high vulnerability success rates (successful prompt injections, leaked system instructions, raw PII outputs), while Pathway B will showcase 0% vulnerability success, with blocked logs appearing in the Security Dashboard.

---

## Complete Tool Stack Summary

| Category | Tools | Why This Combination |
|:---------|:------|:---------------------|
| **API Framework** | FastAPI, Uvicorn, Pydantic | Async Python with native validation |
| **ML Models** | DeBERTa-v3, RoBERTa, sentence-transformers | Best-in-class text classification + semantic understanding |
| **Safety** | Llama Guard 3, Ollama | On-prem content safety, zero data exposure |
| **PII** | Microsoft Presidio, SpaCy NER | Most comprehensive PII coverage available |
| **Runtime Guardrails** | Guardrails AI, RAIL specs | Declarative input/output validation |
| **Behavioral Analysis** | scikit-learn (Isolation Forest), Redis, PostgreSQL | Real-time + historical anomaly detection |
| **LLM Routing** | LiteLLM, Ollama, OpenAI API | Unified interface, privacy-aware routing |
| **Testing** | Giskard (quality/bias), Garak (vulnerabilities), GitHub Actions | Complete shift-left QA & security scanning suite |
| **Observability** | Langfuse, Grafana, Prometheus, Streamlit | LLM-native tracing + infra monitoring + security dashboards |
| **Data** | PostgreSQL + TimescaleDB, Redis | Relational + time-series + real-time cache |
| **Feedback** | Label Studio, Celery, HF PEFT (LoRA), DVC | Human annotation → versioned data → lightweight retraining |
| **Logging** | structlog, PostgreSQL JSONB | Structured, queryable, audit-ready |

