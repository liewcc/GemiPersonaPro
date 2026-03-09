# 🧠 Advanced Algorithm: Inverse Alpha & LaMa

GemiPersonaPro achieves near-perfect watermark removal by combining high-precision mathematics with state-of-the-art AI. This page details the logic behind our **Hybrid Cleaning System**.

---

## 1. Inverse Alpha Compositing (Math)
The most efficient way to remove a watermark is to "unblend" it using the original alpha compositing formula.

### The Problem
When a watermark (Logo) is overlaid on an image (Background), the resulting color $C_{res}$ is:
$$C_{res} = C_{logo} \cdot \alpha + C_{bg} \cdot (1 - \alpha)$$

### The Solution: "Unblending"
If we know the exact color $C_{logo}$ and the transparency $\alpha$ of the watermark, we can solve for the original background $C_{bg}$:
$$C_{bg} = \frac{C_{res} - C_{logo} \cdot \alpha}{1 - \alpha}$$

In GemiPersonaPro, we pre-capture the watermark over a neutral background (`bg_48/96.png`) to derive a pixel-perfect alpha map. This process is nearly instantaneous and preserves 100% of the original image detail.

---

## 2. LaMa Inpainting (AI)
While mathematics is precise, compression artifacts or slight position offsets (sub-pixel shifts) can sometimes leave faint "ghosts" or noise. This is where AI steps in.

**LaMa (Large Mask Inpainting)** is a deep learning model specifically designed for resolution-robust image completion. Instead of just blurring, it analyzes the semantic structure of the image to fill the "hole" left by a watermark with contextually accurate textures.

---

## 3. The Hybrid Workflow
We don't choose one over the other; we use both in a specific sequence:
1.  **Math Pass**: The Inverse Alpha algorithm performs the heavy lifting, restoring the vast majority of the image data losslessly.
2.  **AI Pass**: The LaMa model then "refines" the restored area, smoothing out any remaining noise or compression artifacts.

**Result**: A clean, artifact-free image processed in under 5 seconds.

---

## 💎 Credits & Attributions
GemiPersonaPro stands on the shoulders of giants. We would like to give full credit to the original creators of these algorithms:

### [Allen Kuo (allenk)](https://github.com/GargantuaX)
**The Pioneer of Gemini Watermark Removal**. 
Allen Kuo authored the original research and implementation of the **Reverse Alpha Blending** method specifically for Gemini AI. His mathematical approach is what makes the high-precision restoration in this project possible.

### [Sanster (Chenxi Liu)](https://github.com/Sanster) & [IOPaint](https://www.iopaint.com/)
**The Masters of AI Inpainting**.
Sanster is the creator of **IOPaint** (formerly LaMa-Cleaner), the industry-leading open-source framework for image editing. Our integration of the **LaMa** model relies heavily on the standards and models established by his incredible work.

---
*Technical Note: All AI processing is performed locally on your machine. No data is sent to external servers for cleaning.*
