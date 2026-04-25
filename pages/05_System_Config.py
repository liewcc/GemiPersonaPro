import streamlit as st
import json
import os
import sys
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

# --- Main Logic ---
config = load_config()
login_data = load_login_lookup()

st.session_state.cfg_show_console = config.get("show_engine_console", True)
st.session_state.cfg_headless = config.get("headless", False)
st.session_state.cfg_timeout = int(config.get("heartbeat_timeout", 3600))
st.session_state.cfg_watchdog_delay = int(config.get("watchdog_initial_delay", 20))
st.session_state.cfg_quota_cooldown_hrs = int(config.get("quota_cooldown_hours", 24))
st.session_state.cfg_quota_cooldown_min = config.get("quota_cooldown_minutes", 0)

if st.session_state.get("current_page") != "System_Config":
    st.session_state.current_page = "System_Config"
    for k in ["pm_sys_initialized", "pm_df_work_sys", "pm_rerender_idx_sys"]:
        if k in st.session_state: del st.session_state[k]
    for k in list(st.session_state.keys()):
        if k.startswith("pm_editor_sys_"): del st.session_state[k]

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
    nav_options = ["Engine Settings", "Automation Settings", "Quota Full Phrases", "Account Credentials"]
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
