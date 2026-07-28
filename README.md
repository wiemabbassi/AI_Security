# 🔐 LLM Security Gateway — Complete Implementation

Production-grade, asynchronous LLM Security Gateway implementing multi-layered prompt injection detection, jailbreak prevention, bi-directional PII masking, local Llama Guard safety classification, behavioral anomaly detection, and operational observability.

---

## 🏗️ Architecture Overview

```
Client App
   │
   ▼ POST /v1/chat
1. API Gateway & Token Bucket Rate Limiter (Redis)
   │
   ▼
2. Input Security Pipeline
   ├── Normalization (unicodedata + ftfy)
   ├── Prompt Injection Detector (DeBERTa-v3 + Regex + Heuristics)
   ├── Jailbreak Detector (RoBERTa + Multi-turn context)
   ├── PII Masker (Presidio + SpaCy NER)
   ├── Llama Guard 3 (Ollama local inference)
   └── Guardrails AI Input Validator
   │
   ▼
3. Risk & Policy Engine
   ├── Risk Scoring Engine (NumPy weighted aggregation)
   ├── Behavioral Analysis (Isolation Forest anomaly model)
   ├── Policy Engine (YAML Policy-as-code)
   └── Structured Audit Logger (structlog + TimescaleDB)
   │
   ▼
4. LLM Backend (Ollama local model runtime / Fallback)
   │
   ▼
5. Output Security Pipeline
   ├── Output PII Scanner (Presidio)
   ├── Data Leak Detector (sentence-transformers)
   ├── Llama Guard Output Safety Check
   └── Guardrails AI Output Validator & PII Restorer
   │
   ▼
Sanitized Response → Client App
```

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run API Gateway
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Launch Operations Dashboard
```bash
streamlit run dashboard/app.py
```
Dashboard: [http://localhost:8501](http://localhost:8501)

### 4. Run Test Suite & Red Teaming Verification
```bash
pytest tests/ -v
```

---

## 📄 License
MIT License
