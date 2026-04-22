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

## 3. Account Health Analysis (Loading Performance)
Located on the **System Config** page, this tool tracks how quickly each account loads the Gemini environment.

- **Visual Trends**: Use the **Plot Graph** button to visualize loading speed trends over time. 
- **Identify Bottlenecks**: Significant spikes in loading duration (Health) can indicate network issues or account-specific throttling.
- **Artifact Tracking**: The graph explicitly labels which loading events resulted in successful image downloads, allowing you to correlate performance with output.

---

## 4. Reject Rate Stats Chart
Click the **"📈 Stats Chart"** button to open a visual representation of your performance data.

### Performance Trends
This dialog displays a **Line Chart** summarizing the efficiency of each downloaded image:
- **X-Axis**: Individual filenames (with `.png` extension removed for clarity).
- **Y-Axis**:
    - **Duration (m)**: The total processing time in minutes.
    - **Refused**: The number of times Gemini refused to generate that specific image.
    - **Resets**: The number of times the browser engine had to reset during the generation.

This chart is essential for identifying patterns, such as specific prompts or times of day when Gemini is more likely to refuse requests or when the engine stability fluctuates.

---

## 5. Key Metrics Explained

### Refusals (Gemini Block)
Occurs when Gemini returns a "I can't help with that" or "Safety Policy" response. 
- **The Engine's Response**: GemiPersonaPro automatically detects these, logs the event, and retries until completion or manual intervention.
- **Optimization Tip**: If you see high refusal counts, consider refining your prompt in the **Gemini Setup** page.

### Resets (Engine Recovery)
Occurs when the browser tab hangs, the URL deviates significantly, or the "Generate" button remains missing for too long.
- **The Engine's Response**: The engine performs a hard reset of the tab and re-navigates to your target URL.
- **Optimization Tip**: Ensure you have a stable internet connection and that the target URL is a valid Gemini Gem / App link.

---

## 6. Performance Summary
When automation stops, the dialog displays a final summary:
- **Total Images**: Count of successfully saved assets.
- **Total Time**: Total wall-clock time spent.
- **Avg/Img**: Average time taken to acquire one final image (including all retries).

---

## 7. Background Image Notifier
GemiPersonaPro natively supports a silent **Background Image Notifier** (`image_notifier.py` / `start_notifier.vbs`) that runs as an **independent program** in your Windows System Tray.
- **Independent Operation**: Because it runs entirely independent from the Streamlit UI, **it will continue to operate even after you close the Streamlit browser window**. This is designed so you can step away from the setup page and still receive updates.
- **Function**: It monitors your configured save directory and pops up a native Windows UI notification (including your currently active profile state) whenever new images are successfully downloaded.
- **Enhanced Taskbar UI**: The notifier popup includes interactive buttons:
  - **Open Folder**: Instantly opens the directory where the new images were saved.
  - **Open GemiPersona**: A smart launch button. If the GemiPersona main application or engine is not running, this button is active; clicking it will launch the `run.bat` automatically. If the application is already running, the button will be disabled to prevent duplicate processes.
- **How to Control**: You can toggle the notifier on/off directly from the **Dashboard UI**, using the **Start/Stop Notifier** button on the bottom left. Alternatively, to stop it completely when the UI is closed, look for its blue `GemiPersona Notifier` icon in your Windows right-bottom SystemTray, right-click, and select **"Quit"**.

---
*Stay informed, optimize your prompts.*
