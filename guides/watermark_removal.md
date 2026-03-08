# 🧠 AI Watermark Removal Technology

GemiPersonaPro uses the **LaMa (Large Mask Inpainting)** model to intelligently remove watermarks from AI-generated images. This page explains the underlying technology and how to configure it for optimal performance.

---

## 1. Core Technology: LaMa AI
Unlike traditional cropping or simple blurring, LaMa can "re-imagine" the area behind a watermark by analyzing the surrounding textures and colors. This results in a much cleaner, professional finish.

### 🧩 Hybrid Processing
The system uses a hybrid approach:
- **Inverse Alpha**: A lightning-fast, lossless method for standard watermarks.
- **LaMa Refinement**: An AI-powered pass that handles complex logos, offsets, or multiple watermarks.
- **Result**: The two are combined to ensure the highest possible image quality.

---

## 2. Hardware Configuration
You can find these settings in the **Gemini Setup** page under **WATERMARK SETTINGS**:

| Feature | Requirement / Detail |
| :--- | :--- |
| **System RAM** | **16GB+ recommended**. The model and its dependencies consume ~3GB when active. |
| **Device Choice** | **CPU** or **GPU (NVIDIA)**. GPU is faster, but CPU is surprisingly efficient (only a few seconds per image). |
| **VRAM** | 8GB is plenty for GPU mode. |

> [!NOTE]
> **Zero Resource Leak**: When the engine stops or times out, the LaMa model is automatically unloaded from your RAM/VRAM.

---

## 3. Storage & Organization
- **Non-Destructive**: The AI **never** overwrites your original downloaded images.
- **`processed/` Folder**: All cleaned versions are stored in a `processed/` sub-directory within your chosen download folder.
- **Comparison**: This structure allows you to compare the original and the AI-cleaned version at any time in the Dashboard.

---
*Next Step: Learn how to manage these files on the [🛡️ Asset Sanitizer Page](./asset_sanitizer.md).*
