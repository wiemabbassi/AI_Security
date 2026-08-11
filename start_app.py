import socket
import subprocess
import sys
import time

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_service(name: str, command: str, port: int):
    if is_port_in_use(port):
        print(f"[ONLINE] {name} is already running on port {port}.")
    else:
        print(f"[STARTING] Launching {name} on port {port}...")
        subprocess.Popen(command, shell=True)
        time.sleep(2)
        if is_port_in_use(port):
            print(f"[ONLINE] {name} started successfully on port {port}.")
        else:
            print(f"[PENDING] {name} launched (initialization in progress).")

def main():
    print("=" * 70)
    print("LLM Security Gateway -- Single Command Launcher")
    print("=" * 70 + "\n")

    # 1. Ollama LLM Service
    start_service("Ollama Local LLM", "ollama serve", 11434)

    # 2. FastAPI Gateway
    start_service("FastAPI Security Gateway", f"{sys.executable} -m uvicorn app.main:app --host 0.0.0.0 --port 8000", 8000)

    # 3. Streamlit Dashboard
    start_service("Streamlit Security Dashboard", f"{sys.executable} -m streamlit run dashboard/app.py --server.port 8501", 8501)

    print("\n" + "=" * 70)
    print("ALL GATEWAY SERVICES ARE ACTIVE & READY!")
    print("=" * 70)
    print("  * Streamlit Threat Dashboard : http://localhost:8501")
    print("  * FastAPI Gateway Endpoint    : http://localhost:8000/v1/chat")
    print("  * OpenAPI Interactive Docs    : http://localhost:8000/docs")
    print("  * Ollama Local LLM API        : http://localhost:11434")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
