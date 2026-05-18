# 🖼️ Image Reference Modes

The **IMAGE REFERENCE** section on the Gemini Setup page provides two powerful ways to use existing images to guide your workflow. This guide explains how each mode works and when to use them.

---

## 1. Extract Metadata From Image

### Purpose
This mode is designed to **retrieve the creative instructions** (metadata) embedded within an existing image without directly uploading the image itself for modification.

### How it works
1. **Extraction**: The system reads the selected image file and extracts its embedded metadata (specifically the original generation prompt) and any attached reference URLs.
2. **Population**: It automatically fills this information into your current **Prompt** box and the **UPLOAD FILES TO BROWSER** queue.
3. **Usage**: This is ideal when you want to recreate a similar image or use a previous successful prompt as a starting point for a new generation, without necessarily using the original image as a visual input.

---

## 2. Modify Image

### Purpose
This mode tells Gemini to use the selected image as a direct visual input and **apply modifications to it** based on your prompt.

### How it works
1. **Selection & Prompting**: When you select an image (e.g., `image.png`) and apply this mode, the system automatically prepends `modify image "image.png":` to your prompt.
2. **Automated Upload**: The URL/path of the selected image is saved to the **UPLOAD FILES TO BROWSER** queue. When the automation engine runs, it will automatically upload this specific image to Gemini along with your instructions.
3. **Metadata Lineage**: When Gemini finishes generating the new, modified image and it is downloaded back to your local computer, the system **preserves the lineage**. It takes the metadata from the original reference image and injects it into the newly generated image. This ensures you never lose the history of how an image evolved.

### When to use
Use this mode when you want Gemini to perform tasks like outpainting, inpainting, style transfer, or specific edits on an existing image, and you want the resulting file to carry forward the original prompt history.
