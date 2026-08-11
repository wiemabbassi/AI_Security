@echo off
TITLE LLM Security Gateway Launcher

echo ================================================================================
echo 🚀 Starting LLM Security Gateway Suite
echo ================================================================================

echo 1. Starting Ollama LLM Server...
start "Ollama Server" cmd /k "ollama serve"

echo 2. Starting FastAPI Gateway Server (Port 8000)...
start "FastAPI Gateway" cmd /k "uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo 3. Starting Streamlit Operations Dashboard (Port 8501)...
start "Streamlit Dashboard" cmd /k "streamlit run dashboard/app.py --server.port 8501"

echo ================================================================================
echo ✅ All services launched in background windows!
echo - Gateway API  : http://localhost:8000
echo - API Docs     : http://localhost:8000/docs
echo - Dashboard UI : http://localhost:8501
echo ================================================================================
pause
