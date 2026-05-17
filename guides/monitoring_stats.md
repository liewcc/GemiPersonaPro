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

### Time Threshold Monitor
At the bottom of the dialog, a dedicated status bar tracks the **Time Threshold Elapsed**:
- **Timer Display**: Shows the cumulative active time for the current account (e.g., `12:45 / 30m`).
- **Manual Reset (🔄)**: A dedicated button to manually reset the Time Threshold timer to zero without switching accounts. This is useful if you want to give the current account "extra time" without interrupting the session.

---

## 3. Account Health Analysis
Located on the dedicated **Account Health** page, this tool provides a powerful diagnostic suite to visualize the performance and stability of your account rotation.

### Interactive Performance Graphs
Toggle **Plot Performance Graph** to access modular analysis containers:

- **Round Duration (Bar Chart)**:
    - **Purpose**: Tracks the time consumed by each automation round.
    - **Y-Axis**: Duration in **minutes**. 
    - **Session Grouping**: Uses alternating colors (Base/Light) to visually separate distinct automation sessions.
    - **Linear/Logarithmic Toggle**: Switch scales to visualize both large duration spikes and subtle timing variations.
- **Retry Analysis (Line Chart)**:
    - **Purpose**: Observes the number of "Refused" and "Reset" events encountered for each successful image download.
    - **Interpretation**: A high count of retries for a single image suggests the account is heavily filtered or the prompt is problematic.
    - **Success Correlation**: The X-Axis maps directly to successful image filenames, allowing you to identify which assets were the hardest to acquire.

### Advanced Layout & Controls
- **Modular Containers**: Graph modes and Y-Axis scales are organized into bordered containers for a clean, professional interface.
- **View Modes**: Choose between **Full Loading History**, **Detailed History (Active Account)**, or a **Latest Summary** table for all accounts.
- **Auto-Refresh**: Enable to keep the charts synced with `engine.log` every 5 seconds.

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
*Stay informed, optimize your prompts.*
