import argparse
import os
import time
import sys
import datetime
from playwright.sync_api import sync_playwright, TimeoutError

import traceback

def log(msg):
    ts = datetime.datetime.now().strftime("[%H:%M:%S]")
    line = f"{ts} {msg}\n"
    print(line, end="")
    try:
        with open("upscaler.log", "a", encoding="utf-8") as f:
            f.write(line)
    except:
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()

    # Create lock file
    with open("upscaler.lock", "w") as f:
        f.write(str(os.getpid()))

    try:
        if not os.path.isdir(args.input):
            log(f"Error: Input directory {args.input} does not exist.")
            return

        os.makedirs(args.output, exist_ok=True)
        
        # Get list of images
        valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
        files = [f for f in os.listdir(args.input) if f.lower().endswith(valid_exts)]
        files.sort()
        
        if not files:
            log("No images found in input directory.")
            return

        # Create isolated sandbox for upscaler to avoid clashing with main browser
        base_dir = os.path.abspath(os.path.dirname(__file__))
        source_user_data = os.path.join(base_dir, "browser_user_data")
        
        # Look up the actual physical profile directory (e.g. "Profile 1") for the username
        physical_profile_dir = args.profile
        local_state_path = os.path.join(source_user_data, "Local State")
        if os.path.exists(local_state_path):
            try:
                import json
                with open(local_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    info_cache = state.get("profile", {}).get("info_cache", {})
                    for p_dir, p_info in info_cache.items():
                        u_name = p_info.get("user_name")
                        if u_name and args.profile.split('@')[0].lower() == u_name.split('@')[0].lower():
                            physical_profile_dir = p_dir
                            break
            except Exception as e:
                log(f"Warning: Failed to parse Local State for profile lookup: {e}")
                
        target_profile_path = os.path.join(source_user_data, physical_profile_dir)
        
        sandbox_dir = os.path.join(base_dir, "upscaler_session_sandbox")
        os.makedirs(sandbox_dir, exist_ok=True)
        sandbox_default = os.path.join(sandbox_dir, "Default")
        
        # Cleanup old junction if exists
        import subprocess
        import shutil
        if os.path.exists(sandbox_default):
            subprocess.run(['rmdir', sandbox_default], shell=True, capture_output=True)
            
        if not os.path.exists(target_profile_path):
            log(f"❌ Error: Profile path not found: {target_profile_path}")
            return
            
        # Create junction Playwright will use
        cmd = f'mklink /J "{sandbox_default}" "{target_profile_path}"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            log(f"❌ Error: Junction failed: {res.stderr.strip()}")
            return
            
        # Copy root config files just like main engine
        for f_name in ["Local State", "Variations"]:
            src = os.path.join(source_user_data, f_name)
            if os.path.exists(src):
                dest = os.path.join(sandbox_dir, f_name)
                shutil.copy2(src, dest)
                if f_name == "Local State":
                    try:
                        import json
                        with open(dest, "r", encoding="utf-8") as f:
                            state = json.load(f)
                        if "profile" in state:
                            state["profile"]["last_used"] = "Default"
                            state["profile"]["last_active_profiles"] = ["Default"]
                        with open(dest, "w", encoding="utf-8") as f:
                            json.dump(state, f)
                    except: pass
                    
        try:
            with open(os.path.join(sandbox_dir, "Last Profile"), "w", encoding="utf-8") as f:
                f.write("Default")
        except: pass

        log(f"Starting Upscaler Worker...")
        log(f"Profile: {args.profile}")
        log(f"Total Images: {len(files)}")

        with sync_playwright() as p:
            context = None
            page = None
            
            def init_browser(headless_mode):
                nonlocal context, page
                if context:
                    try: context.close()
                    except: pass
                log("Launching browser...")
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=sandbox_dir,
                        headless=headless_mode,
                        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                        ignore_https_errors=True,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={'width': 1920, 'height': 1080}
                    )
                except Exception as e:
                    log(f"❌ Failed to launch browser: {e}")
                    log("Is the profile already in use by another browser?")
                    return False
                    
                page = context.pages[0] if context.pages else context.new_page()
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => False});
                """)
                
                if not headless_mode:
                    try:
                        session = context.new_cdp_session(page)
                        info = session.send("Browser.getWindowForTarget")
                        window_id = info.get("windowId")
                        if window_id:
                            session.send("Browser.setWindowBounds", {
                                "windowId": window_id,
                                "bounds": {"windowState": "minimized"}
                            })
                    except Exception as minimize_e:
                        log(f"Warning: Could not minimize window: {minimize_e}")
                        
                log("Navigating to Gemini...")
                try:
                    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)
                    if page.locator("a[href*='ServiceLogin']").is_visible() or page.locator("input[type='email']").is_visible():
                        log("❌ Error: Not logged in. Please use the main UI to login to this profile first.")
                        return False
                except Exception as e:
                    log(f"❌ Failed to load Gemini: {e}")
                    return False
                return True

            base_headless = not args.show_browser
            current_headless = base_headless
            if not init_browser(current_headless):
                return
                
            log("✅ Logged in successfully.")

            files_to_process = files.copy()
            idx = 0
            total = len(files)
            
            status_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "upscaler_status.json"))
            status_data = {"current_file": None, "history": {}}
            def save_status():
                try:
                    import json
                    with open(status_file, "w", encoding="utf-8") as f:
                        json.dump(status_data, f, ensure_ascii=False)
                except: pass
            
            save_status()

            while idx < len(files_to_process):
                filename = files_to_process[idx]
                
                status_data["current_file"] = filename
                if filename not in status_data["history"]:
                    status_data["history"][filename] = {"status": "processing", "refusals": 0}
                save_status()
                if os.path.exists("upscaler_stop.signal"):
                    log("⛔ Stop signal received. Halting.")
                    os.remove("upscaler_stop.signal")
                    break

                in_path = os.path.join(args.input, filename)
                out_path = os.path.join(args.output, filename)
                
                if os.path.exists(out_path):
                    log(f"⏭️ Skipping {filename} (Already exists in output)")
                    idx += 1
                    continue

                log(f"[{idx+1}/{total}] Processing: {filename}")
                
                success = False
                try:
                    # Clear chat (optional, but good to keep clean)
                    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    # 1. Upload File
                    log("  -> Uploading image...")
                    with page.expect_file_chooser() as fc_info:
                        # Click the + button
                        page.evaluate('''() => {
                            const plusBtn = document.querySelector('button[aria-label="Open upload file menu"]') ||
                                            document.querySelector('button[aria-label*="upload" i]');
                            if (plusBtn) plusBtn.click();
                            else {
                                const gemsIcon = document.querySelector('mat-icon[data-mat-icon-name="add_2"]');
                                if (gemsIcon) gemsIcon.closest('button').click();
                            }
                        }''')
                        page.wait_for_timeout(1000)
                        page.evaluate('''() => {
                            const opt = Array.from(document.querySelectorAll('.menu-text, span, .mdc-list-item__primary-text'))
                                            .find(i => i.innerText.toLowerCase().includes("upload") || i.innerText.toLowerCase().includes("attach"));
                            if (opt) opt.click();
                        }''')
                    
                    file_chooser = fc_info.value
                    file_chooser.set_files(in_path)
                    page.wait_for_timeout(3000) # wait for upload
                    
                    # 2. Type Prompt
                    log("  -> Sending prompt...")
                    prompt_input = page.locator("div.ql-editor[contenteditable='true']").first
                    prompt_input.fill(args.prompt)
                    page.keyboard.press("Enter")

                    while True:
                        # 3. Wait for generation
                        log("  -> Waiting for generation...")
                        page.wait_for_timeout(5000)
                        
                        # Wait for progress bar to disappear
                        try:
                            page.locator("mat-progress-bar").wait_for(state="hidden", timeout=90000)
                            page.locator("section.processing-state_container--processing").wait_for(state="hidden", timeout=90000)
                        except TimeoutError:
                            log("  -> ⚠️ Timeout waiting for generation to finish.")
                            raise Exception("Timeout waiting for generation")
                        
                        page.wait_for_timeout(3000)

                        # Find last response img
                        last_resp = page.locator("model-response").last
                        imgs = last_resp.locator("img")
                        
                        if imgs.count() == 0:
                            try:
                                msg_text = page.evaluate('''() => {
                                    const lastResp = Array.from(document.querySelectorAll('model-response')).pop();
                                    if (!lastResp) return "";
                                    const contentNode = lastResp.querySelector('.model-response-text') || lastResp.querySelector('.message-content') || lastResp;
                                    return contentNode.innerText || contentNode.textContent || "";
                                }''')
                                if msg_text and msg_text.strip():
                                    flat_text = " ".join(msg_text.split())
                                    log(f"  -> ❌ Gemini failed/refused: {flat_text[:300]}")
                                else:
                                    log("  -> ❌ No image generated and no error message found.")
                            except Exception:
                                log("  -> ❌ No image generated.")
                            
                            log("  -> 🔄 Triggering Redo...")
                            redo_result = page.evaluate('''() => {
                                const findBtn = (sel) => document.querySelector(sel);
                                let redoBtn = findBtn('regenerate-button button') || 
                                              findBtn('button[aria-label="Redo"]') ||
                                              document.querySelector('mat-icon[data-mat-icon-name="refresh"]')?.closest('button') ||
                                              document.querySelector('mat-icon[fonticon="refresh"]')?.closest('button');
                                if (redoBtn) {
                                    redoBtn.scrollIntoView({behavior: "instant", block: "center"});
                                    redoBtn.click();
                                    return true;
                                }
                                return false;
                            }''')
                            
                            if redo_result:
                                page.wait_for_timeout(1000)
                                page.evaluate('''() => {
                                    const tryAgain = Array.from(document.querySelectorAll('.menu-text, span, button')).find(b => b.innerText.toLowerCase().includes('try again'));
                                    if (tryAgain) tryAgain.click();
                                }''')
                                status_data["history"][filename]["refusals"] += 1
                                save_status()
                                continue
                            else:
                                log("  -> ❌ Redo button not found! Cannot retry.")
                                raise Exception("No image generated and Redo failed")
                        else:
                            break

                    # 4. Download Result
                    log("  -> Downloading result...")
                    
                    target_img = imgs.nth(0) # Usually the generated image is the only large one
                    
                    target_img.scroll_into_view_if_needed()
                    page.wait_for_timeout(1000)
                    
                    # Click image to open dialog
                    target_img.click(force=True)
                    page.wait_for_timeout(2000)
                    
                    try:
                        with page.expect_download(timeout=30000) as download_info:
                            # Try to click the download button via evaluate to handle dynamic classes
                            dl_clicked = page.evaluate('''() => {
                                const icons = Array.from(document.querySelectorAll('mat-icon'));
                                const dlIcon = icons.find(i => 
                                    i.getAttribute('data-mat-icon-name') === 'download' || 
                                    i.getAttribute('fonticon') === 'download'
                                );
                                if (dlIcon) {
                                    const btn = dlIcon.closest('button');
                                    if (btn && !btn.disabled && btn.offsetParent !== null) {
                                        btn.click();
                                        return true;
                                    }
                                }
                                
                                const btns = Array.from(document.querySelectorAll('button'));
                                const dlBtn = btns.find(b => b.ariaLabel && b.ariaLabel.toLowerCase().includes('download') && b.offsetParent !== null);
                                if (dlBtn && !dlBtn.disabled) {
                                    dlBtn.click();
                                    return true;
                                }
                                return false;
                            }''')
                            
                            if not dl_clicked:
                                log("  -> ⚠️ Could not find download button in UI.")
                                page.keyboard.press("Escape")
                                raise Exception("Could not find download button")
                                
                        download = download_info.value
                        download.save_as(out_path)
                        log(f"  -> ✅ Saved: {filename}")
                        success = True
                        
                    except TimeoutError:
                        log("  -> ❌ Timeout waiting for download to start.")
                        raise Exception("Timeout waiting for download")
                    
                    # Close dialog if open
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(1000)

                except Exception as e:
                    log(f"  -> ❌ Error processing {filename}: {e}")
                    success = False

                if success:
                    status_data["history"][filename]["status"] = "success"
                    save_status()
                    idx += 1
                    if base_headless and current_headless != base_headless:
                        log("✅ Succeeded. Reverting to headless mode.")
                        current_headless = base_headless
                        if not init_browser(current_headless):
                            break
                else:
                    if base_headless:
                        current_headless = not current_headless
                        state_str = "headless" if current_headless else "visible (minimized)"
                        log(f"🔄 Retrying in {state_str} mode...")
                        if not init_browser(current_headless):
                            break
                    else:
                        log(f"❌ Failed for {filename}. Skipping.")
                        idx += 1

            log("🎉 Upscaling task completed!")
            if context:
                try: context.close()
                except: pass
    except Exception as e:
        log(f"❌ Unhandled Crash: {e}")
        log(traceback.format_exc())
    finally:
        try: os.remove("upscaler.lock")
        except: pass
        try:
            # Cleanup sandbox junction
            sandbox_default = os.path.join(os.path.abspath(os.path.dirname(__file__)), "upscaler_session_sandbox", "Default")
            if os.path.exists(sandbox_default):
                subprocess.run(['rmdir', sandbox_default], shell=True, capture_output=True)
        except: pass

if __name__ == "__main__":
    main()
