"""
capture_live_screenshots.py
Captures live screenshots with full element rendering from:
- Live Streamlit Dashboard (http://localhost:8501)
- Live FastAPI Swagger UI (http://localhost:8000/docs)
- Live Local LLM Security Gateway Studio (http://localhost:8000/demo)
"""

import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("c:/Users/wiema/OneDrive/Desktop/summer_internship/implementation")
LIVE_DIR = OUTPUT_DIR / "live_screenshots"
ARTIFACT_DIR = Path("C:/Users/wiema/.gemini/antigravity-ide/brain/cc4982b4-a389-42c6-be71-03eb52854207")

LIVE_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def capture_all_live():
    print("Launching Playwright to capture LIVE running servers...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1.5
        )
        page = context.new_page()

        # ---------------------------------------------------------
        # 1. STREAMLIT APP (http://localhost:8501)
        # ---------------------------------------------------------
        print("Navigating to http://localhost:8501 ...")
        page.goto("http://localhost:8501", wait_until="networkidle")
        time.sleep(3.0)

        # Tab 1: Real-time Monitoring
        print("Capturing Tab 1: Real-time Monitoring...")
        page.get_by_text("Real-time Monitoring").first.click()
        time.sleep(2.0)
        p1 = LIVE_DIR / "live_dashboard_executive_metrics.png"
        page.screenshot(path=str(p1), full_page=False)
        shutil.copyfile(str(p1), str(OUTPUT_DIR / "dashboard_executive_metrics.png"))
        shutil.copyfile(str(p1), str(ARTIFACT_DIR / "dashboard_executive_metrics.png"))

        # Tab 2: Event Log & Conversation Replay
        print("Capturing Tab 2: Event Log & Conversation Replay...")
        page.get_by_text("Event Log & Conversation Replay").first.click()
        time.sleep(2.0)
        # Click visible Event #239 text to expand
        ev = page.locator("text=Event #239").first
        if ev.count() > 0:
            ev.click()
            time.sleep(1.5)
        p2 = LIVE_DIR / "live_dashboard_event_replay.png"
        page.screenshot(path=str(p2), full_page=False)
        shutil.copyfile(str(p2), str(OUTPUT_DIR / "dashboard_event_replay.png"))
        shutil.copyfile(str(p2), str(ARTIFACT_DIR / "dashboard_event_replay.png"))

        # Tab 3: Human-in-the-Loop Triage
        print("Capturing Tab 3: Human-in-the-Loop Triage...")
        page.get_by_text("Human-in-the-Loop Triage").first.click()
        time.sleep(2.0)
        # Click visible Event ID #239 text to expand
        tri = page.locator("text=Event ID #239").first
        if tri.count() > 0:
            tri.click()
            time.sleep(2.0)
        p3 = LIVE_DIR / "live_dashboard_hitl_triage.png"
        page.screenshot(path=str(p3), full_page=False)
        shutil.copyfile(str(p3), str(OUTPUT_DIR / "dashboard_hitl_triage.png"))
        shutil.copyfile(str(p3), str(ARTIFACT_DIR / "dashboard_hitl_triage.png"))

        # Tab 4: Red Teaming & Testing
        print("Capturing Tab 4: Red Teaming & Testing...")
        page.get_by_text("Red Teaming & Testing").first.click()
        time.sleep(2.0)
        p4 = LIVE_DIR / "live_dashboard_red_teaming.png"
        page.screenshot(path=str(p4), full_page=False)
        shutil.copyfile(str(p4), str(OUTPUT_DIR / "dashboard_red_teaming.png"))
        shutil.copyfile(str(p4), str(ARTIFACT_DIR / "dashboard_red_teaming.png"))

        # Tab 5: Live Demo Playground
        print("Capturing Tab 5: Live Demo Playground...")
        page.get_by_text("Live Demo Playground").first.click()
        time.sleep(2.0)
        p5 = LIVE_DIR / "live_dashboard_before_after.png"
        page.screenshot(path=str(p5), full_page=False)
        shutil.copyfile(str(p5), str(OUTPUT_DIR / "dashboard_before_after.png"))
        shutil.copyfile(str(p5), str(ARTIFACT_DIR / "dashboard_before_after.png"))

        # ---------------------------------------------------------
        # 2. FASTAPI SWAGGER DOCS (http://localhost:8000/docs)
        # ---------------------------------------------------------
        print("Navigating to http://localhost:8000/docs ...")
        page.goto("http://localhost:8000/docs", wait_until="networkidle")
        time.sleep(2.0)
        try:
            ep = page.locator(".opblock-summary-path").filter(has_text="/v1/chat")
            if ep.count() > 0:
                ep.first.click()
                time.sleep(1.0)
        except Exception as e:
            print("Swagger click error:", e)
        p_sw = LIVE_DIR / "live_swagger_api_endpoints.png"
        page.screenshot(path=str(p_sw), full_page=False)
        shutil.copyfile(str(p_sw), str(OUTPUT_DIR / "swagger_api_endpoints.png"))
        shutil.copyfile(str(p_sw), str(ARTIFACT_DIR / "swagger_api_endpoints.png"))

        # ---------------------------------------------------------
        # 3. CHATGPT DEMO STUDIO (http://localhost:8000/demo)
        # ---------------------------------------------------------
        print("Navigating to http://localhost:8000/demo ...")
        try:
            page.goto("http://localhost:8000/demo", wait_until="networkidle")
            time.sleep(2.0)
            p_demo = LIVE_DIR / "live_chatgpt_demo_ui.png"
            page.screenshot(path=str(p_demo), full_page=False)
        except Exception as e:
            print("Demo UI error:", e)

        browser.close()

    print("All live server screenshots successfully captured!")

if __name__ == "__main__":
    capture_all_live()
