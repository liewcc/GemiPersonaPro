# 🛡️ Asset Sanitizer

The **Asset Sanitizer** provides tools for auditing, managing, and refining your generated images. It is one of the core modules in the Utilities page.

## 1. Interface Layout
When you select the **Asset Sanitizer** tab, you'll see a sidebar to get started:
1. **Select Folder**: Choose a download directory to load its contents.
2. **Select File**: Choose a specific image for deep inspection.
3. **Gallery View**: Once a folder is selected, the page transforms into an interactive grid of your images.

## 2. Metadata & Prompt Audit
GemiPersonaPro tracks more than just pixels. You can:
- **View Metadata**: See the exact prompt, source URL, and timestamp for every image.
- **Edit & Save**: Modify metadata if needed and save it back to the image.
- **Re-Generate**: One-click to send an old prompt back to the Gemini setup for a new iteration.

## 3. Manual Watermark Removal
While automation handles most cleaning, the Asset Sanitizer gives you ultimate control:
- **Precision Popup**: Click **"Remove Watermark"** on any image to open the manual editor.
- **Brush & Mask**: Paint over exactly what you want to remove.
- **AI Refinement**: The editor uses the same LaMa AI engine to clean the painted areas.
- **Save**: Your manual fixes are saved into the `processed/` folder, preserving the original.

## 4. Batch Processing
You can trigger batch operations for entire sequences:
- **Resequence & Export**: Automatically copy and rename all images into a new sibling folder, sequentially numbered starting from 1. Padding is detected automatically, and the `processed/` subfolder is synchronized.
- **Range Control**: Specify a start and end image number (e.g., `1` to `50`).
- **Batch Clean**: Click to run the AI sanitizer across the entire selected range.
