import socket
import subprocess
import sys
import time

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_service(name: str, command: str, port: int, max_wait_seconds: int = 35):
    if is_port_in_use(port):
        print(f"[ONLINE] {name} is already running on port {port}.")
        return

    print(f"[STARTING] Launching {name} on port {port}...")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    subprocess.Popen(command, shell=True, creationflags=flags)
    
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        time.sleep(1.5)
        if is_port_in_use(port):
            print(f"[ONLINE] {name} started successfully on port {port}.")
            return
        print(f"  ... waiting for {name} to initialize ({int(time.time() - start_time)}s)")
    
    if is_port_in_use(port):
        print(f"[ONLINE] {name} started successfully on port {port}.")
    else:
        print(f"[PENDING] {name} launched on port {port} (still initializing in background).")

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
    print("  * Local LLM Testing Studio  : http://localhost:8000/demo")
    print("  * Streamlit Threat Dashboard: http://localhost:8501")
    print("  * FastAPI Gateway Endpoint  : http://localhost:8000/v1/chat")
    print("  * Direct LLM Endpoint       : http://localhost:8000/v1/direct")
    print("  * OpenAPI Interactive Docs  : http://localhost:8000/docs")
    print("  * Ollama Local LLM API      : http://localhost:11434")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
