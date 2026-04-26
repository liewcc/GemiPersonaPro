# 📊 Account Health & Cycle Management Guide

The **Account Health** page is a dedicated diagnostic suite designed to help you monitor, analyze, and maintain the performance and stability of your automated Google accounts. It acts as the "medical record" for your automation engine, tracking every successful generation, refusal, reset, and failure.

The page is divided into two primary tabs: **Account Health Analysis** and **Automation Cycle Management**.

---

## 1. Account Health Analysis

This powerful visual dashboard parses `engine.log` to visualize the performance of your account rotation. It is essential for identifying problematic accounts that trigger frequent refusals or cause page resets, allowing you to optimize your automation settings.

### View Modes
Use the dropdown menu to select the scope of your analysis:
- **Full Loading History (All Events)**: A chronological audit trail of every loading attempt across all accounts. Best for system-wide stability monitoring.
- **Detailed History: Active Account**: Filters the data to show only events for the currently active profile. Useful for deep-diving into a single account's behavior.
- **Latest Summary (All Accounts)**: A high-level overview showing the most recent loading status and duration for every account in the system.
- **Detailed History: [Specific Account]**: Focuses the analysis on any individual account found in your system.

### Performance Visualizations
When viewing detailed histories, toggle **Plot Graph** to access interactive Altair charts:

#### Loading Duration (Bar Chart)
- **Y-Axis**: Duration in **minutes (minite)**. Choose between Linear or Logarithmic scales.
- **Colors**: 
  - 🟩 **Green**: Success
  - 🟪 **Purple/Blue**: Reject (Safety filter refused the prompt)
  - 🟧 **Orange**: Reset (Page crashed or required a hard refresh)
  - 🟥 **Light Red**: Fail (A success was detected but the file was missing/corrupted)
- **Session Banding**: The chart uses alternating Base/Light colors for the bars to visually group events by account session. This makes it easy to see exactly where automated account switches occurred. **Continue Session** (Stop → Resume without resetting) preserves the same session color — only a fresh start (Round 1) or a real account switch creates a new color band.

#### Reject Rates (Line Chart)
- **X-Axis**: Successful image downloads.
- **Y-Axis**: Cumulative count of Refusals or Resets encountered *before* achieving that success.
- **Purpose**: A rising trend line indicates that an account is becoming "tired" or heavily filtered. If you see consistent spikes in rejects, it suggests the account needs a longer cooldown or your prompts need more variation.

### Status Indicators & Engine Logic
The parser uses a robust state-tracking mechanism to ensure data integrity:
- **Session Boundaries**: The system detects physical log markers (like `Automation Finished.` or `Profile switched to <username>`) to correctly group events, even if you manually intervene.
- **Orphan Recovery**: The system captures `Saved:` events even if the initial `Loading` marker was missed due to manual page reloads or network hiccups.

---

## 2. Automation Cycle Management

Over time, your `engine.log` file can become cluttered with test runs, failed sessions, or old data that skews your current performance charts. The **Cycle Management** utility allows you to safely prune this file.

### Cycle Identification
- **Intelligent Parsing**: Automatically scans the system log to identify unique, complete automation "Cycles" (defined from a fresh start of Round 1 until an explicit stop signal).
- **Continue Session Grouping**: The system is smart enough to group "Continue Session" triggers within their original parent cycle, preventing fragmented entries in the table.

### Log Maintenance & Decluttering
- **Data Selection**: Provides an interactive table listing every identified cycle, showing its **Start Time**, **Stop Time**, **Cycle ID**, **Successful Downloads**, and the total number of log lines it occupies.
- **Selective Deletion**: 
  1. Check the boxes under the **Select for Deletion** column for any historical cycles you wish to remove.
  2. Click **🗑️ Delete Selected Cycles**.
  3. **Warning**: This action permanently deletes the associated lines from your physical `engine.log` file.
- **Why use this?** Use this tool to remove "stale" or early test data. Deleting bad cycles prevents them from cluttering the performance charts in the **Account Health Analysis** tab and reduces the overall log file size, leading to faster loading times for the dashboard.

---

*💡 **Pro Tip**: If a specific account shows a consistent "Reject" pattern in the graphs, consider using the System Config page to increase the **Quota Cooldown** hours for your system, or manually bypass that account in the Credentials table.*
