# 📊 Monitoring & Statistics Guide

GemiPersonaPro provides detailed, real-time tracking of your automation efficiency. This is critical for understanding how Gemini interacts with your prompts and how the engine recovers from errors.

---

## 1. Dashboard Status Bar
Located at the top of the **Dashboard** main panel, this bar provides high-level metrics for the current session:
- **● RUNNING / ○ IDLE**: Current engine state.
- **Cycles**: Total number of automated loops completed.
- **Images**: Successfully downloaded and processed images.
- **Refused**: Times Gemini refused to generate content (e.g., safety filters).
- **Resets**: Times the browser engine had to refresh or recover from a freeze.

---

## 2. Reject Rate Stats Dialog
Click the **"📊 Reject Rate Stats"** button to open a detailed breakdown.

### Live Tracking (Real-time)
If automation is running, this dialog **auto-refreshes every 1 second**. It shows:
- **⌛ Processing Entry**: A live row tracking the current active generation, showing how many times Gemini has refused the current prompt and how long it has been running.
- **Historical Table**: A reverse-chronological list of completed downloads with their specific duration and individual count of refusals/resets.

---

## 3. Key Metrics Explained

### Refusals (Gemini Block)
Occurs when Gemini returns a "I can't help with that" or "Safety Policy" response. 
- **The Engine's Response**: GemiPersonaPro automatically detects these, logs the event, and retries until completion or manual intervention.
- **Optimization Tip**: If you see high refusal counts, consider refining your prompt in the **Gemini Setup** page.

### Resets (Engine Recovery)
Occurs when the browser tab hangs, the URL deviates significantly, or the "Generate" button remains missing for too long.
- **The Engine's Response**: The engine performs a hard reset of the tab and re-navigates to your target URL.
- **Optimization Tip**: Ensure you have a stable internet connection and that the target URL is a valid Gemini Gem / App link.

---

## 4. Performance Summary
When automation stops, the dialog displays a final summary:
- **Total Images**: Count of successfully saved assets.
- **Total Time**: Total wall-clock time spent.
- **Avg/Img**: Average time taken to acquire one final image (including all retries).

---

## 5. Background Image Notifier
GemiPersonaPro natively supports a silent **Background Image Notifier** (`image_notifier.py` / `start_notifier.vbs`) that runs as an **independent program** in your Windows System Tray.
- **Independent Operation**: Because it runs entirely independent from the Streamlit UI, **it will continue to operate even after you close the Streamlit browser window**. This is designed so you can step away from the setup page and still receive updates.
- **Function**: It monitors your configured save directory and pops up a native Windows UI notification (including your currently active profile state) whenever new images are successfully downloaded.
- **Enhanced Taskbar UI**: The notifier popup includes interactive buttons:
  - **Open Folder**: Instantly opens the directory where the new images were saved.
  - **Open GemiPersona**: A smart launch button. If the GemiPersona main application or engine is not running, this button is active; clicking it will launch the `run.bat` automatically. If the application is already running, the button will be disabled to prevent duplicate processes.
- **How to Control**: You can toggle the notifier on/off directly from the **Dashboard UI**, using the **Start/Stop Notifier** button on the bottom left. Alternatively, to stop it completely when the UI is closed, look for its blue `GemiPersona Notifier` icon in your Windows right-bottom SystemTray, right-click, and select **"Quit"**.

---
*Stay informed, optimize your prompts.*
