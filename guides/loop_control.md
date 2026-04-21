# 🔄 Loop Control Config: Automation Strategy guide

The **Loop Control Config** is the "brain" of GemiPersonaPro's automation. It determines how the system navigates through multiple accounts and how it reacts when things don't go as planned. 

This guide explains the deeper purpose of each control and how to configure them for maximum efficiency.

---

## 1. ♾️ Infinite Table Loop (The "Perpetual Mode")

**Purpose**: To keep the automation running identity-loops indefinitely without manual intervention.

- **How it Works**: Normally, automation stops once the last account in your `Credentials Table` is processed. If this is enabled, the system won't stop. Instead, it enters a "Cooldown" state.
- **Cooldown (Minutes)**: How long the system waits after finishing the last account before jumping back to the very first account and starting again.
- **Strategic Benefit**: Perfect for 24/7 generation. By setting a cooldown (e.g., 60 minutes), you give your accounts time to "rest" and potentially reset their own daily quotas before the next loop begins.
- **⏱ Unit**: **Minutes**. (e.g., 1440 = 24 hours).

## 2. ⏱ Time Threshold (The "Account Duty Cycle")

**Purpose**: To prevent "Session Stale" and rotate accounts based on time, even if they haven't hit their quota.

- **How it Works**: Monitors how long a single account has been active in the current session.
- **Threshold (Minutes)**: Once an account has been running for this many minutes, the system triggers an action (Next Profile or Re-login).
- **Strategic Benefit**: 
    - **Freshness**: Browser sessions can become slow or buggy over hours. Periodic rotation keeps the engine responsive.
    - **Detection Avoidance**: Regularly switching profiles mimics more natural human behavior compared to one account generating for 10 hours straight.
- **⏱ Unit**: **Minutes**.

## 3. 🚫 Refused Threshold (Filter Management)

**Purpose**: To handle Gemini's "I can't create that image" refusals intelligently.

- **How it Works**: If Gemini refuses a prompt, the system retries. If the number of refusals for a *single image* hits this limit, it assumes the current account's filter is too "sensitive" at the moment.
- **Action**: Usually switches to the **Next Profile** to try the same prompt on a different account.

## 4. 🔄 Reset Threshold (Stability Management)

**Purpose**: To recover from server-side hangs or "Application Reset" errors.

- **How it Works**: If the page crashes or requires a refresh too many times for one image download, the system intervenes.
- **Action**: Switches to a fresh profile to avoid getting stuck in a loop of server-side instability.

## 5. ⏯️ Pausing & Resuming (Continue Session)

**Purpose**: To safely pause a long-running automation session, or recover from an unexpected crash, without losing your current progress metrics.

- **How it Works**: 
    - During an active session, clicking **Stop Looping Process** will safely halt the automation. 
    - The **Continue Session** button will then become available.
    - Clicking it resumes the automation loop right where it left off.
- **State Hydration**: Even if you completely shut down the application or restart your computer, the engine uses "State Hydration" to rebuild your previous session's statistics (Successes, Refusals, Resets) from the `reject_stat_log.json` log file.
- **Strategic Benefit**: You can adjust settings (like modifying the Prompt) mid-session, or recover from a network outage, and your Reject Rate Chart will continue uninterrupted instead of resetting to zero.
- **Goal Protection**: The system prevents you from continuing a session if the originally configured Target Goal has already been reached.

---

## ⚙️ Configuration Summary

| Parameter | Unit | Purpose | Recommended |
| :--- | :--- | :--- | :--- |
| **Infinite Loop Cooldown** | **Minutes** | Wait time before restarting the account list. | `60 - 120` |
| **Time Threshold** | **Minutes** | Max time per account before rotating. | `30 - 60` |
| **Refused Threshold** | Count | Retries before giving up on a filtered account. | `5` |
| **Reset Threshold** | Count | Retries before giving up on a crashing account. | `3` |

---

> [!TIP]
> **Balance is Key**: Setting a **Time Threshold** of 30 minutes combined with an **Infinite Loop** cooldown of 60 minutes ensures that your accounts are used in healthy bursts, significantly reducing the chance of long-term account flags or shadow-bans.

---
*Back to [README](../README.md)*
