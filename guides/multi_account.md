# 👥 Multi-Account & Auto-Switching Guide

GemiPersonaPro supports seamless management of multiple Gemini accounts. This guide explains how to set them up and how the system automatically rotates through them when quotas are reached.

---

## 1. Adding Multiple Profiles
Before the system can switch accounts, you must first register them as browser profiles.
1. Go to **Gemini Setup**.
2. **Stop Browser** (if running).
3. Click **"Add Profile"** and log in with your first Google account (e.g., `Alpha.Demo.User@gmail.com`).
4. Once logged in, close the browser window.
5. Repeat the process for your other accounts (`Blueberry.Test.99`, `Cloud.Support.Sample`, etc.).

---

## 2. Configuring the Account Table
To enable automation to "know" your accounts, you must list them in the system configuration.
1. Navigate to the **System Config** page.
2. Locate the **User Login Credentials** section.
3. Add your account usernames (the part before `@gmail.com` is usually enough) into the table.
4. Click **"Save Credentials Tables"**.

---

## 3. Switching Profiles
### Manual Switching
On the **Gemini Setup** page, use the **ACCOUNT ACTIONS** section:
- **Navigation**: Use "Switch to Next" or "Switch to Last" to cycle through your saved accounts.
- **Direct Select**: Choose a specific account from the dropdown menu.
- **Observation**: The browser will automatically restart and log into the selected profile.

### Automated "Chain" Switching
This is where the power of GemiPersonaPro shines. During an automation loop:
1. **Quota Detection**: If the active account (e.g., `Alpha`) hits a daily limit, the system detects the "Quota Full" message.
2. **Auto-Switch**: The program automatically stops the current session and restarts using the *next* account in your table (e.g., `Blueberry`).
3. **Continuous Workflow**: It continues generating images until the next quota is hit, then moves to the third account (`Cloud`).
4. **Safety Stop**: If the system cycles through all available accounts and returns to the first one that was already full, the process stops to prevent infinite looping.

---

## 4. Verification Tools
- **Check Login Status**: Use this button in the side panel to confirm which account is currently active, especially when running in **Headless Mode**.
- **Status Bar**: The Dashboard's top bar always displays the current `Active User`.

---
*Tip: Keep your account table sorted in the order you want the "chain reaction" to occur!*
