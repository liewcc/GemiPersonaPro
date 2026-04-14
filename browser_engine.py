import asyncio
import os
import sys
import time
import json
import traceback
from config_utils import load_config, save_config
from playwright.async_api import async_playwright
from datetime import datetime

# Fix for Windows asyncio NotImplementedError with subprocesses
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class BrowserEngine:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self.is_running = False
        self._state_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "browser_state.json"))
        self._sandbox_dir = None
        self._log_queue = []
        self._stop_automation_event = asyncio.Event()
        self.automation_status = {
            "is_running": False,
            "mode": "rounds",
            "goal": 0,
            "cycles": 0,
            "successes": 0,
            "refusals": 0,
            "resets": 0,
            "start_time": None,
            "initial_user": None
        }
        # Per-image reject rate tracking
        self._reject_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "reject_stat_log.json"))
        self._cycle_start_time = None   # float: time.time() at start of current cycle
        self._pending_refused = 0       # refused count waiting to be attributed to next successful image
        self._pending_resets = 0        # reset count waiting to be attributed to next successful image
        self._automation_needs_new_chat = True # Flag to force New Chat on next cycle
        self._session_lost = False      # Watchdog flag for engine_service to detect logout
        self._watchdog_task = None      # Handle for the background watchdog task
        self._watchdog_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "watchdog.log"))
        # Per-account session stats snapshot: captured when an account becomes active.
        # Stores {"successes": N, "refusals": N, "resets": N} so that per-account deltas
        # can be computed when that account is later switched away.
        self._acct_snapshot = None
        # Registration browser handles (separate from main browser)
        self._reg_playwright = None
        self._reg_context = None


    @property
    def current_url(self):
        """Returns the current page URL."""
        if self._page:
            return self._page.url
        return None

    @property
    def browser_pids(self):
        """Returns a list of all browser-related PIDs."""
        pids = []
        try:
            import psutil
            current_proc = psutil.Process(os.getpid())
            for child in current_proc.children(recursive=True):
                try:
                    name = child.name().lower()
                    if "chrome" in name or "chromium" in name:
                        if child.pid not in pids:
                            pids.append(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return pids

    @property
    def browser_pid(self):
        """Returns the main browser PID (first in list)."""
        pids = self.browser_pids
        return pids[0] if pids else None

    async def inject_session_state(self):
        """Inject saved session state from browser_state.json."""
        if not os.path.exists(self._state_file) or not self._context:
            return
        try:
            import json
            with open(self._state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if 'cookies' in state:
                await self._context.add_cookies(state['cookies'])
        except Exception as e:
            print(f"Session injection failed: {e}")

    async def save_session_state(self):
        """Safely export current state."""
        if self._context:
            try:
                await self._context.storage_state(path=self._state_file)
            except Exception as e:
                print(f"Session save failed: {e}")

    async def apply_hardcore_stealth(self, page):
        """Manual JS injection for anti-detection and auto-interruption handling."""
        try:
            await page.add_init_script("""
                // Anti-detection
                Object.defineProperty(navigator, 'webdriver', {get: () => False});
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

                // Proactive Dialog Dismissal (MutationObserver)
                const observer = new MutationObserver((mutations) => {
                    for (const mutation of mutations) {
                        for (const node of mutation.addedNodes) {
                            if (node.nodeType === 1) { // Element node
                                // Target the "Agree" button in the MMGen disclaimer dialog
                                const agreeBtn = node.querySelector('button[data-test-id="upload-image-agree-button"]');
                                if (agreeBtn) {
                                    console.log("[GemiPersona] Disclaimer detected. Auto-clicking Agree...");
                                    agreeBtn.click();
                                }
                            }
                        }
                    }
                });
                observer.observe(document.documentElement, { childList: true, subtree: true });
            """)
        except Exception as e:
            print(f"Stealth injection failed: {e}")

    async def _cleanup_sandbox(self):
        """Cleanup junction and sandbox directory."""
        if self._sandbox_dir and os.path.exists(self._sandbox_dir):
            try:
                # Remove junction first (Windows 'rmdir' on junction doesn't delete source)
                junction_path = os.path.join(self._sandbox_dir, "Default")
                if os.path.exists(junction_path):
                    import subprocess
                    subprocess.run(['rmdir', junction_path], shell=True, capture_output=True)
                
                # Small delay to release file handles
                import shutil
                shutil.rmtree(self._sandbox_dir, ignore_errors=True)
                print(f"[DEBUG] Sandbox {self._sandbox_dir} cleaned up.")
            except Exception as e:
                print(f"[DEBUG] Sandbox cleanup failed: {e}")
            self._sandbox_dir = None

    async def start(self, headless=True, url="https://gemini.google.com/app", profile_name="Default"):
        """
        Scheme A: Dynamic Sandbox - Creates a junction to the target profile
        and launches Playwright with a unique temporary user data dir.
        """
        self.last_headless = headless
        
        if self.is_running:
            return
        
        # Guard: close any lingering registration browser before starting the main one
        await self.stop_registration()
        
        # 1. Prepare Sandbox
        base_dir = os.path.abspath(os.path.dirname(__file__))
        source_user_data = os.path.join(base_dir, "browser_user_data")
        
        # Note: _cleanup_sandbox() sets self._sandbox_dir to None, so we must 
        # initialize/re-initialize it AFTER cleanup.
        temp_sandbox_path = os.path.join(base_dir, "browser_session_sandbox")
        if os.path.exists(temp_sandbox_path):
            # Temporarily set it so cleanup knows what to delete
            self._sandbox_dir = temp_sandbox_path
            await self._cleanup_sandbox()
        
        self._sandbox_dir = temp_sandbox_path
        os.makedirs(self._sandbox_dir, exist_ok=True)
        
        # 2. Map Profile
        if profile_name:
            target_profile_path = os.path.join(source_user_data, profile_name)
            sandbox_default = os.path.join(self._sandbox_dir, "Default")
            
            if os.path.exists(target_profile_path):
                import subprocess
                # Create Junction: Playwright will look for 'Default' inside the sandbox
                cmd = f'mklink /J "{sandbox_default}" "{target_profile_path}"'
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode != 0:
                    print(f"[ERROR] Junction failed (Code {res.returncode}): {res.stderr.strip()}")
                else:
                    if os.path.exists(sandbox_default):
                        print(f"[DEBUG] Sandbox junction verified: {profile_name} -> {sandbox_default}")
                    else:
                        print(f"[ERROR] Junction reported success but path does not exist!")
            else:
                print(f"[ERROR] Source profile path not found: {target_profile_path}")
            
            # Copy root config files
            import shutil
            for f_name in ["Local State", "Variations"]:
                src = os.path.join(source_user_data, f_name)
                if os.path.exists(src):
                    dest = os.path.join(self._sandbox_dir, f_name)
                    shutil.copy2(src, dest)
                    
                    # Force "Default" profile in Local State to match our junction
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
                            print(f"[DEBUG] Local State forced to 'Default' profile.")
                        except Exception as e:
                            print(f"[ERROR] Failed to patch Local State: {e}")
            
            # Explicitly force "Last Profile" file in sandbox root
            try:
                last_profile_path = os.path.join(self._sandbox_dir, "Last Profile")
                with open(last_profile_path, "w", encoding="utf-8") as f:
                    f.write("Default")
                print(f"[DEBUG] Forced 'Last Profile' file created.")
            except Exception as e:
                print(f"[ERROR] Failed to create 'Last Profile': {e}")

        # 3. Launch Playwright
        self._playwright = await async_playwright().start()
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        target_viewport = {'width': 2560, 'height': 1440} if headless else None
        
        launch_args = [
            "--start-minimized",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
        
        # Use our sandbox as the persistent context root
        launch_dir = self._sandbox_dir if profile_name else source_user_data
        
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=launch_dir,
            headless=headless,
            user_agent=user_agent,
            viewport=target_viewport,
            ignore_default_args=["--enable-automation", "--use-mock-keychain"],
            args=launch_args,
            ignore_https_errors=True,
            java_script_enabled=True,
            device_scale_factor=1
        )
        
        # Removed manual state injection - Playwright Persistent Context 
        # handles this more reliably via the profile folder itself.
        # if headless:
        #    await self.inject_session_state()

        self._page = await self._context.new_page()
        await self.apply_hardcore_stealth(self._page)
        
        # Force minimize for non-headless mode.
        # --start-minimized gets overridden by Playwright's new_page(), so we
        # re-minimize via CDP to keep the headed fallback window invisible.
        if not headless:
            await self._force_minimize_window()
        
        self.is_running = True

    async def _force_minimize_window(self):
        """Use CDP to force the browser window into minimized state.
        
        Called after new_page() in non-headless mode because Playwright's
        page creation overrides Chrome's --start-minimized flag.
        """
        if not self._page:
            return
        try:
            cdp = await self._page.context.new_cdp_session(self._page)
            window_info = await cdp.send("Browser.getWindowForTarget")
            await cdp.send("Browser.setWindowBounds", {
                "windowId": window_info["windowId"],
                "bounds": {"windowState": "minimized"}
            })
        except Exception as e:
            print(f"[DEBUG] CDP minimize failed: {e}")

    async def stop(self):
        """Stops the browser session and cleans up sandbox."""
        if not self.is_running:
            return
        
        # Removed manual state save 
        # await self.save_session_state()
        
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
            
        self.is_running = False
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        
        # Final cleanup
        await self._cleanup_sandbox()

    async def start_registration(self):
        """
        Opens a headed browser directly against browser_user_data/ (no sandbox).
        Allows the user to add new Google accounts / Chrome profiles.
        Data is written directly to disk and will be visible to the engine on next start.
        """
        # Close any previous registration browser first
        await self.stop_registration()
        
        base_dir = os.path.abspath(os.path.dirname(__file__))
        user_data_dir = os.path.join(base_dir, "browser_user_data")
        
        self._reg_playwright = await async_playwright().start()
        self._reg_context = await self._reg_playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            ignore_default_args=["--enable-automation", "--use-mock-keychain"],
            args=["--start-minimized", "--disable-blink-features=AutomationControlled", "--no-sandbox"],
            ignore_https_errors=True,
        )
        print("[REG] Registration browser started. user_data_dir:", user_data_dir)

    async def stop_registration(self):
        """Closes the registration browser if it is open."""
        if self._reg_context:
            try:
                await self._reg_context.close()
            except Exception as e:
                print(f"[REG] Error closing registration context: {e}")
            self._reg_context = None
        if self._reg_playwright:
            try:
                await self._reg_playwright.stop()
            except Exception as e:
                print(f"[REG] Error stopping registration playwright: {e}")
            self._reg_playwright = None
        print("[REG] Registration browser stopped.")


    async def navigate(self, url):
        """Navigates to a URL using reference-aligned wait state."""
        if not self.is_running:
            raise Exception("Browser Engine not started")
        
        try:
            # Use domcontentloaded as per reference watcher.py (more stable for SPAs)
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # PROACTIVE: Check for agreement popups immediately after navigation
            await self.dismiss_agreement_popups()
            await asyncio.sleep(0.5)  # Grace period: let DOM stabilize after popup dismissal
            # Re-minimize after navigation if running in non-headless mode,
            # since goto() can restore a minimized window.
            if not self.last_headless:
                await self._force_minimize_window()
            return response.status if response else 0
        except Exception as e:
            print(f"Navigation warning: {e}")
            return 200 

    async def send_prompt(self, text):
        """Types text into Gemini's prompt area and sends it."""
        if not self.is_running:
            raise Exception("Browser Engine not started")
        
        # Target Gemini's prompt input (common selectors)
        prompt_selectors = [
            "div[aria-label='Enter a prompt here']",
            "div.ql-editor[contenteditable='true']",
            "textarea[aria-label='Enter a prompt here']",
            # NOTE: "[contenteditable='true']" removed — too broad, causes Playwright
            # strict=True violation when multiple contenteditable elements exist (e.g.
            # after a popup is dismissed and Gemini re-renders its UI).
        ]
        
        target = None
        retry_waits = [0, 3, 5, 8]  # Progressive waits in seconds (first attempt is instant)
        for attempt, wait_sec in enumerate(retry_waits):
            if wait_sec > 0:
                self._log_debug(f"Prompt input not found. Retrying in {wait_sec}s (attempt {attempt + 1}/{len(retry_waits)})...")
                await asyncio.sleep(wait_sec)
            for sel in prompt_selectors:
                try:
                    elem = self._page.locator(sel).first
                    if await elem.is_visible(timeout=2000):
                        target = elem
                        break
                except:
                    continue
            if target:
                break
        
        if not target:
            raise Exception("Could not find prompt input area on current page.")
        
        # Clear existing text if any (Gemini uses contenteditable often)
        await target.click()
        # For contenteditable, sometimes we need to select all and delete
        await self._page.keyboard.press("Control+A")
        await self._page.keyboard.press("Backspace")
        
        # Type the new prompt
        await target.fill(text) if await target.is_editable() else await target.type(text)
        
        return {"status": "filled", "prompt": text}

    async def attach_files(self, file_paths):
        """
        Smart Incremental Sync (Stem-Based):
        1. Scans Gemini DOM for existing attached filenames.
        2. Compares filenames by STEM (name without extension) to handle Gemini's auto-conversion/renaming.
        3. Only Adds/Removes the differences.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")
        
        LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "engine.log"))
        
        def log_debug(msg):
            timestamp = datetime.now().strftime("[%H:%M:%S]")
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [DEBUG_SYNC] {msg}\n")
            print(f"[DEBUG_SYNC] {msg}")

        # 1. Detection Phase: Get filenames currently in Gemini
        raw_labels = await self._page.evaluate('''() => {
            const buttons = Array.from(document.querySelectorAll('button[data-test-id="cancel-button"]'));
            return buttons.map(btn => btn.getAttribute('aria-label') || "").filter(l => l.length > 0);
        }''')
        
        attached_filenames = []
        for label in raw_labels:
            parts = label.split()
            low_parts = [p.lower() for p in parts]
            if "file" in low_parts:
                idx = low_parts.index("file")
                name = " ".join(parts[idx+1:]).strip()
            else:
                name = parts[-1].strip()
            if name.endswith('.'): name = name[:-1]
            attached_filenames.append(name.strip())

        # CRITICAL FIX: Match by STEM (filename without extension)
        # Because Gemini often renames .png to .jpg in the label.
        def get_stem(filename):
            return os.path.splitext(filename)[0].lower()

        attached_stems = [get_stem(n) for n in attached_filenames]
        
        # Build local target mapping by stem
        target_map = {} # stem -> (original_name, full_path)
        for p in file_paths:
            base = os.path.basename(p)
            target_map[get_stem(base)] = (base, p)
        
        target_stems = list(target_map.keys())
        
        log_debug(f"Browser has (Raw): {attached_filenames}")
        log_debug(f"Target has (Raw): {[v[0] for v in target_map.values()]}")
        log_debug(f"Matching via stems: {attached_stems} vs {target_stems}")
        
        added_count = 0
        removed_count = 0
        
        # 2. Remove Phase: Delete files from browser whose STEM is NOT in target
        for i, stem in enumerate(attached_stems):
            if stem not in target_stems:
                real_name = attached_filenames[i]
                try:
                    log_debug(f"Removing (Stem mismatch): {real_name}")
                    selector = f'button[data-test-id="cancel-button"][aria-label*="{real_name}"]'
                    btn = self._page.locator(selector).first
                    if await btn.is_visible():
                        await btn.click()
                        removed_count += 1
                        await asyncio.sleep(0.8)
                except Exception as e:
                    log_debug(f"Remove failed: {real_name} -> {e}")

        # 3. Add Phase: Upload local files whose STEM is NOT in browser
        for stem, (orig_name, full_path) in target_map.items():
            if stem not in attached_stems:
                if not os.path.exists(full_path):
                    continue
                
                try:
                    log_debug(f"Adding (New stem): {orig_name}")
                    async with self._page.expect_file_chooser(timeout=20000) as fc_info:
                        await self._page.evaluate('''() => {
                            const gemsIcon = document.querySelector('mat-icon[data-mat-icon-name="add_2"]') || 
                                           document.querySelector('mat-icon[fonticon="add"]');
                            if (gemsIcon) { gemsIcon.closest('button').click(); }
                        }''')
                        await asyncio.sleep(1.2)
                        await self._page.evaluate('''() => {
                            const opt = Array.from(document.querySelectorAll('.menu-text, span'))
                                             .find(i => i.innerText.toLowerCase().includes("upload files"));
                            if (opt) opt.click();
                        }''')
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(full_path)
                    
                    # PROACTIVE: Immediately check for the MMGen disclaimer after upload
                    await self.dismiss_agreement_popups()
                    
                    added_count += 1
                    await asyncio.sleep(2.5)
                except Exception as e:
                    log_debug(f"Add failed: {orig_name} -> {e}")
            else:
                log_debug(f"Skipping (Stem already present): {orig_name}")
        
        return {
            "status": "success", 
            "added": added_count, 
            "removed": removed_count, 
            "total_now": len(file_paths)
        }

    def _log_debug(self, msg):
        """Helper to log debug info to engine.log and internal queue."""
        LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "engine.log"))
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        # Standardize prefix for the UI backend logs
        log_msg = f"{timestamp} API>> {msg}"
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{log_msg}\n")
        except (PermissionError, IOError):
            # Silently ignore write errors to log file to prevent automation crashes on Windows
            pass
        # print(log_msg)  # Silenced: user requested no general printing
        
        # Add to internal queue for API consumption
        if not hasattr(self, '_log_queue'):
             self._log_queue = []
        self._log_queue.append(log_msg)
        # Keep queue somewhat bounded
        if len(self._log_queue) > 500:
             self._log_queue = self._log_queue[-500:]

    def clear_physical_logs(self):
        """Truncates the engine.log file."""
        LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "engine.log"))
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] API>> Engine log cleared by user.\n")
            return True
        except Exception as e:
            print(f"Failed to clear log: {e}")
            return False

    def _log_watchdog(self, msg, to_ui=False):
        """Helper to log anomalies to watchdog.log and optionally to the UI."""
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_entry = f"{timestamp} {msg}\n"
        try:
            with open(self._watchdog_log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except:
            pass
        
        if to_ui:
            self._log_debug(f"WATCHDOG>> {msg}")
            # Ensure the critical record is also printed to console as per "正式log" request
            timestamp_now = datetime.now().strftime("[%H:%M:%S]")
            print(f"{timestamp_now} WATCHDOG>> {msg}")

    def get_and_clear_logs(self):
        """Returns all queued logs and clears the queue."""
        if not hasattr(self, '_log_queue'):
             self._log_queue = []
        logs = list(self._log_queue)
        self._log_queue.clear()
        return logs

    def _write_reject_stat(self, filename, duration_sec, refused_count, reset_count):
        """Appends a per-image stat record to reject_stat_log.json."""
        try:
            records = []
            if os.path.exists(self._reject_log_path):
                with open(self._reject_log_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
            records.append({
                "index": len(records) + 1,
                "filename": filename,
                "duration_sec": round(duration_sec, 2),
                "refused_count": refused_count,
                "reset_count": reset_count
            })
            with open(self._reject_log_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
            self._log_debug(f"RejectStat: Wrote record for {filename} (dur={duration_sec:.1f}s, ref={refused_count}, rst={reset_count})")
        except Exception as e:
            self._log_debug(f"RejectStat: Failed to write stat for {filename}: {e}")

    async def discover_capabilities(self):
        """
        Scans Gemini DOM to find available models and tools.
        Updates config.json with discovery results.
        """
        if not self.is_running:
            return {"status": "error", "message": "Browser not started"}
        
        self._log_debug("Starting discovery scan...")
        results = {"models": [], "tools": [], "current_model": "Unknown"}
        
        try:
            # 1. Discover Models
            # First, check current visible model
            current_model_el = await self._page.query_selector('button[data-test-id="bard-mode-menu-button"] .logo-pill-label-container span')
            if current_model_el:
                results["current_model"] = (await current_model_el.innerText()).split('\n')[0].strip()

            # Trigger model menu
            await self._page.click('button[data-test-id="bard-mode-menu-button"]')
            await asyncio.sleep(1.2)
            
            # Extract models - only first line to avoid descriptions
            results["models"] = await self._page.evaluate('''() => {
                const items = Array.from(document.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"]'));
                return items.map(i => {
                    const primary = i.querySelector('.mdc-list-item__primary-text');
                    const raw = primary ? primary.innerText : i.innerText;
                    return raw.split('\\n')[0].trim();
                }).filter(t => t.length > 0);
            }''')
            
            # Close menu
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # 2. Discover Tools
            # Use the confirmed 'toolbox-drawer-button'
            self._log_debug("Attempting to open Tools drawer...")
            btn = self._page.locator('button.toolbox-drawer-button').first
            if await btn.is_visible():
                await btn.click()
            else:
                # Fallback to text matching if class fails
                await self._page.evaluate('''() => {
                    const btn = Array.from(document.querySelectorAll('button'))
                                     .find(b => b.innerText.includes("Tools"));
                    if (btn) btn.click();
                }''')
            
            # Wait for the drawer
            try:
                await self._page.wait_for_selector('#toolbox-drawer-menu, toolbox-drawer-item', timeout=5000)
            except:
                self._log_debug("Tools drawer did not appear.")

            await asyncio.sleep(0.8)
            
            # Grab tool labels - SCOPE TO #toolbox-drawer-menu to avoid external items
            results["tools"] = await self._page.evaluate('''() => {
                const menu = document.getElementById('toolbox-drawer-menu');
                if (!menu) return [];
                const items = Array.from(menu.querySelectorAll('toolbox-drawer-item'));
                return items.map(i => {
                    const label = i.querySelector('.label.gds-label-l') || i.querySelector('.mdc-list-item__primary-text');
                    if (label) {
                        // Take only the first line to avoid "New" badges etc.
                        return label.innerText.split('\\n')[0].trim();
                    }
                    return "";
                }).filter(t => t.length > 0);
            }''')
            
            # Close by clicking escape
            await self._page.keyboard.press("Escape")
            
            # Persist to config.json
            config_path = os.path.abspath(os.path.join(os.getcwd(), "config.json"))
            if os.path.exists(config_path):
                import json
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    
                    cfg["discovery"] = {
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "available_models": results["models"],
                        "available_tools": results["tools"]
                    }
                    
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4, ensure_ascii=False)
                    self._log_debug(f"Discovery results saved. Models: {len(results['models'])}, Tools: {len(results['tools'])}")
                except Exception as e:
                    self._log_debug(f"Failed to save discovery: {e}")
            
            return {"status": "success", "data": results}
            
        except Exception as e:
            self._log_debug(f"Discovery failed: {e}")
            return {"status": "error", "message": str(e)}

    async def apply_settings(self, model_name=None, tool_name=None):
        """
        Automates switching to the specified model and/or tool.
        """
        if not self.is_running:
            return {"status": "error", "message": "Browser not started"}
            
        try:
            # 1. Apply Model
            if model_name:
                self._log_debug(f"Applying model: {model_name}")
                await self._page.click('button[data-test-id="bard-mode-menu-button"]')
                await asyncio.sleep(0.8)
                
                await self._page.evaluate(f'''(name) => {{
                    const items = Array.from(document.querySelectorAll('.mat-mdc-menu-item, [role="menuitem"]'));
                    const target = items.find(i => {{
                        const raw = i.innerText.split('\\n')[0].trim().toLowerCase();
                        return raw.startsWith(name.toLowerCase()) || name.toLowerCase().startsWith(raw);
                    }});
                    if (target) target.click();
                }}''', model_name)
                await asyncio.sleep(1.5)

            # 2. Apply Tool
            if tool_name:
                self._log_debug(f"Applying tool: {tool_name}")
                if tool_name.lower() == "default":
                    pass
                else:
                    # Open Tools drawer
                    btn = self._page.locator('button.toolbox-drawer-button').first
                    if await btn.is_visible():
                        await btn.click()
                    else:
                        await self._page.evaluate('''() => {
                            const btn = Array.from(document.querySelectorAll('button'))
                                             .find(b => b.innerText.includes("Tools"));
                            if (btn) btn.click();
                        }''')
                    
                    await asyncio.sleep(1.0)
                    
                    await self._page.evaluate(f'''(name) => {{
                        const menu = document.getElementById('toolbox-drawer-menu');
                        if (!menu) return;
                        const items = Array.from(menu.querySelectorAll('toolbox-drawer-item'));
                        const target = items.find(i => {{
                            const label = i.querySelector('.label.gds-label-l') || i.querySelector('.mdc-list-item__primary-text');
                            return label && label.innerText.toLowerCase().includes(name.toLowerCase());
                        }});
                        if (target) {{
                            const btn = target.querySelector('button');
                            if (btn) btn.click();
                        }}
                    }}''', tool_name)
                    await asyncio.sleep(1.0)

            return {"status": "success"}
        except Exception as e:
            self._log_debug(f"Apply settings failed: {e}")
            return {"status": "error", "message": str(e)}

    async def clear_attachments(self):
        """
        Forcefully removes all file attachments from the Gemini UI.
        Matches all elements with data-test-id="cancel-button".
        """
        if not self.is_running:
            return {"status": "error", "message": "Browser not started"}
            
        try:
            # Locate all cancel buttons
            buttons = await self._page.query_selector_all('button[data-test-id="cancel-button"]')
            removed = 0
            for btn in buttons:
                try:
                    await btn.click()
                    removed += 1
                    await asyncio.sleep(0.5)
                except:
                    continue
            return {"status": "success", "removed": removed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def dismiss_agreement_popups(self):
        """
        Detects and clicks 'Agree' or 'Got it' buttons in modal dialogs.
        Specifically handles the 'Creating content from images and files' popup.
        """
        if not self.is_running or not self._page:
            return

        # Target buttons with specific text patterns and data-test-ids
        popup_selectors = [
            'button[data-test-id="upload-image-agree-button"]', # Precise MMGen Agree
            "button:has-text('Agree')",
            "button:has-text('I agree')",
            "button:has-text('Got it')",
            "button:has-text('Confirm')",
            "button:has-text('同意')" # Support for Chinese UI
        ]
        
        try:
            # We use a very short timeout - if it's there, we kill it; if not, we move on.
            for selector in popup_selectors:
                btn = self._page.locator(selector).first
                if await btn.is_visible(timeout=1500):
                    self._log_debug(f"Popup detected. Clicking: {selector}")
                    await btn.click()
                    await asyncio.sleep(1.0) # Grace period for animation
                    return True
        except Exception:
            # Silence timeouts - if button isn't found/visible, it's not a failure
            pass
        return False

    async def get_screenshot(self, output_path=None):
        """Captures a screenshot with reference-aligned stability."""
        if not self.is_running:
            raise Exception("Browser Engine not started")
        
        # Stability waits
        await self._page.wait_for_load_state("load")
        await self._page.wait_for_timeout(2000) 
        
        # Fix for white screen: ensure body is present and visible
        try:
            body_visible = await self._page.is_visible("body")
            if not body_visible:
                await self._page.wait_for_selector("body", state="visible", timeout=10000)
        except Exception:
            pass
        
        if not output_path:
            out_dir = "browser_screen_capture"
            output_path = f"{out_dir}/screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            os.makedirs(out_dir, exist_ok=True)
            
        # Using full_page=True as seen in reference check_signin.py
        await self._page.screenshot(path=output_path, full_page=True)
        return output_path

    async def get_gem_title(self) -> dict:
        """Extracts the Custom Gem Title from the active Gemini page."""
        if not self.is_running:
            raise Exception("Browser Engine not started")
            
        try:
            # We look for the main heading element that typically holds the Gem name
            # in gemini.google.com/gem/*
            title_text = await self._page.evaluate('''() => {
                const clean = (t) => t ? t.trim().replace(/\\n/g, ' ') : "";
                
                // Try to find Name using the reliable legacy selector
                const nameContainer = document.querySelector('.bot-name-container');
                let name = "";
                if (nameContainer) {
                    const temp = nameContainer.cloneNode(true);
                    const badge = temp.querySelector('bot-experiment-badge, .bot-name-container-animation-box');
                    if (badge) badge.remove();
                    name = clean(temp.innerText);
                    if (name) return name;
                }
                
                // Fallback to document title, stripped of generic "Gemini"
                const docTitle = document.title;
                if (docTitle.includes(" - Gemini") || docTitle === "Gemini") {
                    return docTitle.replace(" - Gemini", "").trim();
                }
                return docTitle;
            }''')
            
            return {"status": "success", "title": title_text or "Unknown"}
        except Exception as e:
            self._log_debug(f"Error extracting gem title: {e}")
            return {"status": "error", "message": str(e)}

    async def get_gem_info(self) -> dict:
        """Extracts the Custom Gem Title AND Description from the active Gemini Gem page."""
        if not self.is_running:
            raise Exception("Browser Engine not started")

        try:
            result = await self._page.evaluate('''() => {
                const clean = (t) => t ? t.trim().replace(/\\n/g, ' ') : "";

                // --- Extract Name (Exact logic from get_gem_title) ---
                const nameContainer = document.querySelector('.bot-name-container');
                let name = "";
                if (nameContainer) {
                    const temp = nameContainer.cloneNode(true);
                    const badge = temp.querySelector('bot-experiment-badge, .bot-name-container-animation-box');
                    if (badge) badge.remove();
                    name = clean(temp.innerText);
                }
                if (!name) {
                    // Fallback to document title, stripped of generic "Gemini"
                    const docTitle = document.title;
                    if (docTitle.includes(" - Gemini") || docTitle === "Gemini") {
                        name = docTitle.replace(" - Gemini", "").trim();
                    } else {
                        name = docTitle;
                    }
                }

                // --- Extract Description ---
                let description = "";
                // Primary: dedicated description container
                const descContainer = document.querySelector('.bot-description-container');
                if (descContainer) {
                    description = clean(descContainer.innerText);
                }
                // Fallback: look for the subtitle/instruction text near the gem header
                if (!description) {
                    const subtitle = document.querySelector('.bot-subtitle, .bot-instruction-text, .gem-description');
                    if (subtitle) {
                        description = clean(subtitle.innerText);
                    }
                }
                // Fallback: aria-label on the main gem card
                if (!description) {
                    const card = document.querySelector('[data-test-id="gem-card"]');
                    if (card) {
                        const label = card.getAttribute('aria-label') || "";
                        if (label && label !== name) {
                            description = clean(label);
                        }
                    }
                }

                return { name: name || "Unknown Gem", description: description || "" };
            }''')

            return {
                "status": "success",
                "name": result.get("name", "Unknown Gem"),
                "description": result.get("description", "")
            }
        except Exception as e:
            self._log_debug(f"Error extracting gem info: {e}")
            return {"status": "error", "message": str(e)}

    async def submit_response(self, text=None, expect_attachments=False):
        """
        1. Injects prompt if provided.
        2. Presses Enter to submit.
        3. Monitors DOM for: Success (image), Quota Exceeded, or Policy Refusal.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        if text:
            await self.send_prompt(text)
            # Submit only if we injected text
            await self._page.keyboard.press("Enter")
            self._log_debug("Prompt submitted. Checking for intercepting popups...")
            
            # CRITICAL: Dismiss "Creating content from images/files" popup if it appears after Enter
            await self.dismiss_agreement_popups()
            
            self._log_debug("Monitoring for response...")
        else:
            self._log_debug("Monitoring existing response (no prompt injected)...")

        # Monitor loop - dynamic quota keywords from config
        quota_kws = ["quota exceeded", "daily limit", "reached your limit"]
        try:
            config_path = os.path.abspath(os.path.join(os.getcwd(), "config.json"))
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    quota_kws = cfg.get("quota_full", quota_kws)
                    # Convert to lowercase for comparison
                    quota_kws = [k.lower() for k in quota_kws]
        except:
            pass

        self._log_debug("Waiting for Gemini response...")
        
        has_started_generating = False
        start_gen_time = None
        last_logged_text = ""

        for _ in range(90): # 180 seconds max
            if self._stop_automation_event.is_set():
                self._log_debug("Stop signal received during monitoring. Bailing out.")
                # Also try to click the browser's stop button to halt generation
                try:
                    await self.stop_response()
                except:
                    pass
                return {"status": "stopped", "message": "Monitoring interrupted by stop signal."}

            data = await self._page.evaluate('''(args) => {
                const bodyText = document.body.innerText.toLowerCase();
                
                // 1. Quota check (text-based - these are standard system phrases)
                for (const kw of args.quota) {
                    if (bodyText.includes(kw)) return { status: "quota_exceeded", text: kw };
                }

                // 2. Active generation signals (highest priority)
                const stopIcon = document.querySelector('mat-icon[data-mat-icon-name="stop"]');
                const hasProgressBar = !!document.querySelector('mat-progress-bar');
                const activeLoadingContainer = document.querySelector('section.processing-state_container--processing');

                if (stopIcon || hasProgressBar || activeLoadingContainer) {
                    let genText = "";
                    if (activeLoadingContainer) {
                        // Extract text from the active loading container's specific spans
                        const labelSpan = activeLoadingContainer.querySelector('.processing-state_ext-name_label span');
                        const placeholderSpan = activeLoadingContainer.querySelector('.processing-state_ext-name_placeholder span');
                        
                        if (labelSpan && labelSpan.textContent) {
                            genText = labelSpan.textContent.trim();
                        } else if (placeholderSpan && placeholderSpan.textContent) {
                            genText = placeholderSpan.textContent.trim();
                        } else {
                            genText = activeLoadingContainer.textContent.trim();
                        }
                    } else {
                        // Extract regular streaming generation text
                        const responses = Array.from(document.querySelectorAll('model-response'));
                        const lastResp = responses.length > 0 ? responses[responses.length - 1] : null;
                        if (lastResp) {
                            const contentNode = lastResp.querySelector('.model-response-text') || lastResp.querySelector('.message-content') || lastResp;
                            genText = contentNode.innerText.trim();
                        }
                    }
                    return { status: "generating", text: genText };
                }

                // 3. Idle state (send icon visible)
                const sendIcon = document.querySelector('mat-icon[data-mat-icon-name="send"]');
                if (sendIcon) {
                    const responses = Array.from(document.querySelectorAll('model-response'));
                    
                    // Metadata for reset detection
                    const editor = document.querySelector('.ql-editor');
                    const inputEmpty = !editor || !editor.innerText.trim();
                    const attachmentCount = document.querySelectorAll('button[data-test-id="cancel-button"]').length;

                    // No conversation history visible - Gemini was reset or is a fresh session.
                    if (responses.length === 0) {
                        return { 
                            status: "reset", 
                            text: "", 
                            inputEmpty: inputEmpty,
                            attachmentCount: attachmentCount
                        };
                    }
                    
                    const lastResp = responses[responses.length - 1];
                    const hasImg = !!lastResp.querySelector('img');
                    
                    // Filter out the 'XXX said' header portion
                    const contentNode = lastResp.querySelector('.model-response-text') || lastResp.querySelector('.message-content') || lastResp;
                    const respText = contentNode.innerText.trim();

                    if (hasImg) return { status: "success", text: respText };
                    
                    // Structural refusal detection:
                    // Gemini refused if the response is "complete" (has the complete footer class)
                    // and it has text content but NO image.
                    const completeFooter = lastResp.querySelector('.response-footer.complete');
                    if (completeFooter && respText.length > 0) {
                        return { status: "refused", text: respText };
                    }

                    // Otherwise treat as stopped or transitional
                    return { status: "idle_no_img", text: respText };
                }

                return { status: "loading", text: "" };
            }''', {"quota": quota_kws})

            status = data['status']
            resp_text = data.get('text', '') or ''
            current_time = time.time()

            # If generating but JS returned no text, try to read the loading label
            # via Playwright's native locator (more reliable than evaluate for this)
            if status == "generating" and not resp_text:
                try:
                    import re as _re
                    locator = self._page.locator('section.processing-state_container--processing').first
                    if await locator.count() > 0:
                        jslog_attr = await locator.get_attribute('jslog') or ""
                        m = _re.search(r'\["([^"]+)",0\]', jslog_attr)
                        if m:
                            resp_text = m.group(1)
                except Exception:
                    pass

            # Log any new status text (throttled to avoid noise)
            if resp_text and resp_text != last_logged_text and len(resp_text) > 2:
                flat = " ".join(resp_text.replace('\n', ' ').split())
                self._log_debug(f"Gemini: \"{flat[:200]}\"")
                last_logged_text = resp_text

            if status == "generating":
                if not has_started_generating:
                    has_started_generating = True
                    start_gen_time = current_time
            
            if status == "success":
                self._log_debug("Response successful: Image detected.")
                return {"status": "success", "message": "Image generated successfully."}
            elif status == "quota_exceeded":
                self._log_debug(f"Response failed: Quota exceeded.")
                return {"status": "error", "message": "Quota exceeded. Please wait before retrying."}
            elif status == "refused":
                flat_text = " ".join(resp_text.replace('\n', ' ').split())
                self._log_debug(f"Response failed (Refused): {flat_text[:300]}")
                return {"status": "refused", "message": f"Gemini refused: {flat_text[:300]}"}
            elif status == "idle_no_img":
                # Only report 'stopped' after sustained generation (4s grace period)
                if has_started_generating and start_gen_time and (current_time - start_gen_time > 4.0):
                    self._log_debug(f"Idle detected after {current_time - start_gen_time:.1f}s of generation.")
                    return {"status": "error", "message": "Stopped or failed to generate image."}
                else:
                    self._log_debug("Idle detected - in grace period, continuing to monitor...")
            elif status == "reset":
                # Gemini reset to initial state (no conversation history)
                if has_started_generating:
                    # Was generating but now page is empty - definitely an unexpected reset
                    self._log_debug("Gemini page was unexpectedly reset during generation.")
                    return {"status": "error", "message": "Gemini was reset unexpectedly."}
                
                # If we are NOT injecting a new prompt (monitoring a Redo) and we see a reset,
                # it means the Redo triggered a soft-reset. Return immediately to trigger recovery.
                if not text:
                    self._log_debug("Gemini reset detected during Redo monitoring. Triggering recovery...")
                    return {"status": "reset", "message": "Gemini reset during Redo."}
                
                # Case: Initial Prompt Submission (text has value)
                input_empty = data.get('inputEmpty', True)
                attachment_count = data.get('attachmentCount', 0)

                # Signal 1: Prompt is still in the input box (Submission failed or page reset)
                # Note: We give it a few seconds grace period to clear
                if not input_empty:
                    if not hasattr(self, '_reset_watchdog_start') or self._reset_watchdog_start is None:
                        self._reset_watchdog_start = current_time
                    elif (current_time - self._reset_watchdog_start) > 6.0:
                        self._log_debug("Prompt still remains in input box after 6s. Submission likely failed.")
                        self._reset_watchdog_start = None
                        return {"status": "reset", "message": "Prompt remains in input box."}
                
                # Signal 2: Missing attachments (Env reset)
                # If we expected attachments but they are gone, it's a reset.
                if expect_attachments and attachment_count == 0:
                    self._log_debug("Expected attachments disappeared. Env reset detected.")
                    return {"status": "reset", "message": "Attachments missing during monitoring."}
                
                self._log_debug("Waiting for conversation to appear...")
            else:
                # Any other status (generating, success, etc.) clears the watchdog
                self._reset_watchdog_start = None

            
            await asyncio.sleep(2)

        return {"status": "timeout", "message": "Timed out waiting for image response."}


    async def redo_response(self):
        """
        Triggers Gemini's redo (regenerate) action.
        Handles both the single button redo and the menu-based 'Try again' redo.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        # 1. Scroll to reveal Redo if hidden
        await self._page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(0.5)

        # 2. Click redo/refresh button
        result = await self._page.evaluate('''async () => {
            const findBtn = (sel) => document.querySelector(sel);
            const findByText = (txt) => Array.from(document.querySelectorAll('.menu-text, span, button'))
                                            .find(b => b.innerText.toLowerCase().includes(txt));
            
            let redoBtn = findBtn('regenerate-button button') || 
                          findBtn('button[aria-label="Redo"]') ||
                          document.querySelector('mat-icon[data-mat-icon-name="refresh"]')?.closest('button') ||
                          document.querySelector('mat-icon[fonticon="refresh"]')?.closest('button');

            if (redoBtn) {
                redoBtn.scrollIntoView({behavior: "instant", block: "center"});
                redoBtn.click();
                
                // Wait briefly for sub-menu if it exists
                await new Promise(r => setTimeout(r, 1000));
                
                let tryAgain = findByText("try again");
                if (tryAgain) {
                    tryAgain.click();
                    return "REDO_WITH_TRY_AGAIN";
                }
                return "REDO_CLICKED";
            }
            return "NOT_FOUND";
        }''')

        if result != "NOT_FOUND":
            self._log_debug(f"Redo triggered: {result}")
            # Extra wait to allow the UI to transition to 'generating'
            await asyncio.sleep(1.0)
            return {"status": "success", "message": f"Redo action sent ({result})."}
        else:
            self._log_debug("Redo button not found.")
            return {"status": "error", "message": "Redo button not found on page."}

    async def download_images(self, save_dir, naming_cfg, extra_meta=None):
        """
        Downloads images from the last response and enriches metadata.
        naming_cfg: {prefix, padding, start}
        extra_meta: {prompt, url, upload_path}
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        os.makedirs(save_dir, exist_ok=True)
        
        # 1. Identify images in last response
        last_response = await self._page.query_selector('model-response:last-of-type')
        if not last_response:
            return {"status": "error", "message": "No response found to download from."}

        imgs = await last_response.query_selector_all('img')
        valid_imgs = []
        for img in imgs:
            box = await img.bounding_box()
            if box and box['width'] > 250:
                valid_imgs.append(img)

        if not valid_imgs:
            return {"status": "ignored", "message": "No valid large images found."}

        self._log_debug(f"Downloading {len(valid_imgs)} images...")
        
        prefix = naming_cfg.get("prefix", "")
        padding = naming_cfg.get("padding", 2)
        start_idx = naming_cfg.get("start", 1)
        
        from PIL import Image
        import io
        from processing_utils import save_with_metadata

        dl_count = 0
        saved_paths = []

        for img in valid_imgs:
            try:
                # Preview and download
                await img.evaluate('el => el.scrollIntoView({behavior: "instant", block: "center"})')
                await asyncio.sleep(1.0)
                await img.click(force=True)
                await asyncio.sleep(3.0)

                async with self._page.expect_download(timeout=15000) as dl_info:
                    await self._page.evaluate('''() => {
                        const b = Array.from(document.querySelectorAll('button'))
                                     .find(x => x.ariaLabel?.includes("Download") || 
                                               x.title?.includes("Download") ||
                                               x.innerText.includes("Download"));
                        if(b) b.click();
                    }''')
                    download = await dl_info.value
                    
                    # Find the next available index to avoid overwriting
                    while True:
                        save_name = f"{prefix}{str(start_idx).zfill(padding)}.png"
                        save_path = os.path.join(save_dir, save_name)
                        if not os.path.exists(save_path):
                            break
                        start_idx += 1
                    
                    temp_path = await download.path()
                    
                    # Open and save with metadata
                    with Image.open(temp_path) as pil_img:
                        save_with_metadata(pil_img, pil_img, save_path, extra_meta=extra_meta)
                    
                    saved_paths.append(save_path)
                    start_idx += 1
                    dl_count += 1
                    self._log_debug(f"Saved: {save_name}")

                await self._page.keyboard.press("Escape")
                await asyncio.sleep(1.0)
            except Exception as e:
                self._log_debug(f"Download skip: {e}")
                await self._page.keyboard.press("Escape")

        if dl_count == 0:
            return {"status": "ignored", "message": "Images detected but all downloads failed.", "saved_paths": []}

        return {
            "status": "success", 
            "count": dl_count, 
            "next_start": start_idx,
            "saved_paths": saved_paths
        }

    async def stop_response(self):
        """
        Clicks the 'Stop' button (square icon) if it exists.
        Returns immediately without waiting for confirmation to keep the UI responsive.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        self._log_debug("Attempting to stop response via 'stop' icon...")
        
        stopped = await self._page.evaluate('''() => {
            const stopIcon = document.querySelector('mat-icon[data-mat-icon-name="stop"]');
            if (stopIcon) {
                const btn = stopIcon.closest('button');
                if (btn) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''')

        if stopped:
            self._log_debug("Stop command sent successfully.")
            return {"status": "success", "message": "Response stop command triggered."}
        else:
            self._log_debug("Stop icon not found.")
            return {"status": "ignored", "message": "No active 'stop' icon found to click."}

    async def new_chat(self, target_url: str = None):
        """
        Clicks the 'New chat' button in the Gemini sidebar.
        If target_url is a Gem URL, it navigates directly instead.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        # 1. Smarter Navigation for Gems
        current_target = target_url
        if not current_target:
            # Try to read from config if not provided
            try:
                config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.json"))
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        current_target = cfg.get("browser_url")
            except: pass

        if current_target and "gemini.google.com/gem/" in current_target:
            self._log_debug(f"Gem URL detected: {current_target}")
            await self.navigate(current_target)
            await asyncio.sleep(2.0)
            return {"status": "success", "message": "Navigated to Gem URL directly."}

        self._log_debug("Attempting to trigger New Chat via UI...")
        
        # We use the data-test-id provided by the user for maximum reliability
        result = await self._page.evaluate('''() => {
            const btn = document.querySelector('side-nav-action-button[data-test-id="new-chat-button"]');
            if (btn) {
                // The actual clickable element might be the anchor inside
                const link = btn.querySelector('a[aria-label="New chat"]');
                if (link) {
                    link.click();
                    return "CLICKED_LINK";
                }
                btn.click();
                return "CLICKED_BUTTON";
            }
            return "NOT_FOUND";
        }''')

        if result != "NOT_FOUND":
            self._log_debug(f"New Chat triggered: {result}")
            # Wait for navigation/reset
            await asyncio.sleep(1.0)
            return {"status": "success", "message": f"New Chat triggered ({result})."}
        else:
            self._log_debug("New Chat button not found. Falling back to default URL.")
            await self.navigate("https://gemini.google.com/app")
            return {"status": "success", "message": "Navigated to default app as fallback."}

    async def delete_activity_history(self, range_name: str = "Last hour"):
        """
        Navigates to the Gemini Activity page and deletes activity based on the specified range.
        range_name: 'Last hour', 'Last day', 'Always'
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        self._log_debug(f"Initiating history deletion: {range_name}")
        
        try:
            # 1. Direct navigation to the Gemini activity page
            await self.navigate("https://myactivity.google.com/product/gemini")
            await asyncio.sleep(2.0)
            
            # --- [NEW] Pre-deletion: Handle initial warnings, tours, or banners ---
            # These can block the 'Delete' button or other interactions
            pre_dismiss_selectors = [
                'button:has-text("Dismiss")',
                'button:has-text("Got it")',
                'button[aria-label="Dismiss"]',
                '.xPkBGb:has-text("Dismiss")', # Specific selector for "Safer with Google" banner
                'div[role="dialog"] button:has-text("OK")'
            ]
            
            # Attempt to clear up to 2 distinct banners/popups
            for _ in range(2):
                dismiss_found = False
                for selector in pre_dismiss_selectors:
                    btn = self._page.locator(selector).first
                    if await btn.is_visible():
                        btn_text = await btn.inner_text() or selector
                        self._log_debug(f"Pre-deletion: Dismissing blocker ({btn_text})...")
                        await btn.click()
                        await asyncio.sleep(1.0)
                        dismiss_found = True
                        break # Check for next banner if any
                if not dismiss_found:
                    break

            # 2. Find and click the 'Delete' button
            delete_btn = self._page.locator('button[aria-label="Delete"]').first
            if not await delete_btn.is_visible():
                self._log_debug("Delete button not visible. Trying to scroll or force dismiss any overlays...")
                await self._page.mouse.click(10, 10) # Click corner to lose focus/dismiss lightboxes
                await self._page.keyboard.press("PageDown")
                await asyncio.sleep(1.0)
                if not await delete_btn.is_visible():
                    self._log_debug("Delete button still not visible on activity page.")
                    # Final attempt: click by coordinates if possible or log failure
                    return {"status": "error", "message": "Delete button not visible"}
            
            await delete_btn.click()
            await asyncio.sleep(1.0)
            
            # 3. Select the range option
            # Map user-friendly names to selectors/text
            range_map = {
                "Last hour": "Last hour",
                "Last day": "Last day",
                "All time": "Always"
            }
            target_text = range_map.get(range_name, "Last hour")
            
            # Use a more flexible locator to handle 'Always' vs 'All time' variants
            import re
            if range_name == "All time":
                self._log_debug("Searching for 'Always' or 'All time' option...")
                option = self._page.locator('li[role="menuitem"]').filter(has_text=re.compile(r"^(Always|All time)$", re.I)).first
            else:
                option = self._page.locator(f'li[role="menuitem"]:has-text("{target_text}")')

            if not await option.is_visible():
                return {"status": "error", "message": f"Option '{target_text}' not found"}
            
            await option.click()
            await asyncio.sleep(2.0)
            
            # 4. Handle Confirmation or "Got it" dialogs
            # These can appear for "Always" range or as a one-time warning/info
            # The USER reported: "Confirm that you would like to delete the following activity -> delete or close"
            dialog_selectors = [
                'button:has-text("Delete")',
                'button:has-text("Got it")',
                'button:has-text("Confirm")',
                'button.VfPpkd-LgbsSe:has-text("Delete")',
                'button.VfPpkd-LgbsSe:has-text("Got it")',
                'button:has-text("Close")'
            ]
            
            self._log_debug("Checking for post-selection dialogs...")
            for _ in range(4):
                dialog_handled = False
                
                modal = self._page.locator('div.llhEMd, div.VfPpkd-Sx9N0d').first
                if await modal.is_visible():
                    # Case 1: Detect "No activity" text inside modal
                    no_activity_text = modal.locator('text="You have no selected activity"').first
                    if await no_activity_text.is_visible():
                        close_btn = modal.locator('button:has-text("Close"), button:has-text("Got it")').first
                        if await close_btn.is_visible():
                            self._log_debug("Gemini Activity: No activity found to delete. Closing...")
                            await close_btn.click(force=True)
                            await asyncio.sleep(1.0)
                            return {"status": "success", "message": "No activity to delete"}

                    # Case 2: Detect "Delete" button inside modal
                    modal_delete_btn = modal.locator('button:has-text("Delete"), button[jsname="nUV0Pd"]').first
                    if await modal_delete_btn.is_visible():
                        self._log_debug("Gemini Activity: Deleting confirmed items...")
                        await modal_delete_btn.click(force=True)
                        await asyncio.sleep(2.0)
                        dialog_handled = True
                        continue

                    # Generic "Got it" or "OK" inside modal
                    modal_got_it_btn = modal.locator('button:has-text("Got it"), button:has-text("OK")').first
                    if await modal_got_it_btn.is_visible():
                        await modal_got_it_btn.click(force=True)
                        await asyncio.sleep(1.0)
                        dialog_handled = True
                        continue

                # Fallback to general selectors if modal check didn't catch it
                for selector in dialog_selectors:
                    btn = self._page.locator(selector).first
                    if await btn.is_visible():
                        btn_text = await btn.inner_text() or selector
                        await btn.click(force=True)
                        await asyncio.sleep(1.5)
                        dialog_handled = True
                        break 
                
                if not dialog_handled:
                    break
            
            # 5. Monitor Snackbar Feedback
            self._log_debug("Monitoring for snackbar feedback...")
            # Locator for snackbar/alert
            snackbar = self._page.locator('[role="alert"], [role="status"]').first
            
            # Monitoring loop for snackbar messages
            for _ in range(10): # 10 seconds timeout
                if await snackbar.is_visible():
                    msg = await snackbar.inner_text()
                    if msg:
                        flat_msg = " ".join(msg.strip().split())
                        self._log_debug(f"Gemini Activity: {flat_msg}")
                        
                        # Stop if we see a completion message
                        if any(x in flat_msg.lower() for x in ["deleted", "complete", "removed"]):
                            break
                await asyncio.sleep(1.0)
                
            return {"status": "success", "message": f"History deletion ({range_name}) completed."}
            
        except Exception as e:
            self._log_debug(f"Error during history deletion: {e}")
            return {"status": "error", "message": str(e)}

    async def stop_automation(self):
        """Signals the automation loop to stop and attempts to stop current page activity."""
        self._stop_automation_event.set()
        self.automation_status["is_running"] = False
        self._log_debug("Automation stop signaled. Attempting browser halt...")
        try:
            # Propagate stop to the actual browser button
            await self.stop_response()
        except:
            pass

    async def run_automation_loop(self, settings: dict):
        """
        Main automation loop.
        settings: {mode: 'rounds'|'images', goal: int, config: dict}
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        self._stop_automation_event.clear()
        self.automation_status["is_running"] = True
        
        # We NO LONGER reset cycles/successes here because this function is called per-round.
        # Initialization happens in engine_service or via a dedicated reset call.
        if self.automation_status.get("start_time") is None:
            from datetime import datetime
            self.automation_status["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Reset session lost flag for this run
            self._session_lost = False
            
            # Start Watchdog Task
            cfg = settings.get("config", {})
            if not cfg:
                self._log_debug("ERROR: Missing config in settings.")
                return {"status": "error", "message": "Missing config"}
                
            target_user = cfg.get("active_user")
            if self._watchdog_task is None:
                self._watchdog_task = asyncio.create_task(self._run_account_watchdog(target_user=target_user))

            self.automation_status["is_running"] = True
            self._log_debug(f"--- [AUTO] RUNNING ROUND: {self.automation_status.get('cycles', 0) + 1} ---")
            
            while self.automation_status.get("is_running", False):
                # Proactive Watchdog Check: if previous iteration (or watchdog) flagged session loss
                if getattr(self, "_session_lost", False):
                    self._log_debug("Watchdog: Critical session loss detected. Aborting loop.")
                    return {"status": "quota", "message": "Session lost or account mismatch."}

                if self._stop_automation_event.is_set():
                    break


                # Refresh cycles and stats from status in each iteration
                mode = self.automation_status.get("mode", "rounds")
                goal = self.automation_status.get("goal", 0)
                cycles = self.automation_status.get("cycles", 0)
                successes = self.automation_status.get("successes", 0)

                if mode == "rounds":
                    if cycles >= goal: break
                else: # images
                    if successes >= goal: break

                # 2. Cycle Strategy — record start time for this cycle
                if getattr(self, '_cycle_start_time', None) is None:
                    self._cycle_start_time = time.time()
                if getattr(self, '_lc_cycle_start_time', None) is None:
                    self._lc_cycle_start_time = time.time()
                is_initial = (cycles == 0) or getattr(self, "_automation_needs_new_chat", True)
                
                try:
                    # 3. Execution
                    if is_initial:
                        target_url = cfg.get("browser_url")
                        self._log_debug(f"Cycle #{cycles + 1}: Starting Fresh Setup (Navigating to: {target_url or 'New Chat'})...")
                        await self.new_chat(target_url=target_url)
                        if self._stop_automation_event.is_set(): break
                        await asyncio.sleep(2.0)
                        
                        await self.apply_settings(model_name=cfg.get("selected_model"), tool_name=cfg.get("selected_tool"))
                        if self._stop_automation_event.is_set(): break
                        
                        has_files = bool(cfg.get("selected_files"))
                        if has_files:
                            await self.attach_files(cfg.get("selected_files"))
                        if self._stop_automation_event.is_set(): break
                        
                        resp = await self.submit_response(text=cfg.get("prompt"), expect_attachments=has_files)
                        if self._stop_automation_event.is_set(): break
                        self._automation_needs_new_chat = False
                    else:
                        self._log_debug(f"Cycle #{cycles + 1}: Triggering Redo...")
                        resp = await self.redo_response()
                        if resp and resp.get("status") == "success":
                            resp = await self.submit_response(text=None) 
                        else:
                            # If Redo button not found, check if it's because of a reset
                            self._log_debug(f"Redo trigger failed: {resp.get('message') if resp else 'No response'}")
                            snapshot_data = await self._page.evaluate('''(args) => {
                                const responses = Array.from(document.querySelectorAll('model-response'));
                                if (responses.length === 0) return "reset";
                                return "error";
                            }''')
                            if snapshot_data == "reset":
                                resp = {"status": "reset", "message": "Reset detected during Redo attempt."}

                    # 4. Analyze Final Cycle Result
                    if not resp:
                        self._log_debug("ERROR: No response object after execution.")
                        return {"status": "error", "message": "Empty response"}

                    status = resp.get("status")
                    
                    if status == "success":
                        self.automation_status["cycles"] += 1
                        # NOTE: successes is NOT incremented here yet.
                        # It is only counted AFTER download_images confirms files are on disk.
                        # This prevents the count from inflating when a Reset occurs mid-download.
                        
                        naming = {
                            "prefix": cfg.get("name_prefix", ""), 
                            "padding": cfg.get("name_padding", 2), 
                            "start": cfg.get("name_start", 1)
                        }
                        
                        # Safety for join
                        selected_files = cfg.get("selected_files") or []
                        meta = {
                            "prompt": cfg.get("prompt", ""), 
                            "url": self.current_url or "", 
                            "upload_path": ", ".join(selected_files) if isinstance(selected_files, list) else str(selected_files)
                        }
                        
                        dl_resp = await self.download_images(cfg.get("save_dir"), naming, meta)
                        saved_paths = []
                        if dl_resp and dl_resp.get("status") == "success":
                            new_start = dl_resp.get("next_start", cfg.get("name_start"))
                            cfg["name_start"] = new_start
                            saved_paths = dl_resp.get("saved_paths", [])
                            self._update_config_start(new_start)
                            
                            # Confirm files actually landed on disk before counting as a true success.
                            if not saved_paths:
                                self._log_debug("Download returned success but saved_paths is empty. Success NOT counted.")
                            else:
                                self.automation_status["successes"] += 1
                            
                            # Write per-image reject stat record
                            cycle_end = time.time()
                            cycle_dur = cycle_end - self._cycle_start_time if self._cycle_start_time else 0
                            for sp in saved_paths:
                                self._write_reject_stat(
                                    filename=os.path.basename(sp),
                                    duration_sec=cycle_dur / max(len(saved_paths), 1),
                                    refused_count=self._pending_refused,
                                    reset_count=self._pending_resets
                                )
                            # Snapshot pending counters BEFORE zeroing
                            cycle_refused_snap = getattr(self, '_pending_refused', 0)
                            cycle_resets_snap  = getattr(self, '_pending_resets', 0)
                            lc_cycle_refused_snap = getattr(self, '_lc_pending_refused', 0)
                            lc_cycle_resets_snap = getattr(self, '_lc_pending_resets', 0)
                            
                            lc_cycle_end = time.time()
                            lc_cycle_dur = lc_cycle_end - self._lc_cycle_start_time if getattr(self, '_lc_cycle_start_time', None) else 0

                            # Reset global pending counters and mark cycle end cleanly.
                            self._pending_refused = 0
                            self._pending_resets = 0
                            self._cycle_start_time = None
                            
                            # Reset loop control pending counters.
                            self._lc_pending_refused = 0
                            self._lc_pending_resets = 0
                            self._lc_cycle_start_time = None
                        else:
                            # Download failed (e.g. Reset mid-download). Do NOT count as success.
                            self._log_debug("Download failed after image detected. Success NOT counted. Forcing New Chat.")
                            self.automation_status["resets"] += 1
                            self._pending_resets = getattr(self, '_pending_resets', 0) + 1
                            self._lc_pending_resets = getattr(self, '_lc_pending_resets', 0) + 1
                            self._automation_needs_new_chat = True
                            
                            cycle_refused_snap = 0
                            cycle_resets_snap  = 0
                            lc_cycle_refused_snap = 0
                            lc_cycle_resets_snap = 0
                            cycle_dur          = 0
                            lc_cycle_dur       = 0
                        
                        # Cycle complete — expose cycle stats for loop-control threshold check
                        return {
                            "status": "success",
                            "saved_paths": saved_paths,
                            "cycle_duration_sec": cycle_dur,
                            "cycle_refused": cycle_refused_snap,
                            "cycle_resets":  cycle_resets_snap,
                            "lc_cycle_duration_sec": lc_cycle_dur,
                            "lc_cycle_refused": lc_cycle_refused_snap,
                            "lc_cycle_resets": lc_cycle_resets_snap,
                        }
                        
                    elif status == "refused":
                        self.automation_status["cycles"] += 1
                        self.automation_status["refusals"] += 1
                        self._pending_refused = getattr(self, '_pending_refused', 0) + 1
                        self._lc_pending_refused = getattr(self, '_lc_pending_refused', 0) + 1
                        return {"status": "refused"}
                        
                    elif status == "reset":
                        self.automation_status["resets"] += 1
                        self.automation_status["cycles"] += 1
                        self._pending_resets = getattr(self, '_pending_resets', 0) + 1
                        self._lc_pending_resets = getattr(self, '_lc_pending_resets', 0) + 1
                        self._log_debug(f"Reset detected in Cycle #{self.automation_status['cycles']}. Counting and forcing New Chat.")
                        self._automation_needs_new_chat = True
                        return {"status": "reset"}
                        
                    elif status in ["error", "timeout"]:
                        if status == "error" and "quota" in str(resp.get("message", "")).lower():
                            self._log_debug("QUOTA EXCEEDED.")
                            await self.stop()
                            self.automation_status["is_running"] = False
                            self._automation_needs_new_chat = True
                            return {"status": "quota", "message": "Quota reached."}
                        else:
                            self._log_debug(f"Automation loop encountered an issue: {resp.get('message')}")
                            self.automation_status["cycles"] += 1
                            self.automation_status["resets"] += 1
                            self._pending_resets += 1
                            self._lc_pending_resets = getattr(self, '_lc_pending_resets', 0) + 1
                            self._automation_needs_new_chat = True
                            return {"status": status, "message": resp.get("message", "Unknown issue occurred")}

                    await asyncio.sleep(2)
                    

                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    self._log_debug(f"Automation Error in Cycle #{self.automation_status['cycles']+1}:\n{tb}")
                    # Treat as a recoverable reset instead of breaking the entire loop.
                    # This allows engine_service to continue with the next round or switch accounts.
                    self.automation_status["cycles"] += 1
                    self.automation_status["resets"] += 1
                    self._pending_resets = getattr(self, '_pending_resets', 0) + 1
                    self._lc_pending_resets = getattr(self, '_lc_pending_resets', 0) + 1
                    self._automation_needs_new_chat = True
                    self._log_debug("Recoverable error — will retry with New Chat on next round.")
                    return {"status": "reset", "message": f"Automation error (recovered): {e}"}

            # NOTE: We NO LONGER clear _cycle_start_time here...
            self.automation_status["is_running"] = False
            self._log_debug(f"Automation Finished. Final Stats: {self.automation_status}")
            
            # --- FINAL EXIT RECORDING REMOVED FROM HERE ---
            # Now handled by engine_service.py's finally block for better session-wide accuracy.
            
            final_status = "finished"
            if getattr(self, "_session_lost", False):
                final_status = "quota"
            elif self._stop_automation_event.is_set():
                final_status = "stopped"
                
            return {"status": final_status, "stats": self.automation_status}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._log_debug(f"CRITICAL CRASH in run_automation_loop:\n{tb}")
            self.automation_status["is_running"] = False
            return {"status": "error", "message": str(e)}
        finally:
            # Lifecycle: Ensure watchdog is killed when automation loop ends
            if self._watchdog_task:
                # Silently cancel the watchdog - no log needed for routine teardown
                self._watchdog_task.cancel()
                try:
                    await self._watchdog_task
                except asyncio.CancelledError:
                    pass
                self._watchdog_task = None

    async def _run_account_watchdog(self, target_user: str = None):
        """
        Independent background task to periodically verify login status.
        Runs until _stop_automation_event is set.
        """
        # Fully silent start - anomalies only are logged
        try:
            # Initial cooldown to let first-page navigation settle.
            # Read from config; default 20s to cover Gem URL load + model/tool apply.
            try:
                _cfg = load_config()
                initial_delay = _cfg.get("watchdog_initial_delay", 20)
            except Exception:
                initial_delay = 20
            await asyncio.sleep(initial_delay)
            
            while not self._stop_automation_event.is_set():
                if not self.is_running or not self._page:
                    break
                
                try:
                    # Non-invasive account check
                    acc = await self.get_account_info()
                    
                    # 1. Detection: Not Logged In
                    if not acc.get("logged_in"):
                        self._log_watchdog("CRITICAL - Session lost (Guest detected).", to_ui=True)
                        self._session_lost = True
                        self._stop_automation_event.set()
                        break
                    
                    # 2. Detection: Account Mismatch (if target_user provided as email)
                    current_acc = acc.get("account_id")
                    if target_user and "@" in target_user and current_acc:
                        if target_user.lower() != current_acc.lower() and current_acc != "Unknown Account":
                            self._log_watchdog(f"CRITICAL - Account mismatch! Expected {target_user}, found {current_acc}.", to_ui=True)
                            self._session_lost = True
                            self._stop_automation_event.set()
                            break

                except Exception as e:
                    self._log_watchdog(f"Anomaly: Check failed ({e}). Retrying in 30s...")

                # Periodic check interval
                await asyncio.sleep(45)
                
        except asyncio.CancelledError:
            pass # Clean exit
        except Exception as e:
            self._log_watchdog(f"Critical Watchdog Internal Error: {e}")
        # No finally log - fully silent on normal end

    def _update_config_start(self, next_start):
        """Helper to persist the next available start number using config_utils."""
        try:
            save_config({"name_start": next_start})
            self._log_debug(f"Persistence: next start number updated to {next_start}.")
        except Exception as e:
            self._log_debug(f"Persistence Error: Failed to update config: {e}")

    async def get_account_info(self):
        """Checks the browser's top-right login status via DOM selectors.
        Returns a dict: {logged_in: bool, account_id: str|None, status: str}
        Based on the proven check_signin.py reference pattern.
        """
        if not self.is_running:
            raise Exception("Browser Engine not started")

        import re

        # Brief stability wait, then try network idle
        await self._page.wait_for_timeout(200)
        try:
            await self._page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass  # Proceed even if network idle times out

        # Selector 1: Google Account button (logged-in indicator)
        user_avatar = self._page.locator(
            'a[href*="accounts.google.com/SignOut"], button[aria-label*="Google Account"]'
        ).first

        # Selector 2: Sign-in button (not-logged-in indicator)
        signin_button = self._page.locator(
            'a[href*="accounts.google.com/ServiceLogin"], button:has-text("Sign in")'
        ).first

        is_logged_in = await user_avatar.is_visible()
        is_not_logged_in = await signin_button.is_visible()

        if is_logged_in:
            account_id = "Unknown Account"
            try:
                aria_label = await user_avatar.get_attribute("aria-label")
                if aria_label:
                    # Extract email from "Google Account: Name (email@gmail.com)"
                    match_email = re.search(r"\(([^)]+@[^)]+)\)", aria_label, re.I)
                    match_name = re.search(r"Google Account:\s*(.*?)\s*\(", aria_label, re.I)
                    if match_email:
                        account_id = match_email.group(1)
                    elif match_name:
                        account_id = match_name.group(1)
                    else:
                        account_id = aria_label.split(':')[-1].strip()
            except Exception:
                pass
            
            # Cache it in automation_status so it can be exposed cheaply
            self.automation_status["current_account_id"] = account_id
            return {"logged_in": True, "account_id": account_id, "status": "logged_in"}

        elif is_not_logged_in:
            self.automation_status["current_account_id"] = None
            return {"logged_in": False, "account_id": None, "status": "not_logged_in"}

        else:
            # Fallback: check Gemini sidebar conversations list
            chat_list = self._page.locator('div[data-test-id="conversations-list"]').first
            if await chat_list.is_visible():
                account_id = "Unknown (sidebar detected)"
                self.automation_status["current_account_id"] = account_id
                return {"logged_in": True, "account_id": account_id, "status": "logged_in"}
            
            self.automation_status["current_account_id"] = None
            return {"logged_in": False, "account_id": None, "status": "unknown"}

    async def test_connection(self):
        """Simple test to verify Playwright installation."""
        try:
            await self.start()
            status = await self.navigate("https://www.google.com")
            print(f"Connection Test: Google returned {status}")
            await self.get_screenshot("browser_screen_capture/test_google.png")
            await self.stop()
            return True
        except Exception as e:
            print(f"Connection Test Failed: {e}")
            return False

if __name__ == "__main__":
    # Test script
    engine = BrowserEngine()
    asyncio.run(engine.test_connection())
