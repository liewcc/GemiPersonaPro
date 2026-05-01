# 🛠️ Utilities Page Guide

The **Utilities** page is your dedicated workstation for auditing and managing generated assets, organizing Gemini "Gems", and performing post-generation enhancements like high-resolution upscaling. This page is divided into three main tabs: **Asset Sanitizer**, **Gems Bookmark**, and **4K Upscaler**.

---

## 🛡️ Tab 1: Asset Sanitizer

The Asset Sanitizer provides tools for auditing, managing, and refining your generated images.

### 1. Interface Layout
When you select the **Asset Sanitizer** tab, you'll see a sidebar to get started:
1. **Select Folder**: Choose a download directory to load its contents.
2. **Select File**: Choose a specific image for deep inspection.
3. **Gallery View**: Once a folder is selected, the page transforms into an interactive grid of your images.

### 2. Metadata & Prompt Audit
GemiPersonaPro tracks more than just pixels. You can:
- **View Metadata**: See the exact prompt, source URL, and timestamp for every image.
- **Edit & Save**: Modify metadata if needed and save it back to the image.
- **Re-Generate**: One-click to send an old prompt back to the Gemini setup for a new iteration.

### 3. Manual Watermark Removal
While automation handles most cleaning, the Asset Sanitizer gives you ultimate control:
- **Precision Popup**: Click **"Remove Watermark"** on any image to open the manual editor.
- **Brush & Mask**: Paint over exactly what you want to remove.
- **AI Refinement**: The editor uses the same LaMa AI engine to clean the painted areas.
- **Save**: Your manual fixes are saved into the `processed/` folder, preserving the original.

### 4. Batch Processing
You can trigger batch operations for entire sequences:
- **Resequence & Export**: Automatically copy and rename all images into a new sibling folder, sequentially numbered starting from 1. Padding is detected automatically, and the `processed/` subfolder is synchronized.
- **Range Control**: Specify a start and end image number (e.g., `1` to `50`).
- **Batch Clean**: Click to run the AI sanitizer across the entire selected range.

---

## 🔖 Tab 2: Gems Bookmark

Gemini "Gems" are custom versions of Gemini that you can create for specific tasks. The **Gems Bookmark** feature is a powerful tool for maintaining consistency in your AI generations.

### 1. The Power of Gems: Character Consistency
One of the biggest challenges in AI generation is keeping a character's appearance the same across different scenes. Gems solve this perfectly:
1.  **The "Avatar" Strategy**: Create a Gem in your browser and upload a reference photo of your character.
2.  **Fixed Identity**: Because the Gem "remembers" the reference photo, you don't need to re-upload it every time.
3.  **Varying the Scene**: Simply send different background or action prompts to that specific Gem URL. The character stays the same, while the world changes!

### 2. Managing Your Bookmarks
Navigate to the **Gems Bookmark** tab to organize your workflows:
- **Manual Add**: Enter a Name, the Gem's URL, and a short description.
- **🔍 Auto-Fetch**: Enter the URL and click "Send to Browser & Extract". The engine will navigate to the Gem, scrape its official name and description, and fill out the form for you!
- **Save**: Click Save to add it to your permanent collection (`Gems_bookmark.json`).

### 3. Quick Actions
Each saved bookmark has three main controls:
- **Send**: ⚡ **The most important button**. Clicking this sends the Gem's URL directly to your **Gemini Setup** configuration.
- **Edit**: Modify the name or description.
- **Delete**: Remove the bookmark from your lab.

---

## 🖼️ Tab 3: 4K Upscaler

The **4K Upscaler** is a dedicated background tool designed to enhance the resolution of your generated images using Gemini's native upscaling capabilities.

### 1. Automated Workflow
The upscaler operates autonomously via a dedicated background worker, ensuring your Streamlit UI remains responsive:
- **Input & Output**: Select the directory containing the images you want to upscale, and the system will automatically suggest an `/Upscale` output folder.
- **Headless Operation**: Runs entirely in the background (hidden browser) by default, but can be toggled to visible mode for debugging.

### 2. Advanced Control Logic
The upscaler includes built-in safeguards for reliability:
- **🗑️ Delete Activity**: Automatically clean your Gemini history ("Last hour", "Last day", etc.) either before starting or after the upscaling job finishes. This prevents your Gemini history from becoming cluttered with upscaling requests.
- **🔄 Max Redo Limit**: If the AI refuses to upscale an image, the system will attempt to click "Try Again". If it exceeds your defined retry limit, it will safely skip the image and continue to the next one to prevent the automation from stalling.

### 3. Real-Time Monitoring
- **Progressive Log**: Watch the background engine's live terminal output directly within the dashboard.
- **Status Indicators**: The file list instantly reflects whether an image is Processing (`🔄`), Skipped (`💨`), Failed (`❌`), or Successfully Completed (`✅`).

---
*Tip: Use the Utilities page to do final quality control on your assets, organize your Gems to switch between different "AI actors" seamlessly, and finalize your work with the 4K Upscaler!*
