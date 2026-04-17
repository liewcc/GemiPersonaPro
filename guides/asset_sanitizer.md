# 🛡️ Asset Sanitizer Page Guide

The **Asset Sanitizer** (found on the sidebar) is your dedicated workstation for auditing, managing, and refining your generated assets.

---

## 1. Interface Layout
When you first open the page, the main area is an introduction. Use the **Sidebar** to get started:
1. **Select Folder**: Choose a download directory to load its contents.
2. **Select File**: Choose a specific image for deep inspection.
3. **Gallery View**: Once a folder is selected, the page transforms into an interactive grid of your images.

---

## 2. Metadata & Prompt Audit
GemiPersonaPro tracks more than just pixels. In the Asset Sanitizer, you can:
- **View Metadata**: See the exact prompt, source URL, and timestamp for every image.
- **Edit & Save**: Modify metadata if needed and save it back to the JSON database.
- **Re-Generate**: One-click to send an old prompt back to the Gemini setup for a new iteration.

---

## 3. Manual Watermark Removal
While automation handles most cleaning, the Asset Sanitizer gives you ultimate control:
- **Precision Popup**: Click **"Remove Watermark"** on any image to open the manual editor.
- **Brush & Mask**: Paint over exactly what you want to remove. 
- **AI Refinement**: The editor uses the same LaMa AI engine to clean the painted areas.
- **Save**: Your manual fixes are saved into the `processed/` folder, preserving the original.

---

## 4. Batch Processing
On the Asset Sanitizer page, you can trigger batch operations for entire sequences:
- **Resequence & Export**: Automatically copy and rename all images into a new sibling folder, sequentially numbered starting from 1 (e.g. `001.png`, `002.png`). Padding is detected automatically, and the `processed/` subfolder is synchronized if present. The original folder and files are never modified.
- **Range Control**: Specify a start and end image number (e.g., `1` to `50`).
- **Batch Clean**: Click to run the AI sanitizer across the entire selected range.

---

## 5. Visual Comparison
Use the **"Show AI-Cleaned Images"** toggle in the sidebar of the **Dashboard** or **Asset Sanitizer**:
- **Magic Swap**: Instantly replace the gallery view with the cleaned versions from the `processed/` folder.
- **Quality Check**: Toggle it back and forth to ensure the AI removal is perfect.

---
*Tip: Use the Asset Sanitizer for final quality control before publishing your work!*
