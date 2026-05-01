# 🖼️ 4K Upscaler

The **4K Upscaler** is a dedicated background tool designed to enhance the resolution of your generated images using Gemini's native upscaling capabilities.

## 1. Account Requirements
To use the 4K Upscaler, you must select a **Paid Account Profile** from the settings menu. Please ensure the following conditions are met:
- **Gemini Advanced Required**: The selected account must have an active Gemini Advanced (AI Pro) subscription to access the high-resolution upscaling capabilities.
- **Profile Registration**: The account must first be logged in and saved using the "Add Profile" feature in the **Gemini Setup** page.
- **Credentials Table Verification**: The account must be successfully registered in the `USER LOGIN CREDENTIALS` table within the **System Config** page. Only accounts present in this table will appear in the Upscaler's dropdown menu.

## 2. Automated Workflow
The upscaler operates autonomously via a dedicated background worker, ensuring your Streamlit UI remains responsive:
- **Input & Output**: Select the directory containing the images you want to upscale, and the system will automatically suggest an `/Upscale` output folder.
- **Headless Operation**: Runs entirely in the background (hidden browser) by default, but can be toggled to visible mode for debugging.

## 3. Advanced Control Logic
The upscaler includes built-in safeguards for reliability:
- **🗑️ Delete Activity**: Automatically clean your Gemini history ("Last hour", "Last day", etc.) either before starting or after the upscaling job finishes. This prevents your Gemini history from becoming cluttered with upscaling requests.
- **🔄 Max Redo Limit**: If the AI refuses to upscale an image, the system will attempt to click "Try Again". If it exceeds your defined retry limit, it will safely skip the image and continue to the next one to prevent the automation from stalling.

## 4. Real-Time Monitoring
- **Progressive Log**: Watch the background engine's live terminal output directly within the dashboard.
- **Status Indicators**: The file list instantly reflects whether an image is Processing (`🔄`), Skipped (`💨`), Failed (`❌`), or Successfully Completed (`✅`).
