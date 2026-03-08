# ✨ AI Sanitizer & Watermark Removal Guide

GemiPersonaPro features a professional-grade "Asset Sanitizer" that uses the LaMa AI model to remove watermarks and clean up generated images.

---

## 1. How to Enable AI Cleaning
You can configure the AI settings on the **Gemini Setup** page under the **WATERMARK SETTINGS** section:
- **Toggle On**: Enable the "Remove Watermark" feature.
- **Hardware Selection**: Choose between **CPU** or **GPU** (NVIDIA).
  - *Note from the Author*: Even on older systems or using CPU, the process usually takes only a few seconds.

---

## 2. System Requirements
To ensure smooth AI processing, your computer should meet these criteria:
- **System RAM**: **16GB or higher** is strongly recommended. The AI models and dependencies consume about 3GB of RAM when loaded.
- **VRAM (for GPU mode)**: 8GB is sufficient.
- **Auto-Unload**: Don't worry about memory leaks! The engine automatically unloads the LaMa model and releases RAM/VRAM when the engine times out or is stopped.

---

## 3. The Processing Logic
When automation is running, the system follows a safe and organized workflow:
1. **Hybrid Mode**: The program automatically uses a hybrid approach to detect and remove watermarks.
2. **Non-Destructive Saving**: Processed images are saved in a sub-folder named `processed/` inside your main download directory.
3. **Comparison**: This ensures your original images are never overwritten and allows you to compare the "Before" and "After" results.

---

## 4. Viewing Results in the Dashboard
The **Dashboard** gallery is your control center for quality checks:
- **Comparison Toggle**: Turn on **"View Cleaned AI Picture"** in the side panel. 
- **The Magic Switch**: When enabled, the gallery will swap the original images with their counterparts from the `processed/` folder. You can toggle this back and forth to see exactly how well the AI performed.

---

## 5. Manual Refinement
If the AI misses a spot or if you want absolute perfection, you can refine images manually:
1. **Gallery Action**: Click the **"Remove Watermark"** button on any image in the Dashboard (ensure automation is stopped first).
2. **Manual Dialog**: A popup will appear. Use the brush tool to paint over the remaining watermark areas.
3. **Save**: Click Save to update the cleaned version in the `processed/` folder.

---
*Tip: Always check your images with the comparison toggle before finalizing your collection!*
