# 🔄 Loop Control Config (循环控制配置)

The **Loop Control Config** is an advanced automation feature in GemiPersonaPro designed to maximize image generation success rates by intelligently handling server-side restrictions and overloads.

## 📖 Overview

When generating images with Gemini, you may encounter two primary types of interruptions:
1.  **Refusals**: Gemini's safety filters or "sensitive prompt" blockers prevent an image from being generated.
2.  **Resets**: The server becomes overloaded, causing the page to hang or require a refresh.

The **Loop Control Config** allows you to automate the response to these events, turning potential failures into opportunities for success.

## 🛠️ How it Works

This feature monitors the generation process and triggers specific actions based on user-defined thresholds.

### 1. Refusal Management (`refused_threshold`)
Gemini's image filter is dynamic and influenced by server load. Sometimes, a prompt that is rejected during peak hours might be accepted if retried when the server is "busy" or during a different session, as the filter's strictness can vary.
- **Action**: By seting a refusal threshold, the system will retry the download multiple times. If the limit is reached, it will automatically perform a **Next Profile** switch or **New Chat** restart.
- **Benefit**: Increases the probability of bypassing occasional filter false positives.

### 2. Reset Management (`reset_threshold`)
Server overloads can lead to "Page Resets." Frequent resets often indicate a degraded session or a throttled account.
- **Action**: If the number of resets for a single image exceeds your threshold, the system will switch to a fresh account.
- **Benefit**: Prevents the automation from getting stuck in a loop of server errors.

## ⚙️ Configuration Parameters

You can find these settings in the **Dashboard** under the **Loop Control** section:

| Parameter | Description | Recommended |
| :--- | :--- | :--- |
| **Enable Refused Control** | Monitor and act on image rejections. | `On` |
| **Refused Threshold** | Max rejections per image before switching. | `5 - 10` |
| **Enable Reset Control** | Monitor and act on page resets. | `On` |
| **Reset Threshold** | Max resets per image before switching. | `3` |
| **Action Type** | What to do when threshold is hit (`Next Profile` or `New Chat`). | `Next Profile` |

## 💡 Pro Tip
This feature is particularly effective for high-volume automation. By allowing a few "refusals" before switching, you capitalize on the moments when Gemini's filtering is less intensive due to server traffic, significantly increasing your total successful downloads.

---
*Back to [README](../README.md)*
