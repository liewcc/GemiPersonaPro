# 🆕 Latest Updates & Features

Welcome to the latest release notes for **GemiPersonaPro**. This document outlines the most recent improvements, bug fixes, and new features added to the system.

## 🚀 Recent Features & Enhancements

### 1. Quota Cooldown — Automatic Account Lock After Quota Hit
Accounts can now be automatically held out of the rotation for a configurable period after hitting their daily quota.
- A new **Quota Cooldown (hours)** setting has been added to the **ENGINE SETTINGS** panel on the System Config page (default: **24 hours**).
- When set to a value greater than `0`, the engine computes an **unlock time** for each account: `unlock_time = quota_full_time + cooldown_hours`.
- During every profile switch, any account whose unlock time has not yet been reached is **automatically skipped**, preventing the engine from wasting a session on an account that is still locked.
- The engine log will display the exact unlock timestamp and minutes remaining, e.g.: `API>> Skipping 'user@gmail.com' (Quota locked until 21/04 00:00, 180 min remaining).`
- Set the value to `0` to disable the feature entirely and restore the original behavior.

### 2. Dynamic Prompt Reload Logic
The automation engine now supports dynamically reloading prompts without interrupting the ongoing session. 
- When you click **"Load"** or **"Save"** in the Gemini Setup dashboard during an active automation cycle, the engine will safely request a new chat (`request_new_chat` endpoint) at the start of the next loop.
- This ensures the system utilizes the most up-to-date prompts immediately, eliminating the need to stop and restart the automation.

### 2. Formatted Prompt Metadata Text
- Added improvements to text-processing when pasting text copied from the dashboard's Image Metadata into the Gemini setup prompt input. The system now automatically converts `\n\n` sequences into proper paragraph breaks, retaining the intended formatting and structure.

### 3. Configurable Watchdog Delay
- Introduced a configurable Watchdog delay to improve automation stability. This helps manage the timing of automated tasks and prevents premature timeouts.

### 4. Resequence & Export Assets
- Introduced a **Resequence Files** utility in the Asset Sanitizer's batch processing options.
- This non-destructive feature allows users to safely copy and rename a sequence of images into a new sibling folder, sequentially numbered starting from 1 (with automatic zero-padding detection based on the original filenames).
- Any corresponding AI-cleaned images in the `processed/` subfolder are automatically synchronized and re-numbered to match the new naming scheme.

### 5. Enhanced Duration Formatting in Reject Rate Stats
- Updated the duration display in the **Reject Rate Stats** dialog to a more readable `H:MM:SS` format.
- Durations under 1 minute display as seconds (e.g., `42s`).
- Durations between 1 minute and 1 hour display as `M:SS` (e.g., `3:05`).
- Durations over 1 hour display as `H:MM:SS` (e.g., `1:03:07`).
- This update applies to the live elapsed timer, total session time, average time per image, and individual record durations.

### 6. Fully Real-Time Editable Login Credentials & Batch Actions
- The entire **User Login Credentials** table now saves instantly upon editing any field (including usernames, delete ranges, and session statistics). This provides greater manual control and improved workflow efficiency.
- The manual "Save Credentials Table" button has been repurposed as **"Set Active Account"** and moved next to the account dropdown, strictly for explicitly setting the active profile.
- Added four new **Batch Action** buttons beneath the table to instantly Select All or Clear All for `Bypass` and `Auto Delete` across all accounts.

### 7. Atomic Configuration Persistence
- Implemented a robust "atomic write" mechanism for the `user_login_lookup.json` file.
- The system now writes to a temporary file before performing an atomic replacement, ensuring that the background automation engine never reads a partially-written or corrupted configuration file during a UI save operation.

## 🐛 Critical Bug Fixes

### 1. Fixed Duplicate Image Downloads (Race Condition)
- Resolved a critical bug where the automation engine would perform redundant image downloads. By ensuring atomic task handling and stabilizing the redo-response logic, the system no longer incorrectly detects and processes stale browser states.

### 2. Corrected Login Timestamps
- Fixed an issue where the system incorrectly recorded timestamps in the `USER LOGIN CREDENTIALS` log when a re-login was triggered by a modified `refused_threshold`. Login timestamp updates now strictly occur only when a legitimate profile switch is initiated.

### 3. Fixed Profile Switching & Quota Full Errors
- **Quota Full Timestamp**: Updated the `quota_full` timestamp formatting to include seconds, ensuring more precise tracking and fixing profile switch failures.
- **Manual Switching Logic**: Modified the `perform_switch_logic` to ensure the traversal limit only applies during automated sessions. Manual profile switches from the dashboard are no longer incorrectly blocked by the automation's "quota full" anchor logic.

### 4. Browser Minimization Logic
- Investigated and fixed the "headed fallback" mechanism. The browser now correctly remains minimized during fallback operations when login verification fails in headless mode.

### 5. Accurate Reject Rate Statistics
- Resolved data inconsistency in `reject_stat_log.json` where session interruptions were being misreported as image downloads.
- The automation manager's cleanup logic now correctly stops logging `[Stopped/Interrupted]` entries, ensuring that refused and reset counts are accurately attributed without double-counting.

### 6. Suppressed Streamlit Fragment Warning
- Added a logging filter in the application entry point (`start.py`) to suppress the benign but noisy "fragment does not exist anymore" warning.
- This warning naturally occurs during full-app reruns when periodic `@st.fragment` components are destroyed before their timers fire.

### 7. Precise Reject Rate Duration Tracking & UI Stabilization
- **Fixed "Processing..." Duration Offset**: Resolved an issue where the live "Processing..." duration would reset or start with a 2-minute offset. The system now uses raw float timestamps (	ime.time()) passed directly from the engine to ensure 100% accuracy and consistency with completed records.
- **Refinement Phase Monitoring**: The dashboard now distinguishes between the **Image Generation** phase ("Processing...") and the **Watermark Removal** phase ("Refining Image..."), tracking the time spent in each independently.
- **Stats Cache & UI Stability**: Implemented a caching mechanism for automation stats. This prevents the "Summary" table header from flashing momentarily when the API times out during heavy CPU-bound watermark processing (LaMa), ensuring a smooth, persistent monitoring experience.

### 8. Dashboard Gallery Concurrency Handling
- Fixed a crash (`UnidentifiedImageError`) in the Dashboard gallery fragment that occurred when the system attempted to display an image while it was still being written to disk by the automation engine.
- The gallery now gracefully handles partially-written files by displaying a "⏳ Loading..." status, preventing the UI from crashing and ensuring a more resilient monitoring experience.

### 9. Reject Rate Stats Visual Chart
- Added a new **📈 Stats Chart** button to the Dashboard main panel.
- This feature provides a visual breakdown of automation efficiency using a multi-metric line chart.
- It tracks **Duration (in minutes)**, **Refusals**, and **Resets** per file, with filenames automatically cleaned (removing `.png` suffixes) for better readability on the X-axis.
- This visualization helps users quickly identify performance bottlenecks or problematic prompts in long automation sessions.

