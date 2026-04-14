# 🛠️ System Configuration Guide

The **System Config** page is the central hub for managing the automation engine, account rotation rules, and performance history.

---

## 1. Engine Settings
These settings control the behavior of the background browser process.

- **Show Engine Console Window**: If enabled (default: True), the engine service runs in a visible terminal window. This is useful for real-time debugging.
- **Run Browser Headless**: If enabled (default: False), the automated browser will run invisibly in the background. High-speed generation is best performed in this mode.
- **Heartbeat Timeout**: The duration (in seconds) the engine will wait for a response from the UI before auto-shutting down to save resources. Set to `0` to keep the engine alive indefinitely.
- **Watchdog Initial Delay**: The duration (in seconds) the background Watchdog waits after automation starts before running its first session/login check. Increase this (e.g., to 20 or 30 seconds) if your Gem URLs or models take a long time to load, preventing the Watchdog from falsely detecting a "Guest" status during the initial page transition.
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

### 🔒 Save & 🔄 Reload
- **Save Credentials Table**: Commits all manual changes (Bypass, Auto Delete settings, etc.) to `user_login_lookup.json`.
- **Reload Credentials Table**: Discards unsaved changes and pulls the freshest data from disk.

### 🧹 Cleaning Tools
- **Clear Quota Full Recorded Date**: Resets all "Quota Full At" timestamps to empty, allowing accounts to enter the rotation again if they were previously blocked.
- **Reset Session Stats**: Wipes all historical session data (`Switched At`, `Images`, `Refused`, `Resets`) for all accounts to start tracking with a clean slate.

---
*Tip: Always click **Save Credentials Table** after editing usernames or toggling Bypass settings to ensure the background engine sees the updates.*
