import streamlit as st
import json
import os
import pandas as pd
import altair as alt
from datetime import datetime
from style_utils import apply_premium_style, render_dashboard_header
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk, load_login_lookup, save_login_lookup

# --- Page Config ---
st.set_page_config(page_title="GemiPersona | SYSTEM CONFIG", page_icon="sys_img/logo.png", layout="wide")
apply_premium_style()

# --- Data Loading Functions ---
def load_config():
    return load_cfg_disk()

def save_config(updates):
    return save_cfg_disk(updates)

# --- Engine Config Callbacks ---
def on_change_console():
    save_config({"show_engine_console": st.session_state.cfg_show_console})

def on_change_headless():
    save_config({"headless": st.session_state.cfg_headless})

def on_change_timeout():
    save_config({"heartbeat_timeout": st.session_state.cfg_timeout})

def on_change_watchdog_delay():
    save_config({"watchdog_initial_delay": st.session_state.cfg_watchdog_delay})

def on_change_quota_cooldown():
    save_config({"quota_cooldown_hours": st.session_state.cfg_quota_cooldown_hrs})

def on_change_health_graph():
    save_config({"health_graph_type": st.session_state.widget_health_graph_type})

def on_change_health_view():
    save_config({"health_view_mode": st.session_state.widget_health_view_mode})

def on_change_health_y_scale():
    save_config({"health_y_scale": st.session_state.widget_health_y_scale})

def on_change_navigation():
    save_config({"system_navigation": st.session_state.cfg_system_nav})
    # Clear aspect ratio initialization flag to force fresh reload when switching sections
    for k in ["pm_sys_initialized", "pm_df_work_sys", "pm_rerender_idx_sys"]:
        if k in st.session_state: del st.session_state[k]
    # Also clear any editor buffers
    for k in list(st.session_state.keys()):
        if k.startswith("pm_editor_sys_"): del st.session_state[k]

def on_change_url():
    save_config({"browser_url": st.session_state.cfg_browser_url})

def on_change_redirect():
    save_config({"startup_redirect": st.session_state.cfg_startup_redirect})

def on_change_watermark():
    # Nested update
    cfg = load_config()
    if "automation" not in cfg: cfg["automation"] = {}
    cfg["automation"]["remove_watermark"] = st.session_state.cfg_watermark
    save_config({"automation": cfg["automation"]})

def on_change_gpu():
    cfg = load_config()
    if "automation" not in cfg: cfg["automation"] = {}
    cfg["automation"]["use_gpu"] = st.session_state.cfg_gpu
    save_config({"automation": cfg["automation"]})

def on_change_cooldown_min():
    save_config({"quota_cooldown_minutes": st.session_state.cfg_quota_cooldown_min})

def on_change_save_dir():
    save_config({"save_dir": st.session_state.cfg_save_dir})

def on_change_prefix():
    save_config({"name_prefix": st.session_state.cfg_name_prefix})

def on_change_padding():
    save_config({"name_padding": st.session_state.cfg_name_padding})

def on_change_start_num():
    save_config({"name_start": st.session_state.cfg_name_start})

def on_change_prompt():
    save_config({"prompt": st.session_state.cfg_prompt})

def on_change_tool():
    save_config({"selected_tool": st.session_state.cfg_selected_tool})

def on_change_model():
    save_config({"selected_model": st.session_state.cfg_selected_model})

def on_change_auto_mode():
    cfg = load_config()
    if "automation" not in cfg: cfg["automation"] = {}
    cfg["automation"]["mode"] = st.session_state.cfg_auto_mode
    save_config({"automation": cfg["automation"]})

def on_change_auto_goal():
    cfg = load_config()
    if "automation" not in cfg: cfg["automation"] = {}
    cfg["automation"]["goal"] = st.session_state.cfg_auto_goal
    save_config({"automation": cfg["automation"]})

def on_change_auto_looping():
    cfg = load_config()
    if "automation" not in cfg: cfg["automation"] = {}
    cfg["automation"]["auto_looping"] = st.session_state.cfg_auto_looping
    save_config({"automation": cfg["automation"]})

def on_change_prompt_matrix_toggle():
    cfg = load_config()
    if "prompt_matrix" not in cfg: cfg["prompt_matrix"] = {}
    cfg["prompt_matrix"]["enabled"] = st.session_state.cfg_matrix_enabled
    save_config({"prompt_matrix": cfg["prompt_matrix"]})

def on_change_loop_control(key):
    def callback():
        cfg = load_config()
        if "automation" not in cfg: cfg["automation"] = {}
        if "loop_control" not in cfg["automation"]: cfg["automation"]["loop_control"] = {}
        cfg["automation"]["loop_control"][key] = st.session_state[f"cfg_loop_{key}"]
        save_config({"automation": cfg["automation"]})
    return callback

# --- Health Analysis Logic ---
def parse_engine_cycles():
    LOG_PATH = "engine.log"
    if not os.path.exists(LOG_PATH):
        return []
    
    cycles = []
    current_cycle = None
    
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if "--- [AUTO] RUNNING ROUND: 1 ---" in line:
                if current_cycle is not None:
                    current_cycle['end_idx'] = i - 1
                    cycles.append(current_cycle)
                
                import re
                match = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", line)
                ts = match.group(1) if match else "Unknown"
                
                current_cycle = {
                    'start_idx': i,
                    'start_time_str': ts,
                    'end_idx': None,
                    'lines_count': 0
                }
            
            if current_cycle is not None:
                current_cycle['lines_count'] += 1
                
                if "Final Stats:" in line and "'start_time': '" in line:
                    import re
                    match = re.search(r"'start_time': '([^']+)'", line)
                    if match:
                        current_cycle['full_start_time'] = match.group(1)
        
        if current_cycle is not None:
            current_cycle['end_idx'] = i
            cycles.append(current_cycle)
            
    return cycles

def parse_account_health(target_account=None, login_data=None):
    LOG_PATH = "engine.log"
    if not os.path.exists(LOG_PATH):
        return [], [], []
    
    summary_results = {} # normalized_acc -> record
    detailed_results = []
    found_accounts_ordered = []
    found_accounts_set = set()
    
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        current_account = "Unknown"
        import re
        
        # New State-based Parsing Approach
        current_session_id = 1
        active_event = None # {start_time, account, start_line_idx}
        last_boundary_idx = -1
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Extract potential account update first to check if it's a real switch
            potential_new_acc = None
            if "profile switched to" in line_lower:
                try: potential_new_acc = line.split("switched to")[1].split()[0].strip().rstrip('.:').split('@')[0].lower()
                except: pass
            elif "re-login detected for" in line_lower:
                try: potential_new_acc = line.split("detected for")[1].split()[0].strip().rstrip('.:').split('@')[0].lower()
                except: pass
            
            # 1. Detect Session Boundaries (Force reset and increment session)
            is_boundary = False
            if "automation finished" in line_lower or "automation manager started" in line_lower:
                is_boundary = True
            elif potential_new_acc and potential_new_acc != current_account:
                # Only treat as a boundary if the account actually changes
                is_boundary = True
            
            if is_boundary:
                # Only bump session if not immediately following another boundary
                if last_boundary_idx != i - 1:
                    current_session_id += 1
                last_boundary_idx = i
                active_event = None

            # Always update account info if found
            if potential_new_acc:
                current_account = potential_new_acc
                found_accounts_set.add(potential_new_acc)


            # 2. Track simple account updates (might happen inside session)
            if "current_account_id" in line:
                match = re.search(r"['\"]current_account_id['\"]\s*:\s*['\"]([^'\"]+)['\"]", line)
                if match: 
                    current_account = match.group(1).split('@')[0].lower()
                    found_accounts_set.add(current_account)

            # 3. Detect Start of Image Generation
            if "正在加载 Nano Banana 2..." in line or "API>> Gemini:" in line and "加载" in line:
                # If we already have an active event that wasn't closed, it was likely a refusal cycle
                # We keep the original start time to calculate total duration for the final image
                if active_event is None:
                    active_event = {
                        "start_time": line[1:9],
                        "account": current_account,
                        "session_index": current_session_id,
                        "line_idx": i,
                        "closed": False
                    }
            
            # 4. Detect Result (Success / Reject / Reset)
            status = None
            if "response successful" in line_lower: status = "Success"
            elif "saved: " in line_lower and ".png" in line_lower: status = "Success" # Trigger Success directly from Saved line
            elif "response failed (refused)" in line_lower: status = "Reject"
            elif "gemini page was unexpectedly reset" in line_lower: status = "Reset"
            elif "automation loop encountered an issue" in line_lower: status = "Reset"
            
            if status:
                # Deduplicate: If we just saw a Success for this line, don't double count if it's the Saved line
                # (Simple check: if last detailed record has same filename or time, skip)
                
                temp_start_time = active_event["start_time"] if active_event else line[1:9]
                temp_session_idx = active_event["session_index"] if active_event else current_session_id
                temp_account = active_event["account"] if active_event else current_account

                if status == "Success":
                    # Look AROUND (back and forth) for filename and RejectStat
                    fname = ""
                    if "saved: " in line_lower:
                        try: fname = line.split("Saved: ")[1].strip()
                        except: pass
                    
                    true_dur = None
                    true_rej = 0
                    true_res = 0
                    
                    # Search window for metadata (filenames, stats)
                    search_range = range(max(0, i - 10), min(i + 50, len(lines)))
                    for k in search_range:
                        if not fname and "saved: " in lines[k].lower():
                            fname = lines[k].split("Saved: ")[1].strip()
                        if "rejectstat: wrote record for" in lines[k].lower() and fname and fname in lines[k]:
                            stat_match = re.search(r"dur=([\d.]+)s, ref=(\d+), rst=(\d+)", lines[k])
                            if stat_match:
                                true_dur = float(stat_match.group(1))
                                true_rej = int(stat_match.group(2))
                                true_res = int(stat_match.group(3))
                                break
                    
                    # Avoid double-counting if we already have this filename in this session
                    is_dup = False
                    if fname:
                        for prev in detailed_results[-5:]:
                            if prev.get("filename") == fname and prev.get("session_index") == temp_session_idx:
                                is_dup = True; break
                    
                    if not is_dup and (true_dur is not None or active_event or fname):
                        if true_dur is None and active_event:
                            try:
                                fmt = '%H:%M:%S'
                                tdelta = datetime.strptime(line[1:9], fmt) - datetime.strptime(active_event["start_time"], fmt)
                                true_dur = int(tdelta.total_seconds())
                                if true_dur < 0: true_dur += 86400
                            except: true_dur = 0
                        
                        if true_dur is None: true_dur = 0

                        record = {
                            "account": temp_account,
                            "time": temp_start_time,
                            "health": f"{true_dur}s",
                            "filename": fname,
                            "status": "Success" if fname else "Fail",
                            "session_index": temp_session_idx,
                            "true_rej": true_rej,
                            "true_res": true_res
                        }
                        detailed_results.append(record)
                        summary_results[record["account"]] = record
                    
                    # Only clear active event if we successfully processed a success
                    if not is_dup: active_event = None
                else:
                    # For Reject/Reset
                    try:
                        fmt = '%H:%M:%S'
                        tdelta = datetime.strptime(line[1:9], fmt) - datetime.strptime(temp_start_time, fmt)
                        fail_dur = int(tdelta.total_seconds())
                        if fail_dur < 0: fail_dur += 86400
                    except: fail_dur = 0
                    
                    record = {
                        "account": temp_account,
                        "time": temp_start_time,
                        "health": f"{fail_dur}s",
                        "filename": "",
                        "status": status,
                        "session_index": temp_session_idx
                    }
                    detailed_results.append(record)
                    if record["account"] not in summary_results or summary_results[record["account"]]["status"] != "Success":
                        summary_results[record["account"]] = record
                    
                    if active_event: active_event["start_time"] = line[1:9]



        # Smarter Backfill for "Unknown"
        # 1. Try first account encountered in log
        first_real = None
        for r in detailed_results:
            if r["account"] and r["account"] != "Unknown":
                first_real = r["account"]
                break
        
        # 2. Fallback: If no switches in logs, find the account marked as 'active' or with latest 'last_switched_at'
        if not first_real and login_data:
            try:
                # Priority 1: The account explicitly marked as "active" in the lookup table
                active_acc = next((u.get("username", "").lower().strip() for u in login_data if u.get("active")), None)
                if active_acc:
                    first_real = active_acc
                else:
                    # Priority 2: Account with most recent last_switched_at
                    latest_acc = None
                    latest_ts = None
                    for u in login_data:
                        ts_str = u.get("last_switched_at")
                        if ts_str:
                            try:
                                ts = datetime.strptime(ts_str, "%d/%m/%Y %H:%M:%S")
                                if latest_ts is None or ts > latest_ts:
                                    latest_ts = ts
                                    latest_acc = u.get("username", "").lower().strip()
                            except: continue
                    first_real = latest_acc
            except: pass
        
        if first_real:
            for r in detailed_results:
                if r["account"] == "Unknown" or not r["account"]: 
                    r["account"] = first_real
            
            if "Unknown" in summary_results:
                # If the first real account doesn't have a record yet, move it
                if first_real not in summary_results:
                    summary_results[first_real] = summary_results["Unknown"]
                    summary_results[first_real]["account"] = first_real
                del summary_results["Unknown"]
        
        # Final catch-all: if Unknown still exists for some reason, and we have a first_real, clean it up
        if first_real:
            summary_results = { (first_real if k == "Unknown" else k): v for k, v in summary_results.items() }
            for v in summary_results.values():
                if v["account"] == "Unknown": v["account"] = first_real

        if target_account == "ALL_EVENTS":
            # Keep all results
            pass
        elif target_account:
            detailed_results = [r for r in detailed_results if r["account"].lower() == target_account.lower()]
        else:
            detailed_results = []
    except Exception as e:
        import traceback
        st.error(f"Error parsing log: {e}")
        print(traceback.format_exc())
    
    summary_list = list(reversed(list(summary_results.values())))
    detailed_list = list(reversed(detailed_results))
    
    return summary_list, detailed_list, sorted(list(found_accounts_set))



# --- Main Logic ---
config = load_config()
login_data = load_login_lookup()

st.session_state.cfg_show_console = config.get("show_engine_console", True)
st.session_state.cfg_headless = config.get("headless", False)
st.session_state.cfg_timeout = int(config.get("heartbeat_timeout", 3600))
st.session_state.cfg_watchdog_delay = int(config.get("watchdog_initial_delay", 20))
st.session_state.cfg_quota_cooldown_hrs = int(config.get("quota_cooldown_hours", 24))
st.session_state.cfg_quota_cooldown_min = config.get("quota_cooldown_minutes", 0)

if "cfg_system_nav" not in st.session_state:
    st.session_state.cfg_system_nav = config.get("system_navigation", "Engine Settings")

st.session_state.cfg_browser_url = config.get("browser_url", "https://gemini.google.com/app")
st.session_state.cfg_startup_redirect = config.get("startup_redirect", "dashboard")
st.session_state.cfg_watermark = config.get("automation", {}).get("remove_watermark", True)
st.session_state.cfg_gpu = config.get("automation", {}).get("use_gpu", True)
st.session_state.cfg_save_dir = config.get("save_dir", "")
st.session_state.cfg_name_prefix = config.get("name_prefix", "")
st.session_state.cfg_name_padding = int(config.get("name_padding", 2))
st.session_state.cfg_name_start = int(config.get("name_start", 1))

st.session_state.cfg_prompt = config.get("prompt", "")
st.session_state.cfg_selected_tool = config.get("selected_tool", "")
st.session_state.cfg_selected_model = config.get("selected_model", "")

auto_c = config.get("automation", {})
st.session_state.cfg_auto_mode = auto_c.get("mode", "rounds")
st.session_state.cfg_auto_goal = int(auto_c.get("goal", 1))
st.session_state.cfg_auto_looping = auto_c.get("auto_looping", False)

pm = config.get("prompt_matrix", {})
st.session_state.cfg_matrix_enabled = pm.get("enabled", False)

lc = auto_c.get("loop_control", {})
st.session_state.cfg_loop_infinite_loop_enabled = lc.get("infinite_loop_enabled", True)
st.session_state.cfg_loop_infinite_loop_minutes = int(lc.get("infinite_loop_minutes", 1))
st.session_state.cfg_loop_time_enabled = lc.get("time_enabled", False)
st.session_state.cfg_loop_time_minutes = int(lc.get("time_minutes", 20))
st.session_state.cfg_loop_time_action = lc.get("time_action", "next_profile")
st.session_state.cfg_loop_refused_enabled = lc.get("refused_enabled", True)
st.session_state.cfg_loop_refused_threshold = int(lc.get("refused_threshold", 20))
st.session_state.cfg_loop_refused_action = lc.get("refused_action", "next_profile")
st.session_state.cfg_loop_reset_enabled = lc.get("reset_enabled", True)
st.session_state.cfg_loop_reset_threshold = int(lc.get("reset_threshold", 5))
st.session_state.cfg_loop_reset_action = lc.get("reset_action", "re_login")

st.session_state.login_rows = list(login_data)
st.session_state._login_reload = False

# --- Sidebar Navigation ---
with st.sidebar:
    st.markdown("<p style='font-weight: bold; color: #a0a0ff; margin-bottom: 10px;'>SYSTEM NAVIGATION</p>", unsafe_allow_html=True)
    
    # Ensure value exists in options
    nav_options = ["Engine Settings", "Automation Settings", "Quota Full Phrases", "Account Credentials", "Account Health Analysis", "Automation Cycle Management"]
    if st.session_state.cfg_system_nav not in nav_options:
        st.session_state.cfg_system_nav = nav_options[0]

    menu_selection = st.radio(
        "Select Section", 
        options=nav_options, 
        key="cfg_system_nav",
        on_change=on_change_navigation,
        label_visibility="collapsed"
    )

WATCHDOG_LOG_PATH = "watchdog.log"

def get_watchdog_log():
    if not os.path.exists(WATCHDOG_LOG_PATH): return None
    try:
        with open(WATCHDOG_LOG_PATH, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: return f"Error reading log: {e}"

def clear_watchdog_log():
    try:
        with open(WATCHDOG_LOG_PATH, "w", encoding="utf-8") as f: f.write("")
    except Exception as e: st.error(f"Failed to clear log: {e}")

if menu_selection == "Engine Settings":
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>CORE BROWSER SETTINGS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.text_input("Base URL", key="cfg_browser_url", on_change=on_change_url)
            c1, c2 = st.columns(2)
            with c1: st.toggle("Show Console", key="cfg_show_console", on_change=on_change_console)
            with c2: st.toggle("Headless Mode", key="cfg_headless", on_change=on_change_headless)
            st.selectbox("Startup Redirect", options=["dashboard", "gemini_setup", "asset_sanitizer"], key="cfg_startup_redirect", on_change=on_change_redirect)

        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-transform: uppercase;'>TIMING & WATCHDOG</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.number_input("Heartbeat Timeout (s)", min_value=0, max_value=86400, key="cfg_timeout", on_change=on_change_timeout, step=1)
            st.number_input("Watchdog Initial Delay (s)", min_value=5, max_value=120, step=5, key="cfg_watchdog_delay", on_change=on_change_watchdog_delay)
            c1, c2 = st.columns(2)
            with c1: st.number_input("Quota Cooldown (h)", min_value=0, max_value=168, step=1, key="cfg_quota_cooldown_hrs", on_change=on_change_quota_cooldown)
            with c2: st.number_input("Quota Cooldown (m)", min_value=0, max_value=59, step=1, key="cfg_quota_cooldown_min", on_change=on_change_cooldown_min)

        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-transform: uppercase;'>AUTOMATION OPTIONS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.toggle("Remove AI Watermark", key="cfg_watermark", on_change=on_change_watermark)
            st.toggle("Use GPU Acceleration", key="cfg_gpu", on_change=on_change_gpu)

    with col_right:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>FILE OUTPUT SETTINGS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.text_input("Save Directory", key="cfg_save_dir", on_change=on_change_save_dir)
            st.text_input("Filename Prefix", key="cfg_name_prefix", on_change=on_change_prefix)
            c1, c2 = st.columns(2)
            with c1: st.number_input("Prefix Padding", min_value=0, max_value=10, key="cfg_name_padding", on_change=on_change_padding, step=1)
            with c2: st.number_input("Starting Index", min_value=1, key="cfg_name_start", on_change=on_change_start_num, step=1)

        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-transform: uppercase;'>WATCHDOG LOG</p>", unsafe_allow_html=True)
        with st.container(border=True):
            log_content = get_watchdog_log()
            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if st.button("Reload Log", key="btn_reload_watchdog", icon="🔄", width='stretch'): st.rerun()
            with btn_col2:
                if st.button("Clear Log", key="btn_clear_watchdog", icon="🗑️", width='stretch'):
                    clear_watchdog_log()
                    st.rerun()
            st.markdown("")
            if log_content is None: st.info("Watchdog log not found.")
            elif not log_content.strip(): st.info("Watchdog log is empty.")
            else: st.text_area("Log Output", value=log_content, height=205, disabled=True, label_visibility="collapsed")

elif menu_selection == "Automation Settings":
    col_main, col_loop = st.columns([1, 1.2])
    with col_main:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>PROMPT & CAPABILITIES</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.text_area("Default Prompt", key="cfg_prompt", on_change=on_change_prompt, height=200)
            discovery = config.get("discovery", {})
            st.selectbox("Default Tool", options=discovery.get("available_tools", []), key="cfg_selected_tool", on_change=on_change_tool)
            st.selectbox("Default Model", options=discovery.get("available_models", []), key="cfg_selected_model", on_change=on_change_model)

        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-transform: uppercase;'>ASPECT RATIO SETTING</p>", unsafe_allow_html=True)
        pm_config = config.get("prompt_matrix", {})
        pm_enabled = pm_config.get("enabled", False)

        # Pre-fetch status for UI locking
        is_engine_running = False
        is_auto_running = False
        try:
            import requests
            r = requests.get("http://localhost:8000/health", timeout=1)
            is_engine_running = r.json().get("engine_running", False)
            is_auto_running = r.json().get("automation_running", False)
        except:
            pass
        
        with st.container(border=True):
            mode_opts = ["Fixed Aspect Ratio", "Dynamic Prefix Loop"]
            radio_idx = 1 if pm_enabled else 0
            
            c_ar1, c_ar2 = st.columns([1.5, 1])
            with c_ar1:
                ar_mode = st.radio("Mode Selection", options=mode_opts, index=radio_idx, horizontal=True, key="cfg_ar_mode_radio")
            
            if (ar_mode == "Dynamic Prefix Loop") != pm_enabled:
                pm_config["enabled"] = (ar_mode == "Dynamic Prefix Loop")
                # REMOVED: Automatic reset on toggle
                save_config({"prompt_matrix": pm_config})
                st.rerun()

            with c_ar2:
                ratio_list = ["16:9 (Landscape)", "9:16 (Portrait)", "1:1 (Square)", "4:3 (Landscape)", "3:4 (Portrait)", "21:9 (Ultrawide)", "3:2 (Landscape)", "2:3 (Portrait)", "None"]
                saved_fixed = config.get("fixed_aspect_ratio", "16:9 (Landscape)")
                try: f_idx = ratio_list.index(saved_fixed)
                except: f_idx = 0
                
                # Fixed Ratio selection is always visible and editable
                selected_fixed = st.selectbox("Fixed Ratio", options=ratio_list, index=f_idx, key="cfg_fixed_ar_select")
                if selected_fixed != saved_fixed:
                    save_config({"fixed_aspect_ratio": selected_fixed})
                



            # --- 1. State initialization logic ---
            if "pm_sys_initialized" not in st.session_state:
                for k in ["pm_df_work_sys", "pm_editor_sys", "pm_rerender_idx_sys"]:
                    if k in st.session_state: del st.session_state[k]
                st.session_state.pm_sys_initialized = True
                st.session_state.pm_rerender_idx_sys = 0
                
            fresh_cfg = load_config()
            pm_config_fresh = fresh_cfg.get("prompt_matrix", {})
            pm_items = pm_config_fresh.get("items", [
                {"ratio": "16:9 (Landscape)", "target": 5, "current": 0},
                {"ratio": "9:16 (Portrait)", "target": 5, "current": 0},
                {"ratio": "1:1 (Square)", "target": 5, "current": 0}
            ])
            
            # 2. Initialize working data in session state for callback support
            if "pm_df_work_sys" not in st.session_state:
                active_idx = -1
                for i, it in enumerate(pm_items):
                    if it.get("current", 0) < it.get("target", 1):
                        active_idx = i
                        break
                if active_idx == -1: active_idx = 0
                
                pm_data = []
                for i, it in enumerate(pm_items):
                    pm_data.append({
                        "ratio": it.get("ratio", ""),
                        "target": int(it.get("target", 0)),
                        "current": int(it.get("current", 0)),
                        "Active": (i == active_idx)
                    })
                st.session_state.pm_df_work_sys = pd.DataFrame(pm_data)
            

            # 2. Callback to enforce mutual exclusivity (Radio behavior)
            def on_pm_change_sys():
                editor_key = f"pm_editor_sys_{st.session_state.pm_rerender_idx_sys}"
                changes = st.session_state[editor_key].get("edited_rows", {})
                if not changes: return
                
                target_row = -1
                for row_idx, val in changes.items():
                    if val.get("Active") is True:
                        target_row = int(row_idx)
                        break
                
                if target_row != -1:
                    # Update data
                    for i in range(len(st.session_state.pm_df_work_sys)):
                        st.session_state.pm_df_work_sys.at[i, "Active"] = (i == target_row)
                    # Force rerender to clear buffer
                    st.session_state.pm_rerender_idx_sys += 1



            # 3. Render Table with dynamic key
            editor_key = f"pm_editor_sys_{st.session_state.pm_rerender_idx_sys}"
            edited_pm_df = st.data_editor(
                st.session_state.pm_df_work_sys,
                column_config={
                    "ratio": st.column_config.SelectboxColumn("Aspect Ratio", options=["16:9 (Landscape)", "9:16 (Portrait)", "1:1 (Square)", "4:3 (Landscape)", "3:4 (Portrait)", "21:9 (Ultrawide)", "3:2 (Landscape)", "2:3 (Portrait)", "None (Master Prompt)"], required=True, width="medium"),
                    "target": st.column_config.NumberColumn("Repeat", min_value=1, step=1, required=True, width="small"),
                    "current": st.column_config.NumberColumn("Count", disabled=True, width="small"),
                    "Active": st.column_config.CheckboxColumn("Active", width="small")
                },
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=editor_key,
                on_change=on_pm_change_sys
            )
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Save Setting", icon="💾", width="stretch"):
                    records = edited_pm_df.to_dict("records")
                    
                    # Find which row is active
                    new_active_idx = 0
                    for i, r in enumerate(records):
                        if r.get("Active"):
                            new_active_idx = i
                            break
                            
                    new_items = []
                    for i, r in enumerate(records):
                        target = int(r.get("target") or 1)
                        current = int(r.get("current") or 0)
                        
                        if i < new_active_idx:
                            current = target
                        elif i == new_active_idx:
                            if current >= target: current = 0
                        else:
                            current = 0
                                
                        new_items.append({
                            "ratio": r.get("ratio") or "None (Master Prompt)",
                            "target": target,
                            "current": current
                        })
                    
                    cfg = load_config()
                    if "prompt_matrix" not in cfg: cfg["prompt_matrix"] = {}
                    cfg["prompt_matrix"]["items"] = new_items
                    save_config({"prompt_matrix": cfg["prompt_matrix"]})
                    
                    # Cleanup session state
                    for k in ["pm_df_work_sys", "pm_editor_sys", "pm_rerender_idx_sys", "pm_sys_initialized"]:
                        if k in st.session_state: del st.session_state[k]
                    # Clear keyed buffers
                    for k in list(st.session_state.keys()):
                        if k.startswith("pm_editor_sys_"): del st.session_state[k]
                        
                    st.success("Setting saved!")
                    st.rerun()
            with c2:
                if st.button("Reset Progress", icon="🔄", width="stretch"):
                    new_items = []
                    for r in edited_pm_df.to_dict("records"):
                        new_items.append({
                            "ratio": r.get("ratio") or "None (Master Prompt)",
                            "target": int(r.get("target") or 1),
                            "current": 0
                        })
                    cfg = load_config()
                    if "prompt_matrix" not in cfg: cfg["prompt_matrix"] = {}
                    cfg["prompt_matrix"]["items"] = new_items
                    save_config({"prompt_matrix": cfg["prompt_matrix"]})
                    
                    # Cleanup session state
                    for k in ["pm_df_work_sys", "pm_editor_sys", "pm_rerender_idx_sys", "pm_sys_initialized"]:
                        if k in st.session_state: del st.session_state[k]
                    for k in list(st.session_state.keys()):
                        if k.startswith("pm_editor_sys_"): del st.session_state[k]
                        
                    st.success("Progress reset!")
                    st.rerun()

        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-top: 15px; margin-bottom: 5px; text-transform: uppercase;'>AUTOMATION GOALS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.toggle("Auto-Looping Enabled", key="cfg_auto_looping", on_change=on_change_auto_looping)
            st.selectbox("Execution Mode", options=["images", "rounds"], key="cfg_auto_mode", on_change=on_change_auto_mode)
            st.number_input("Target Goal", min_value=1, key="cfg_auto_goal", on_change=on_change_auto_goal, step=1)

    with col_loop:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>LOOP CONTROL & THRESHOLDS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            # Infinite Loop
            st.markdown("<p style='font-size: 0.8em; font-weight: bold; color: #a0a0ff;'>INFINITE LOOP (NO ACTIVITY)</p>", unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1: st.toggle("Enabled", key="cfg_loop_infinite_loop_enabled", on_change=on_change_loop_control("infinite_loop_enabled"))
            with c2: st.number_input("Minutes to wait", key="cfg_loop_infinite_loop_minutes", on_change=on_change_loop_control("infinite_loop_minutes"), step=1)
            
            st.markdown("---")
            # Time Based
            st.markdown("<p style='font-size: 0.8em; font-weight: bold; color: #a0a0ff;'>TIME-BASED ROTATION</p>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.8, 1.2, 2])
            with c1: st.toggle("Enabled", key="cfg_loop_time_enabled", on_change=on_change_loop_control("time_enabled"))
            with c2: st.number_input("Minutes", key="cfg_loop_time_minutes", on_change=on_change_loop_control("time_minutes"), step=1)
            with c3: st.selectbox("Action", options=["next_profile", "re_login", "stop"], key="cfg_loop_time_action", on_change=on_change_loop_control("time_action"))

            st.markdown("---")
            # Refusal Based
            st.markdown("<p style='font-size: 0.8em; font-weight: bold; color: #a0a0ff;'>REFUSAL THRESHOLD</p>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.8, 1.2, 2])
            with c1: st.toggle("Enabled", key="cfg_loop_refused_enabled", on_change=on_change_loop_control("refused_enabled"))
            with c2: st.number_input("Count", key="cfg_loop_refused_threshold", on_change=on_change_loop_control("refused_threshold"), step=1)
            with c3: st.selectbox("Action ", options=["next_profile", "re_login", "stop"], key="cfg_loop_refused_action", on_change=on_change_loop_control("refused_action"))

            st.markdown("---")
            # Reset Based
            st.markdown("<p style='font-size: 0.8em; font-weight: bold; color: #a0a0ff;'>RESET THRESHOLD</p>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.8, 1.2, 2])
            with c1: st.toggle("Enabled", key="cfg_loop_reset_enabled", on_change=on_change_loop_control("reset_enabled"))
            with c2: st.number_input("Count ", key="cfg_loop_reset_threshold", on_change=on_change_loop_control("reset_threshold"), step=1)
            with c3: st.selectbox("Action  ", options=["next_profile", "re_login", "stop"], key="cfg_loop_reset_action", on_change=on_change_loop_control("reset_action"))

elif menu_selection == "Account Credentials":
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>USER LOGIN CREDENTIALS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        rows = st.session_state.login_rows
        usernames = [r.get("username", "") for r in rows if r.get("username")]
        active_index = next((i for i, r in enumerate(rows) if r.get("active")), 0)

        if usernames:
            sel_col, btn_col = st.columns([3, 1])
            with sel_col:
                selected_active = st.selectbox("Active Account", options=usernames, index=min(active_index, len(usernames) - 1), key="active_account_select")
            with btn_col:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button("Set Active Account", icon="🔒", type="primary", width="stretch"):
                    current_rows = load_login_lookup()
                    final = [{**r, "active": (r.get("username") == selected_active)} for r in current_rows]
                    save_login_lookup(final)
                    st.session_state._login_reload = True
                    if "active_account_select" in st.session_state: del st.session_state["active_account_select"]
                    st.success("Active account updated!")
                    st.rerun()
        else: st.info("Add a new credential row below.")

        st.markdown("")
        editor_data = [{"active": r.get("active", False), "bypass": r.get("bypass", False), "username": r.get("username", ""), "auto_delete": r.get("auto_delete", False), "delete_range": r.get("delete_range", "Last hour"), "quota_full": r.get("quota_full", ""), "last_switched_at": r.get("last_switched_at", ""), "session_images": r.get("session_images", ""), "session_refused": r.get("session_refused", ""), "session_resets": r.get("session_resets", "")} for r in rows]
        editor_df = pd.DataFrame(editor_data) if editor_data else pd.DataFrame(columns=["active", "bypass", "username", "auto_delete", "delete_range", "quota_full", "last_switched_at", "session_images", "session_refused", "session_resets"])

        edited_df = st.data_editor(
            editor_df, 
            column_config={
                "active": st.column_config.CheckboxColumn("Active", disabled=True, width="small"), 
                "bypass": st.column_config.CheckboxColumn("Bypass", width="small"), 
                "username": st.column_config.TextColumn("Username"), 
                "auto_delete": st.column_config.CheckboxColumn("Auto Delete", width="small"), 
                "delete_range": st.column_config.SelectboxColumn("Range", options=["Last hour", "Last day", "All time"], width="small"), 
                "quota_full": st.column_config.TextColumn("Quota Full At", width=125), 
                "last_switched_at": st.column_config.TextColumn("Switched At", width=125), 
                "session_images": st.column_config.NumberColumn("Images", width="small"), 
                "session_refused": st.column_config.NumberColumn("Refused", width="small"), 
                "session_resets": st.column_config.NumberColumn("Resets", width="small")
            }, 
            num_rows="dynamic", 
            width="stretch", 
            hide_index=True, 
            height=430, 
            key="login_editor"
        )

        _INSTANT_COLS = ["bypass", "auto_delete", "delete_range", "username", "quota_full", "last_switched_at", "session_images", "session_refused", "session_resets"]
        if not editor_df.empty and not edited_df.empty and len(editor_df) == len(edited_df):
            if not editor_df[_INSTANT_COLS].reset_index(drop=True).equals(edited_df[_INSTANT_COLS].reset_index(drop=True)):
                edited_records = edited_df.to_dict("records")
                patched = []
                for idx, disk_row in enumerate(rows):
                    if idx < len(edited_records):
                        e = edited_records[idx]
                        patched.append({**disk_row, "bypass": bool(e.get("bypass", False)), "auto_delete": bool(e.get("auto_delete", False)), "delete_range": str(e.get("delete_range", "All time")), "username": str(e.get("username", disk_row.get("username", ""))).strip(), "quota_full": e.get("quota_full") if pd.notna(e.get("quota_full")) else "", "last_switched_at": e.get("last_switched_at") if pd.notna(e.get("last_switched_at")) else "", "session_images": e.get("session_images") if pd.notna(e.get("session_images")) else "", "session_refused": e.get("session_refused") if pd.notna(e.get("session_refused")) else "", "session_resets": e.get("session_resets") if pd.notna(e.get("session_resets")) else ""})
                    else: patched.append(disk_row)
                save_login_lookup(patched); st.toast("Credentials updated.", icon="💾")
        elif not edited_df.empty:
            valid = [r for r in edited_df.to_dict("records") if str(r.get("username", "")).strip()]
            if valid: save_login_lookup(valid); st.toast("Credentials updated.", icon="💾")

        btn_reload, btn_clear, btn_clear_stats = st.columns([1, 1.2, 1.2])
        with btn_reload:
            if st.button("Reload Table", icon="🔄", width="stretch"): st.session_state._login_reload = True; st.rerun()
        with btn_clear:
            if st.button("Clear Quota", icon="🧹", width="stretch"):
                for r in rows:
                    if r.get("quota_full"):
                        r["quota_full"] = ""
                        r["session_images"] = r["session_refused"] = r["session_resets"] = "0"
                save_login_lookup(rows); st.session_state._login_reload = True; st.rerun()
        with btn_clear_stats:
            if st.button("Reset Stats", icon="🧹", width="stretch"):
                for r in rows: r["last_switched_at"] = ""; r["session_images"] = r["session_refused"] = r["session_resets"] = ""
                save_login_lookup(rows); st.session_state._login_reload = True; st.rerun()

elif menu_selection == "Quota Full Phrases":
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>QUOTA FULL PHRASES</p>", unsafe_allow_html=True)
    with st.container(border=True):
        quota_phrases = config.get("quota_full", [])
        quota_df = pd.DataFrame([{"phrase": p} for p in quota_phrases])
        edited_quota_df = st.data_editor(
            quota_df, 
            column_config={"phrase": st.column_config.TextColumn("Identification Phrase")}, 
            num_rows="dynamic", 
            width="stretch", 
            hide_index=True, 
            height=415, 
            key="quota_editor"
        )
        st.markdown("<div style='height: 85px;'></div>", unsafe_allow_html=True)
        if st.button("Save Quota Phrases", icon="📝", width='stretch'):
            new_phrases = [p.strip() for p in edited_quota_df["phrase"].tolist() if p and p.strip()]
            save_config({"quota_full": new_phrases})
            st.success("Quota phrases updated!")
            st.rerun()

@st.fragment(run_every=5 if st.session_state.get("health_auto_refresh", True) else None)
def _render_health_content(view_mode, login_data, graph_type):
    """Auto-refreshes every 5 s independently; only this content area reruns."""
    _is_full = view_mode == "Full Loading History (All Events)"
    _is_active = view_mode == "Detailed History: Active Account"
    _is_summary = view_mode == "Latest Summary (All Accounts)"

    st.markdown("---")

    if _is_full:
        st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing every recorded loading event in chronological order (latest first).</p>", unsafe_allow_html=True)
        _, all_detailed, _ = parse_account_health(target_account="ALL_EVENTS", login_data=login_data)
        if not all_detailed:
            st.info("No loading records found in engine.log.")
        else:
            if st.session_state.show_health_graph:
                st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>All Events</b></p>", unsafe_allow_html=True)
                chart_df = pd.DataFrame(all_detailed)
                if graph_type == "Loading Duration":
                    chart_df = pd.DataFrame(all_detailed[::-1]) # Chronological order
                    chart_df["Event"] = range(1, len(chart_df) + 1)
                    chart_df["Minutes"] = chart_df["health"].str.replace("s", "").astype(float) / 60.0
                    chart_df["cycle"] = chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                    chart_df["variant"] = chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                    legend_labels = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Fail', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                    legend_colors = ['#2ecc71', '#a0a0ff', '#f39c12', '#ff9999', '#a0e6b5', '#d0d0ff', '#f9e79f']
                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})" if r['status'] != 'Fail' else 'Fail', axis=1)
                    def _fmt_dur(x):
                        h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
                        return f"{h}:{m:02d}:{s:02d}" if h > 0 else (f"{m}:{s:02d}" if m > 0 else f"{s}s")
                    chart_df["Duration"] = chart_df["health"].str.replace("s", "").astype(float).apply(_fmt_dur)
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('Event:Q', title=None, scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                        y=alt.Y('Minutes:Q', title="Duration (minite)", scale=alt.Scale(type='symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear')),
                        color=alt.Color('legend:N',
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors),
                                        legend=alt.Legend(title=None, orient='bottom', columns=4)),
                        tooltip=['time', 'account', 'Duration', 'filename', 'status']
                    ).properties(height=400).interactive(bind_y=False)
                    st.altair_chart(chart, width="stretch")
                else: # Reject Rates (Dashboard Style)
                    st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance & Reject Rates (X-Axis: Successful Images)</p>", unsafe_allow_html=True)
                    agg_data = []; curr_rej = 0; curr_res = 0; curr_dur = 0.0; seg_id = 0; prev_si = None
                    for row in reversed(all_detailed):
                        si = row["session_index"]
                        if prev_si is not None and si != prev_si:
                            # Reset counters on session/account switch
                            curr_rej = 0; curr_res = 0; curr_dur = 0.0
                            seg_id += 1
                        
                        row_dur = float(row["health"].replace("s", ""))
                        if row["status"] == "Reject":
                            curr_rej += 1
                            curr_dur += row_dur
                        elif row["status"] == "Reset":
                            curr_res += 1
                            curr_dur += row_dur
                        elif row["status"] == "Success" or row["status"] == "Fail":
                            d = row.copy()
                            # Priority: Use anchored RejectStat if available (handles session resets correctly)
                            if "true_rej" in d:
                                d["Rejects"] = d["true_rej"]
                                d["Resets"] = d["true_res"]
                                d["Duration"] = row_dur # RejectStat dur is already cumulative
                            else:
                                d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                d["Duration"] = curr_dur + row_dur
                            
                            d["Image"] = row["filename"].replace(".png", "") if row["filename"] else "FAILED"
                            d["seg_id"] = seg_id; d["bg"] = 'A' if seg_id % 2 == 0 else 'B'
                            d["Event"] = len(agg_data) + 1
                            d["Display"] = f"{d['Image']} (#{d['Event']})"
                            agg_data.append(d)
                            # Reset for next image
                            curr_rej = 0; curr_res = 0; curr_dur = 0.0
                        prev_si = si
                    if not agg_data:
                        st.info("No successful image downloads found to plot trends.")
                    else:
                        agg_df = pd.DataFrame(agg_data)
                        agg_df["Event_Start"] = agg_df["Event"] - 0.5
                        agg_df["Event_End"] = agg_df["Event"] + 0.5
                        # Layer 1: background bands
                        bg_bands = alt.Chart(agg_df).mark_rect(opacity=0.25).encode(
                            x=alt.X('Event_Start:Q', title="Image Sequence", scale=alt.Scale(nice=False)),
                            x2='Event_End:Q',
                            color=alt.Color('bg:N', scale=alt.Scale(domain=['A','B'], range=['#d0d0d0','#f5f5f5']), legend=None),
                            tooltip=['account:N', 'session_index:Q']
                        )
                        # Layer 2: line chart
                        agg_df["t_dur"] = agg_df["Duration"] / 60.0
                        agg_df["t_rej"] = agg_df["Rejects"]
                        agg_df["t_res"] = agg_df["Resets"]
                        agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                        plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res','status'], value_vars=['t_dur','Rejects','Resets'], var_name='Metric', value_name='Value')
                        # Map internal names to display names for the legend
                        plot_df['Metric'] = plot_df['Metric'].replace({'t_dur': 'Duration (minite)'})
                        
                        y_scale_type = 'symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear'

                        # Define common color scale to ensure synchronization
                        health_color_scale = alt.Scale(
                            domain=['Duration (minite)', 'Rejects', 'Resets'],
                            range=['#2ecc71', '#a0a0ff', '#f39c12']
                        )

                        base_chart = alt.Chart(plot_df).encode(
                            x=alt.X('Event:Q', title=None, axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Value:Q', title=None, scale=alt.Scale(type=y_scale_type)),
                            color=alt.Color('Metric:N', scale=health_color_scale, legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3))
                        )

                        lines = base_chart.mark_line()
                        points = base_chart.mark_point(opacity=0.9, size=50, filled=True).encode(
                            color=alt.condition(
                                "datum.status == 'Fail'",
                                alt.value("#ff3333"), # Bold Red for failures
                                alt.Color('Metric:N', scale=health_color_scale, legend=None)
                            ),
                            tooltip=[
                                alt.Tooltip('Image:N', title='Filename'),
                                alt.Tooltip('account:N', title='Account'),
                                alt.Tooltip('time:N', title='Time'),
                                alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                alt.Tooltip('t_rej:Q', title='Reject Count'),
                                alt.Tooltip('t_res:Q', title='Reset Count'),
                                alt.Tooltip('status:N', title='Status')
                            ]
                        )
                        
                        st.altair_chart(alt.layer(bg_bands, lines, points).resolve_scale(color='independent').properties(height=400).interactive(), width="stretch")
            else:
                st.data_editor(
                    pd.DataFrame(all_detailed),
                    column_config={
                        "account": st.column_config.TextColumn("Account"),
                        "time": st.column_config.TextColumn("Time"),
                        "health": st.column_config.TextColumn("Health"),
                        "filename": st.column_config.TextColumn("Filename"),
                        "status": st.column_config.TextColumn("Status")
                    },
                    disabled=True, width="stretch", hide_index=True, height=450,
                    key="health_full_history_table"
                )
    elif _is_active:
        _active_user = next((u.get("username", "") for u in login_data if u.get("active")), None)
        if not _active_user:
            st.info("No active account is currently set.")
        else:
            _active_acc = _active_user.lower()
            _, _active_detailed, _ = parse_account_health(target_account=_active_acc, login_data=login_data)
            if not _active_detailed:
                st.info(f"No detailed records found for active account: {_active_user}.")
            else:
                if st.session_state.show_health_graph:
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>{_active_user}</b> (Active Account)</p>", unsafe_allow_html=True)
                    if graph_type == "Loading Duration":
                        _chart_df = pd.DataFrame(_active_detailed[::-1])
                        _chart_df["Event"] = range(1, len(_chart_df) + 1)
                        _chart_df["Minutes"] = _chart_df["health"].str.replace("s", "").astype(float) / 60.0
                        _chart_df["cycle"] = _chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                        _chart_df["variant"] = _chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                        _ll = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Fail', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                        _lr = ['#2ecc71', '#a0a0ff', '#f39c12', '#ff9999', '#a0e6b5', '#d0d0ff', '#f9e79f']
                        _chart_df['legend'] = _chart_df.apply(lambda r: f"{r['status']} ({r['variant']})" if r['status'] != 'Fail' else 'Fail', axis=1)
                        def _fmt_dur(x):
                            h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
                            return f"{h}:{m:02d}:{s:02d}" if h > 0 else (f"{m}:{s:02d}" if m > 0 else f"{s}s")
                        _chart_df["Duration"] = _chart_df["health"].str.replace("s", "").astype(float).apply(_fmt_dur)
                        _chart = alt.Chart(_chart_df).mark_bar().encode(
                            x=alt.X('Event:Q', title=None, scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Minutes:Q', title="Duration (minite)", scale=alt.Scale(type='symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear')),
                            color=alt.Color('legend:N', scale=alt.Scale(domain=_ll, range=_lr), legend=alt.Legend(title=None, orient='bottom', columns=4)),
                            tooltip=['time', 'account', 'Duration', 'filename', 'status']
                        ).properties(height=400).interactive(bind_y=False)
                        st.altair_chart(_chart, width="stretch")
                    else: # Reject Rates (Dashboard Style)
                        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Reject Rate for <b>{_active_user}</b> (X-Axis: Successful Images)</p>", unsafe_allow_html=True)
                        agg_data = []; curr_rej = 0; curr_res = 0; curr_dur = 0.0; seg_id = 0; prev_si = None
                        for row in reversed(_active_detailed):
                            si = row["session_index"]
                            if prev_si is not None and si != prev_si:
                                curr_rej = 0; curr_res = 0; curr_dur = 0.0
                                seg_id += 1
                            
                            row_dur = float(row["health"].replace("s", ""))
                            if row["status"] == "Reject":
                                curr_rej += 1
                                curr_dur += row_dur
                            elif row["status"] == "Reset":
                                curr_res += 1
                                curr_dur += row_dur
                            elif row["status"] == "Success" or row["status"] == "Fail":
                                d = row.copy()
                                # Priority: Use anchored RejectStat if available (handles session resets correctly)
                                if "true_rej" in d:
                                    d["Rejects"] = d["true_rej"]
                                    d["Resets"] = d["true_res"]
                                    d["Duration"] = row_dur # RejectStat dur is already cumulative
                                else:
                                    d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                    d["Duration"] = curr_dur + row_dur
                                d["Image"] = row["filename"].replace(".png", "") if row["filename"] else "FAILED"
                                d["seg_id"] = seg_id; d["bg"] = 'A' if seg_id % 2 == 0 else 'B'
                                d["Event"] = len(agg_data) + 1
                                d["Display"] = f"{d['Image']} (#{d['Event']})"
                                agg_data.append(d)
                                curr_rej = 0; curr_res = 0; curr_dur = 0.0
                            prev_si = si
                        if not agg_data:
                            st.info("No successful image downloads found to plot trends.")
                        else:
                            agg_df = pd.DataFrame(agg_data)
                            agg_df["Event_Start"] = agg_df["Event"] - 0.5
                            agg_df["Event_End"] = agg_df["Event"] + 0.5
                            bg_bands = alt.Chart(agg_df).mark_rect(opacity=0.25).encode(
                                x=alt.X('Event_Start:Q', title="Image Sequence", scale=alt.Scale(nice=False)),
                                x2='Event_End:Q',
                                color=alt.Color('bg:N', scale=alt.Scale(domain=['A','B'], range=['#d0d0d0','#f5f5f5']), legend=None),
                                tooltip=['account:N', 'session_index:Q']
                            )
                            agg_df["t_dur"] = agg_df["Duration"] / 60.0
                            agg_df["t_rej"] = agg_df["Rejects"]
                            agg_df["t_res"] = agg_df["Resets"]
                            agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                            plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res','status'], value_vars=['t_dur','Rejects','Resets'], var_name='Metric', value_name='Value')
                            # Map internal names to display names for the legend
                            plot_df['Metric'] = plot_df['Metric'].replace({'t_dur': 'Duration (minite)'})
                            
                            y_scale_type = 'symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear'

                            # Define common color scale to ensure synchronization
                            health_color_scale = alt.Scale(
                                domain=['Duration (minite)', 'Rejects', 'Resets'],
                                range=['#2ecc71', '#a0a0ff', '#f39c12']
                            )

                            base_chart = alt.Chart(plot_df).encode(
                                x=alt.X('Event:Q', title=None, axis=alt.Axis(format='d', tickMinStep=1)),
                                y=alt.Y('Value:Q', title=None, scale=alt.Scale(type=y_scale_type)),
                                color=alt.Color('Metric:N', scale=health_color_scale, legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3))
                            )

                            lines = base_chart.mark_line()
                            points = base_chart.mark_point(opacity=0.9, size=50, filled=True).encode(
                                color=alt.condition(
                                    "datum.status == 'Fail'",
                                    alt.value("#ff3333"), # Bold Red for failures
                                    alt.Color('Metric:N', scale=health_color_scale, legend=None)
                                ),
                                tooltip=[
                                    alt.Tooltip('Image:N', title='Filename'),
                                    alt.Tooltip('account:N', title='Account'),
                                    alt.Tooltip('time:N', title='Time'),
                                    alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                    alt.Tooltip('t_rej:Q', title='Reject Count'),
                                    alt.Tooltip('t_res:Q', title='Reset Count'),
                                    alt.Tooltip('status:N', title='Status')
                                ]
                            )
                            st.altair_chart(alt.layer(bg_bands, lines, points).resolve_scale(color='independent').properties(height=400).interactive(), width="stretch")
                else:
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing all loading performance records for <b>{_active_user}</b> (Active Account).</p>", unsafe_allow_html=True)
                    st.data_editor(
                        pd.DataFrame(_active_detailed),
                        column_config={
                            "account": st.column_config.TextColumn("Account"),
                            "time": st.column_config.TextColumn("Time"),
                            "health": st.column_config.TextColumn("Health"),
                            "filename": st.column_config.TextColumn("Filename", help="Downloaded image filename"),
                            "status": st.column_config.TextColumn("Status")
                        },
                        disabled=True, width="stretch", hide_index=True, height=450,
                        key="health_active_account_table"
                    )
    elif _is_summary:
        _summary_all, _, _ = parse_account_health(login_data=login_data)
        st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing the last recorded loading performance for each account.</p>", unsafe_allow_html=True)
        if not _summary_all:
            st.info("No loading records found in engine.log.")
        else:
            st.data_editor(
                pd.DataFrame(_summary_all),
                column_config={
                    "account": st.column_config.TextColumn("Account"),
                    "time": st.column_config.TextColumn("Time"),
                    "health": st.column_config.TextColumn("Health"),
                    "filename": st.column_config.TextColumn("Filename", help="Last successful image filename"),
                    "status": st.column_config.TextColumn("Status")
                },
                disabled=True, width="stretch", hide_index=True, height=450,
                key="health_summary_table"
            )
    else:
        # Detailed mode for a specific account
        target_acc = view_mode.replace("Detailed History: ", "")
        _, detailed_list, _ = parse_account_health(target_account=target_acc, login_data=login_data)
        if not detailed_list:
            st.info(f"No detailed records found for {target_acc}.")
        else:
            if st.session_state.show_health_graph:
                st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>{target_acc}</b></p>", unsafe_allow_html=True)
                chart_df = pd.DataFrame(detailed_list)
                if graph_type == "Loading Duration":
                    chart_df = pd.DataFrame(detailed_list[::-1])
                    chart_df["Event"] = range(1, len(chart_df) + 1)
                    chart_df["Minutes"] = chart_df["health"].str.replace("s", "").astype(float) / 60.0
                    chart_df["cycle"] = chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                    chart_df["variant"] = chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                    legend_labels = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Fail', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                    legend_colors = ['#2ecc71', '#a0a0ff', '#f39c12', '#ff9999', '#a0e6b5', '#d0d0ff', '#f9e79f']
                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})" if r['status'] != 'Fail' else 'Fail', axis=1)
                    def _fmt_dur(x):
                        h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
                        return f"{h}:{m:02d}:{s:02d}" if h > 0 else (f"{m}:{s:02d}" if m > 0 else f"{s}s")
                    chart_df["Duration"] = chart_df["health"].str.replace("s", "").astype(float).apply(_fmt_dur)
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('Event:Q', title=None, scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                        y=alt.Y('Minutes:Q', title="Duration (minite)", scale=alt.Scale(type='symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear')),
                        color=alt.Color('legend:N',
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors),
                                        legend=alt.Legend(title=None, orient='bottom', columns=4)),
                        tooltip=['time', 'account', 'Duration', 'filename', 'status']
                    ).properties(height=400).interactive(bind_y=False)
                    st.altair_chart(chart, width="stretch")
                else: # Reject Rates (Dashboard Style)
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Reject Rate for <b>{target_acc}</b> (X-Axis: Successful Images)</p>", unsafe_allow_html=True)
                    agg_data = []; curr_rej = 0; curr_res = 0; curr_dur = 0.0; seg_id = 0; prev_si = None
                    for row in reversed(detailed_list):
                        si = row["session_index"]
                        if prev_si is not None and si != prev_si:
                            curr_rej = 0; curr_res = 0; curr_dur = 0.0
                            seg_id += 1
                        
                        row_dur = float(row["health"].replace("s", ""))
                        if row["status"] == "Reject":
                            curr_rej += 1
                            curr_dur += row_dur
                        elif row["status"] == "Reset":
                            curr_res += 1
                            curr_dur += row_dur
                        elif row["status"] == "Success" or row["status"] == "Fail":
                            d = row.copy()
                            # Priority: Use anchored RejectStat if available
                            if "true_rej" in d:
                                d["Rejects"] = d["true_rej"]
                                d["Resets"] = d["true_res"]
                                d["Duration"] = row_dur
                            else:
                                d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                d["Duration"] = curr_dur + row_dur
                            
                            d["Image"] = row["filename"].replace(".png", "") if row["filename"] else "FAILED"
                            d["seg_id"] = seg_id; d["bg"] = 'A' if seg_id % 2 == 0 else 'B'
                            d["Event"] = len(agg_data) + 1
                            d["Display"] = f"{d['Image']} (#{d['Event']})"
                            agg_data.append(d)
                            curr_rej = 0; curr_res = 0; curr_dur = 0.0
                        prev_si = si
                    if not agg_data:
                        st.info("No successful image downloads found to plot trends.")
                    else:
                        agg_df = pd.DataFrame(agg_data)
                        agg_df["Event_Start"] = agg_df["Event"] - 0.5
                        agg_df["Event_End"] = agg_df["Event"] + 0.5
                        bg_bands = alt.Chart(agg_df).mark_rect(opacity=0.25).encode(
                            x=alt.X('Event_Start:Q', title="Image Sequence", scale=alt.Scale(nice=False)),
                            x2='Event_End:Q',
                            color=alt.Color('bg:N', scale=alt.Scale(domain=['A','B'], range=['#d0d0d0','#f5f5f5']), legend=None),
                            tooltip=['account:N', 'session_index:Q']
                        )
                        # Use melt to reshape data for line chart
                        agg_df["t_dur"] = agg_df["Duration"] / 60.0
                        agg_df["t_rej"] = agg_df["Rejects"]
                        agg_df["t_res"] = agg_df["Resets"]
                        def _fmt_dur(x):
                            h = int(x // 3600); m = int((x % 3600) // 60); s = int(x % 60)
                            return f"{h}:{m:02d}:{s:02d}" if h > 0 else (f"{m}:{s:02d}" if m > 0 else f"{s}s")
                        agg_df["t_dur_fmt"] = agg_df["Duration"].apply(_fmt_dur)
                        plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res','status'], value_vars=['t_dur','Rejects','Resets'], var_name='Metric', value_name='Value')
                        # Map internal names to display names for the legend
                        plot_df['Metric'] = plot_df['Metric'].replace({'t_dur': 'Duration (minite)'})
                        
                        y_scale_type = 'symlog' if load_config().get("health_y_scale", "Linear") == "Logarithmic" else 'linear'

                        # Define common color scale to ensure synchronization
                        health_color_scale = alt.Scale(
                            domain=['Duration (minite)', 'Rejects', 'Resets'],
                            range=['#2ecc71', '#a0a0ff', '#f39c12']
                        )

                        base_chart = alt.Chart(plot_df).encode(
                            x=alt.X('Event:Q', title=None, axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Value:Q', title=None, scale=alt.Scale(type=y_scale_type)),
                            color=alt.Color('Metric:N', scale=health_color_scale, legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3))
                        )

                        lines = base_chart.mark_line()
                        points = base_chart.mark_point(opacity=0.9, size=50, filled=True).encode(
                            color=alt.condition(
                                "datum.status == 'Fail'",
                                alt.value("#ff3333"), # Bold Red for failures
                                alt.Color('Metric:N', scale=health_color_scale, legend=None)
                            ),
                            tooltip=[
                                alt.Tooltip('Image:N', title='Filename'),
                                alt.Tooltip('account:N', title='Account'),
                                alt.Tooltip('time:N', title='Time'),
                                alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                alt.Tooltip('t_rej:Q', title='Reject Count'),
                                alt.Tooltip('t_res:Q', title='Reset Count'),
                                alt.Tooltip('status:N', title='Status')
                            ]
                        )
                        
                        st.altair_chart(alt.layer(bg_bands, lines, points).resolve_scale(color='independent').properties(height=400).interactive(), width="stretch")
            else:
                st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing all loading performance records for <b>{target_acc}</b>.</p>", unsafe_allow_html=True)
                st.data_editor(
                    pd.DataFrame(detailed_list),
                    column_config={
                        "account": st.column_config.TextColumn("Account"),
                        "time": st.column_config.TextColumn("Time"),
                        "health": st.column_config.TextColumn("Health"),
                        "filename": st.column_config.TextColumn("Filename", help="Downloaded image filename"),
                        "status": st.column_config.TextColumn("Status")
                    },
                    disabled=True, width="stretch", hide_index=True, height=450,
                    key=f"health_detailed_{target_acc}"
                )

if menu_selection == "Account Health Analysis":
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>ACCOUNT HEALTH ANALYSIS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        # Initial parse to get account list from logs
        summary_all, _, log_accs = parse_account_health(login_data=login_data)
        
        # Merge with accounts from user_login_lookup.json to ensure ALL are selectable
        # Preserve order from user_login_lookup.json
        lookup_order = [u.get("username", "").lower() for u in login_data if u.get("username")]
        log_accs_set = set(log_accs)
        lookup_accs_set = set(lookup_order)
        
        # 1. Start with accounts from lookup table in their original order
        final_dropdown_accs = [acc for acc in lookup_order]
        # 2. Append any accounts found in logs but NOT in lookup table (at the end, alphabetically)
        extra_accs = sorted(list(log_accs_set - lookup_accs_set))
        final_dropdown_accs.extend(extra_accs)

        col_sel, col_ref, col_btn1, col_btn2 = st.columns([2, 0.8, 0.6, 0.6])
        with col_ref:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            st.toggle("Auto-refresh", value=True, key="health_auto_refresh", help="Disable to prevent chart reset while zooming.")

        with col_sel:
            # Ensure persistent view mode is valid for current options
            options = ["Full Loading History (All Events)", "Detailed History: Active Account", "Latest Summary (All Accounts)"] + [f"Detailed History: {acc}" for acc in final_dropdown_accs]
            
            cfg_val = config.get("health_view_mode", "Full Loading History (All Events)")
            try:
                view_index = options.index(cfg_val)
            except ValueError:
                view_index = 0

            view_mode = st.selectbox(
                "Select View Mode",
                options=options,
                index=view_index,
                key="widget_health_view_mode",
                on_change=on_change_health_view,
                help="Choose between a complete history of all loading events, a summary of all accounts, or detailed history for a specific account."
            )
        
        is_full_history = view_mode == "Full Loading History (All Events)"
        is_active_account = view_mode == "Detailed History: Active Account"
        is_latest_summary = view_mode == "Latest Summary (All Accounts)"
        is_detailed = not (is_full_history or is_active_account or is_latest_summary)
        
        # Initialize graph toggle state if not exists
        if "show_health_graph" not in st.session_state:
            st.session_state.show_health_graph = True

        with col_btn1:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Refresh Log", icon="🔄", width="stretch"):
                st.rerun()
        
        with col_btn2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if is_detailed or is_full_history or is_active_account:
                btn_label = "Show Table" if st.session_state.show_health_graph else "Plot Graph"
                btn_icon = "📋" if st.session_state.show_health_graph else "📊"
                if st.button(btn_label, icon=btn_icon, width="stretch", type="secondary"):
                    st.session_state.show_health_graph = not st.session_state.show_health_graph
                    st.rerun()
            else:
                # Placeholder to keep layout consistent
                st.button("Plot Graph", icon="📊", width="stretch", disabled=True)

        if st.session_state.show_health_graph and not is_latest_summary:
            st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True)
            _, col_rad, col_scale = st.columns([1.5, 1, 1])
            
            graph_opts = ["Loading Duration", "Reject Rates"]
            scale_opts = ["Linear", "Logarithmic"]

            cfg_graph = config.get("health_graph_type", "Loading Duration")
            try:
                graph_idx = graph_opts.index(cfg_graph)
            except ValueError:
                graph_idx = 0

            cfg_scale = config.get("health_y_scale", "Linear")
            try:
                scale_idx = scale_opts.index(cfg_scale)
            except ValueError:
                scale_idx = 0

            with col_rad:
                st.radio("Graph Mode", graph_opts, index=graph_idx, horizontal=True, key="widget_health_graph_type", on_change=on_change_health_graph, label_visibility="collapsed")
            with col_scale:
                st.radio("Y-Axis Scale", scale_opts, index=scale_idx, horizontal=True, key="widget_health_y_scale", on_change=on_change_health_y_scale, help="Use Logarithmic scale to see small counts (Rejects/Resets) alongside large durations.")

        _render_health_content(view_mode, login_data, config.get("health_graph_type", "Loading Duration"))

elif menu_selection == "Automation Cycle Management":
    st.markdown("### 🔄 Automation Cycle Management")
    st.write("This tool analyzes `engine.log` for complete automation cycles (Start -> Stop). **Continue Session** triggers are grouped within their original parent cycle.")
    
    cycles = parse_engine_cycles()
    
    if not cycles:
        st.info("No complete cycles found in the log.")
    else:
        st.write(f"Found **{len(cycles)}** complete cycle(s).")
        
        cycle_data = []
        for idx, c in enumerate(cycles):
            display_time = c.get('full_start_time', c['start_time_str'])
            cycle_data.append({
                "Select": False,
                "Cycle ID": idx + 1,
                "Start Time": display_time,
                "Log Lines": c['lines_count'],
                "_start_idx": c['start_idx'],
                "_end_idx": c['end_idx']
            })
            
        df = pd.DataFrame(cycle_data)
        
        edited_df = st.data_editor(
            df,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select for Deletion", default=False),
                "_start_idx": None,
                "_end_idx": None
            },
            disabled=["Cycle ID", "Start Time", "Log Lines"],
            hide_index=True,
        )
        
        selected_rows = edited_df[edited_df["Select"] == True]
        
        if not selected_rows.empty:
            st.warning(f"You have selected {len(selected_rows)} cycle(s) to delete. This action will permanently remove their associated logs from `engine.log`.")
            if st.button("🗑️ Delete Selected Cycles", type="primary", width="stretch"):
                cycles_to_delete = []
                for _, row in selected_rows.iterrows():
                    cycles_to_delete.append({
                        'start_idx': row["_start_idx"],
                        'end_idx': row["_end_idx"]
                    })
                
                LOG_PATH = "engine.log"
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                
                to_keep = []
                for i, line in enumerate(lines):
                    deleted = False
                    for c in cycles_to_delete:
                        if c['start_idx'] <= i <= c['end_idx']:
                            deleted = True
                            break
                    if not deleted:
                        to_keep.append(line)
                        
                with open(LOG_PATH, "w", encoding="utf-8") as f:
                    f.writelines(to_keep)
                
                st.success(f"Successfully deleted {len(cycles_to_delete)} cycle(s).")
                st.rerun()
