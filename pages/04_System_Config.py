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
    save_config({"health_graph_type": st.session_state.cfg_health_graph_type})

def on_change_health_view():
    save_config({"health_view_mode": st.session_state.cfg_health_view_mode})

def on_change_navigation():
    save_config({"system_navigation": st.session_state.cfg_system_nav})

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

def on_change_loop_control(key):
    def callback():
        cfg = load_config()
        if "automation" not in cfg: cfg["automation"] = {}
        if "loop_control" not in cfg["automation"]: cfg["automation"]["loop_control"] = {}
        cfg["automation"]["loop_control"][key] = st.session_state[f"cfg_loop_{key}"]
        save_config({"automation": cfg["automation"]})
    return callback

# --- Health Analysis Logic ---
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
        
        # Pre-process lines to find all real accounts mentioned in logs in order
        for line in lines:
            acc_id = None
            if "Re-login detected for" in line:
                acc_id = line.split("Re-login detected for")[1].split()[0].strip().rstrip('.:')
            elif "switched to" in line:
                acc_id = line.split("switched to")[1].split()[0].strip().rstrip('.:')
            elif "current_account_id" in line:
                match = re.search(r"['\"]current_account_id['\"]\s*:\s*['\"]([^'\"]+)['\"]", line)
                if match: acc_id = match.group(1)
            
            if acc_id:
                norm = acc_id.split('@')[0].lower().strip()
                if norm not in found_accounts_set:
                    found_accounts_set.add(norm)
                    found_accounts_ordered.append(norm)

        # Main parsing loop
        session_index = 1
        last_noted_account = None

        for i, line in enumerate(lines):
            # Track account switches
            acc_id = None
            if "Re-login detected for" in line:
                acc_id = line.split("Re-login detected for")[1].split()[0].strip().rstrip('.:')
            elif "switched to" in line:
                acc_id = line.split("switched to")[1].split()[0].strip().rstrip('.:')
            elif "current_account_id" in line:
                match = re.search(r"['\"]current_account_id['\"]\s*:\s*['\"]([^'\"]+)['\"]", line)
                if match: acc_id = match.group(1)
            
            if acc_id:
                normalized = acc_id.split('@')[0].lower().strip()
                # Only increment session if the account actually changed
                if last_noted_account is not None and normalized != last_noted_account:
                    session_index += 1
                
                last_noted_account = normalized
                current_account = normalized
            
            # Detect loading events
            if "正在加载 Nano Banana 2..." in line:
                start_ts_str = line[1:9]
                
                duration_secs = None
                completion_idx = -1
                is_success = False
                filename = ""
                
                # Look ahead for completion
                for j in range(i + 1, min(i + 200, len(lines))): 
                    next_line = lines[j]
                    if any(marker in next_line for marker in ["Response successful", "Response failed", "Automation loop encountered an issue", "Gemini page was unexpectedly reset"]):
                        end_ts_str = next_line[1:9]
                        completion_idx = j
                        if "Response successful" in next_line: is_success = True
                        try:
                            fmt = '%H:%M:%S'
                            tdelta = datetime.strptime(end_ts_str, fmt) - datetime.strptime(start_ts_str, fmt)
                            sec = int(tdelta.total_seconds())
                            if sec < 0: sec += 86400
                            duration_secs = sec
                            break
                        except: continue
                    
                    # Fallback completion: Any subsequent Gemini output
                    if "API>> Gemini:" in next_line and "正在加载 Nano Banana 2..." not in next_line:
                        end_ts_str = next_line[1:9]
                        completion_idx = j
                        try:
                            fmt = '%H:%M:%S'
                            tdelta = datetime.strptime(end_ts_str, fmt) - datetime.strptime(start_ts_str, fmt)
                            sec = int(tdelta.total_seconds())
                            if sec < 0: sec += 86400
                            duration_secs = sec
                            break
                        except: continue
                
                if duration_secs is not None:
                    if is_success and completion_idx != -1:
                        for k in range(completion_idx + 1, min(completion_idx + 10, len(lines))):
                            if "Saved: " in lines[k]:
                                filename = lines[k].split("Saved: ")[1].strip()
                                # Look a bit further for the RejectStat log which contains high-precision cumulative data
                                for l in range(k + 1, min(k + 20, len(lines))):
                                    if "RejectStat: Wrote record for" in lines[l] and filename in lines[l]:
                                        stat_match = re.search(r"dur=([\d.]+)s, ref=(\d+), rst=(\d+)", lines[l])
                                        if stat_match:
                                            true_dur = float(stat_match.group(1))
                                            true_rej = int(stat_match.group(2))
                                            true_res = int(stat_match.group(3))
                                            # We use these high-precision values for the success record
                                            duration_secs = true_dur
                                            # We also store them as metadata to bypass accumulation in charts
                                            record_meta = {"true_rej": true_rej, "true_res": true_res}
                                            break
                                break

                    status = "Reject"
                    if is_success: status = "Success"
                    else:
                        # Re-scan completion marker to distinguish Reject vs Reset
                        for j in range(i + 1, min(i + 200, len(lines))):
                            if "Gemini page was unexpectedly reset" in lines[j] or "Automation loop encountered an issue" in lines[j]:
                                status = "Reset"; break
                            if "Response failed" in lines[j]:
                                status = "Reject"; break
                    
                    record = {
                        "account": current_account,
                        "time": start_ts_str,
                        "health": f"{duration_secs}s",
                        "filename": filename,
                        "status": status,
                        "session_index": session_index
                    }
                    if 'record_meta' in locals() and record_meta:
                        record.update(record_meta)
                        del record_meta
                    
                    detailed_results.append(record)
                    # Always keep the LATEST record for each account in summary
                    summary_results[current_account] = record

        # Smarter Backfill for "Unknown"
        # 1. Try first account encountered in log
        first_real = found_accounts_ordered[0] if found_accounts_ordered else None
        
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
st.session_state.cfg_health_graph_type = config.get("health_graph_type", "Loading Duration")
st.session_state.cfg_health_view_mode = config.get("health_view_mode", "Full Loading History (All Events)")
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
    nav_options = ["Engine Settings", "Automation Settings", "Account Credentials", "Quota Full Phrases", "Account Health Analysis"]
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
                    chart_df["Seconds"] = chart_df["health"].str.replace("s", "").astype(float)
                    chart_df["variant"] = chart_df["session_index"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                    legend_labels = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                    legend_colors = ['#2ecc71', '#a0a0ff', '#f39c12', '#a0e6b5', '#d0d0ff', '#f9e79f']
                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                    chart_df["Duration"] = chart_df["Seconds"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('Event:Q', title="Event Sequence", scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                        y=alt.Y('Seconds:Q', title=None),
                        color=alt.Color('legend:N',
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors),
                                        legend=alt.Legend(title=None, orient='bottom')),
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
                        elif row["status"] == "Success":
                            d = row.copy()
                            # Priority: Use anchored RejectStat if available (handles session resets correctly)
                            if "true_rej" in d:
                                d["Rejects"] = d["true_rej"]
                                d["Resets"] = d["true_res"]
                                d["Duration"] = row_dur # RejectStat dur is already cumulative
                            else:
                                d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                d["Duration"] = curr_dur + row_dur
                            
                            d["Image"] = row["filename"].replace(".png", "")
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
                        agg_df["t_dur"] = agg_df["Duration"]
                        agg_df["t_rej"] = agg_df["Rejects"]
                        agg_df["t_res"] = agg_df["Resets"]
                        agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                        plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res'], value_vars=['Duration','Rejects','Resets'], var_name='Metric', value_name='Value')
                        main = alt.Chart(plot_df).mark_line(point=alt.OverlayMarkDef(opacity=0.8, size=40)).encode(
                            x=alt.X('Event:Q', title="Image Sequence", axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Value:Q', title=None),
                            color=alt.Color('Metric:N', scale=alt.Scale(
                                domain=['Duration','Rejects','Resets'],
                                range=['#2ecc71','#a0a0ff','#f39c12']),
                                legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3)),
                            tooltip=[
                                alt.Tooltip('Image:N', title='Artifact'),
                                alt.Tooltip('account:N', title='Account'),
                                alt.Tooltip('time:N', title='Time'),
                                alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                alt.Tooltip('t_rej:Q', title='Reject Count'),
                                alt.Tooltip('t_res:Q', title='Reset Count')
                            ]
                        )
                        st.altair_chart(alt.layer(bg_bands, main).resolve_scale(color='independent').properties(height=400).interactive(), width="stretch")
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
                        _chart_df["Seconds"] = _chart_df["health"].str.replace("s", "").astype(float)
                        _chart_df["cycle"] = _chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                        _chart_df["variant"] = _chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                        _ll = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                        _lr = ['#2ecc71', '#a0a0ff', '#f39c12', '#a0e6b5', '#d0d0ff', '#f9e79f']
                        _chart_df['legend'] = _chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                        _chart_df["Duration"] = _chart_df["Seconds"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                        _chart = alt.Chart(_chart_df).mark_bar().encode(
                            x=alt.X('Event:Q', title="Event Sequence", scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Seconds:Q', title=None),
                            color=alt.Color('legend:N', scale=alt.Scale(domain=_ll, range=_lr), legend=alt.Legend(title=None, orient='bottom')),
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
                            elif row["status"] == "Success":
                                d = row.copy()
                                # Priority: Use anchored RejectStat if available (handles session resets correctly)
                                if "true_rej" in d:
                                    d["Rejects"] = d["true_rej"]
                                    d["Resets"] = d["true_res"]
                                    d["Duration"] = row_dur # RejectStat dur is already cumulative
                                else:
                                    d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                    d["Duration"] = curr_dur + row_dur
                                d["Image"] = row["filename"].replace(".png", "")
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
                            agg_df["t_dur"] = agg_df["Duration"]
                            agg_df["t_rej"] = agg_df["Rejects"]
                            agg_df["t_res"] = agg_df["Resets"]
                            agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                            plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res'], value_vars=['Duration','Rejects','Resets'], var_name='Metric', value_name='Value')
                            main = alt.Chart(plot_df).mark_line(point=alt.OverlayMarkDef(opacity=0.8, size=40)).encode(
                                x=alt.X('Event:Q', title="Image Sequence", axis=alt.Axis(format='d', tickMinStep=1)),
                                y=alt.Y('Value:Q', title=None),
                                color=alt.Color('Metric:N', scale=alt.Scale(
                                    domain=['Duration','Rejects','Resets'],
                                    range=['#2ecc71','#a0a0ff','#f39c12']),
                                    legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3)),
                                tooltip=[
                                    alt.Tooltip('Image:N', title='Artifact'),
                                    alt.Tooltip('account:N', title='Account'),
                                    alt.Tooltip('time:N', title='Time'),
                                    alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                    alt.Tooltip('t_rej:Q', title='Reject Count'),
                                    alt.Tooltip('t_res:Q', title='Reset Count')
                                ]
                            )
                            st.altair_chart(alt.layer(bg_bands, main).resolve_scale(color='independent').properties(height=400).interactive(), width="stretch")
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
                    chart_df["Seconds"] = chart_df["health"].str.replace("s", "").astype(float)
                    chart_df["cycle"] = chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                    chart_df["variant"] = chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                    legend_labels = ['Success (Base)', 'Reject (Base)', 'Reset (Base)', 'Success (Light)', 'Reject (Light)', 'Reset (Light)']
                    legend_colors = ['#2ecc71', '#a0a0ff', '#f39c12', '#a0e6b5', '#d0d0ff', '#f9e79f']
                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                    chart_df["Duration"] = chart_df["Seconds"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('Event:Q', title="Event Sequence", scale=alt.Scale(nice=False), axis=alt.Axis(format='d', tickMinStep=1)),
                        y=alt.Y('Seconds:Q', title=None),
                        color=alt.Color('legend:N',
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors),
                                        legend=alt.Legend(title=None, orient='bottom')),
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
                        elif row["status"] == "Success":
                            d = row.copy()
                            # Priority: Use anchored RejectStat if available
                            if "true_rej" in d:
                                d["Rejects"] = d["true_rej"]
                                d["Resets"] = d["true_res"]
                                d["Duration"] = row_dur
                            else:
                                d["Rejects"] = curr_rej; d["Resets"] = curr_res
                                d["Duration"] = curr_dur + row_dur
                            
                            d["Image"] = row["filename"].replace(".png", "")
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
                        agg_df["t_dur"] = agg_df["Duration"]
                        agg_df["t_rej"] = agg_df["Rejects"]
                        agg_df["t_res"] = agg_df["Resets"]
                        agg_df["t_dur_fmt"] = agg_df["Duration"].apply(lambda x: f"{int(x // 60)}:{int(x % 60):02d}")
                        plot_df = agg_df.melt(id_vars=['Event','Display','Image','account','time','session_index','t_dur_fmt','t_rej','t_res'], value_vars=['Duration','Rejects','Resets'], var_name='Metric', value_name='Value')
                        main = alt.Chart(plot_df).mark_line(point=alt.OverlayMarkDef(opacity=0.8, size=40)).encode(
                            x=alt.X('Event:Q', title="Image Sequence", axis=alt.Axis(format='d', tickMinStep=1)),
                            y=alt.Y('Value:Q', title=None),
                            color=alt.Color('Metric:N', scale=alt.Scale(
                                domain=['Duration','Rejects','Resets'],
                                range=['#2ecc71','#a0a0ff','#f39c12']),
                                legend=alt.Legend(title=None, orient='bottom', symbolType='stroke', symbolStrokeWidth=3)),
                            tooltip=[
                                alt.Tooltip('Image:N', title='Artifact'),
                                alt.Tooltip('account:N', title='Account'),
                                alt.Tooltip('time:N', title='Time'),
                                alt.Tooltip('t_dur_fmt:N', title='Duration'),
                                alt.Tooltip('t_rej:Q', title='Reject Count'),
                                alt.Tooltip('t_res:Q', title='Reset Count')
                            ]
                        )
                        st.altair_chart((bg_bands + main).properties(height=400).interactive(), width="stretch")
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
            
            if st.session_state.cfg_health_view_mode not in options:
                st.session_state.cfg_health_view_mode = "Full Loading History (All Events)"

            view_mode = st.selectbox(
                "Select View Mode",
                options=options,
                key="cfg_health_view_mode",
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
            _, col_rad = st.columns([1.5, 1])
            with col_rad:
                st.radio("Graph Mode", ["Loading Duration", "Reject Rates"], horizontal=True, key="cfg_health_graph_type", on_change=on_change_health_graph, label_visibility="collapsed")

        _render_health_content(view_mode, login_data, st.session_state.get("cfg_health_graph_type", "Loading Duration"))
