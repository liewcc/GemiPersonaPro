# 🆕 Latest Updates & Features

Welcome to the latest release notes for **GemiPersonaPro**. This document outlines the most recent improvements, bug fixes, and new features added to the system.

## 🚀 Recent Features & Enhancements

### Update: 2026-05-18 - Gemini Setup Image Reference Improvements
- **IMAGE REFERENCE Section**: Renamed the container from "EXTRACT METADATA FROM IMAGE" to "IMAGE REFERENCE" for a cleaner and more professional presentation.
- **Dual-Mode Image Handling**: Added two horizontal radio buttons (`extract metadata from image` and `modify image`) directly below the file path text box:
  - **extract metadata from image**: Retains the original functionality of parsing embedded generation prompt, URL, and uploaded files list from the PNG metadata.
  - **modify image**: A new workflow for modifying existing images. When selected and applied, the system generates the prefix `modify image "filename.png":` and automatically injects it into the prompt text area.
- **Automatic File Synchronisation**: In `modify image` mode, clicking "Apply" also automatically clears the existing **UPLOAD FILES TO BROWSER** queue and replaces it entirely with the selected reference image, ensuring the target image is attached for modification.
- **Reference Metadata Inheritance**: When a new image is successfully downloaded in `modify image` mode, its embedded PNG metadata (`prompt`, `url`, `upload_path`) is inherited from the original reference image selected in IMAGE REFERENCE, not from the ephemeral modification prompt. This preserves the correct generation provenance chain across multiple modification rounds. The reference metadata is stored in `config.json` under `image_ref_source_meta` by the UI layer and read by the automation engine at download time.
- **Streamlit State Hydration & Rerun**: Implemented an explicit state hydration flow. By updating the backend configuration and setting `st.session_state["_load_from_config"] = True` before triggering a rerun, the page reliably reads the fresh prompt and updates the text area UI immediately, preventing the native Streamlit widget state lag.
- **Aspect Ratio Metadata Prioritization**: Restructured the embedded PNG metadata injection pipeline across all automated and manual workflows (`Submit`, `Redo`, `run_automation_loop`). The `aspect_ratio` category is now explicitly inserted as the very first field in the metadata dictionary, followed by `prompt`, `url`, and `upload_path`, ensuring optimal parsing visibility.
- **Automated Aspect Ratio UI Synchronization**: When an image is applied in either `extract metadata from image` or `modify image` mode, the system automatically extracts its embedded aspect ratio and synchronizes it directly with the **ASPECT RATIO SETTING** panel. It forces a switch to `Fixed Aspect Ratio` mode and uses Streamlit's `widget_rerender_key` pattern to instantly update the UI selectbox without caching lag.
- **Lineage Prompt Pollution Prevention**: Enhanced the metadata extraction lifecycle to actively clear stale `image_ref_source_meta` cache when switching to `extract metadata from image` mode. This prevents previous modification prompt lineage data from polluting the metadata of subsequent standalone image generations.

### Update: 2026-05-17 - Monitor Image Processing Controls
- **Quick Actions Container**: Added a new "Process Latest Download Image" control panel directly below the performance charts in the standalone GemiPersona Monitor.
- **View Image**: Added a dedicated button that instantly opens the most recently downloaded image using the default Windows photo viewer.
- **Move to New Folder**: Enables users to quickly select a destination folder (defaults to the current download directory) and move the most recently downloaded image out of the auto-download directory with a single click. If a sanitized version exists in the `processed/` subfolder, it will automatically be moved to a `processed/` folder in the new destination.
- **Delete to Recycle Bin**: Added a quick-delete function that safely moves the most recently downloaded image directly to the Windows Recycle Bin (using the native `send2trash` mechanism). It simultaneously deletes the corresponding file in the `processed/` subfolder if it exists, streamlining the workflow for discarding unwanted generations.

### Update: 2026-05-17 - Monitor Dashboard Comprehensive Optimization

#### New "By Account" Chart Tab
- Added a third chart tab **"By Account"** in the GemiPersona Monitor, specifically designed to display the aggregated image downloads ordered by the account switching sequence.
- The X-axis represents each account Session (ordered by switch sequence, without text labels to avoid clutter), and the Y-axis represents the number of successfully downloaded images for each Session.
- The color scheme is perfectly aligned with the main Dashboard's "Account Switch Duration Chart" (Images Download mode):
  - Successful image downloads (>0): Alternating dark and light green (`#2ecc71` / `#a0e6b5`).
  - Zero-image Sessions: No bar is drawn, leaving it blank (improving visual cleanliness).
- **Mouse-over Tooltip**: When hovering over any bar, the account name (with the `@domain` suffix removed) and the exact image count will be displayed in the bottom right corner of the chart. It does not track the mouse, preventing the popup from extending beyond the application window.

#### Data Synchronization Fixes (Perfectly Aligned with Main Dashboard)
- **Total Images**: Now calculated from the row count of `reject_stat_log.json`, consistent with the Dashboard.
- **Total Refused / Total Reset**:
  - While Running: Directly utilizes the `refusals` / `resets` fields from the `/browser/automation/stats` API (the same source as the Dashboard status bar).
  - While Stopped: Aggregates the historical `refused_count` / `reset_count` for each cycle from `reject_stat_log.json`.
- **Total Cycles**: Corrected to use the `cycles` field from the API (the true engine cycle counter), no longer mistakenly using `round` (which is a per-image sequence number).

#### Second Row Account Stats Fixes
- Fixed the account name matching logic: The API returns the full email (e.g., `dapmuar@gmail.com`), while `user_login_lookup.json` stores the short name (e.g., `dapmuar`). The comparison now uniformly extracts the prefix before the `@` symbol, ensuring Switch At, Images, Refused, and Reset statistics are displayed correctly.
- Moved the `user_login_lookup.json` lookup logic to the outermost layer. It now executes immediately regardless of whether the log cache is loaded, preventing the second row of data from missing during initial startup.

#### CPU Usage Optimization (Smart Incremental Parsing)
- Previously, the 21MB `engine.log` was forcibly and fully parsed every 5 seconds, causing high CPU fan speeds.
- Introduced the `_count_events_tail()` function: Each polling cycle now only reads the last ~64KB of the log to count key event lines. A full re-parse is triggered only when new events are detected.
- The numeric dashboard prioritizes fetching from the lightweight API, and log parsing is strictly used for chart rendering. CPU usage now drops to near 0% when there are no new events.

#### Typography and Interface Improvements
- Uniformly applied the `Microsoft YaHei UI` font across the interface for correct rendering of mixed English and CJK content.
- The number of chart bars is now dynamically calculated based on the actual Canvas width (~7.5px per bar), eliminating large blank spaces on the right side.


### Update: 2026-05-16 - Notifier Monitor Aesthetics
- **Account Differentiation via Background Stripes**: Enhanced the standalone GemiPersona Monitor window (`monitor_window.py`) by implementing alternating background color bands behind the chart bars. This elegantly distinguishes the sequence of different accounts or sessions without adding complex color variants to the bars themselves, maintaining a clean and simple aesthetic for the event statuses (Success, Refused, Reset, Fail).
- **Gridline Visibility Optimization**: Lightened the Y-axis horizontal gridlines (time intervals like 1s, 10s, 1m) in the Notifier's dark-themed chart from a very dark `#1e2535` to a more visible, crisp Slate gray (`#475569`), significantly improving readability without overpowering the data.

### Update: 2026-05-16 - Account Health Optimization & Tray Notifier
- **Real-Time Log Polling (Decoupled)**: Engineered a dual-loop polling system that decouples the fast 1s log-line updater from the heavy 5s chart parser. This ensures the latest engine status appears instantly upon window opening without freezing the UI.
- **Robust Character Sanitization**: Implemented aggressive string filtering to strip out control characters and non-BMP Unicode codepoints (emojis) that would otherwise trigger `TclError` crashes in the Tkinter text renderer.
- **Synchronized 'New Images' Downloads Counter**: Updated the "New" image counter in the Health Analysis dashboard to "New Images" for clarity. It mirrors the main Notifier's "Auto" count. Added a dedicated `Reset New Images Count` button adjacent to the Close button, allowing users to manually acknowledge and zero-out the counter instantly without waiting for popups.
- **Optimized UI Grid Layout**: Refined the statistics grid padding to flawlessly accommodate 6 columns in the fixed-width dashboard window, preventing text truncation or layout overflow.
- **Accurate Event Filtering**: Updated charts to automatically exclude "Ongoing" processes, ensuring the performance visualization only reflects completed automation rounds for 100% data accuracy.
- **Logarithmic Y-Axis Scale**: Integrated a logarithmic scale for the duration axis (using `log1p`), ensuring that short-duration successes remain clearly visible even when significant delays occur.
- **Enterprise Stability**: Added background tray restart loops and safe exception handling for all background UI threads.

### Update: 2026-05-16 - Load Metadata from File in Gemini Setup
- **Metadata Extraction & Auto-fill**: Added a new **EXTRACT METADATA FROM IMAGE** container directly above the BROWSER URL section in the `Gemini Setup` page. Users can now select an existing generated PNG image file to automatically extract its embedded metadata (`prompt`, `url`, `upload_path`).
- **Seamless State Synchronization**: Clicking "Apply" instantly updates the workspace configuration, injecting the extracted `prompt` into the text area, the `url` into the browser navigation bar, and automatically overriding the **UPLOAD FILES TO BROWSER** queue with the extracted image paths. This creates a powerful preset-loading workflow straight from historical outputs.
- **Native File Picker**: Utilizes a robust, always-on-top `tkinter` file dialog specifically filtered for images (`.png`, `.webp`, `.jpg`), ensuring a smooth native Windows browsing experience.

### Update: 2026-05-15 - Account Health Chart Enhancements
- **Cycle Performance Insights Y-Axis Toggle**: Added a new radio button to the "Cycle Performance Insights" tab, allowing users to instantly toggle the Y-axis of the "Account Switch Duration Chart" between **Duration** (minutes) and **Images Downloaded** counts.
- **Dynamic Data Formatting**: The chart dynamically updates based on the selected Y-axis. The data labels above the bars have been removed for a cleaner look, while tooltips continue to provide full context on duration and image counts.

### Update: 2026-05-01 - 4K Upscaler Workflow & Reliability Enhancements
- **Delete Activity Integration**: Added a dedicated `🗑️ Delete Activity` control panel to the 4K Upscaler dashboard. Users can now automatically delete Gemini activity history ("Last hour", "Last day", or "All time") directly from the upscaler workflow.
- **Trigger Timing Control**: The activity deletion can be configured to execute either immediately `After Start` (cleaning history before processing begins) or `After Stop` (running a dedicated, lightweight cleanup process after the main worker is stopped), ensuring no interference with the actual upscaling tasks.
- **Max Redo Limit**: Introduced a new `🔄 Max Redo Limit` toggle and numeric input to prevent infinite retry loops. If Gemini refuses a prompt repeatedly, the worker will automatically mark the image as an error and skip to the next file once the defined limit is reached, maintaining process momentum.
- **Intelligent Output Directory Auto-fill**: To streamline setup, the `Output Directory` now automatically populates with an `/Upscale` subfolder appended to the chosen Input Directory path whenever the input is changed, while still allowing full manual overrides.
- **Directory Shortcuts**: Added native `📂` (View Folder) shortcut buttons next to the Input and Output directory selectors, allowing users to instantly open the corresponding Windows Explorer folders with one click.
- **Enhanced Status UI & Icons**: The progressive log and status tables now correctly distinguish between files that are actively processing (`🔄`), successfully finished (`✅`), fully failed (`❌`), or skipped because they already exist (`💨`). The worker accurately updates `upscaler_status.json` to reflect these exact states.
- **Bug Fix (Max Redo Limit)**: Corrected an off-by-one arithmetic error where the worker required one additional refusal beyond the user's defined limit before triggering a skip.
- **Bug Fix (Atomic Config Persistence)**: Fixed a critical state-management flaw in the UI where modifying one upscaler setting (like `Max Redo Limit`) would accidentally erase sibling parameters (like `Delete Activity`) from `config.json` via shallow dictionary overwriting. All upscaler settings are now securely bundled and written atomically.

### Update: 2026-05-01 - Notifier UI Overhaul & Dual-Tracking
- **Dual-Directory Monitoring**: The `image_notifier.py` background process now concurrently monitors both the Automation save directory and the 4K Upscaler output directory, providing unified alerts for all system activities.
- **Side-by-Side Typography**: Overhauled the notification pop-up UI to feature a sleek, two-column layout showing "Auto" and "Upscaler" statistics side-by-side using large, easily readable font numbers.
- **Dynamic State Highlighting**: The numbers and text labels will intelligently dim into a muted grey if a particular subsystem (Automation or Upscaler) is currently stopped or not configured, ensuring users instantly know what's active.
- **Dedicated Folder Navigation**: Replaced the generic "Open Folder" button with dedicated `📁 Download Folder` and `📁 Upscale Folder` buttons, allowing one-click access directly to the specific image outputs right from the taskbar popup.

### Update: 2026-04-29 - Log Record Export & Loading Management
- **Universal 'Load Record' Integration**: Added a new `📂 Load Record` button across the entire Account Health suite (Analysis, Insights, and Debugging tabs). This allows users to import and analyze historical `.log` files exported by the system.
- **Save Record Logic**: Implemented a `💾 Save Record` feature in the Automation Cycle Management tab. Users can now select specific automation cycles and export them to a standalone `.log` file with custom filenames based on the cycle's start timestamp.
- **Native File Selection**: Integrated `tkinter` file and directory dialogs into Streamlit to provide a premium, native folder/file selection experience. The dialogs have been engineered to remain open while the user browses their filesystem.
- **Global Data Context**: When a record is loaded, the entire application intelligently overrides its data source. All charts, tables, dropdowns, and raw log viewers instantly switch to the context of the loaded file.
- **Data Source Awareness**: Implemented high-visibility "Loaded from: [path]" indicators across all relevant dashboard tabs to ensure users always know whether they are looking at live engine logs or historical archives.
- **Editable Default Filenames**: The Save Record dialog now automatically generates a safe, timestamped filename (e.g., `cycle_20260429_143644.log`) and presents it in an editable text box for user customization.

### Update: 2026-04-28 - Account Health Architecture & UI Responsiveness
- **Independent Fragment Architecture**: Completely reverted the `Account Health` dashboard to its stable, independent `@st.fragment` architecture. Removed shared global data caching wrappers that were previously interfering with fragment lifecycles, completely eliminating the persistent UI flickering and layout "jumping".
- **Absolute Event Sequence Numbering**: Solved the visual bug where the "Show Last N Events" slider appeared broken. The background parser now assigns a chronological `Absolute_Event_Num` to every record *before* any slicing occurs. The X-axis for all charts now accurately reflects the true chronological sequence (e.g., displaying events 101-150 instead of defaulting to 1-50), allowing users to immediately verify that the chronological slice was successful.
- **Real-Time UI Reactivity**: Refactored all Account Health settings (Graph Mode, Y-Axis Scale, Event Slider, and Toggles) to bypass config I/O latency. Fragments now read directly from `st.session_state`, guaranteeing that any adjustment to the UI controls triggers an instantaneous and isolated visual update in the charts.
- **Engine Logs Debugging Independence**: Validated and locked the layout for the "Engine Logs Debugging" tab. It now operates securely inside its own fragment with a strictly fixed-height (`800px`) container and correctly contextualized filtering statistics (`📊 Stats: Lines X | Events Y`), ensuring smooth operation without disrupting the rest of the dashboard.


### Update: 2026-04-28 - Account Health UI Scaling & Stability
- **Dynamic Log Scaling**: The `Show Last N Events` slider in the Account Health page is no longer capped at 2000 events. It now dynamically calculates its maximum value based on the exact number of events currently stored in `engine.log`.
- **Global Cycle Isolation**: Introduced a new **Show Last Cycle Only** toggle. When enabled, it intelligently identifies the start of the most recent *global* automation cycle and filters out all older events. It seamlessly merges multi-session data caused by Loop Control account switches, providing a clean view of the current run regardless of how many accounts are involved.
- **Contextual UI De-cluttering**: The graph controls container (including the events slider and cycle toggle) now automatically hides when the user switches to **Table Mode**, maximizing vertical screen real estate for the data grid.
- **Total Events Tracking**: Added a new **Events** column to the Automation Cycle Management table. This new data point summarizes the absolute total of all processing events (Successes + Refusals + Resets) contained within each historical cycle.
- **Streamlit Garbage Collection Bypass**: Addressed a known Streamlit core bug (`MediaFileStorageError`) that caused the backend to crash when auto-refreshing fragments (`@st.fragment`) coexisted with a local static file path for `page_icon`. The application's `page_icon` has been converted to an emoji (`🏥`) to permanently bypass this frontend caching issue.

### Update: 2026-04-27 - Aspect Ratio Table UI Fix
- **Aspect Ratio 'Active' Save Logic**: Fixed a bug where selecting the "Active" row in the Aspect Ratio Looping Table (both in Gemini Setup and System Config) failed to properly update the underlying counting math. Saving a specifically marked "Active" row now automatically resets its count and marks prior rows as complete, ensuring the generation sequence reliably resumes exactly where the user clicked.

### Update: 2026-04-26 - UI Consolidation & Enhanced Cycle Analytics

#### 1. Unified Utilities Dashboard
- **Page Merge**: Successfully combined the `Asset Sanitizer` and `Gems Bookmark` tools into a single, unified `Utilities` page (`02_Utilities.py`). This reduces sidebar clutter and centralizes post-generation asset management and character consistency workflows.
- **Horizontal Navigation**: Implemented a sleek horizontal tab layout (`st.tabs`) at the top of the main panel, allowing users to seamlessly switch between the Image Sanitizer and Bookmark Manager without losing their current state or context.
- **Shared Architecture**: Retained the powerful sidebar controls (Path Selection, Auto-Clean toggle) for the Sanitizer, while dynamically adapting the layout to keep the Gems Bookmark interface clean and full-width when active.

#### 2. Enhanced Automation Cycle Insights
- **Precision Tracking**: Upgraded the `health_parser.py` backend to extract high-precision stopping timestamps (`stop_time_str`) and calculate the exact number of successful image downloads (`success_count`) per automation cycle.
- **Rich Data Display**: The **Automation Cycle Management** table in the Account Health page now features two new dedicated columns: `Stop Time` (positioned immediately after Start Time) and `Successful Downloads`. 
- **Analytical Value**: These additions allow users to instantly gauge the duration and productivity of historical automation sessions before deciding whether to prune them from the engine logs.
- **Legacy Compatibility**: The new parser logic is fully backwards-compatible, intelligently extracting success counts from both the modern JSON event streams and legacy text-based logs (`[HH:MM:SS]` timestamps and "Saved:" markers).

### Update: 2026-04-25 - Account Health Session & Accuracy Fixes

#### Fix 0: Continue Session Bar Color No Longer Changes After Stop & Resume
- **Root Cause**: When the user clicked **Stop** and then **Continue Session**, the engine wrote a `BOUNDARY` JSON event followed (a few DEBUG lines later) by a new `START` event with the same round number (> 1). The old parser incremented `current_session_id` immediately upon encountering any `BOUNDARY` event. Since the `START` after a continue carries the same account and a round_id > 1, it received the new `session_index`, causing its bar to render in the alternate color band.
- **Fix**: Deferred the session_id bump from the `BOUNDARY` event to the next `START` event. At `START` time, the parser inspects `round_id`: if `round_id == 1` (fresh start) or the account changed, it is a genuine new session and the counter increments. If `round_id > 1` with the same account (continue session), the counter is **not** incremented. The same deferred logic is applied to the legacy text-path (`"automation finished"`).
- **Rule**: `ACCOUNT_SWITCH` with a real account change still bumps immediately. Only `BOUNDARY`-triggered session boundaries are deferred until the next `START` to absorb continues.

#### Fix 0b: Account Switch Color Change Now Visible in Loading Duration Chart
- **Root Cause**: The bar color `cycle` was computed with `groupby("account")["session_index"].rank(method="dense")`. This means each account's sessions are ranked **independently starting from 1**. When the user stopped and switched from `nusa.direct` (session 1) to `kiongsoo` (session 2), kiongsoo's per-account rank was 1 (its first session), the same as nusa.direct's. Both rendered as `Base` color â€” the account switch was visually invisible.
- **Fix**: Changed to a **global dense rank** â€” `df["session_index"].rank(method="dense")`. Since `session_index` is a globally incrementing counter in `health_parser.py`, kiongsoo's session gets global rank 2 â†’ `cycle=2` â†’ `Light`, visually distinct from nusa.direct's `Base`. This works correctly for both single-account views (no sessions shared between accounts) and the full-history view.


#### Fix 1: Continue Session No Longer Creates a False New Session
- **Root Cause**: The legacy text-path boundary detector in `health_parser.py` matched the string `"automation manager started"` as a session boundary. Since "Continue Session" writes exactly this line, every resume was incorrectly incrementing `session_id`, splitting what should be one continuous session into multiple visual segments in the Loading Duration chart.
- **Fix**: Removed `"automation manager started"` from the boundary condition. The only remaining text-path boundary trigger is `"automation finished"` (a real, deliberate stop). The JSON-path boundaries (`BOUNDARY` / `ACCOUNT_SWITCH` events) are unaffected and remain the authoritative signals for genuine new sessions.
- **Rule**: A new session is only created by two conditions: (1) manual account switch â†’ continue, or (2) quota full. Any other interruption that resumes is the same session.

#### Fix 2: Loading Duration Chart Session Colors Now Per-Account
- **Root Cause**: The Base/Light alternating bar color was computed using a global `rank()` of `session_index` across all accounts. Since `session_index` is a globally incrementing integer, a single account's sessions could all share odd ranks (e.g., 1, 3, 5) and thus always render as "Base" color, never alternating.
- **Fix**: Changed to `.transform(lambda s: s.rank(method="dense"))` grouped by `account`, so each account's sessions independently restart at rank 1 and correctly alternate Base â†’ Light â†’ Base.

#### Fix 3: Wrong Account Name Shown on Chart Bars
- **Root Cause**: All JSON log entries written by `browser_engine.py` used `automation_status["initial_user"]` as the `account` field. `initial_user` is set once at automation start and never updated, so after any account switch, every subsequent log record was still stamped with the original (first) account name.
- **Fix**: The `_log_debug` method now resolves the account field with: `current_account_id â†’ initial_user â†’ "unknown"`. `current_account_id` is updated in real-time by `get_account_info()` after each profile switch, ensuring all log entries are correctly attributed to the account that actually produced them. The value is also normalized to lowercase username-only (stripping the `@domain` part) for consistency with the parser.

#### Fix 4: Account Switch Fails to Change Color on Quota Full (Re-Login Logic Fix)
- **Root Cause**: The parser was checking `acct != prev_account` line-by-line to detect a real account switch. However, during a quota full sequence, the background engine updates `current_account_id` early. Intermediate `DEBUG` logs (like history deletion) reflect the new account name. When the official `ACCOUNT_SWITCH` event was logged seconds later, `prev_account` had already bled the new account name, causing the parser to wrongly classify it as a "re-login" (same account) and failing to trigger a session color bump.
- **Fix**: Replaced the line-by-line `prev_account` tracker with a `last_stable_account` tracker that only updates on major state events (`START`, `BOUNDARY`, `ACCOUNT_SWITCH`). The parser now reliably detects `acct != last_stable_account` and accurately triggers a new session color band for real account switches.

#### Fix 5: Aspect Ratio Looping Table Save Logic
- **Issue**: Previously, manually selecting a row as "Active" and clicking "Save Setting" would automatically mark all preceding rows as completed (max count) and zero out all subsequent rows, losing progress.
- **Fix**: The saving logic in `01_Gemini_Setup.py` and `05_System_Config.py` has been updated. Now, when saving the table, **only the row explicitly marked as Active** has its count reset to 0. All other rows preserve their existing counts.



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
- Added a highly requested **â¯ï¸ Continue Session** functionality to both the Dashboard and Gemini Setup pages.
- Allows users to pause an active automation loop and subsequently resume it without wiping the current session's Reject Rate statistics or counter metrics.
- Features a robust **State Hydration** mechanism: if the application or backend engine is restarted while a session is paused, the engine will automatically parse the `reject_stat_log.json` to seamlessly rebuild the previous metrics (Successes, Refusals, Resets) directly into memory upon clicking Continue.
- Implements strict **Goal Protection**: attempting to continue a session that has already reached its configured image/round target will automatically trigger an alert dialog, preventing accidental data pollution or instant-stop loops.
- **UI Stabilization**: Refactored the control layout across both pages. The `Start / Stop` buttons now swap seamlessly in place, while the `Continue` button securely occupies the adjacent column, ensuring absolute layout stability and zero button-jumping during active automation.

### 2. Interactive Wheel-Zoom for Dashboard Reject Rate Chart
- Upgraded the Dashboard's **ðŸ“ˆ Reject Rate Chart** to support smooth, mouse-wheel-based zooming and horizontal panning.
- Migrated the X-axis from a string-based (Nominal) scale to a sequential quantitative scale (`order_index:Q`). This enables Altair's native interactive zooming capabilities, which are otherwise limited for nominal axes.
- **Improved UX**: The chart now supports `bind_y=False`, allowing users to zoom and pan specifically along the timeline (X-axis) while keeping the metric values (Y-axis) stable and visible. This makes it significantly easier to analyze long automation sessions with dozens of processed images.
- **Contextual Clarity**: Filenames remain clearly visible in the interactive tooltips, ensuring that per-image performance data is always accessible even when zoomed in.


### 2. Quota Cooldown â€” Automatic Account Lock After Quota Hit
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

## ðŸ› Critical Bug Fixes

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
- The gallery now gracefully handles partially-written files by displaying a "â³ Loading..." status, preventing the UI from crashing and ensuring a more resilient monitoring experience.

### 9. Reject Rate Stats Visual Chart
- Added a new **ðŸ“ˆ Stats Chart** button to the Dashboard main panel.
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
- Implemented a safety confirmation prompt when starting a new automation loop via the **"â–¶ï¸ Start Looping Process"** button in both the Dashboard and Gemini Setup modules.
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
- **Intelligent UI Locking**: All aspect ratio controls (Radio buttons, Dropdowns, and Data Editors) are now strictly tied to the **Loop è¿›ç¨‹ (Automation Loop)** status. Controls are locked only during active generation and automatically unlock when idle, even if the browser is open.
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

### Update: 2026-04-26 - Automation Stability & Time Threshold Logic
- **Streamlit Asyncio Conflict Fix**: Completely refactored the Dashboard's automation statistics fetching mechanism. Replaced `asyncio.run()` with native `requests.get()` to prevent critical `RuntimeError` crashes caused by Streamlit's internal event loop overlapping, ensuring the Reject Rate Stats timers no longer freeze or disappear into a false `API Timeout` state.
- **Time Threshold Absolute Priority**: Overhauled the Loop Control logic to ensure the **Time Threshold** is strictly respected. Previously, if a heavily throttled account managed to slowly succeed, the success status would bypass the time check and fail to switch the profile. The system now evaluates the time duration *before* processing a success, guaranteeing an immediate account switch/re-login if the configured time limit is breached, regardless of the final generation outcome.
- **Background Event Loop Unblocking**: Fixed a critical backend traffic jam where the CPU-intensive Watermark Removal (LaMa) process blocked FastAPI's main event loop for several seconds. Image post-processing is now safely delegated to an asynchronous background thread (`asyncio.to_thread`), keeping the UI metrics 100% responsive and preventing false timeout drops during active image refinement.
- **Time Threshold Reset UI**: Added a dedicated **Time Threshold Elapsed** monitor and a manual **🔄 Reset** button to the Reject Rate Stats dialog. This allows users to track exactly how much "duty cycle" time remains for the active account and manually extend the session if desired.
- **Diagnostic UI Cleanup**: Removed the temporary `(✅ API OK)` debug status from the Dashboard after verifying the stability of the new synchronous API requests.
