# 🛠️ System Configuration Guide

The **System Config** page is the central hub for managing the automation engine, account rotation rules, and performance history.

---

## 1. Engine Settings
These settings control the behavior of the background browser process.

- **Show Engine Console Window**: If enabled (default: True), the engine service runs in a visible terminal window. This is useful for real-time debugging.
- **Run Browser Headless**: If enabled (default: False), the automated browser will run invisibly in the background. High-speed generation is best performed in this mode.
- **Heartbeat Timeout**: The duration (in seconds) the engine will wait for a response from the UI before auto-shutting down to save resources. Set to `0` to keep the engine alive indefinitely.
- **Watchdog Initial Delay**: The duration (in seconds) the background Watchdog waits after automation starts before running its first session/login check. Increase this (e.g., to 20 or 30 seconds) if your Gem URLs or models take a long time to load, preventing the Watchdog from falsely detecting a "Guest" status during the initial page transition.
- **Quota Cooldown (hours)**: When set to a value greater than `0`, the engine calculates an **unlock time** for each account as `quota_full_time + cooldown_hours`. During profile switching, any account whose unlock time has not yet been reached will be **automatically skipped**. For example, if an account hit its quota at midnight and the cooldown is set to `24`, it will be skipped until midnight the following day. Set to `0` (default) to disable this check entirely.
---

## 2. Quota Full Phrases
The engine uses these phrases to detect when an account has reached its generation limit.
- **How it works**: When Gemini outputs text matching any of these phrases (e.g., *"You've reached your limit"*), the engine triggers an automatic profile switch.
- **Customization**: You can add or remove phrases based on the specific language or Gem behavior you are encountering.

---

## 3. User Login Credentials
This table manages your account rotation and tracks individual session performance.

### Column Definitions
| Column | Description |
| :--- | :--- |
| **Active** | Indicates the account currently in use. Only one can be active. |
| **Bypass** | If checked, the automation loop will skip this account. |
| **Username** | The specific Google account/profile identifier. |
| **Auto Delete** | If enabled, the engine will clear browser history/cache upon switching away. |
| **Range** | Time range for history deletion (`Last hour`, `Last day`, `All time`). |
| **Quota Full At** | Timestamp recorded automatically when a "Quota Full" phrase is detected. |
| **Switched At** | Timestamp when this specific account last finished its session. |
| **Images** | Total successful downloads during the last session. |
| **Refused** | Count of Gemini refusals encountered during the last session. |
| **Resets** | Count of engine recoveries/resets triggered during the last session. |

---

## 4. Management Buttons

### 🔒 Account Activation & 🔄 Reload
- **Set Active Account**: Commits the currently selected username from the dropdown as the "Active" account for the engine.
- **Reload Credentials Table**: Pulls the freshest data from disk to ensure the UI is perfectly synced with the underlying JSON.

### ⚡ Batch Actions
- Use the **Batch Action** buttons (All Bypass, Clear Bypass, etc.) to instantly apply settings to every account in your list simultaneously.

### 🧹 Cleaning Tools
- **Clear Quota Full Recorded Date**: Resets all "Quota Full At" timestamps to empty, allowing accounts to enter the rotation again if they were previously blocked.
- **Reset Session Stats**: Wipes all historical session data (`Switched At`, `Images`, `Refused`, `Resets`) for all accounts to start tracking with a clean slate.

---

## 5. Account Health Analysis
A specialized diagnostic tool for monitoring **Nano Banana 2** loading performance across different accounts.

- **Full Loading History (All Events)**: Aggregates every recorded loading event from `engine.log` into a single chronological view. Useful for auditing system-wide stability.
- **Latest Summary**: Shows the most recent loading performance (Health/Duration) for each unique account found in the logs.
- **Detailed History**: Allows you to drill down into a specific account's historical performance.
- **Performance Graph**:
    - Toggle **Plot Graph** to see a bar chart of loading durations.
    - **Success (Green)**: Indicates images were successfully downloaded during that load.
    - **Normal (Purple)**: Indicates a standard successful load without an immediate download.
    - **Tooltips**: Hover over any bar to see the exact timestamp, account, and the specific **Artifact** (filename) downloaded.

---
*Tip: Credential edits (usernames, bypass, stats) are now saved **instantly** to disk. Use the **Set Active Account** button only when you want to change which profile the engine is currently using.*
