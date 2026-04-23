# 🛠️ System Configuration Guide

The **System Config** page is the central hub for managing the automation engine, task logic, and performance analysis. The interface is organized into five specialized sections via the **System Navigation** sidebar.

---

## 1. Engine Settings
Controls the core behavior of the browser and the file output logic.

### Core Browser Settings
- **Base URL**: The default starting address for the automated browser.
- **Show Console**: Runs the engine service in a visible terminal window for real-time debugging.
- **Headless Mode**: Runs the browser invisibly in the background. Recommended for high-speed automated sessions.
- **Startup Redirect**: Choose which page the UI should load by default upon launch.

### Timing & Watchdog
- **Heartbeat Timeout**: Seconds the engine waits for UI response before auto-shutdown. Set to `0` to keep alive.
- **Watchdog Initial Delay**: Seconds the background Watchdog waits before its first login/status check. Increase if pages load slowly.
- **Quota Cooldown (h/m)**: Set the duration an account is skipped after hitting a quota limit.

### Automation Options
- **Remove AI Watermark**: Automatically attempts to remove Google's SynthID or visual watermarks from generated images.
- **Use GPU Acceleration**: Enables hardware acceleration for smoother browser performance.

### File Output Settings
- **Save Directory**: The absolute path where all generated artifacts are stored.
- **Filename Prefix**: Optional text appended to the start of every saved file.
- **Prefix Padding**: Number of leading zeros for the file sequence (e.g., `padding=3` results in `001.png`).
- **Starting Index**: The number at which the file sequence begins.

---

## 2. Automation Settings
Manages default task parameters and advanced account-switching logic.

### Prompt & Capabilities
- **Default Prompt**: The primary instruction set for the AI.
- **Default Tool**: The tool to be selected upon navigation (e.g., *Create image*).
- **Default Model**: The specific Gemini model version to utilize.

### Automation Goals
- **Auto-Looping Enabled**: Global toggle to start/stop the autonomous cycle.
- **Execution Mode**: Choose between generating a specific number of **images** or completing a set number of **rounds**.
- **Target Goal**: The numerical objective for the current mode.

### Loop Control & Thresholds
Defines the "intelligence" of the account rotation engine:
- **Infinite Loop**: Detects if the engine has been idling for too long and triggers recovery.
- **Time-Based Rotation**: Forces a profile switch or re-login after a set duration.
- **Refusal Threshold**: Automatically switches accounts if Gemini refuses to generate too many times consecutively.
- **Reset Threshold**: Triggers a recovery action (like re-login) if the page crashes or hangs repeatedly.

---

## 3. Account Credentials
Manages Google account rotation and session statistics.
- **Active Account**: Select and lock the current profile used by the engine.
- **Credentials Table**: Edit usernames, toggle bypass status, and monitor real-time session metrics (`Images`, `Refused`, `Resets`).

---

## 4. Quota Full Phrases
A customizable list of phrases used by the engine to detect when an account has reached its daily limit (e.g., *"You've reached your limit"*). Detection triggers an immediate profile switch.

---

## 5. Account Health Analysis
A diagnostic suite for monitoring loading performance and identifying problematic accounts through chronological logs and interactive bar charts.

---
*Tip: Navigation selections and all numerical settings are saved **instantly** to config.json. Numerical thresholds are strictly enforced as integers.*
