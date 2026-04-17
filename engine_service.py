import sys
import asyncio
import time
import json
from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
import uvicorn
from browser_engine import BrowserEngine
import os
from datetime import datetime
from config_utils import load_config, save_config

# Fix for Windows asyncio NotImplementedError with subprocesses
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="GemiPersona Engine Service")
engine = BrowserEngine()

# Heartback logic
last_heartbeat = time.time()
HEARTBEAT_TIMEOUT = 3600 # Default 1 hour

async def monitor_heartbeat():
    global last_heartbeat
    while True:
        await asyncio.sleep(10)
        if HEARTBEAT_TIMEOUT > 0:
            # If automation is running, effectively pause the heartbeat timeout
            # by constantly refreshing the last heartbeat time.
            if engine.automation_status.get("is_running"):
                last_heartbeat = time.time()
                
            elapsed = time.time() - last_heartbeat
            if elapsed > HEARTBEAT_TIMEOUT:
                print(f"No heartbeat for {elapsed:.1f}s. Auto-shutting down...")
                # We can't easily trigger app.shutdown() from here in all uvicorn setups, 
                # but we can stop engine and exit.
                await engine.stop()
                os._exit(0)

class NavigateRequest(BaseModel):
    url: str

class PromptRequest(BaseModel):
    text: str

class PersonaRequest(BaseModel):
    headless: bool | None = None

class DownloadRequest(BaseModel):
    save_dir: str
    naming: dict  # {prefix, padding, start}
    meta: dict    # {prompt, url, upload_path}

class ProcessRequest(BaseModel):
    paths: list[str]
    save_dir: str

class AutomationRequest(BaseModel):
    mode: str  # "rounds" or "images"
    goal: int
    config: dict

@app.on_event("startup")
async def startup_event():
    print("Engine Service Starting...")
    asyncio.create_task(monitor_heartbeat())

@app.post("/engine/heartbeat")
async def heartbeat():
    global last_heartbeat
    last_heartbeat = time.time()
    return {"status": "heartbeat received", "timestamp": last_heartbeat}

@app.on_event("shutdown")
async def shutdown_event():
    await engine.stop()
    print("Engine Service Stopped.")

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "engine_running": engine.is_running,
        "service_pid": os.getpid(),
        "browser_pids": engine.browser_pids if engine.is_running else []
    }

@app.get("/browser/status")
async def get_browser_status():
    if not engine.is_running:
        return {"engine_running": False}
    return {
        "engine_running": True,
        "url": engine.current_url,
        "browser_pids": engine.browser_pids
    }

@app.get("/engine/logs")
async def get_engine_logs():
    """Retrieve and clear the recent internal engine logs."""
    logs = engine.get_and_clear_logs() if hasattr(engine, 'get_and_clear_logs') else []
    return {"logs": logs}

@app.post("/engine/clear_logs")
async def clear_engine_logs():
    """Clear physical engine.log file."""
    success = engine.clear_physical_logs()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear log file.")
    return {"status": "success", "message": "Engine log file cleared."}

@app.post("/engine/start")
async def start_engine(req: PersonaRequest | None = None):
    global HEARTBEAT_TIMEOUT, last_heartbeat
    
    def get_abs_path(rel_path):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), rel_path))

    config_path = get_abs_path("config.json")
    
    headless_config = True
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                HEARTBEAT_TIMEOUT = cfg.get("heartbeat_timeout", 3600)
                headless_config = cfg.get("headless", True)
    except:
        pass
    
    last_heartbeat = time.time()
    try:
        h_val = headless_config
        if req and req.headless is not None:
            h_val = req.headless
        
        # Determine if we should load the last active user from config
        active_profile = None
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    active_user = cfg.get("active_user")
                    if active_user:
                        # Map to profile
                        lookup_path = get_abs_path("user_login_lookup.json")
                        local_state_path = get_abs_path(os.path.join("browser_user_data", "Local State"))
                        if os.path.exists(local_state_path):
                            with open(local_state_path, "r", encoding="utf-8") as f:
                                state = json.load(f)
                                info_cache = state.get("profile", {}).get("info_cache", {})
                                for p_dir, p_info in info_cache.items():
                                    u_name = p_info.get("user_name")
                                    if u_name and active_user.split('@')[0].lower() == u_name.split('@')[0].lower():
                                        active_profile = p_dir
                                        break
        except:
            pass

        if req:
            await engine.start(
                headless=h_val,
                profile_name=active_profile
            )
        else:
            await engine.start(headless=h_val, profile_name=active_profile)
        return {"message": f"Engine started (headless={h_val}, profile={active_profile})"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/engine/stop")
async def stop_engine():
    await engine.stop()
    return {"message": "Engine stopped"}

@app.post("/engine/start_registration")
async def start_registration():
    """Opens a headed browser directly against browser_user_data/ for profile registration."""
    if engine.is_running:
        raise HTTPException(status_code=400, detail="Stop the main browser before opening Registration Mode.")
    try:
        await engine.start_registration()
        return {"status": "success", "message": "Registration browser opened. Add your Google account, then close the browser window or call stop_registration."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/engine/stop_registration")
async def stop_registration():
    """Closes the registration browser."""
    try:
        await engine.stop_registration()
        return {"status": "success", "message": "Registration browser closed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/navigate")
async def navigate(req: NavigateRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        status = await engine.navigate(req.url)
        return {"status_code": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/browser/snapshot")
async def get_snapshot():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        path = await engine.get_screenshot()
        return {"screenshot_path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def perform_switch_logic(h: bool = None, direction: int = 1, target_username: str = None, reason: str = None):
    """
    Internal logic for profile switching.
    direction: +1 = next (default), -1 = previous.
    target_username: if provided, switch directly to that user (ignores direction).
    """
    def get_abs_path(rel_path):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), rel_path))

    lookup_path = get_abs_path("user_login_lookup.json")
    config_path = get_abs_path("config.json")
    
    if not os.path.exists(lookup_path):
        return {"status": "error", "message": "user_login_lookup.json not found"}
    local_state_path = get_abs_path(os.path.join("browser_user_data", "Local State"))

    # 1. Detect current user
    current_email = None
    if engine.is_running:
        try:
            acc_info = await engine.get_account_info()
            current_email = acc_info.get("account_id")
        except: pass

    # 2. Load users
    try:
        with open(lookup_path, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Read lookup failed: {e}"}

    if not users:
        return {"status": "error", "message": "No users found"}

    def normalize(val):
        if not val: return ""
        return val.split('@')[0].lower().strip()

    # Determine outgoing user index based on current_email or 'active' flag
    outgoing_index = -1
    if current_email:
        norm_current = normalize(current_email)
        for i, u in enumerate(users):
            if normalize(u.get("username")) == norm_current:
                outgoing_index = i
                break
    if outgoing_index == -1:
        for i, u in enumerate(users):
            if u.get("active"):
                outgoing_index = i
                break

    # 3a. Direct target: find the requested user immediately
    if target_username:
        norm_target = normalize(target_username)
        start_index = next(
            (i for i, u in enumerate(users) if normalize(u.get("username")) == norm_target),
            -1
        )
        if start_index == -1:
            return {"status": "error", "message": f"User '{target_username}' not found in lookup"}
        # If the direct target (e.g. re-login) is bypassed, fall back to sequential next
        if users[start_index].get("bypass", False):
            print(f"[ENGINE] Direct target '{target_username}' is bypassed. Falling back to sequential next.")
            direction = 1  # Fall back to sequential next
        else:
            # Treat start_index as the target itself (offset=0)
            direction = 0

    # 3b. Sequential: find current user's index
    else:
        start_index = outgoing_index if outgoing_index != -1 else 0

    # 4. Find target / next valid profile
    profile_name = None
    target_user = None
    num_users = len(users)
    initial_user = engine.automation_status.get("initial_user")

    # If reason is quota, mark current user as full BEFORE finding next
    if reason == "quota":
        # We mark the user at outgoing_index (the one that was just active)
        if 0 <= outgoing_index < len(users):
            u = users[outgoing_index]
            u["quota_full"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            print(f"[ENGINE] Marked {u['username']} as Quota Full.")
            try:
                with open(lookup_path, "w", encoding="utf-8") as f:
                    json.dump(users, f, indent=4, ensure_ascii=False)
            except: pass

    # For direct target: only try offset 0; for sequential: try offsets 1..N in direction
    offsets = [0] if direction == 0 else range(1, num_users + 1)
    for offset in offsets:
        idx = (start_index + offset * (direction if direction != 0 else 1)) % num_users
        candidate = users[idx]
        norm_email = normalize(candidate.get("username"))
        
        # ANCHOR LOGIC: If we've looped back to initial_user, we are done with one full traversal.
        # But only if we actually moved (offset > 0) AND we are in an automated search (reason is not None).
        if reason and direction != 0 and offset > 0:
             if initial_user and normalize(initial_user) == norm_email:
                 print("[ENGINE] Table traversal complete. Back to initial user.")
                 return {"status": "table_full", "message": "All profiles have been processed or hit quota."}

        cand_profile = None
        try:
            if os.path.exists(local_state_path):
                with open(local_state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    info_cache = state.get("profile", {}).get("info_cache", {})
                    for p_dir, p_info in info_cache.items():
                        if normalize(p_info.get("user_name")) == norm_email:
                            cand_profile = p_dir
                            break
        except: continue

        # Skip accounts flagged as Bypass
        if candidate.get("bypass", False):
            print(f"[ENGINE] Skipping '{candidate.get('username')}' (Bypass enabled).")
            continue

        if cand_profile:
            prof_dir = get_abs_path(os.path.join("browser_user_data", cand_profile))
            if os.path.exists(prof_dir):
                profile_name = cand_profile
                target_user = candidate
                break

    if not profile_name:
        return {"status": "error", "message": "No valid profile found"}

    is_real_switch = True
    if target_user and outgoing_index != -1:
        if normalize(users[outgoing_index].get("username")) == normalize(target_user.get("username")):
            is_real_switch = False

    # 5a. Record per-account session stats for the outgoing account (delta vs. snapshot)
    if is_real_switch and 0 <= outgoing_index < len(users) and getattr(engine, "_acct_snapshot", None) is not None:
        snap = engine._acct_snapshot
        cur  = engine.automation_status
        users[outgoing_index]["last_switched_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        users[outgoing_index]["session_images"]   = max(0, int(cur.get("successes", 0)) - int(snap.get("successes", 0)))
        users[outgoing_index]["session_refused"]  = max(0, int(cur.get("refusals",  0)) - int(snap.get("refusals",  0)))
        users[outgoing_index]["session_resets"]   = max(0, int(cur.get("resets",    0)) - int(snap.get("resets",    0)))
        print(f"[ENGINE] Session stats for '{users[outgoing_index]['username']}': "
              f"images={users[outgoing_index]['session_images']}, "
              f"refused={users[outgoing_index]['session_refused']}, "
              f"resets={users[outgoing_index]['session_resets']}")

    # 5b. Load Target URL for Navigation
    target_url = "https://gemini.google.com/app"
    cfg = load_config()
    target_url = cfg.get("browser_url", target_url)

    # 6. Restart Engine
    print(f"[ENGINE] Switching to: {target_user['username']}")
    await engine.stop()
    await asyncio.sleep(2.0)
    
    h_val = h if h is not None else engine.last_headless
    await engine.start(headless=h_val, profile_name=profile_name)
    print(f"[ENGINE] Navigating to: {target_url}")
    await engine.navigate(target_url)
    
    # --- Headless Login Fallback Logic ---
    await asyncio.sleep(3.0) # Wait for initial load
    
    def check_match(current_id, expected_user):
        if not current_id: return False
        return normalize(current_id) == normalize(expected_user)
        
    try:
        acc_info = await engine.get_account_info()
        is_logged_in = acc_info.get("logged_in", False)
        current_id = acc_info.get("account_id")
        
        if not is_logged_in or not check_match(current_id, target_user['username']):
            if h_val: # If we are in headless mode, try headed fallback
                print(f"[ENGINE] Headless login check failed for {target_user['username']}. Attempting headed fallback...")
                await engine.stop()
                await asyncio.sleep(2.0)
                
                # Start headed
                await engine.start(headless=False, profile_name=profile_name)
                await engine.navigate(target_url)
                await asyncio.sleep(5.0) # Wait a bit longer for headed load
                
                # Check again immediately
                acc_info_headed = await engine.get_account_info()
                is_logged_in_headed = acc_info_headed.get("logged_in", False)
                current_id_headed = acc_info_headed.get("account_id")
                
                if not is_logged_in_headed or not check_match(current_id_headed, target_user['username']):
                    # Fallback failed
                    err_msg = f"Headed fallback login failed or account mismatch. Expected: {target_user['username']}, Got: {current_id_headed}"
                    print(f"[ENGINE] {err_msg}")
                    await engine.stop()
                    return {"status": "error", "message": err_msg}
                else:
                    # Fallback succeeded, back to headless
                    print(f"[ENGINE] Headed fallback succeeded for {target_user['username']}. Returning to headless...")
                    await engine.stop()
                    await asyncio.sleep(2.0)
                    await engine.start(headless=True, profile_name=profile_name)
                    await engine.navigate(target_url)
                    await asyncio.sleep(3.0)
            else:
                # Already headed, but failed
                err_msg = f"Login failed or account mismatch. Expected: {target_user['username']}, Got: {current_id}"
                print(f"[ENGINE] {err_msg}")
                return {"status": "error", "message": err_msg}
                
    except Exception as e:
        print(f"[ENGINE] Error during login check: {e}")
        return {"status": "error", "message": f"Login check failed: {e}"}

    # --- [FIX BUG 1] Update persistence ONLY AFTER successful login verification ---
    for u in users:
        u["active"] = (u["username"] == target_user["username"])
    try:
        with open(lookup_path, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
        save_config({"active_user": target_user["username"]})
    except Exception as e:
        print(f"[ENGINE] Warning: failed to save persistence after login check: {e}")

    # --- [NEW] Trigger History Deletion if enabled for this profile ---
    try:
        from config_utils import load_login_lookup
        login_lookup = load_login_lookup()
        user_settings = next((u for u in login_lookup if u.get("username") == target_user["username"]), {})
        
        if user_settings.get("auto_delete"):
            del_range = user_settings.get("delete_range", "Last hour")
            engine._log_debug(f"API>> Auto-delete triggered ({del_range})...")
            del_resp = await engine.delete_activity_history(range_name=del_range)
            engine._log_debug(f"API>> {del_resp.get('message')}")
            
            # Navigate back to the intended Gemini URL after deletion
            engine._log_debug(f"API>> Returning to Gemini App: {target_url}")
            await engine.navigate(target_url)
    except Exception as e:
        engine._log_debug(f"API>> Error triggering auto-delete: {e}")
        
    # --- [NEW] Deep Clean Gemini Context on Re-login ---
    # If the user switched to the exact same account, it's a re-login. We should clear Local Storage
    # to completely obliterate the stuck context before the new loop starts.
    if current_email and normalize(current_email) == normalize(target_user['username']):
        engine._log_debug(f"API>> Re-login detected for {current_email}. Clearing local state...")
        try:
            # Must navigate to Gemini domain first before clearing storage for that origin
            await engine.navigate("https://gemini.google.com/")
            await asyncio.sleep(2.0)
            if hasattr(engine, "_page") and engine._page:
                await engine._page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
                engine._log_debug("API>> Cleared Gemini local/session storage.")
            # Restore the target URL
            await engine.navigate(target_url)
            await asyncio.sleep(2.0)
        except Exception as e:
            engine._log_debug(f"API>> Failed to clear local storage: {e}")
    # -----------------------------------
    
    # Reset the per-account snapshot to current cumulative stats so that the incoming
    # account's session begins with a clean delta baseline.
    if is_real_switch:
        engine._acct_snapshot = {
            "successes": engine.automation_status.get("successes", 0),
            "refusals":  engine.automation_status.get("refusals",  0),
            "resets":    engine.automation_status.get("resets",    0),
        }

    return {
        "status": "success",
        "message": f"Switched to {target_user['username']}",
        "user": target_user["username"],
        "profile": profile_name
    }

@app.post("/engine/switch_profile")
async def switch_profile(h: bool = Query(None)):
    res = await perform_switch_logic(h, direction=1)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

@app.post("/engine/switch_profile_previous")
async def switch_profile_previous(h: bool = Query(None)):
    res = await perform_switch_logic(h, direction=-1)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

@app.post("/engine/switch_to_profile")
async def switch_to_profile(username: str = Query(...), h: bool = Query(None)):
    res = await perform_switch_logic(h, target_username=username)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

def _check_loop_control_thresholds(loop_ctrl: dict, result: dict):
    """
    Checks the three loop-control thresholds against the just-settled cycle stats.
    Returns (should_switch: bool, action: str)  action = 'next_profile' | 're_login'
    """
    if not loop_ctrl:
        return False, "next_profile"

    dur_min = result.get("cycle_duration_sec", 0) / 60.0
    refused   = result.get("cycle_refused", 0)
    resets    = result.get("cycle_resets",  0)

    # Time threshold
    if loop_ctrl.get("time_enabled") and dur_min >= loop_ctrl.get("time_minutes", 999):
        return True, loop_ctrl.get("time_action", "next_profile")
    # Refused threshold
    if loop_ctrl.get("refused_enabled") and refused >= loop_ctrl.get("refused_threshold", 999):
        return True, loop_ctrl.get("refused_action", "next_profile")
    # Reset threshold
    if loop_ctrl.get("reset_enabled") and resets >= loop_ctrl.get("reset_threshold", 999):
        return True, loop_ctrl.get("reset_action", "next_profile")

    return False, "next_profile"


async def automation_manager(req: AutomationRequest):
    """Background task to manage loops and quota-restarts."""
    try:
        while True:
            # Modified Check: If stop signal is set, ONLY break if it's NOT a session loss.
            # If session loss is True, we want to proceed to the recovery logic below.
            if engine._stop_automation_event.is_set() and not getattr(engine, "_session_lost", False):
                print("[AUTO] User stop signal detected in manager.")
                break
                
            # 1. Reload Config from Disk (Ensures profile switches/URL changes are picked up)
            req.config.update(load_config())

            # 1b. Check Goal Satisfaction
            status = engine.automation_status
            mode = req.mode
            goal = req.goal
            
            if mode == "rounds":
                if status["cycles"] >= goal:
                    print(f"[AUTO] Goal reached: {goal} rounds.")
                    break
            elif mode == "images":
                if status["successes"] >= goal:
                    print(f"[AUTO] Goal reached: {goal} images.")
                    break

            # 2. Pre-load Watermark Removal Model if enabled
            cfg = req.config
            use_gpu_cfg = cfg.get("automation", {}).get("use_gpu", True)
            if cfg.get("remove_watermark", False):
                try:
                    from processing_utils import get_shared_processor
                    # Singleton access (cached)
                    get_shared_processor(use_gpu=use_gpu_cfg)
                except Exception as p_err:
                    print(f"[AUTO] Model pre-load failed: {p_err}")

            # 3. Execute ONE iteration
            result = await engine.run_automation_loop(req.dict())
            
            # 4. Post-action: Remove Watermark if enabled (MIMIC Gemini Actions flow: Download -> Process)
            if result.get("status") == "success" and cfg.get("remove_watermark", False):
                paths = result.get("saved_paths", [])
                if paths:
                    try:
                        from processing_utils import get_shared_processor, save_with_metadata
                        from PIL import Image
                        processor = get_shared_processor(use_gpu=use_gpu_cfg)
                        p_dir = os.path.join(cfg.get("save_dir"), "processed")
                        os.makedirs(p_dir, exist_ok=True)
                        
                        print(f"[AUTO] Refining {len(paths)} new images...")
                        for p in paths:
                            if os.path.exists(p):
                                with Image.open(p) as img:
                                    final_img = processor.hybrid_process(img)
                                    p_path = os.path.join(p_dir, os.path.basename(p))
                                    # save_with_metadata already fixed to NOT preserve unnecessary original info
                                    save_with_metadata(final_img, img, p_path)
                        print("[AUTO] Refinement complete.")
                    except Exception as p_err:
                        print(f"[AUTO] Refinement step failed: {p_err}")

            # 4b. Loop-Control Threshold Check (applies to success, refused, reset, error, timeout)
            if result.get("status") in ["success", "refused", "reset", "error", "timeout"]:
                loop_ctrl = req.config.get("automation", {}).get("loop_control", {})
                lc_trigger, lc_action = False, "next_profile"
                
                if loop_ctrl:
                    v_dur = result.get("lc_cycle_duration_sec", (time.time() - getattr(engine, '_lc_cycle_start_time', time.time())) if getattr(engine, '_lc_cycle_start_time', None) else 0)
                    v_ref = result.get("lc_cycle_refused", getattr(engine, '_lc_pending_refused', 0))
                    v_rst = result.get("lc_cycle_resets", getattr(engine, '_lc_pending_resets', 0))
                    
                    lc_trigger, lc_action = _check_loop_control_thresholds(
                        loop_ctrl,
                        {"cycle_duration_sec": v_dur, "cycle_refused": v_ref, "cycle_resets": v_rst}
                    )

                if lc_trigger:
                    engine._log_debug(f"API>> Loop Control triggered (action={lc_action}). Attempting switch...")
                    current_user = (
                        engine.automation_status.get("current_account_id")
                        or req.config.get("active_user")
                    )
                    if lc_action == "re_login" and current_user:
                        lc_switch_res = await perform_switch_logic(target_username=current_user)
                    else:
                        lc_switch_res = await perform_switch_logic()  # direction=+1 (next)

                    if lc_switch_res.get("status") == "success":
                        engine._log_debug(
                            f"API>> Loop Control: switched to {lc_switch_res.get('user')}. "
                            f"Resetting loop control pending counters..."
                        )
                        await asyncio.sleep(5)
                        engine._stop_automation_event.clear()
                        engine._lc_pending_refused = 0
                        engine._lc_pending_resets  = 0
                        engine._lc_cycle_start_time = time.time()
                        engine._automation_needs_new_chat = True
                        continue
                    elif lc_switch_res.get("status") == "table_full":
                        loop_ctrl = req.config.get("automation", {}).get("loop_control", {})
                        inf_en = loop_ctrl.get("infinite_loop_enabled", False)
                        if not inf_en:
                            engine._log_debug("API>> Loop Control switch: All profiles processed or hit quota. Table complete. Stopping automation.")
                            break
                        else:
                            sleep_min = loop_ctrl.get("infinite_loop_minutes", 60)
                            engine._log_debug(f"API>> Loop Control switch: All profiles processed. Infinite loop enabled: sleeping for {sleep_min} min...")
                            print(f"[AUTO] Loop Control cycle finish. Sleeping for {sleep_min} minutes before next run.")
                            
                            sleep_sec = int(sleep_min * 60)
                            interrupted = False
                            for _ in range(sleep_sec):
                                if engine._stop_automation_event.is_set():
                                    interrupted = True
                                    break
                                await asyncio.sleep(1)
                                
                            if interrupted:
                                engine._log_debug("API>> Sleep interrupted by user stop.")
                                break
                                
                            # Awake from sleep. Reset anchor point for the next full loop.
                            engine._log_debug("API>> Awakening from sleep. Restarting infinite loop cycle...")
                            new_anchor = load_config().get("active_user")
                            engine.automation_status["initial_user"] = new_anchor
                            if hasattr(engine, '_session_lost'): engine._session_lost = False
                            engine._stop_automation_event.clear()
                            
                            # Short circuit variables for loop control
                            engine._lc_cycle_start_time = time.time()
                            engine._lc_pending_refused = 0
                            engine._lc_pending_resets = 0
                            continue
                    else:
                        engine._log_debug(
                            f"API>> Loop Control switch failed: {lc_switch_res.get('message')}. Breaking loop to prevent infinite retry..."
                        )
                        break

            # 5. Handle Terminal/Retry States
            if result.get("status") == "quota":
                if engine._stop_automation_event.is_set():
                    # If stop signal is set, and session was lost, attempt recovery before breaking.
                    # This allows the watchdog to potentially recover even if automation was told to stop.
                    if getattr(engine, "_session_lost", False):
                        print("[AUTO] Watchdog detected session loss. Attempting recovery...")
                        engine._log_debug("WATCHDOG>> Session loss detected. Triggering recovery...")
                        switch_res = await perform_switch_logic(reason="session_loss")
                        if switch_res.get("status") == "success":
                            engine._log_debug(f"API>> Profile switched to {switch_res.get('user')}. Restarting loop flow...")
                            await asyncio.sleep(5) 
                            engine._stop_automation_event.clear()
                            if hasattr(engine, '_session_lost'): engine._session_lost = False
                            engine._automation_needs_new_chat = True
                            # Reset cycle timer & pending counters so the switch window
                            # is not misrecorded as a [Stopped/Interrupted] entry.
                            engine._cycle_start_time = time.time()
                            engine._pending_refused = 0
                            engine._pending_resets = 0
                            continue # Try next loop with new user
                        else:
                            print(f"[AUTO] Watchdog recovery failed: {switch_res.get('message')}. Stopping automation.")
                            break
                    else:
                        break # Original behavior: if stop signal is set, just break.
                # Check if loop exited due to watchdog/session loss
                if getattr(engine, "_session_lost", False):
                    print("[AUTO] Watchdog detected session loss. Attempting recovery...")
                    engine._log_debug("WATCHDOG>> Session loss detected. Triggering recovery...")
                    switch_res = await perform_switch_logic(reason="session_loss")
                else:
                    print("[AUTO] Quota hit. Attempting profile switch...")
                    switch_res = await perform_switch_logic(reason="quota")
                if switch_res.get("status") == "success":
                    engine._log_debug(f"API>> Profile switched to {switch_res.get('user')}. Restarting loop flow...")
                    await asyncio.sleep(5) 
                    engine._stop_automation_event.clear()
                    if hasattr(engine, '_session_lost'): engine._session_lost = False
                    engine._automation_needs_new_chat = True
                    # DO NOT reset global pending counters here! They should map to the final saved image.
                    engine._lc_pending_refused = 0
                    engine._lc_pending_resets = 0
                    engine._lc_pending_refused = 0
                    engine._lc_pending_resets = 0
                    engine._lc_cycle_start_time = time.time()
                    continue # Try next loop with new user
                elif switch_res.get("status") == "table_full":
                    loop_ctrl = req.config.get("automation", {}).get("loop_control", {})
                    inf_en = loop_ctrl.get("infinite_loop_enabled", False)
                    if not inf_en:
                        engine._log_debug("API>> All profiles processed or hit quota. Table complete. Stopping automation.")
                        break
                    else:
                        sleep_min = loop_ctrl.get("infinite_loop_minutes", 60)
                        engine._log_debug(f"API>> All profiles processed. Infinite loop enabled: sleeping for {sleep_min} min...")
                        print(f"[AUTO] Cycle finish. Sleeping for {sleep_min} minutes before next run.")
                        
                        sleep_sec = int(sleep_min * 60)
                        interrupted = False
                        for _ in range(sleep_sec):
                            if engine._stop_automation_event.is_set():
                                interrupted = True
                                break
                            await asyncio.sleep(1)
                            
                        if interrupted:
                            engine._log_debug("API>> Sleep interrupted by user stop.")
                            break
                            
                        # Awake from sleep. Reset anchor point for the next full loop.
                        engine._log_debug("API>> Awakening from sleep. Restarting infinite loop cycle...")
                        # 重新设置起跑线锚点
                        new_anchor = load_config().get("active_user")
                        engine.automation_status["initial_user"] = new_anchor
                        if hasattr(engine, '_session_lost'): engine._session_lost = False
                        engine._stop_automation_event.clear()
                        # Short circuit variables for loop control
                        engine._lc_cycle_start_time = time.time()
                        engine._lc_pending_refused = 0
                        engine._lc_pending_resets = 0
                        # Try again with current anchor
                        continue
                else:
                    print(f"[AUTO] Profile switch failed: {switch_res.get('message')}")
                    break
            
            if result.get("status") in ["stopped", "finished"]:
                break

            # Small cooldown between successful/refused rounds
            await asyncio.sleep(1)
    except Exception as e:
        print(f"[AUTO] CRITICAL ERROR in manager: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Final cleanup: Write an [Interrupted] record if there's pending time/counts
        # This only triggers when the automation manager COMPLETELY exits.
        if engine._cycle_start_time is not None:
            final_dur = time.time() - engine._cycle_start_time
            if final_dur > 1 or engine._pending_refused > 0 or engine._pending_resets > 0:
                engine._log_debug(f"API>> Automation manager ending. Discarding trailing stats: dur={final_dur:.1f}s, refused={engine._pending_refused}, resets={engine._pending_resets}")

        
        engine.automation_status["is_running"] = False
        stats = engine.automation_status
        engine._log_debug(f"API>> Automation Manager Exited. Final Stats: {stats}")
        print("[AUTO] Automation manager exited.")

@app.post("/browser/automation/start")
async def start_automation(req: AutomationRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    if engine.automation_status["is_running"]:
        return {"status": "error", "message": "Automation already running"}
        
    # Clear the stop signal to allow a clean restart
    engine._stop_automation_event.clear()
    
    # Quota marks are preserved intentionally; use the "Clear All Quotas" button to reset manually.

    # Detect current active user for anchor
    cfg = load_config()
    initial_user = cfg.get("active_user")

    # Reset stats ONLY at the very beginning of a new session
    engine.automation_status.update({
        "mode": req.mode,
        "goal": req.goal,
        "cycles": 0,
        "successes": 0,
        "refusals": 0,
        "resets": 0,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "initial_user": initial_user
    })
    engine._automation_needs_new_chat = True # Ensure first round starts with New Chat

    # Reset per-image reject stat log for the new session
    try:
        with open(engine._reject_log_path, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception as e:
        print(f"[AUTO] Warning: could not reset reject_stat_log.json: {e}")
    engine._pending_refused = 0
    engine._pending_resets = 0
    engine._lc_pending_refused = 0
    engine._lc_pending_resets = 0
    # Initialize cycle timer to capture initial setup time in the first image's duration
    engine._cycle_start_time = time.time()
    engine._lc_cycle_start_time = time.time()
    # Snapshot the current stats baseline for the first account's session.
    # Stats were just reset to 0 above, so this snapshot is always {0, 0, 0}.
    engine._acct_snapshot = {"successes": 0, "refusals": 0, "resets": 0}

    # Mark as running IMMEDIATELY (synchronous) to prevent race conditions.
    # Without this, two near-simultaneous requests can both pass the "is_running" guard
    # above because the async task hasn't set the flag yet — causing duplicate managers.
    engine.automation_status["is_running"] = True

    asyncio.create_task(automation_manager(req))
    return {"status": "success", "message": "Automation started in background"}

@app.post("/browser/automation/stop")
async def stop_automation():
    await engine.stop_automation()
    return {"status": "success", "message": "Stop signal sent"}

@app.post("/browser/automation/request_new_chat")
async def request_new_chat():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    engine._automation_needs_new_chat = True
    return {"status": "success", "message": "New chat requested for next cycle"}

@app.get("/browser/automation/stats")
async def get_automation_stats():
    return engine.automation_status

@app.get("/browser/account")
async def get_account():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.get_account_info()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/prompt")
async def send_prompt(req: PromptRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.send_prompt(req.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/browser/attach_files")
async def attach_files(file_paths: list[str] = Body(...)):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.attach_files(file_paths)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/clear_attachments")
async def clear_attachments():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.clear_attachments()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/discover")
async def discover_capabilities():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.discover_capabilities()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SettingsRequest(BaseModel):
    model: str = None
    tool: str = None

@app.post("/browser/apply_settings")
async def apply_settings(req: SettingsRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.apply_settings(model_name=req.model, tool_name=req.tool)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/browser/gem_title")
async def get_gem_title():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.get_gem_title()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/browser/gem_info")
async def get_gem_info():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.get_gem_info()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/submit")
async def submit_response(req: PromptRequest | None = None):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        text = req.text if req else None
        result = await engine.submit_response(text=text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/stop")
async def stop_response():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.stop_response()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/redo")
async def redo_response():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        result = await engine.redo_response()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/new_chat")
async def new_chat():
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        # Load browser_url from config to handle Gem URLs correctly
        target_url = None
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.json"))
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    target_url = cfg.get("browser_url")
            except: pass
            
        result = await engine.new_chat(target_url=target_url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/browser/download")
async def download_images(req: DownloadRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        # Acquisition Only
        result = await engine.download_images(
            save_dir=req.save_dir,
            naming_cfg=req.naming,
            extra_meta=req.meta
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# We use get_shared_processor from processing_utils to prevent reloading models
@app.post("/browser/process")
async def process_images(req: ProcessRequest):
    try:
        from processing_utils import get_shared_processor, save_with_metadata
        from PIL import Image
        
        cfg = load_config()
        use_gpu_cfg = cfg.get("automation", {}).get("use_gpu", True)
        processor = get_shared_processor(use_gpu=use_gpu_cfg)
            
        p_dir = os.path.join(req.save_dir, "processed")
        os.makedirs(p_dir, exist_ok=True)
        
        processed_count = 0
        for path in req.paths:
            if os.path.exists(path):
                with Image.open(path) as img:
                    final_img = processor.hybrid_process(img)
                    p_path = os.path.join(p_dir, os.path.basename(path))
                    save_with_metadata(final_img, img, p_path)
                    processed_count += 1
        
        return {"status": "success", "processed_count": processed_count, "processed_dir": p_dir}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
