# 🚀 Quick Start Guide

This guide will walk you through the first-time setup and your first automation run with GemiPersonaPro.

## Phase 0: Pre-flight Requirements
Before running the setup, ensure your Windows system is ready:
1. **VC++ Redistributable**: [Download and install this](https://aka.ms/vs/17/release/vc_redist.x64.exe) first. This is the only mandatory system component.
2. **Zero-Config Python**: You do **not** need to install Python manually. The setup script will automatically download and configure a portable Python 3.12 environment using `uv`.
3. **Download Method**: If you don't use Git, ensure you've downloaded the project as a ZIP and extracted it completely.

---

## Phase 1: Launching the System
When you run `run.bat`, the **Launcher (start.py)** will open in your browser. 
1. **Observe the Status**: Wait for the "Engine Service", "Browser", and "AI Model" to show green checkmarks ✅.
2. **Auto-Redirect**: Once everything is ready, the system will automatically redirect you to the **Dashboard** (unless you've changed the default to Gemini Setup).

---

## Phase 2: First-Time Browser Setup
Navigate to the **Gemini Setup** page from the sidebar to configure your Gemini profile.
1. **Manage Profiles**: 
   - Click **"Stop Browser"** if it is currently running.
   - Click **"Add Profile"** and follow the prompts to link your Gemini account.
   - Once added, ensure the browser is closed again.
2. **Headed Mode (for Observation)**: 
   - Ensure the "Headless Mode" toggle is **OFF**.
   - Click **"Start Browser"**. A physical browser window will open—keep this visible so you can watch the automation in action.

---

## Phase 3: Basic Manual Operation
On the **Gemini Setup** main panel, work your way from **top to bottom**:
1. **Configuration**: Set your target `Browser URL` (the Gemini Gem you want to use).
2. **Prompting**: Enter your image/video generation prompt.
3. **Execution**: Scroll down to **GEMINI ACTIONS** and click **"Send to Browser"**. 
4. **Observe**: Watch the headed browser window to see how Gemini responds.

> [!IMPORTANT]
> Mastery First: Don't start the automation loop until you are comfortable with how single actions work.

---

## Phase 4: Your First Automation Loop
Once you've mastered manual actions, let's try a single automated cycle.
1. **Watermark Settings**: Scroll to the Watermark section and set **"Fix Rounds"** to `1`.
2. **Automation Goal**: In the **GEMINI AUTOMATION** section, you can set the number of loops.
3. **Run**: Click **"Start Looping Process"**.
4. **Observe**: Watch the browser perform the full sequence: generation, watermark removal, and saving.

---

## Phase 5: Transition to Headless (Production)
When everything is working perfectly in headed mode:
1. **Stop Browser**: Click **"Stop Browser"** in the side panel.
2. **Enable Headless**: Toggle **"Headless Mode"** to **ON**.
3. **Restart**: Click **"Start Browser"** (it will now run in the background).
4. **Automate**: Click **"Start Looping Process"** to begin your production run.

---

## Phase 6: Monitoring Progress
While the browser is hidden, use the **Dashboard** to stay informed:
- **Status Bar**: Check the main panel top bar for the current browser status.
- **Detailed Stats**: Click **"📊 Reject Rate Stats"** to see a per-image breakdown of refusals and performance.
- **Gallery**: View the latest downloaded and AI-cleaned images as they arrive.
- **Service Status**: Ensure all services remain healthy.

### 💡 Pro-Tip: Background Efficiency
You don't need to keep the UI or the terminal window open while automation is running!
- **Close Anytime**: Once you've started the "Looping Process," you can safely close your browser tab and even the DOS/terminal window. The background engine will continue working until the task is complete.
- **Progress Checks**: Simply run `run.bat` again whenever you want to check the progress or view the latest images in the Dashboard.
- **Manual Stop**: If you need to stop the engine entirely, go to the **Gemini Setup** side panel and click **"Stop Engine"**.

### 🧠 Intelligent Memory Management
GemiPersonaPro is designed to be lightweight on your system:
- **Auto-Timeout**: The engine will automatically shut down after a period of inactivity (defined by the `timeout` in System Config).
- **Automation Safety**: If a loop is running, the engine waits for it to finish before starting the timeout countdown.
- **Resource Release**: When the engine stops, the **LaMa AI model** is automatically unloaded, fully releasing your system's RAM/VRAM.

---

*Happy Automating!*
