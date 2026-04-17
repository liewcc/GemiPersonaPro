# 🆕 Latest Updates & Features

Welcome to the latest release notes for **GemiPersonaPro**. This document outlines the most recent improvements, bug fixes, and new features added to the system.

## 🚀 Recent Features & Enhancements

### 1. Dynamic Prompt Reload Logic
The automation engine now supports dynamically reloading prompts without interrupting the ongoing session. 
- When you click **"Load"** or **"Save"** in the Gemini Setup dashboard during an active automation cycle, the engine will safely request a new chat (`request_new_chat` endpoint) at the start of the next loop.
- This ensures the system utilizes the most up-to-date prompts immediately, eliminating the need to stop and restart the automation.

### 2. Formatted Prompt Metadata Text
- Added improvements to text-processing when pasting text copied from the dashboard's Image Metadata into the Gemini setup prompt input. The system now automatically converts `\n\n` sequences into proper paragraph breaks, retaining the intended formatting and structure.

### 3. Configurable Watchdog Delay
- Introduced a configurable Watchdog delay to improve automation stability. This helps manage the timing of automated tasks and prevents premature timeouts.

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
