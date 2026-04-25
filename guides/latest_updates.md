# 🆕 Latest Updates & Features

Welcome to the latest release notes for **GemiPersonaPro**. This document outlines the most recent improvements, bug fixes, and new features added to the system.

## 🚀 Recent Features & Enhancements

### Update: 2026-04-25 - Modular Architecture & Log Consistency
- **Module Decoupling**: Extracted the Account Health Analysis and Automation Cycle Management features from the monolithic System Config page into a dedicated standalone page (`04_account_health.py`). This massive reduction in script complexity eliminates the "Loading Duration" instability and data disappearance bugs during view-mode switches.
- **Log Parsing Engine**: Migrated the complex `engine.log` parsing algorithms into an independent backend utility (`health_parser.py`) to improve data throughput and isolate logic from UI rendering.
- **Chart Optimization**: Refactored Altair visualization code to deduplicate rendering logic via unified helper functions, significantly boosting performance.
- **Clear Log Consistency**: Fixed a critical bug in the "Clear Engine Log" function from Gemini Setup. The physical log truncation now correctly writes a standardized JSON `LOG_CLEARED` event, preventing the health parser from misinterpreting legacy text markers as active sessions.
- **Navigation Update**: Renamed the System Configuration module to `05_System_Config.py` to accommodate the new Account Health page sequence in the sidebar.

### Update: 2026-04-25 - UI Polish & Noise Reduction
- **Aspect Ratio Dialog**: Removed the redundant `st.success("Setting saved!")` alert that appeared after saving the Aspect Ratio Looping Table. The dialog now closes instantly via `st.rerun()` without displaying an intermediate confirmation banner.
- **Aspect Ratio Data Sync**: Fixed an issue where the Aspect Ratio Looping Table and System Config aspect ratio settings loaded stale data. The UI now intelligently flushes initialization states during cross-page navigation and dialog invocations to ensure it always reads the latest configuration from disk.
- **Persistent Dialogs**: Modified the "Reset Counting" button logic in the Aspect Ratio Looping Table to instantly apply the counter reset and visibly update the grid without forcing the dialog to close.

### Update: 2026-04-24 - Aspect Ratio Stability & Health Parsing Refactor
- **Engine Sync**: Implemented mandatory disk-sync for the automation engine before each cycle, ensuring UI settings take effect immediately.
- **Health Analysis v2**:
    - **Physical Breakpoints**: Implemented session-boundary tracking using physical log markers (`Automation Finished.`, `Profile switched to`).
    - **Orphan Record Recovery**: Now captures successful image saves even when initial loading markers are missing due to manual interventions.
    - **Refinement Duration Fix**: Resolved the "staircase effect" in Reject/Reset timing, ensuring each failure measures its own independent segment.
- **Aspect Ratio Control**:
    - **Progress Persistence**: Ensured generation counts are preserved across mode toggles and session restarts.
    - **Interactive Loop Table**: Enabled real-time editing and "Force Start" functionality in the Dynamic Ratio Loop.

### 1. Continue Session (Resume Automation)
- Added a highly requested **⏯️ Continue Session** functionality to both the Dashboard and Gemini Setup pages.
- Allows users to pause an active automation loop and subsequently resume it without wiping the current session's Reject Rate statistics or counter metrics.
- Features a robust **State Hydration** mechanism: if the application or backend engine is restarted while a session is paused, the engine will automatically parse the `reject_stat_log.json` to seamlessly rebuild the previous metrics (Successes, Refusals, Resets) directly into memory upon clicking Continue.
- Implements strict **Goal Protection**: attempting to continue a session that has already reached its configured image/round target will automatically trigger an alert dialog, preventing accidental data pollution or instant-stop loops.
- **UI Stabilization**: Refactored the control layout across both pages. The `Start / Stop` buttons now swap seamlessly in place, while the `Continue` button securely occupies the adjacent column, ensuring absolute layout stability and zero button-jumping during active automation.

### 2. Interactive Wheel-Zoom for Dashboard Reject Rate Chart
- Upgraded the Dashboard's **📈 Reject Rate Chart** to support smooth, mouse-wheel-based zooming and horizontal panning.
- Migrated the X-axis from a string-based (Nominal) scale to a sequential quantitative scale (`order_index:Q`). This enables Altair's native interactive zooming capabilities, which are otherwise limited for nominal axes.
- **Improved UX**: The chart now supports `bind_y=False`, allowing users to zoom and pan specifically along the timeline (X-axis) while keeping the metric values (Y-axis) stable and visible. This makes it significantly easier to analyze long automation sessions with dozens of processed images.
- **Contextual Clarity**: Filenames remain clearly visible in the interactive tooltips, ensuring that per-image performance data is always accessible even when zoomed in.


### 2. Quota Cooldown — Automatic Account Lock After Quota Hit
Accounts can now be automatically held out of the rotation for a configurable period after hitting their daily quota.
- A new **Quota Cooldown (hours)** setting has been added to the **ENGINE SETTINGS** panel on the System Config page (default: **24 hours**).
- When set to a value greater than `0`, the engine computes an **unlock time** for each account: `unlock_time = quota_full_time + cooldown_hours`.
- During every profile switch, any account whose unlock time has not yet been reached is **automatically skipped**, preventing the engine from wasting a session on an account that is still locked.
- The engine log will display the exact unlock timestamp and minutes remaining, e.g.: `API>> Skipping 'user@gmail.com' (Quota locked until 21/04 00:00, 180 min remaining).`
- Set the value to `0` to disable the feature entirely and restore the original behavior.

### 3. Dynamic Prompt Reload Logic
The automation engine now supports dynamically reloading prompts without interrupting the ongoing session. 
- When you click **"Load"** or **"Save"** in the Gemini Setup dashboard during an active automation cycle, the engine will safely request a new chat (`request_new_chat` endpoint) at the start of the next loop.
- This ensures the system utilizes the most up-to-date prompts immediately, eliminating the need to stop and restart the automation.

### 4. Formatted Prompt Metadata Text
- Added improvements to text-processing when pasting text copied from the dashboard's Image Metadata into the Gemini setup prompt input. The system now automatically converts `\n\n` sequences into proper paragraph breaks, retaining the intended formatting and structure.

### 5. Configurable Watchdog Delay
- Introduced a configurable Watchdog delay to improve automation stability. This helps manage the timing of automated tasks and prevents premature timeouts.

### 6. Resequence & Export Assets
- Introduced a **Resequence Files** utility in the Asset Sanitizer's batch processing options.
- This non-destructive feature allows users to safely copy and rename a sequence of images into a new sibling folder, sequentially numbered starting from 1 (with automatic zero-padding detection based on the original filenames).
- Any corresponding AI-cleaned images in the `processed/` subfolder are automatically synchronized and re-numbered to match the new naming scheme.

### 7. Enhanced Duration Formatting in Reject Rate Stats
- Updated the duration display in the **Reject Rate Stats** dialog to a more readable `H:MM:SS` format.
- Durations under 1 minute display as seconds (e.g., `42s`).
- Durations between 1 minute and 1 hour display as `M:SS` (e.g., `3:05`).
- Durations over 1 hour display as `H:MM:SS` (e.g., `1:03:07`).
- This update applies to the live elapsed timer, total session time, average time per image, and individual record durations.

### 8. Fully Real-Time Editable Login Credentials & Batch Actions
- The entire **User Login Credentials** table now saves instantly upon editing any field (including usernames, delete ranges, and session statistics). This provides greater manual control and improved workflow efficiency.
- The manual "Save Credentials Table" button has been repurposed as **"Set Active Account"** and moved next to the account dropdown, strictly for explicitly setting the active profile.
- Added four new **Batch Action** buttons beneath the table to instantly Select All or Clear All for `Bypass` and `Auto Delete` across all accounts.

### 9. Atomic Configuration Persistence
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
- **Fixed "Processing..." Duration Offset**: Resolved an issue where the live "Processing..." duration would reset or start with a 2-minute offset. The system now uses raw float timestamps (`time.time()`) passed directly from the engine to ensure 100% accuracy and consistency with completed records.
- **Refinement Phase Monitoring**: The dashboard now distinguishes between the **Image Generation** phase ("Processing...") and the **Watermark Removal** phase ("Refining Image..."), tracking the time spent in each independently.
- **Stats Cache & UI Stability**: Implemented a caching mechanism for automation stats. This prevents the "Summary" table header from flashing momentarily when the API times out during heavy CPU-bound watermark processing (LaMa), ensuring a smooth, persistent monitoring experience.

### 8. Dashboard Gallery Concurrency Handling
- Fixed a crash (`UnidentifiedImageError`) in the Dashboard gallery fragment that occurred when the system attempted to display an image while it was still being written to disk by the automation engine.
- The gallery now gracefully handles partially-written files by displaying a "⏳ Loading..." status, preventing the UI from crashing and ensuring a more resilient monitoring experience.

### 9. Reject Rate Stats Visual Chart
- Added a new **📈 Stats Chart** button to the Dashboard main panel.
- This feature provides a visual breakdown of automation efficiency using a highly-optimized multi-metric line chart.
- It tracks **Duration (in minutes)**, **Refusals**, and **Resets** per file, with filenames automatically cleaned (removing `.png` suffixes) for better readability on the X-axis.
- **Architectural Upgrades**: Migrated to a custom-built, single-mark **Altair** implementation. This upgrade allows precise, human-readable tooltips (e.g., `Filename`, `Refused`, `Resets`, `Duration`) without the ambiguous `value` and `color` labels generated by native Streamlit charts.
- **UI Stability Enhancements**: Wrapped the chart in a rigid `st.container` to prevent DOM layout collapses during 1-second auto-refreshes. This ensures the background Image Gallery remains perfectly stable with zero jittering, while also strictly complying with Streamlit 1.40's new `width="stretch"` layout parameters to eliminate console warnings.


### 11. Account Health Analysis (Performance Monitoring)
- Introduced a dedicated **Account Health Analysis** tool within the System Config page to monitor Nano Banana 2 loading performance.
- **Detailed History View**: Users can select a specific account to view its entire loading history from the logs, including exact timestamps, loading durations (in seconds), and success/normal status.
- **Full Loading History (All Events)**: A comprehensive view that aggregates all loading events from all accounts in chronological order, allowing for system-wide performance auditing.
- **Interactive Performance Graphs**: Added a "Plot Graph" feature that visualizes loading trends using color-coded bar charts (Success in green, Normal in purple).
- **Intelligent Tooltips**: Hovering over graph bars reveals detailed metadata, including the specific **Artifact** (downloaded filename) and the associated account.
- **Automatic Account Backfilling**: Implemented a multi-stage fallback logic to identify "Unknown" accounts in truncated logs by cross-referencing the explicitly marked "active" account from the login lookup table.

### 13. Account Health Metric Alignment & 'RejectStat' Integration
- **Aligned Performance Metrics**: Synchronized the Account Health Analysis duration, reject, and reset counts with the Dashboard's logic by integrating with the engine's `RejectStat` logging.
- **Engine-Anchored Success Data**: Success records in health charts now prioritize high-precision, cumulative metrics (Duration, Rejects, Resets) reported directly by the engine. This ensures that a single image (e.g., 1087.png) displays identical data in both the System Config and Dashboard views.
- **MM:SS Duration Formatting**: Standardized all duration displays in health tooltips to a clean `Minutes:Seconds` (MM:SS) format for better readability.
- **Integer X-Axis Scaling**: Enforced integer-only scaling for all health chart X-axes, eliminating confusing decimal artifacts in event sequences.
- **Robust Data Attribution**: Optimized the log parser to automatically bypass manual accumulation when anchored `RejectStat` data is present, preventing double-counting while maintaining a reliable fallback for legacy logs.


### 14. Synchronized 'Detailed History' Performance Logic
- Fixed a logic omission in the **Account Health Analysis**'s "Detailed History: Active Account" view where it was not correctly utilizing the high-precision `RejectStat` markers from the log.
- This view now correctly prioritizes anchored `true_rej`, `true_res`, and cumulative `Duration` data, ensuring that performance metrics for the currently active account are 100% consistent with the "Full History" and Dashboard views.
- This resolves discrepancies where the active account's history might have shown fragmented stats after session resets.

### 11. Migration to Streamlit Latest Layout Parameters
- Standardized the use of `width='stretch'` instead of the deprecated `use_container_width=True` across the entire application (including Dashboard charts and System Config tables). 
- Formally updated the project `rule.md` to ensure future compliance with Streamlit's 2026 API standards.

### 12. Reject Rate Chart Chronological Sorting
- Resolved a visualization issue in the Dashboard's **Reject Rate Chart** where the X-axis (filenames) was being sorted alphabetically instead of chronologically.
- Previously, filenames starting with "1" (e.g., "1000") would incorrectly appear before filenames starting with "8" (e.g., "825") due to string-based sorting.
- The chart now uses a hidden sequential `order_index` to ensure that data points strictly follow the execution timeline, providing a true representation of performance trends over time.

### 13. Session Reset Confirmation Dialog
- Implemented a safety confirmation prompt when starting a new automation loop via the **"▶️ Start Looping Process"** button in both the Dashboard and Gemini Setup modules.
- The system now intelligently checks for existing session records (`history_count`). If no records exist, automation begins immediately. If previous records exist, a warning dialog prompts the user to confirm the session reset, preventing accidental loss of active session statistics.

### 14. System Configuration Navigation & UI Alignment
- **Navigation Reordering**: Reorganized the **SYSTEM NAVIGATION** menu in the System Config page. "Account Credentials" is now intuitively positioned directly above "Account Health Analysis".
- **Chart Color Consistency**: Fixed a visual bug in the Account Health Analysis module where the Reject Rates line chart would render as gray for individual account views (`Detailed History: <account>`). This was resolved by properly separating color scales (`resolve_scale(color='independent')`) for the background bands and the metrics lines.
- **Unified Alternating Colors**: Ensured that the "Base" and "Light" alternating bar chart colors for the "Full Loading History (All Events)" view correctly cycle on a per-account basis using dense ranking (`cycle`), perfectly aligning its visual presentation with the "Detailed History: Active Account" view.

### 15. Automation Metric Persistence & Hydration Fix
- Resolved a data loss issue where **'Refused'** and **'Reset'** counts were being lost when an automation session was stopped and subsequently continued.
- Fixed a **Stop-Action Race Condition** in `browser_engine.py`: previously, the system would eagerly mark automation as stopped before the background manager had finished saving state. The manager now holds the `is_running` lock until state persistence is 100% complete.
- Corrected **Snapshot Synchronization** in `continue_automation`: the system now intelligently detects whether it needs to account for pending stats in the first delta calculation, ensuring that `session_refused` and `session_resets` in the login lookup table are accurately incremented across pauses and restarts.

### 16. Account Health Chart Unit Normalization
- Converted the Y-axis units for all **Account Health Analysis** charts (both bar and line charts) from **Seconds** to **Minutes (Duration (m))**.
- This normalization prevents the relatively large duration values (e.g., 180s) from overwhelming the smaller Refused/Reset counts (e.g., 1, 2, 3), making the efficiency trends and health events clearly visible on the same scale.
- Maintained detailed precision in tooltips, which continue to display the exact time in `M:SS` format.
- Standardized the graph legend to match the **Dashboard's** performance charts for a unified monitoring experience.

### 17. Account Health Y-Axis Scale Persistence & Toggle
- Implemented a **Y-Axis Scale** toggle (Linear vs. Logarithmic) in the Account Health Analysis module.
- Used **Symmetrical Log (symlog)** for logarithmic mode to safely handle zero values (Refused/Reset counts), ensuring visibility for small counts alongside large durations.
- Integrated the scale preference into `config.json`, allowing the system to remember and restore the user's preferred viewing mode across sessions.

### 18. Smart Notifier Tracking & Cumulative Unseen Counts
- Enhanced `image_notifier.py` with a persistent tracking system (`notifier_state.json`) that distinguishes between **Auto-Hide** and **Manual Dismissal**.
- Added a **Cumulative Unseen Count** feature: the notifier now tracks and displays how many images have been downloaded since the user last manually acknowledged a popup.
- High-visibility UI: The "Unseen" count is highlighted in **Bold Red** for immediate recognition of overnight or background download batches.
- Synchronized Status: The manual "Show Status" popup now correctly calculates and displays the same unseen count, ensuring consistency between automatic alerts and manual checks.

### 19. Ghost Success (Fail) Detection & Visualization
- Implemented a new **Fail** status in Account Health Analysis to capture "Ghost Successes" (events reported as successful by the engine but failing to save a file).
- Visual Highlighting:
    - **Bar Charts**: Failed events are rendered in a distinct **Light Red (#ff9999)** with no depth variation, making them immediately stand out from normal Rejects/Resets.
    - **Line Charts**: Critical failures are now plotted on the trend line with **Bold Red (#ff3333)** points for instant error identification.
- Data Integrity: Added "FAILED" placeholders in the filename field for these events to maintain sequence integrity in trends.

### 20. Chart Aesthetics & Point-Line Color Synchronization
- Refined the Reject Rate trend charts to ensure all data points strictly follow their corresponding line colors:
    - **Duration**: Green points on green lines.
    - **Rejects**: Blue points on blue lines.
    - **Resets**: Orange points on orange lines.
- Improved tooltip detail by adding the `Status` field, allowing users to verify if a trend point represents a Success or a critical Fail.
- Fixed an indentation syntax error in the health analysis module to ensure stability across all view modes.

### 21. Chart UI Decluttering & Legend Optimization
- Removed the redundant "Metric" legend title from the right side of the Reject Rates charts by explicitly disabling legends for overlapping layers.
- Removed the X-axis title "Image Sequence" across all Account Health charts to maximize screen real estate and provide a cleaner, more focused visualization.
- Consolidated all chart legends to a consistent bottom-oriented layout.

### 22. Legend Layout Optimization for Bar Charts
- Implemented a two-row legend layout (`columns=4`) for Loading Duration bar charts.

### 23. Unified Aspect Ratio Setting Module
- Standardized aspect ratio configuration across **Gemini Setup** and **System Config** by unifying the control logic and UI persistence.
- **Aspect Ratio Setting (New Container)**: Replaced the legacy "Dynamic Prompt Prefix" toggle with a comprehensive management container featuring two distinct modes:
    - **Fixed Aspect Ratio**: Injects a static, user-selected ratio (e.g., 16:9, 1:1) into every prompt.
    - **Dynamic Prefix Loop**: Automatically cycles through a sequence of pre-configured ratios and target counts.
- **Intelligent Prompt Injection**: The automation engine now automatically prefixes "Aspect Ratio: [Selected Ratio]" to the user's prompt. 
- **Double-Injection Prevention**: Implemented a check to ensure the prefix is only added if not already present, preventing cluttered or corrupted prompts during recursive loops or manual edits.
- **Cross-Mode Editing Freedom**: Updated the UI to allow configuration changes to both the Fixed Ratio and Dynamic List regardless of the active mode. This allows users to pre-configure their next automation sequence without switching tabs or modes.
- **Intelligent UI Locking**: All aspect ratio controls (Radio buttons, Dropdowns, and Data Editors) are now strictly tied to the **Loop 进程 (Automation Loop)** status. Controls are locked only during active generation and automatically unlock when idle, even if the browser is open.
- **Aesthetic Refinements**: Updated the Dynamic Prefix dialog to a responsive medium-width design and moved all titles to sentence-case for a more professional look.

### 24. Account Health Analysis UI & Accuracy
- **Y-Axis Unit Normalization**: Changed the Y-axis duration label from `(m)` to `(minite)` across all performance charts to provide a more descriptive unit label.
- **Logarithmic Scale Integration**: Fixed chart rendering issues where logarithmic scales failed to persist correctly from `config.json`.
- **Time Formatting**: Standardized all time durations in health charts to a high-precision `H:MM:SS` format.

### 25. Real-Time Aspect Ratio Updates & UX Refinements
- **Instantaneous Application**: Modifying the Aspect Ratio Mode or changing the Fixed Ratio now behaves exactly like the Prompt "Save" button. If an automation cycle is active, the system automatically forces a **New Chat** on the next loop, instantly applying the new ratio instructions without relying on stale conversation contexts.
- **Always Editable Looping Table**: Removed arbitrary UI restrictions that disabled the Aspect Ratio Looping Table during `Dynamic Prefix Loop` mode. Users can now freely edit the table (e.g., modifying target counts or ratios) in real-time, and the engine will seamlessly adopt the changes on the next generation cycle.
- **Intuitive Status Control**: Transformed the table's `Status` column from read-only text into an interactive dropdown with a minimalist `["", "Active"]` toggle.
- **Force Start Here (Jump-to-Row)**: Users can intuitively skip to any ratio in their sequence by manually setting its status to `"Active"`. The system intelligently detects this intervention, automatically marks previous sequences as complete, and resumes generating from the newly selected row.
- **Consistent Visual State**: The mathematical `Active` indicator is now permanently visible across the Looping Table, even when the system is operating in `Fixed Aspect Ratio` mode. This ensures users always know where their dynamic sequence paused and where it will resume.
