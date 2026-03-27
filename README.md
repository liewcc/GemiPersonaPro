<p align="center">
  <img src="sys_img/logo.png" width="250" alt="GemiPersonaPro Logo">
</p>

**Contents**
- [📜 Project Origin](#-project-origin)
- [🚀 Features](#-features)
- [📖 Documentation](#-documentation)
  - [⏱️ Quick Start Guide](./guides/quick_start.md)
  - [📊 Monitoring & Stats](./guides/monitoring_stats.md)
  - [👥 Multi-Account Management](./guides/multi_account.md)
  - [🔄 Loop Control Config](./guides/loop_control.md)
  - [🧠 AI Watermark Technology](./guides/watermark_removal.md)
  - [🛡️ Asset Sanitizer Page](./guides/asset_sanitizer.md)
  - [🔖 Gems Bookmark Guide](./guides/gems_bookmark.md)
  - [🧠 Advanced Algorithm Guide](./guides/advanced_algorithm.md)
- [🛠️ Quick Setup](#️-quick-setup)
- [📂 Project Structure](#-project-structure)

# GemiPersonaPro

GemiPersonaPro is a powerful automation tool designed to streamline image generation and asset management using Gemini. It features a built-in browser engine for automation and an AI-powered "Asset Sanitizer" for high-quality watermark removal and image refinement.

## 📜 Project Origin

GemiPersonaPro is the successor to the original [GemiPersona](https://github.com/liewcc/GemiPersona) project. While the initial version proved the concept, it faced stability challenges when handling complex multi-threaded tasks. 

To address this, GemiPersonaPro was completely rewritten to use a more robust API-based architecture. This version introduces:
- **Silky Smooth UI**: A completely redesigned interface for a more fluid user experience.
- **Integrated Watermark Removal**: Professional-grade cleaning built directly into the flow.
- **Enhanced Stability**: Optimized for reliable automation and multi-tasking.

## 🚀 Features

- **Gemini Automation**: Automate image and video generation prompts directly within the Gemini interface.
- **Asset Sanitizer**: Professional-grade watermark removal using a hybrid approach (Inverse Alpha + LaMa AI Refinement).
- **Session Management**: Securely handle multiple browser profiles and sessions.
- **Efficiency Monitoring**: Track API "Refusals" and browser "Resets" in real-time with a dedicated statistics dashboard.
- **Loop Control**: Advanced automation to handle server overloads and bypass intermittent filters via intelligent retries.
- **Real-time Dashboard**: Monitor generation progress, quota status, and manage your library.

## 📖 Documentation

> [!TIP]
> **New User?** Follow our [🚀 Quick Start Guide](./guides/quick_start.md) or learn about [👥 Multi-Account Management](./guides/multi_account.md).

## 🛠️ Quick Setup

### 1. Prerequisites
- Python 3.10 or higher.
- Git installed on your system.

### 2. Installation
Clone the repository and run the setup script:
```bash
git clone https://github.com/liewcc/GemiPersonaPro.git
cd GemiPersonaPro
setup.bat
```
*The setup script will automatically create a virtual environment, install dependencies, and download the required AI models (LaMa).*

### 3. Running the App
After setup, simply run:
```bash
run.bat
```

### 4. Background Image Notifier
GemiPersonaPro natively supports a silent **Background Image Notifier** (`image_notifier.py` / `start_notifier.vbs`) that runs as an **independent program** in your Windows System Tray.
- **Independent Operation**: Because it runs entirely independent from the Streamlit UI, **it will continue to operate even after you close the Streamlit browser window**. This is designed so you can step away from the setup page and still receive updates.
- **Function**: It monitors your configured save directory and pops up a native Windows UI notification (including your currently active profile state) whenever new images are successfully downloaded.
- **How to Control**: You can toggle the notifier on/off directly from the **Dashboard UI**, using the **Start/Stop Notifier** button on the bottom left. Alternatively, to stop it completely when the UI is closed, look for its blue `GemiPersona Notifier` icon in your Windows right-bottom SystemTray, right-click, and select **"Quit"**.

## 📂 Project Structure
- `start.py`: The main launcher and system check.
- `pages/`: Streamlit UI pages (Dashboard, Setup, Sanitizer).
- `browser_engine.py`: The core automation logic.
- `lama_refiner.py`: AI model handling for image refinement.

---
*Developed by liewcc*
