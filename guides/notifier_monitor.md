# 🔔 Notifier & Monitor Guide

## Purpose & Design Philosophy
GemiPersonaPro's **Notifier (System Tray Notifier)** and **Monitor (Performance Dashboard)** are lightweight desktop tools designed to run independently from the main application (Streamlit Web UI).

Their primary **function and purpose**:
When you do not need to open a heavy browser interface, or when you are working on other tasks on your local machine (like editing documents, gaming, or video editing), these tools can run silently in the background. They allow you to monitor the real-time progress and health status of the underlying automation Engine and the 4K Upscaler without needing to switch windows.

They consume very little system resources. Even if you close the GemiPersonaPro browser UI, as long as the engine is still running, they will continue to provide a seamless monitoring experience.

---

## 1. Background Image Notifier
`image_notifier.py` / `start_notifier.vbs` is a silent, independent program that runs in the Windows system tray.

### Core Features
- **Independent Lifecycle**: It runs completely separate from the Streamlit process. This means you can confidently close the browser interface, and the notifier will stay on duty.
- **Dual-Directory Smart Tracking**: It concurrently monitors your **Automation Save Directory** and your **4K Upscaler Output Directory**. As soon as a new image is generated, a borderless notification pops up in the bottom right corner of your screen.
- **Dynamic State Tracking**:
  - The notification UI uses large typography to display the unacknowledged counts for "Auto" and "Upscaler" side-by-side.
  - **Red Highlight**: The notifier tracks and displays how many "unseen" images have been cumulatively generated since you last manually acknowledged a popup.
  - If a specific pipeline (like the Upscaler) is not running, the corresponding text will intelligently dim to grey, letting you identify the current system activity state at a glance.

### Quick Interaction Panel
When a notification pops up, you can perform quick actions directly:
- **📁 Download / Upscale Folder**: One-click direct access to the Windows File Explorer directory where the corresponding images are stored.
- **📊 Monitor**: Instantly wake up the independent `Monitor` dashboard to view detailed performance reports.
- **Open GemiPersona**: A smart launch button. If the main engine is not running, clicking this will directly execute `run.bat`. If the system is already running, the button will be automatically disabled to prevent duplicate process launches.

### How to Control
- **Start**: Click the **Start Notifier** button located at the bottom left of the Dashboard page.
- **Stop**: Locate the blue `GemiPersona Notifier` icon in your Windows system tray at the bottom right, right-click it, and select **"Quit"**. When safely exiting, it will automatically close any linked notification popups and Monitor panels for you.

---

## 2. GemiPersona Monitor (Desktop Performance Dashboard)
`monitor_window.py` is a lightweight, transparent data panel built with Tkinter. It links with the Notifier to provide a geeky data dashboard that rivals the web Dashboard, without consuming any browser resources.

### Core Features
- **Zero-Burden CPU Optimization (Smart Polling)**:
  - The Monitor does not blindly consume system performance. It utilizes incremental log parsing technology, keeping CPU usage near **0%** when the system is idle.
  - For data presentation, it directly aligns with the lightweight API (`/browser/automation/stats`) and `reject_stat_log.json`, ensuring the numbers displayed here are **exactly identical** to the main Dashboard.

### Rich Data Insights
- **Global Statistics (Top Row)**:
  - **Total Cycles**: The number of automation loops the underlying engine has undergone.
  - **Images / Refused / Reset**: Aggregates the total number of images downloaded, the total number of Gemini service refusals, and the total number of engine browser crash restarts across the entire automation history.
- **Current Account Health Status (Second Row)**:
  - Displays the account currently being dispatched in real-time (stripped of the long email domain suffix for a clean short name).
  - Shows the **Switch At** time for the account, along with its contributed image output and encountered resistance (Refused / Reset) during this session.
- **Cycle Performance Insights Charts**:
  - Transforms complex logs into visual bar charts.
  - **By Account Chart**: Displays the image production capacity per session with alternating colors (dark and light green) based on accounts. Sessions with zero output are intelligently filtered out to keep the interface clean.
  - **Interactive Tooltip**: When you hover your mouse near a bar, the bottom right corner of the chart elegantly displays the account name and exact numbers for that bar. It is intuitive and never spawns an out-of-bounds popup that causes the program to flicker.

### Quick Actions Panel (Process Latest Download Image)
Located directly beneath the performance charts, this panel allows you to interact with the most recently generated automation output without leaving the Monitor window:
- **View Image**: Instantly opens the single most recently downloaded image in the default Windows photo viewer.
- **Move to New Folder**: Prompts for a destination folder (defaulting to the current download directory) and instantly moves the latest image. If a sanitized version exists in the `processed/` subfolder, it automatically recreates the structure and moves that file as well.
- **Delete**: A native, safe integration with the Windows Recycle Bin (using no external dependencies) to quickly discard the most recently downloaded image and its `processed` counterpart, keeping your workflow clean and distraction-free.

With the combination of the Notifier and Monitor, GemiPersonaPro truly achieves a "fully automated background production black box," freeing you from browser constraints.
