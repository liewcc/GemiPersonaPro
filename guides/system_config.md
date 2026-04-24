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
- **Aspect Ratio Setting**:
    - **Mode Selection**: Choose between **Fixed Aspect Ratio** (static) and **Dynamic Ratio Loop** (automated sequence).
    - **Fixed Ratio**: Uses a single selected ratio. UI locks during active generation but syncs from disk before each cycle.
    - **Dynamic Loop**: Automatically cycles through the checked items in the ratio list.
    - **Progress Persistence**: Generation counts (Count) are **NEVER** automatically reset. Progress is preserved even when switching modes or restarting. Manual reset via the **Reset Progress** button is required.
    - **Real-time Sync**: The engine performs a fresh config read from disk at the start of every image generation cycle.


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
A powerful diagnostic suite that parses `engine.log` to visualize the performance and "health" of your account rotation. It helps identify problematic accounts that trigger frequent refusals or page resets.

### View Modes
- **Full Loading History (All Events)**: A chronological audit trail of every loading attempt across all accounts. Best for system-wide stability monitoring.
- **Detailed History: Active Account**: Filters the data to show only events for the currently active profile. Useful for deep-diving into a single account's behavior.
- **Latest Summary (All Accounts)**: A high-level overview showing the most recent loading status and duration for every account in the system.

### Performance Visualizations
Toggle **Plot Performance Graph** to access interactive Altair charts:
- **Loading Duration (Bar Chart)**:
    - **Y-Axis**: Duration in **minutes (minite)**.
    - **Colors**: **Green** (Success), **Purple/Blue** (Reject), **Orange** (Reset), **Light Red** (Fail).
    - **Session Banding**: The chart uses alternating Base/Light colors for the background/bars to visually group events by account session, making it easy to see where account switches occurred.
- **Reject Rates (Line Chart)**:
    - **X-Axis**: Successful image downloads.
    - **Y-Axis**: Cumulative count of Refusals or Resets encountered *before* that success.
    - **Purpose**: A rising trend line indicates that an account is becoming "tired" or heavily filtered, suggesting it may need a longer cooldown.

### Status Indicators
- **Success**: The AI responded and a file was successfully saved.
- **Reject**: The AI refused the prompt (safety filter). Now captured as individual, non-cumulative segments in the duration chart.
- **Reset**: The page failed or was refreshed.
- **Fail**: A success event was detected but the filename was missing.

### Physical Breakpoint Logic (New)
The parser now uses a robust state-tracking mechanism:
- **Session End**: Detected by `Automation Finished.` or manual stop signals.
- **Identity Lock**: Triggered by `Profile switched to <username>`. This forces the current account ID for all subsequent events until the next breakpoint.
- **Orphan Recovery**: The system captures `Saved:` events even if the initial `Loading` marker was missed (e.g., after a manual continue).

---

## 6. Automation Cycle Management
A utility designed to audit and maintain the `engine.log` file by identifying and managing historical automation sessions.

### Cycle Identification
- **Log Parsing**: Automatically scans the system log to identify unique automation "Cycles" (defined from a fresh start of Round 1 until a stop signal).
- **Continue Session Grouping**: Intelligent logic ensures that "Continue Session" events are correctly attributed to their original parent cycle, rather than appearing as fragmented entries.

### Log Maintenance & Decluttering
- **Data Selection**: Provides an interactive table listing every identified cycle with its Start Time and total Log Lines.
- **Selective Deletion**: Users can check specific historical cycles for removal. This permanently deletes the associated lines from `engine.log`.
- **Performance Optimization**: Use this tool to remove "stale" or "failed" early test data, preventing it from cluttering the performance charts in **Account Health Analysis** and reducing overall log file size.

---
*Tip: If an account shows a consistent "Reject" pattern in the graphs, consider adding more variation to your prompt or increasing the **Quota Cooldown** hours in Engine Settings.*

