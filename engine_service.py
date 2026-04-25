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
    clear_pending: bool = False

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
        "automation_running": engine.automation_status.get("is_running", False),
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

def _commit_session_stats_to_table(in_memory_users=None):
    """Calculates delta from _acct_snapshot, adds to user_login_lookup.json, and updates snapshot."""
    try:
        current_user = engine.automation_status.get("current_account_id")
        if not current_user:
            from config_utils import load_config
            cfg = load_config()
            current_user = cfg.get("active_user")
        if not current_user:
            return

        def normalize(val):
            if not val: return ""
            return val.split('@')[0].lower().strip()

        snap = getattr(engine, "_acct_snapshot", None) or {"successes": 0, "refusals": 0, "resets": 0}
        cur = engine.automation_status
        delta_img = max(0, int(cur.get("successes", 0)) - int(snap.get("successes", 0)))
        delta_ref = max(0, int(cur.get("refusals", 0)) - int(snap.get("refusals", 0)))
        delta_rst = max(0, int(cur.get("resets", 0)) - int(snap.get("resets", 0)))

        if delta_img > 0 or delta_ref > 0 or delta_rst > 0:
            if in_memory_users is not None:
                users_list = in_memory_users
            else:
                from config_utils import load_login_lookup
                users_list = load_login_lookup()

            for u in users_list:
                if normalize(u.get("username")) == normalize(current_user):
                    u["session_images"] = str(int(u.get("session_images") or 0) + delta_img)
                    u["session_refused"] = str(int(u.get("session_refused") or 0) + delta_ref)
                    u["session_resets"] = str(int(u.get("session_resets") or 0) + delta_rst)
                    break
            
            if in_memory_users is None:
                from config_utils import save_login_lookup
                save_login_lookup(users_list)

        # Always keep snapshot perfectly synced with current global stats
        engine._acct_snapshot = {
            "successes": cur.get("successes", 0),
            "refusals": cur.get("refusals", 0),
            "resets": cur.get("resets", 0)
        }
    except Exception as e:
        engine._log_debug(f"API>> Error committing session stats to table: {e}")

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

    # Pre-read quota cooldown setting once to avoid repeated disk reads inside the loop
    _quota_cooldown_hrs = 0
    try:
        _quota_cooldown_hrs = load_config().get("quota_cooldown_hours", 0) or 0
    except Exception:
        pass

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

        # Skip accounts whose quota unlock time has not yet been reached
        # unlock_time = quota_full_time + cooldown_hours; skip if now < unlock_time
        if _quota_cooldown_hrs > 0:
            qf_str = candidate.get("quota_full", "")
            if qf_str:
                try:
                    from datetime import timedelta
                    qf_time = datetime.strptime(qf_str, "%d/%m/%Y %H:%M:%S")
                    unlock_time = qf_time + timedelta(hours=_quota_cooldown_hrs)
                    if datetime.now() < unlock_time:
                        remaining_min = (unlock_time - datetime.now()).total_seconds() / 60.0
                        engine._log_debug(
                            f"API>> Skipping '{candidate.get('username')}' "
                            f"(Quota locked until {unlock_time.strftime('%d/%m %H:%M')}, "
                            f"{remaining_min:.0f} min remaining)."
                        )
                        continue
                except Exception:
                    pass  # Unparseable timestamp — do not skip

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

    # 5a. Record per-account session stats for the outgoing account (accumulate via delta)
    _commit_session_stats_to_table(users)
    if is_real_switch and 0 <= outgoing_index < len(users):
        users[outgoing_index]["last_switched_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        print(f"[ENGINE] Session stats for '{users[outgoing_index]['username']}': "
              f"images={users[outgoing_index].get('session_images', 0)}, "
              f"refused={users[outgoing_index].get('session_refused', 0)}, "
              f"resets={users[outgoing_index].get('session_resets', 0)}")

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
        is_target = (u["username"] == target_user["username"])
        u["active"] = is_target
        # Clear quota_full timestamp if this is the target account and it was previously marked.
        # If we reached this point, it means the account is usable (expired or cooldown is 0).
        if is_target and u.get("quota_full"):
            print(f"[ENGINE] Account {u['username']} is now active and usable. Clearing quota_full timestamp and session stats.")
            u["quota_full"] = ""
            u["last_switched_at"] = ""
            u["session_images"] = "0"
            u["session_refused"] = "0"
            u["session_resets"] = "0"
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
        # Reset pending counters to prevent leakage from the outgoing account to the incoming one
        engine._pending_refused = 0
        engine._pending_resets = 0
        if "pending_refused" in engine.automation_status:
            engine.automation_status["pending_refused"] = 0
        if "pending_resets" in engine.automation_status:
            engine.automation_status["pending_resets"] = 0

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
    engine._log_debug(f"[AUTO] Manager started with mode={req.mode}, goal={req.goal}, clear_pending={req.clear_pending}")
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
            # --- [FIX] Reload config from disk at every iteration to sync with UI changes ---
            cfg = load_config()
            pm_config = cfg.get("prompt_matrix", {})
            pm_enabled = pm_config.get("enabled", False)
            ratio_prefix = None

            # 2. Pre-load Watermark Removal Model if enabled
            use_gpu_cfg = cfg.get("automation", {}).get("use_gpu", True)
            _wm_enabled = cfg.get("automation", {}).get("remove_watermark", False)
            
            if _wm_enabled:
                try:
                    from processing_utils import get_shared_processor
                    get_shared_processor(use_gpu=use_gpu_cfg)
                except Exception as p_err:
                    print(f"[AUTO] Model pre-load failed: {p_err}")

            # 2.5 Handle Aspect Ratio (Dynamic Loop or Fixed)
            if pm_enabled:
                pm_items = pm_config.get("items", [])
                all_done = all(it.get("current", 0) >= it.get("target", 1) for it in pm_items)
                
                if all_done and pm_items:
                    # Reset all progress for infinite loop
                    for it in pm_items:
                        it["current"] = 0
                    engine._log_debug("[AUTO] Prompt Matrix exhausted. Resetting for infinite loop.")
                    pm_config["items"] = pm_items
                    save_config({"prompt_matrix": pm_config})
                
                # Find active row
                active_idx = -1
                for i, it in enumerate(pm_items):
                    if it.get("current", 0) < it.get("target", 1):
                        active_idx = i
                        break
                
                if active_idx != -1:
                    active_item = pm_items[active_idx]
                    ratio_prefix = active_item.get("ratio", "")
                    
                    # Force a new chat if we just switched to a new matrix index
                    last_idx = getattr(engine, "_last_matrix_idx", -1)
                    if last_idx != active_idx:
                        engine._automation_needs_new_chat = True
                        engine._last_matrix_idx = active_idx
                        engine._log_debug(f"[AUTO] Dynamic Prefix switching to: {ratio_prefix}")
            else:
                # Fixed mode
                fixed_ratio = cfg.get("fixed_aspect_ratio", "None")
                if fixed_ratio and fixed_ratio != "None":
                    ratio_prefix = fixed_ratio

            # Detect ratio change and force a new chat
            last_ratio = getattr(engine, "_last_effective_ratio", None)
            if ratio_prefix != last_ratio:
                engine._automation_needs_new_chat = True
                engine._last_effective_ratio = ratio_prefix
                engine._log_debug(f"[AUTO] Effective ratio changed: '{last_ratio}' -> '{ratio_prefix}'. Forcing New Chat.")

            # Prepare final prompt for this iteration (Clean old prefixes first)
            original_prompt = cfg.get("prompt", "")
            # Remove any existing "Aspect Ratio: ..." line to prevent accumulation
            import re
            clean_prompt = re.sub(r"^Aspect Ratio:.*?\n\n", "", original_prompt, flags=re.DOTALL)
            
            if ratio_prefix and ratio_prefix not in ["None", "None (Master Prompt)"]:
                final_prompt = f"Aspect Ratio: {ratio_prefix}\n\n{clean_prompt}"
            else:
                final_prompt = clean_prompt
            
            # Sync back to the request object that engine.run_automation_loop uses
            req.config = cfg # Update req.config with fresh disk data
            req.config["prompt"] = final_prompt

            # 3. Execute ONE iteration
            result = await engine.run_automation_loop(req.dict())
            
            # 4. Post-action: Remove Watermark if enabled (MIMIC Gemini Actions flow: Download -> Process)
            if result.get("status") == "success" and _wm_enabled:
                paths = result.get("saved_paths", [])
                engine._log_debug(f"[AUTO] WM Post-action: status=success, paths={paths}")
                if paths:
                    try:
                        from processing_utils import get_shared_processor, save_with_metadata
                        from PIL import Image
                        processor = get_shared_processor(use_gpu=use_gpu_cfg)
                        p_dir = os.path.join(cfg.get("save_dir"), "processed")
                        os.makedirs(p_dir, exist_ok=True)
                        
                        engine._log_debug(f"[AUTO] Refining {len(paths)} new images...")
                        await asyncio.sleep(0)  # Yield event loop so dashboard reads inter_cycle_since before blocking
                        for p in paths:
                            if os.path.exists(p):
                                with Image.open(p) as img:
                                    final_img = processor.hybrid_process(img)
                                    p_path = os.path.join(p_dir, os.path.basename(p))
                                    save_with_metadata(final_img, img, p_path)
                        engine._log_debug("[AUTO] Refinement complete.")
                    except Exception as p_err:
                        import traceback
                        engine._log_debug(f"[AUTO] Refinement FAILED: {p_err}\n{traceback.format_exc()}")

            # 4.5 Increment Prompt Matrix on Success
            # Important: reload fresh config again before incrementing to avoid overwriting mid-loop UI saves
            fresh_cfg = load_config()
            pm_enabled = fresh_cfg.get("prompt_matrix", {}).get("enabled", False)
            
            if pm_enabled and result.get("status") == "success":
                saved_count = len(result.get("saved_paths", []))
                if saved_count > 0:
                    pm_data = fresh_cfg.get("prompt_matrix", {})
                    pm_items = pm_data.get("items", [])
                    # We use the index we targeted at the start of THIS iteration
                    active_idx = getattr(engine, "_last_matrix_idx", -1)
                    if 0 <= active_idx < len(pm_items):
                        pm_items[active_idx]["current"] += 1
                        engine._log_debug(f"[AUTO] Prompt Matrix: {pm_items[active_idx]['ratio']} progress -> {pm_items[active_idx]['current']}/{pm_items[active_idx]['target']}")
                        pm_data["items"] = pm_items
                        save_config({"prompt_matrix": pm_data})

            # --- [NEW] Real-time persistence of session stats ---
            _commit_session_stats_to_table()

            # 4b. Loop-Control Threshold Check (applies to success, refused, reset, error, timeout)
            if result.get("status") in ["success", "refused", "reset", "error", "timeout"]:
                loop_ctrl = req.config.get("automation", {}).get("loop_control", {})
                lc_trigger, lc_action = False, "next_profile"
                
                if loop_ctrl:
                    # Modified to align Time Threshold strictly with the Reject Rate Stats global duration.
                    # This ensures time keeps accumulating even if re-login actions reset the lc counters.
                    v_dur = result.get("cycle_duration_sec", (time.time() - getattr(engine, '_cycle_start_time', time.time())) if getattr(engine, '_cycle_start_time', None) else 0)
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
                        
                        # Maintain pending stats across account switches (next_profile or re_login)
                        # Only clear the Loop Control specific counters.
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
                            
                            # Maintain pending stats across watchdog recovery
                            pass
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
                    
                    # Maintain pending stats across quota-triggered account switches
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
        if getattr(engine, '_cycle_start_time', None) is not None:
            final_dur = time.time() - engine._cycle_start_time
            lc_dur = time.time() - getattr(engine, '_lc_cycle_start_time', engine._cycle_start_time)
            
            pending_data = {
                "start_time": engine.automation_status.get("start_time"),
                "pending_duration": final_dur,
                "pending_refused": getattr(engine, '_pending_refused', 0),
                "pending_resets": getattr(engine, '_pending_resets', 0),
                "lc_pending_duration": lc_dur,
                "lc_pending_refused": getattr(engine, '_lc_pending_refused', 0),
                "lc_pending_resets": getattr(engine, '_lc_pending_resets', 0)
            }
            try:
                pending_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "pending_stats.json"))
                with open(pending_file, "w", encoding="utf-8") as f:
                    json.dump(pending_data, f)
                
                # Commit latest deltas to the credentials table before exiting
                _commit_session_stats_to_table()
            except Exception as e:
                engine._log_debug(f"API>> Failed to save pending stats or commit: {e}")
            
            if final_dur > 1 or engine._pending_refused > 0 or engine._pending_resets > 0:
                engine._log_debug(f"API>> Automation manager ending. Saved trailing stats: dur={final_dur:.1f}s, refused={engine._pending_refused}, resets={engine._pending_resets}")

        
        engine.automation_status["is_running"] = False
        stats = engine.automation_status
        engine._log_debug(f"API>> Automation Manager Exited. Final Stats: {stats}")
        print("[AUTO] Automation manager exited.")

def _hydrate_automation_state_from_log():
    try:
        records = []
        if os.path.exists(engine._reject_log_path):
            with open(engine._reject_log_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        
        valid_records = [r for r in records if r.get("filename") and r.get("filename") != "[Stopped/Interrupted]"]
        
        successes = len(valid_records)
        refusals = sum(int(r.get("refused_count", 0)) for r in valid_records)
        resets = sum(int(r.get("reset_count", 0)) for r in valid_records)
        
        return {
            "successes": successes,
            "refusals": refusals,
            "resets": resets,
            "cycles": successes + refusals + resets
        }
    except Exception as e:
        print(f"[AUTO] Failed to hydrate state from log: {e}")
        return None

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
            
        pending_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "pending_stats.json"))
        if os.path.exists(pending_file):
            os.remove(pending_file)
    except Exception as e:
        print(f"[AUTO] Warning: could not reset stats: {e}")
    engine._pending_refused = 0
    engine._pending_resets = 0
    engine._lc_pending_refused = 0
    engine._lc_pending_resets = 0
    # Initialize cycle timer to capture initial setup time in the first image's duration
    engine._cycle_start_time = time.time()
    engine._lc_cycle_start_time = time.time()
    engine.automation_status["current_cycle_start_ts"] = engine._cycle_start_time
    
    # Reset snapshot for the new session
    engine._acct_snapshot = {"successes": 0, "refusals": 0, "resets": 0}

    # Mark as running IMMEDIATELY (synchronous) to prevent race conditions.
    # Without this, two near-simultaneous requests can both pass the "is_running" guard
    # above because the async task hasn't set the flag yet — causing duplicate managers.
    engine.automation_status["is_running"] = True

    asyncio.create_task(automation_manager(req))
    return {"status": "success", "message": "Automation started in background"}

@app.post("/browser/automation/continue")
async def continue_automation(req: AutomationRequest):
    if not engine.is_running:
        raise HTTPException(status_code=400, detail="Engine not running")
    if engine.automation_status.get("is_running"):
        return {"status": "error", "message": "Automation already running"}
    
    engine._log_debug(f"API>> continue_automation called: mode={req.mode}, goal={req.goal}, clear_pending={req.clear_pending}")
    engine._stop_automation_event.clear()
    
    cfg = load_config()
    initial_user = cfg.get("active_user")

    # If state is completely 0 (e.g. after engine restart), hydrate it
    if engine.automation_status.get("successes", 0) == 0 and engine.automation_status.get("refusals", 0) == 0:
        hydrated = _hydrate_automation_state_from_log()
        if hydrated and (hydrated["successes"] > 0 or hydrated["refusals"] > 0):
            engine.automation_status.update({
                "successes": hydrated["successes"],
                "refusals": hydrated["refusals"],
                "resets": hydrated["resets"],
                "cycles": hydrated["cycles"],
            })
            engine._log_debug(f"API>> Hydrated session state from log: {hydrated}")

    # Update mode and goal from current request, preserve existing stats
    engine.automation_status.update({
        "mode": req.mode,
        "goal": req.goal,
        "initial_user": initial_user
    })
    
    if "start_time" not in engine.automation_status or not engine.automation_status["start_time"]:
        engine.automation_status["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not hasattr(engine, "_acct_snapshot") or engine._acct_snapshot is None:
        engine._acct_snapshot = {
            "successes": engine.automation_status.get("successes", 0),
            "refusals": engine.automation_status.get("refusals", 0),
            "resets": engine.automation_status.get("resets", 0)
        }

    if req.clear_pending:
        # Clear the physical file if it exists
        pending_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "pending_stats.json"))
        if os.path.exists(pending_file):
            try:
                os.remove(pending_file)
            except: pass
        # Clear memory variables
        engine._pending_refused = 0
        engine._pending_resets = 0
        engine._lc_pending_refused = 0
        engine._lc_pending_resets = 0
        engine.automation_status["pending_refused"] = 0
        engine.automation_status["pending_resets"] = 0
        
        # Reset cycle timers since we don't want to attribute past duration
        engine._cycle_start_time = time.time()
        engine._lc_cycle_start_time = time.time()
        
        # Hydrate snapshot logic as there's no pending state anymore
        engine._acct_snapshot = {
            "successes": engine.automation_status.get("successes", 0),
            "refusals": engine.automation_status.get("refusals", 0),
            "resets": engine.automation_status.get("resets", 0)
        }
    else:
        # Load saved pending stats if they exist, so we can survive full engine restarts
        pending_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "pending_stats.json"))
        if os.path.exists(pending_file):
            try:
                with open(pending_file, "r", encoding="utf-8") as f:
                    pending_stats = json.load(f)
                
                engine._pending_refused = pending_stats.get("pending_refused", 0)
                engine._pending_resets = pending_stats.get("pending_resets", 0)
                engine._lc_pending_refused = pending_stats.get("lc_pending_refused", 0)
                engine._lc_pending_resets = pending_stats.get("lc_pending_resets", 0)
                
                # Restore transient status for UI display
                engine.automation_status["pending_refused"] = engine._pending_refused
                engine.automation_status["pending_resets"] = engine._pending_resets
                
                # Restore cumulative status values from pending counts ONLY if we just hydrated.
                # If the service was already running, these counts were already incremented in real-time.
                if "hydrated" in locals() and hydrated:
                    engine.automation_status["refusals"] += engine._pending_refused
                    engine.automation_status["resets"] += engine._pending_resets
                    engine.automation_status["cycles"] += (engine._pending_refused + engine._pending_resets)
                
                # Restore start_time if available
                if pending_stats.get("start_time"):
                    engine.automation_status["start_time"] = pending_stats.get("start_time")
    
                engine._cycle_start_time = time.time() - pending_stats.get("pending_duration", 0)
                engine._lc_cycle_start_time = time.time() - pending_stats.get("lc_pending_duration", 0)
                
                # Remove it so we don't accidentally load it again later if we don't want to
                os.remove(pending_file)
                engine._log_debug(f"API>> Loaded and restored pending stats: dur={pending_stats.get('pending_duration'):.1f}s, refused={engine._pending_refused}, resets={engine._pending_resets}")
            except Exception as e:
                engine._log_debug(f"API>> Failed to load pending stats: {e}")
                if not getattr(engine, '_cycle_start_time', None): engine._cycle_start_time = time.time()
                if not getattr(engine, '_lc_cycle_start_time', None): engine._lc_cycle_start_time = time.time()
        else:
            # Do not clear pending counters (_pending_refused, _pending_resets) here.
            # We want to resume the process and correctly attribute past refuses/resets to the next successful image.
            if not getattr(engine, '_cycle_start_time', None):
                engine._cycle_start_time = time.time()
            if not getattr(engine, '_lc_cycle_start_time', None):
                engine._lc_cycle_start_time = time.time()
        
    # Restore internal pending counters to automation_status for UI visibility
    engine.automation_status["pending_refused"] = getattr(engine, "_pending_refused", 0)
    engine.automation_status["pending_resets"] = getattr(engine, "_pending_resets", 0)
    
    engine.automation_status["current_cycle_start_ts"] = engine._cycle_start_time
    if hasattr(engine, '_lc_cycle_start_time'):
        engine.automation_status["lc_cycle_start_ts"] = engine._lc_cycle_start_time
    
    # Synchronize the snapshot ONLY IF we didn't just load from a pending file AND we're not clearing.
    # If we DID load from a file or we're clearing, the snapshot should remain as-is or be handled by the clear logic.
    pending_exists = os.path.exists(os.path.abspath(os.path.join(os.path.dirname(__file__), "pending_stats.json")))
    if not req.clear_pending and not pending_exists:
        engine._acct_snapshot = {
            "successes": engine.automation_status.get("successes", 0),
            "refusals": engine.automation_status.get("refusals", 0),
            "resets": engine.automation_status.get("resets", 0)
        }
    
    engine._log_debug("API>> Starting automation manager task...")
    engine.automation_status["is_running"] = True
    asyncio.create_task(automation_manager(req))
    return {"status": "success", "message": "Automation continued in background"}

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
