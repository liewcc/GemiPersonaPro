import streamlit as st
import asyncio
from streamlit.runtime.scriptrunner import add_script_run_ctx
import sys
import subprocess
import time
from PIL import Image
import io
from api_client import EngineClient
from style_utils import apply_premium_style, render_dashboard_header
from lama_refiner import LaMaRefiner
from inverse_alpha_compositing import InverseAlphaCompositing
import torch
from datetime import datetime

import json
import os
import threading
import psutil
import pandas as pd

# Fix for Windows asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

CONFIG_PATH = "config.json"

def load_config():
    defaults = {
        "show_engine_console": True,
        "heartbeat_timeout": 3600,
        "headless": False,
        "browser_url": "https://gemini.google.com/app",
        "prompt": "",
        "selected_tool": "",
        "selected_model": "",
        "discovery": {
            "available_tools": [],
            "available_models": []
        },
        "automation": {
            "auto_looping": False,
            "mode": "rounds",
            "goal": 1,
            "remove_watermark": True
        }
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
                return defaults
        except:
            pass
    return defaults

def save_config(updates):
    cfg = load_config()
    cfg.update(updates)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)
    return cfg

# --- Page Config ---
st.set_page_config(page_title="GemiPersona | DASHBOARD", page_icon="sys_img/logo.png", layout="wide", initial_sidebar_state="expanded")
apply_premium_style()

# --- Hide Custom Dash Styling ---
st.markdown("""
    <style>
        .main { overflow: hidden !important; }
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar { width: 8px; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-track { background: transparent; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-thumb { background: rgba(160,160,255,0.2); border-radius: 10px; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-thumb:hover { background: rgba(160,160,255,0.4); }

        [data-testid="stSidebar"] {min-width: 250px;} 
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] [data-testid="stHorizontalBlock"] button {
            border: none !important;
            background-color: transparent !important;
            box-shadow: none !important;
            color: #444 !important;
            font-size: 1.4rem !important;
            padding: 0px !important;
            min-height: unset !important;
            height: auto !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] [data-testid="stHorizontalBlock"] button:hover {
            color: #0366d6 !important;
            background-color: transparent !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "config" not in st.session_state:
    st.session_state.config = load_config()
if "client" not in st.session_state:
    st.session_state.client = EngineClient()
if "service_proc" not in st.session_state:
    st.session_state.service_proc = None
if "logs" not in st.session_state:
    st.session_state.logs = []
if "heartbeat_thread" not in st.session_state:
    st.session_state.heartbeat_thread = None
if "is_busy" not in st.session_state:
    st.session_state.is_busy = False
if "last_status_msg" not in st.session_state:
    st.session_state.last_status_msg = ""
if "initial_login_checked" not in st.session_state:
    st.session_state.initial_login_checked = False

# --- Navigation & Widget Key Force Sync ---
if "dash_gal_page" not in st.session_state: st.session_state.dash_gal_page = 1

# Force sync widget keys with shared state on every full run
st.session_state.dash_gal_page_top_widget = st.session_state.dash_gal_page
st.session_state.dash_gal_page_bottom_widget = st.session_state.dash_gal_page
if "dash_gal_page_size" not in st.session_state: st.session_state.dash_gal_page_size = 8
if "dash_gal_check_processed" not in st.session_state: st.session_state.dash_gal_check_processed = False

config = st.session_state.config
auto_cfg = config.get("automation", {})
if "auto_looping" not in st.session_state:
    st.session_state.auto_looping = auto_cfg.get("auto_looping", False)
if "auto_mode" not in st.session_state:
    st.session_state.auto_mode = auto_cfg.get("mode", "rounds")
if "auto_goal" not in st.session_state:
    st.session_state.auto_goal = auto_cfg.get("goal", 1)
if "auto_remove_wm" not in st.session_state:
    st.session_state.auto_remove_wm = auto_cfg.get("remove_watermark", True)
if "last_known_auto_active" not in st.session_state:
    st.session_state.last_known_auto_active = False
if "auto_stop_requested" not in st.session_state:
    st.session_state.auto_stop_requested = False
if "needs_full_rerun" not in st.session_state:
    st.session_state.needs_full_rerun = False
if "selected_files" not in st.session_state:
    st.session_state.selected_files = config.get("selected_files", [])
if "name_start" not in st.session_state: 
    st.session_state.name_start = config.get("name_start", 1)
if "show_stop_confirmation" not in st.session_state:
    st.session_state.show_stop_confirmation = False
if "stop_confirmation_location" not in st.session_state:
    st.session_state.stop_confirmation_location = "main"
if "show_goal_reached_confirmation" not in st.session_state:
    st.session_state.show_goal_reached_confirmation = False

def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    if not msg.startswith("API>> ") and not msg.startswith("UI>> "):
        msg = f"UI>> {msg}"
    st.session_state.logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.logs) > 50:
        st.session_state.logs.pop(0)

# --- Heartbeat Loop ---
def heartbeat_worker(client):
    while True:
        try:
            asyncio.run(client.send_heartbeat())
        except:
            pass
        time.sleep(30)

REJECT_STAT_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reject_stat_log.json")
REJECT_STAT_LOG_PATH = os.path.normpath(REJECT_STAT_LOG_PATH)

def _format_dur_str(dur):
    dur = max(0.0, float(dur or 0))
    h = int(dur // 3600)
    m = int((dur % 3600) // 60)
    s = int(dur % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    elif m > 0:
        return f"{m}:{s:02d}"
    else:
        return f"{s}s"

@st.fragment(run_every=1)
def render_stats_body_fragment():
    # 1. Fetch live stats once
    stats = {}
    is_running = False
    try:
        stats = asyncio.run(st.session_state.client.get_automation_stats())
        if stats:
            st.session_state._last_known_stats = stats
        is_running = stats.get("is_running", False)
    except:
        # API timeout during heavy watermark processing blocks the event loop.
        # Fall back to UI state and last known stats to prevent the "Stopped" summary flashing.
        if st.session_state.get("ui_auto_looping_active", False):
            is_running = True
            stats = st.session_state.get("_last_known_stats", {})
        else:
            is_running = False

    # 2. Read log records
    records = []
    if os.path.exists(REJECT_STAT_LOG_PATH):
        try:
            with open(REJECT_STAT_LOG_PATH, "r", encoding="utf-8") as _f:
                records = json.load(_f)
        except: pass

    # 3. Handle live pending row and summary
    display_records = records
    cur_elapsed_sec = 0.0
    st_str = stats.get("start_time")
    if st_str:
        try:
            st_dt = datetime.strptime(st_str, "%Y-%m-%d %H:%M:%S")
            cur_elapsed_sec = (datetime.now() - st_dt).total_seconds()
        except: pass

    if is_running:
        total_api_refused = int(stats.get("refusals") or 0)
        total_api_resets = int(stats.get("resets") or 0)
        total_log_refused = sum(int(r.get("refused_count", 0)) for r in records)
        total_log_resets = sum(int(r.get("reset_count", 0)) for r in records)
        total_log_dur = sum(float(r.get("duration_sec", 0)) for r in records)
        
        p_refused = max(0, total_api_refused - total_log_refused)
        p_resets = max(0, total_api_resets - total_log_resets)

        # Use current_cycle_start exposed by the engine — mirrors the exact same reference
        import time
        cycle_start_ts = stats.get("current_cycle_start_ts")
        inter_cycle_ts = stats.get("inter_cycle_start_ts")
        filename_display = "Processing..."

        if cycle_start_ts:
            p_dur = max(0.0, time.time() - float(cycle_start_ts))
        elif inter_cycle_ts:
            p_dur = max(0.0, time.time() - float(inter_cycle_ts))
            filename_display = "Refining Image..."
        else:
            # Engine hasn't started the new cycle yet
            p_dur = 0.0
        
        pending_record = {
            "index": "⌛",
            "filename": filename_display,
            "duration_sec": p_dur,
            "refused_count": p_refused,
            "reset_count": p_resets
        }
        filtered_records = [r for r in records if r.get("filename") not in ["[Stopped/Interrupted]", "[Account Switched]"]]
        display_records = [pending_record] + list(reversed(filtered_records))
    else:
        # Stopped: Oldest first (Ascending) for the final summary view
        display_records = [r for r in records if r.get("filename") not in ["[Stopped/Interrupted]", "[Account Switched]"]]

    # 4. Render Layout
    if not display_records:
        st.info("No data yet. Start an automation session to collect statistics.")
        return

    if is_running:
        st.caption("🔄 Auto-refreshing counts every 1s...")
        
        # Compact Running Summary Section
        summary_html = f"""
        <div style="display:flex; justify-content:space-between; background:#f8f9fa; padding:10px; border-radius:6px; margin-bottom:15px; border:1px solid #e9ecef; font-size:0.9em;">
            <div><span style="color:#666;">Refused:</span> <b>{int(stats.get("refusals") or 0)}</b></div>
            <div><span style="color:#666;">Resets:</span> <b>{int(stats.get("resets") or 0)}</b></div>
            <div><span style="color:#666;">Elapsed:</span> <b>{_format_dur_str(cur_elapsed_sec)}</b></div>
        </div>
        """
        st.markdown(summary_html, unsafe_allow_html=True)

        real_img_count = sum(1 for r in records if r.get("filename") not in ["[Stopped/Interrupted]", "[Account Switched]"])
        st.markdown(f"**{real_img_count}** image(s) downloaded.")
        _render_reject_table(display_records)
    else:
        st.caption("🏁 Automation stopped. View final stats below.")
        total_images = sum(1 for r in records if r.get("filename") not in ["[Stopped/Interrupted]", "[Account Switched]"])
        total_dur = sum(r.get("duration_sec", 0) for r in records)
        avg_dur = total_dur / total_images if total_images else 0
        total_r = sum(int(r.get("refused_count", 0)) for r in records)
        total_rs = sum(int(r.get("reset_count", 0)) for r in records)

        # Compact Final Summary Section
        sum_top_html = f"""
        <div style="display:flex; justify-content:space-between; background:#f0f4f8; padding:10px; border-radius:6px; margin-bottom:8px; border:1px solid #d0d7de; font-size:0.9em;">
            <div><span style="color:#555;">Images:</span> <b>{total_images}</b></div>
            <div><span style="color:#555;">Total Time:</span> <b>{_format_dur_str(total_dur)}</b></div>
        </div>
        <div style="display:flex; justify-content:space-between; background:#fff; padding:10px; border-radius:6px; margin-bottom:15px; border:1px solid #e9ecef; font-size:0.9em;">
            <div><span style="color:#666;">Avg/Img:</span> <b>{_format_dur_str(avg_dur)}</b></div>
            <div><span style="color:#666;">Refused:</span> <b>{total_r}</b></div>
            <div><span style="color:#666;">Resets:</span> <b>{total_rs}</b></div>
        </div>
        """
        st.markdown("### Summary")
        st.markdown(sum_top_html, unsafe_allow_html=True)

        _render_reject_table(display_records)

@st.dialog("📊 Reject Rate Stats", width="small")
def show_reject_rate_stats():
    """Renders the stats with 1s auto-refresh if automation is running."""
    render_stats_body_fragment()

@st.dialog("Confirm Stop Automation")
def confirm_stop_automation_dash(location):
    st.write("Are you sure you want to stop the looping process?")
    col_y, col_n = st.columns(2)
    if col_y.button("Yes, Stop", type="primary", width="stretch", key=f"dash_yes_stop_{location}"):
        async def do_stop_auto():
            add_log("Stopping Automation Loop...")
            resp = await st.session_state.client.stop_automation()
            add_log(f"Auto Stop: {resp.get('message')}")
        asyncio.run(do_stop_auto())
        st.session_state.auto_stop_requested = True
        st.session_state.ui_auto_looping_active = False
        st.rerun()
    if col_n.button("Cancel", width="stretch", key=f"dash_no_stop_{location}"):
        st.rerun()

@st.dialog("⚠️ Cannot Continue")
def show_goal_reached_dialog(location):
    st.write("The previously configured goal has already been reached.")
    st.write("To continue, please increase the **Goal** in the settings, or click **Start Looping Process** to begin a fresh session.")
    if st.button("OK", width="stretch", key=f"gr_ok_{location}"):
        st.rerun()

@st.fragment(run_every=1)
def render_chart_body_fragment():
    st.markdown("### Performance Trends")
    
    # 1. Load historical records
    records = []
    if os.path.exists(REJECT_STAT_LOG_PATH):
        try:
            with open(REJECT_STAT_LOG_PATH, "r", encoding="utf-8") as _f:
                records = json.load(_f)
        except: pass
    
    # 2. Fetch live stats
    stats = {}
    is_running = False
    try:
        stats = asyncio.run(st.session_state.client.get_automation_stats())
        is_running = stats.get("is_running", False)
    except: pass

    # 3. Clean historical records
    clean_records = [r for r in records if r.get("filename") and r.get("filename") not in ["[Stopped/Interrupted]", "[Account Switched]"]]

    # 4. Append live 'Processing' data intelligently
    if is_running:
        total_api_refused = int(stats.get("refusals") or 0)
        total_api_resets = int(stats.get("resets") or 0)
        total_log_refused = sum(int(r.get("refused_count", 0)) for r in records)
        total_log_resets = sum(int(r.get("reset_count", 0)) for r in records)
        
        p_refused = max(0, total_api_refused - total_log_refused)
        p_resets = max(0, total_api_resets - total_log_resets)

        cycle_start_ts = stats.get("current_cycle_start_ts")
        inter_cycle_ts = stats.get("inter_cycle_start_ts")
        filename_display = "Processing..."
        
        import time
        now_ts = time.time()
        p_dur_live = 0.0
        
        if cycle_start_ts:
            p_dur_live = max(0.0, now_ts - float(cycle_start_ts))
        elif inter_cycle_ts:
            p_dur_live = max(0.0, now_ts - float(inter_cycle_ts))
            filename_display = "Refining Image..."
            
        current_cycle_id = cycle_start_ts or inter_cycle_ts or "unknown"
        state_key = "chart_pending_state"
        
        if state_key not in st.session_state:
            st.session_state[state_key] = {
                "cycle_id": current_cycle_id,
                "refused": p_refused,
                "resets": p_resets,
                "dur": p_dur_live,
                "last_seen_time": now_ts
            }
            
        prev_state = st.session_state[state_key]
        time_since_last_run = now_ts - prev_state.get("last_seen_time", now_ts)
        
        # Update frozen duration if: new cycle, stats changed, or dialog was just reopened (> 3s pause)
        if (prev_state["cycle_id"] != current_cycle_id or 
            prev_state["refused"] != p_refused or 
            prev_state["resets"] != p_resets or 
            time_since_last_run > 3.0):
            
            st.session_state[state_key] = {
                "cycle_id": current_cycle_id,
                "refused": p_refused,
                "resets": p_resets,
                "dur": p_dur_live,
                "last_seen_time": now_ts
            }
        else:
            # Still running smoothly, just update the heartbeat timestamp
            st.session_state[state_key]["last_seen_time"] = now_ts
            
        p_dur_frozen = st.session_state[state_key]["dur"]

        pending_record = {
            "filename": filename_display,
            "duration_sec": p_dur_frozen, 
            "refused_count": p_refused,
            "reset_count": p_resets
        }
        clean_records.append(pending_record)
    
    if not clean_records:
        st.info("No data yet. Start an automation session to collect statistics.")
        return

    # Prepare data for plotting
    df = pd.DataFrame(clean_records)
    
    # Ensure numeric types and convert Duration to minutes
    df["duration_min"] = pd.to_numeric(df["duration_sec"], errors='coerce').fillna(0) / 60.0
    df["refused_count"] = pd.to_numeric(df["refused_count"], errors='coerce').fillna(0)
    df["reset_count"] = pd.to_numeric(df["reset_count"], errors='coerce').fillna(0)
    
    # Rename for cleaner legend
    df = df.rename(columns={
        "duration_min": "Duration (m)",
        "refused_count": "Refused",
        "reset_count": "Resets"
    })
    
    # Use filename as index for the X-axis (strip .png extension for cleaner display)
    df["Filename"] = df["filename"].apply(lambda x: str(x).replace(".png", ""))
    df.set_index("Filename", inplace=True)
    
    import altair as alt
    
    # Format duration as mm:ss for tooltip display
    df["Duration (m:s)"] = df["duration_sec"].apply(lambda x: f"{int(x // 60):02d}:{int(x % 60):02d}")
    df_chart = df.reset_index()

    chart = alt.Chart(df_chart).transform_fold(
        ['Duration (m)', 'Refused', 'Resets'],
        as_=['Data', 'Value']
    ).mark_line(
        point=alt.OverlayMarkDef(opacity=0.01, size=250)
    ).encode(
        x=alt.X('Filename:N', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Value:Q', title=None),
        color=alt.Color('Data:N', 
            scale=alt.Scale(
                domain=['Duration (m)', 'Refused', 'Resets'],
                range=['#2196F3', '#28a745', '#FF9800']
            ),
            legend=alt.Legend(title=None, orient="bottom", symbolType="stroke", symbolOpacity=1, symbolStrokeWidth=3)),
        tooltip=[
            alt.Tooltip('Filename:N', title="Filename"),
            alt.Tooltip(r'Duration (m\:s):N', title="Duration"),
            alt.Tooltip('Refused:Q', title="Refused"),
            alt.Tooltip('Resets:Q', title="Resets")
        ]
    ).properties(
        height=350
    ).interactive()

    # CRITICAL FIX: We wrap the chart in a rigid Streamlit container.
    # This CSS lock prevents the dialog from collapsing during any split-second unmounts!
    with st.container(height=375, border=False):
        st.altair_chart(chart, width='stretch')


@st.dialog("📈 Reject Rate Chart", width="large")
def show_reject_rate_chart():
    """Displays a bar chart of the reject rate statistics."""
    render_chart_body_fragment()


LOOP_CTRL_DEFAULTS = {
    "infinite_loop_enabled": False, "infinite_loop_minutes": 60,
    "time_enabled": False, "time_minutes": 10, "time_action": "next_profile",
    "refused_enabled": False, "refused_threshold": 5, "refused_action": "next_profile",
    "reset_enabled": False, "reset_threshold": 3, "reset_action": "next_profile",
}

@st.dialog("⚙️ Loop Control Config", width="small")
def show_loop_control_dialog():
    """Dialog for configuring per-cycle threshold-based account switching."""
    cfg_now = load_config()
    lc = {**LOOP_CTRL_DEFAULTS, **cfg_now.get("automation", {}).get("loop_control", {})}

    ACTION_OPTIONS = ["next_profile", "re_login"]
    ACTION_LABELS  = {"next_profile": "Next Profile", "re_login": "Re-login (same account)"}

    # --- Infinite Table Loop ---
    inf_c1, inf_c2 = st.columns([5, 1])
    with inf_c1:
        inf_en = st.toggle("**♾️ Infinite Loop (with Cooldown)**", value=lc["infinite_loop_enabled"], key="lc_inf_en", 
                           help="If enabled, the automation will restart from the first account after processing all profiles in the list. This timer is in MINUTES.")
    with inf_c2:
        inf_min = st.number_input("Cooldown Minutes", min_value=1, max_value=1440,
                                  value=int(lc["infinite_loop_minutes"]), step=1,
                                  disabled=not inf_en, key="lc_inf_min",
                                  label_visibility="collapsed")
    st.markdown("<hr style='margin: 0px 0 15px 0;'/>", unsafe_allow_html=True)

    # --- Time ---
    lc_row1_c1, lc_row1_c2 = st.columns([5, 1])
    with lc_row1_c1:
        t_en = st.toggle("**⏱ Time Threshold**", value=lc["time_enabled"], key="lc_time_en",
                         help="If enabled, switches accounts or re-logins after the set duration (in MINUTES).")
    with lc_row1_c2:
        t_min = st.number_input("Cycle Minutes", min_value=1, max_value=600,
                                value=int(lc["time_minutes"]), step=1,
                                disabled=not t_en, key="lc_time_min",
                                label_visibility="collapsed")
    t_action = st.radio("Time action", options=ACTION_OPTIONS,
                        format_func=lambda x: ACTION_LABELS[x],
                        index=ACTION_OPTIONS.index(lc["time_action"]),
                        horizontal=True, disabled=not t_en,
                        key="lc_time_action", label_visibility="collapsed")
    st.markdown("<hr style='margin: 0px 0 15px 0;'/>", unsafe_allow_html=True)

    # --- Refused ---
    lc_row2_c1, lc_row2_c2 = st.columns([5, 1])
    with lc_row2_c1:
        r_en = st.toggle("**🚫 Refused Threshold**", value=lc["refused_enabled"], key="lc_ref_en",
                         help="Switch account after this many consecutive image refusals.")
    with lc_row2_c2:
        r_thr = st.number_input("Refused count", min_value=1, max_value=999,
                                value=int(lc["refused_threshold"]), step=1,
                                disabled=not r_en, key="lc_ref_thr",
                                label_visibility="collapsed")
    r_action = st.radio("Refused action", options=ACTION_OPTIONS,
                        format_func=lambda x: ACTION_LABELS[x],
                        index=ACTION_OPTIONS.index(lc["refused_action"]),
                        horizontal=True, disabled=not r_en,
                        key="lc_ref_action", label_visibility="collapsed")
    st.markdown("<hr style='margin: 0px 0 15px 0;'/>", unsafe_allow_html=True)

    # --- Reset ---
    lc_row3_c1, lc_row3_c2 = st.columns([5, 1])
    with lc_row3_c1:
        rs_en = st.toggle("**🔄 Reset Threshold**", value=lc["reset_enabled"], key="lc_rst_en",
                          help="Switch account after this many consecutive page resets.")
    with lc_row3_c2:
        rs_thr = st.number_input("Reset count", min_value=1, max_value=999,
                                 value=int(lc["reset_threshold"]), step=1,
                                 disabled=not rs_en, key="lc_rst_thr",
                                 label_visibility="collapsed")
    rs_action = st.radio("Reset action", options=ACTION_OPTIONS,
                         format_func=lambda x: ACTION_LABELS[x],
                         index=ACTION_OPTIONS.index(lc["reset_action"]),
                         horizontal=True, disabled=not rs_en,
                         key="lc_rst_action", label_visibility="collapsed")

    st.markdown("<hr style='margin: 0px 0 15px 0;'/>", unsafe_allow_html=True)
    if st.button("💾 Save", type="primary", width="stretch", key="lc_save"):
        new_lc = {
            "infinite_loop_enabled": inf_en,
            "infinite_loop_minutes": int(inf_min),
            "time_enabled":     t_en,
            "time_minutes":     int(t_min),
            "time_action":      t_action,
            "refused_enabled":  r_en,
            "refused_threshold": int(r_thr),
            "refused_action":   r_action,
            "reset_enabled":    rs_en,
            "reset_threshold":  int(rs_thr),
            "reset_action":     rs_action,
        }
        existing_auto = load_config().get("automation", {})
        existing_auto["loop_control"] = new_lc
        save_config({"automation": existing_auto})
        st.toast("Loop Control config saved.", icon="✅")
        st.rerun()

def _render_reject_table(records):
    rows_html = ""
    for r in records:
        idx = r.get("index", "-")
        fname = r.get("filename", "—")
        dur = r.get("duration_sec", 0)
        ref = int(r.get("refused_count", 0))
        rst = int(r.get("reset_count", 0))
        dur_str = _format_dur_str(dur)
        ref_color = "#28a745" if ref > 0 else "inherit"
        rst_color = "#e36209" if rst > 0 else "inherit"
        rows_html += f"<tr><td style='text-align:center;'>{idx}</td><td style='font-family:monospace;'>{fname}</td><td style='text-align:right;'>{dur_str}</td><td style='text-align:center; color:{ref_color}; font-weight:{'700' if ref > 0 else 'normal'};'>{ref}</td><td style='text-align:center; color:{rst_color}; font-weight:{'700' if rst > 0 else 'normal'};'>{rst}</td></tr>"
    
    table_html = f"""
    <style>
        .rrs-container {{ 
            max-height: 420px; 
            overflow-y: auto; 
            margin-bottom: 2px; 
        }}
        .rrs-table {{ 
            width:100%; 
            border-collapse:collapse; 
            font-size:0.88em; 
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; 
        }}
        .rrs-table th {{ 
            background:#f0f4f8; 
            padding:8px 12px; 
            text-align:left; 
            border-bottom:2px solid #d0d7de; 
            color:#444; 
            font-weight:600;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        .rrs-table td {{ padding:7px 12px; border-bottom:1px solid #e8eaed; background: white; }}
        .rrs-table tr:hover td {{ background:#f9fafb; }}
    </style>
    <div class="rrs-container">
        <table class='rrs-table'>
          <thead><tr><th style='text-align:center;width:50px'>#</th><th>Filename</th><th style='text-align:right;'>Duration</th><th style='text-align:center;'>Refused</th><th style='text-align:center;'>Resets</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
    </div>"""
    st.markdown(table_html, unsafe_allow_html=True)

if st.session_state.heartbeat_thread is None:
    st.session_state.heartbeat_thread = threading.Thread(target=heartbeat_worker, args=(st.session_state.client,), daemon=True)
    st.session_state.heartbeat_thread.start()

# --- Sync Engine Status ---
st.session_state.config = load_config()
config = st.session_state.config
health_data = asyncio.run(st.session_state.client.check_health())
st.session_state.health_data = health_data
service_active = health_data is not None
browser_active = health_data.get("engine_running", False) if service_active else False

# Initial Login Check (Auto-run once if browser is already ON)
if browser_active and not st.session_state.initial_login_checked:
    try:
        st.session_state.initial_login_checked = True
        login_resp = asyncio.run(st.session_state.client.get_account_info())
        st.session_state.login_status = login_resp
        add_log(f"Initial login check: {login_resp.get('status')} - {login_resp.get('account_id')}")
    except Exception as e:
        add_log(f"Initial setup check failed: {e}")

# Handle needs_full_rerun flag set by fragments (avoids calling st.rerun inside a fragment)
if st.session_state.needs_full_rerun:
    st.session_state.needs_full_rerun = False
    st.rerun()

# --- Top-Level Dialog Triggers (Decoupled from Fragments) ---
if st.session_state.show_stop_confirmation:
    st.session_state.show_stop_confirmation = False
    confirm_stop_automation_dash(st.session_state.stop_confirmation_location)

if st.session_state.show_goal_reached_confirmation:
    st.session_state.show_goal_reached_confirmation = False
    show_goal_reached_dialog(st.session_state.stop_confirmation_location)

try:
    auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
    is_auto_running = auto_stats.get("is_running", False)
except:
    auto_stats = {}
    is_auto_running = False

# --- Pagination Callbacks ---
def sync_all_pagination_states(new_page):
    st.session_state.dash_gal_page = new_page
    st.session_state.dash_gal_page_top_widget = new_page
    st.session_state.dash_gal_page_bottom_widget = new_page

def on_dash_page_change_top():
    sync_all_pagination_states(st.session_state.dash_gal_page_top_widget)

def on_dash_page_change_bot():
    sync_all_pagination_states(st.session_state.dash_gal_page_bottom_widget)

def on_dash_page_size_change():
    new_val = st.session_state.dash_gal_page_size_slider
    st.session_state.dash_gal_page_size = new_val
    sync_all_pagination_states(1)

def on_dash_gal_check_processed_change():
    st.session_state.dash_gal_check_processed = st.session_state.dash_gal_check_processed_toggle
    # NO LONGER resetting to page 1 to preserve viewing location

def render_gallery_nav(total_pages, key_suffix):
    col1, col2, col3, col4, col5 = st.columns([0.5, 0.5, 2, 0.5, 0.5])
    with col1:
        st.button("|◀", key=f"gal_first_{key_suffix}", width="stretch", 
                  disabled=total_pages <= 1 or st.session_state.dash_gal_page <= 1,
                  on_click=sync_all_pagination_states, args=(1,))
    with col2:
        st.button("◀", key=f"gal_prev_{key_suffix}", width="stretch", 
                  disabled=total_pages <= 1 or st.session_state.dash_gal_page <= 1,
                  on_click=sync_all_pagination_states, args=(st.session_state.dash_gal_page - 1,))
    with col3:
        st.number_input(
            f"Page (of {total_pages})",
            min_value=1,
            max_value=max(1, total_pages),
            key=f"dash_gal_page_{key_suffix}_widget",
            on_change=on_dash_page_change_top if key_suffix == "top" else on_dash_page_change_bot,
            label_visibility="collapsed",
            disabled=total_pages <= 1
        )
    with col4:
        st.button("▶", key=f"gal_next_{key_suffix}", width="stretch", 
                  disabled=total_pages <= 1 or st.session_state.dash_gal_page >= total_pages,
                  on_click=sync_all_pagination_states, args=(st.session_state.dash_gal_page + 1,))
    with col5:
        st.button("▶|", key=f"gal_last_{key_suffix}", width="stretch", 
                  disabled=total_pages <= 1 or st.session_state.dash_gal_page >= total_pages,
                  on_click=sync_all_pagination_states, args=(total_pages,))

# --- Notifier Button Fragment (Global-Level per Fragment Stability Protocol) ---
@st.fragment(run_every="2s")
def render_notifier_button():
    import psutil
    is_notif_running = False
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = p.info.get('cmdline')
            if cmdline and 'image_notifier.py' in ' '.join(cmdline):
                is_notif_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if is_notif_running:
        if st.button("🔔 Stop Notifier", width="stretch", key="btn_stop_notifier"):
            for p in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmdline = p.info.get('cmdline')
                    if cmdline and 'image_notifier.py' in ' '.join(cmdline):
                        p.terminate()
                except:
                    pass
            st.rerun()
    else:
        if st.button("🔕 Start Notifier", width="stretch", key="btn_start_notifier"):
            vbs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "start_notifier.vbs")
            if os.path.exists(vbs):
                os.startfile(vbs)
            time.sleep(1)
            st.rerun()

# --- Looping Control Button Fragment (Global-Level per Fragment Stability Protocol) ---
# Defined at module level so st.rerun() inside is fragment-scoped (not full-app),
# preventing Fragment ID invalidation races with other run_every fragments.
@st.fragment(run_every="3s")
def render_looping_button(location="sidebar"):
    # Recompute all needed state inside the fragment to be self-contained
    try:
        _auto_status = asyncio.run(st.session_state.client.get_automation_stats())
        _is_active = _auto_status.get("is_running", False)
    except:
        _is_active = False
    try:
        _h = asyncio.run(st.session_state.client.check_health())
        _browser_active = _h.get("engine_running", False) if _h else False
    except:
        _browser_active = False

    _is_busy = st.session_state.get("is_busy", False)
    _auto_enabled = st.session_state.get("auto_looping", False)
    _stop_req = st.session_state.get("auto_stop_requested", False)

    if "ui_auto_looping_active" not in st.session_state:
        st.session_state.ui_auto_looping_active = False
    if _is_active:
        st.session_state.ui_auto_looping_active = True
    elif _browser_active:
        st.session_state.ui_auto_looping_active = False

    _ui_is_active = _is_active or (st.session_state.ui_auto_looping_active and not _browser_active)
    if not _ui_is_active:
        st.session_state.auto_stop_requested = False
        _stop_req = False

    _show_as_inactive = not _ui_is_active or _stop_req

    history_records = []
    if os.path.exists(REJECT_STAT_LOG_PATH):
        try:
            with open(REJECT_STAT_LOG_PATH, "r", encoding="utf-8") as _f:
                history_records = json.load(_f)
        except: pass
    
    clean_history = [r for r in history_records if r.get("filename") and r.get("filename") != "[Stopped/Interrupted]"]
    history_count = len(clean_history)
    
    is_goal_reached = False
    if st.session_state.auto_mode == "rounds" and history_count >= st.session_state.auto_goal:
        is_goal_reached = True
    elif st.session_state.auto_mode == "images" and history_count >= st.session_state.auto_goal:
        is_goal_reached = True

    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if _show_as_inactive:
            _start_disabled = not _browser_active or _is_busy or not _auto_enabled or _stop_req
            if st.button("▶️ Start Looping Process", key=f"start_loop_{location}", width="stretch", type="primary", disabled=_start_disabled):
                current_config = load_config()
                current_config["selected_files"] = st.session_state.selected_files
                current_config["remove_watermark"] = st.session_state.auto_remove_wm

                def trigger_automation():
                    async def do_start_auto():
                        add_log("API>> Triggering Automation Start...")
                        try:
                            resp = await st.session_state.client.start_automation(
                                mode=st.session_state.auto_mode,
                                goal=st.session_state.auto_goal,
                                config=current_config
                            )
                            add_log(f"API>> Start Result: {resp.get('message')}")
                        except Exception as e:
                            add_log(f"API ERROR: {e}")
                    asyncio.run(do_start_auto())

                t = threading.Thread(target=trigger_automation, daemon=True)
                add_script_run_ctx(t)
                t.start()
                st.session_state.ui_auto_looping_active = True
                st.session_state.auto_stop_requested = False
                st.rerun()
        else:
            if st.button("⏹️ Stop Looping Process", key=f"stop_loop_{location}", width="stretch"):
                st.session_state.show_stop_confirmation = True
                st.session_state.stop_confirmation_location = location
                st.rerun()

    with btn_col2:
        _continue_disabled = not _show_as_inactive or history_count == 0 or not _browser_active or _is_busy or not _auto_enabled or _stop_req
        if st.button("⏯️ Continue Session", key=f"continue_loop_{location}", width="stretch", disabled=_continue_disabled):
            if is_goal_reached:
                st.session_state.show_goal_reached_confirmation = True
                st.session_state.stop_confirmation_location = location
                st.rerun()
            else:
                current_config = load_config()
                current_config["selected_files"] = st.session_state.selected_files
                current_config["remove_watermark"] = st.session_state.auto_remove_wm

                def trigger_continue():
                    async def do_continue_auto():
                        add_log("API>> Triggering Automation Continue...")
                        try:
                            resp = await st.session_state.client.continue_automation(
                                mode=st.session_state.auto_mode,
                                goal=st.session_state.auto_goal,
                                config=current_config
                            )
                            add_log(f"API>> Continue Result: {resp.get('message')}")
                        except Exception as e:
                            add_log(f"API ERROR: {e}")
                    asyncio.run(do_continue_auto())

                t = threading.Thread(target=trigger_continue, daemon=True)
                add_script_run_ctx(t)
                t.start()
                st.session_state.ui_auto_looping_active = True
                st.session_state.auto_stop_requested = False
                st.rerun()

# --- UI Layout ---
with st.sidebar:
    with st.container(border=True):
        save_dir = config.get("save_dir", "")
        target_dir = save_dir
        if st.session_state.dash_gal_check_processed:
            proc_dir = os.path.join(save_dir, "processed")
            if os.path.isdir(proc_dir): target_dir = proc_dir
        
        try:
            files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            total_files = len(files)
            p_size = st.session_state.dash_gal_page_size
            total_pages = max(1, (total_files + p_size - 1) // p_size)
        except:
            total_pages = 1
            
        render_gallery_nav(total_pages, "top")
        
        st.slider("Images per page", 4, 32, 
                  value=st.session_state.dash_gal_page_size, 
                  step=4,
                  key="dash_gal_page_size_slider",
                  on_change=on_dash_page_size_change)
            
        processed_dir = os.path.join(save_dir, "processed") if save_dir else ""
        has_processed = os.path.isdir(processed_dir) if processed_dir else False
        st.toggle("Show AI-Cleaned Images", 
                  value=st.session_state.dash_gal_check_processed, 
                  disabled=not has_processed,
                  key="dash_gal_check_processed_toggle",
                  on_change=on_dash_gal_check_processed_change)

    with st.container(border=True):
        # Determine automation status for disabling logic
        auto_status_data = asyncio.run(st.session_state.client.get_automation_stats())
        is_auto_active = auto_status_data.get("is_running", False)
        
        # Lock toggles if running or stop requested
        toggles_disabled = is_auto_active or st.session_state.auto_stop_requested

        remove_wm = st.toggle("Remove Watermark", value=st.session_state.auto_remove_wm, disabled=toggles_disabled)
        auto_enabled = st.toggle("Auto Looping", value=st.session_state.auto_looping, disabled=toggles_disabled)

        if not toggles_disabled and (auto_enabled != st.session_state.auto_looping or remove_wm != st.session_state.auto_remove_wm):
            st.session_state.auto_looping = auto_enabled
            st.session_state.auto_remove_wm = remove_wm
            save_config({
                "automation": {
                    "auto_looping": auto_enabled, 
                    "mode": st.session_state.auto_mode, 
                    "goal": st.session_state.auto_goal,
                    "remove_watermark": remove_wm
                }
            })

        # Inputs are disabled if:
        # 1. Auto Looping toggle is OFF
        # 2. Automation is already running
        # 3. Stop was requested
        inputs_disabled = not auto_enabled or is_auto_active or st.session_state.auto_stop_requested

        a_col1, a_col2 = st.columns([2, 1])
        with a_col1:
            mode_options = {"rounds": "Fixed Rounds", "images": "Target Images"}
            new_mode = st.radio("Stop Condition", options=list(mode_options.keys()), 
                                format_func=lambda x: mode_options[x],
                                index=list(mode_options.keys()).index(st.session_state.auto_mode),
                                horizontal=True, label_visibility="collapsed",
                                disabled=inputs_disabled)
        with a_col2:
            goal_label = "Rounds" if new_mode == "rounds" else "Images"
            new_goal = st.number_input(goal_label, min_value=1, value=st.session_state.auto_goal, 
                                       label_visibility="collapsed", 
                                       disabled=inputs_disabled)
        
        if not inputs_disabled and (new_mode != st.session_state.auto_mode or new_goal != st.session_state.auto_goal):
            st.session_state.auto_mode = new_mode
            st.session_state.auto_goal = new_goal
            save_config({"automation": {"auto_looping": True, "mode": new_mode, "goal": new_goal}})



        # Loop Control Config button (shown below Start/Stop, always visible)
        if st.button("⚙️ Loop Control Config", width="stretch",
                     key="btn_loop_ctrl_cfg",
                     help="Configure threshold-based auto account switching"):
            show_loop_control_dialog()

        render_notifier_button()

def get_status_bar_html(label, msg, color):
    return f"""
        <div style='background: #f9fafb; padding: 0 15px; height: 40px; display: flex; align-items: center; border-radius: 8px; border: 1px solid #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 0.9em; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 15px;'>
            <span style='color: {color}; margin-right: 12px; font-weight: 700; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.6px;'>{label}:</span> 
            <span style='font-weight: 500;'>{msg}</span>
        </div>
    """

@st.fragment(run_every="10s")
def render_dash_account_status():
    """Account + browser status bar for the Dashboard main panel."""
    active = False
    display_account = None
    is_logged_in = False
    result = st.session_state.get("login_status")
    cached_account = None

    try:
        h_data = asyncio.run(st.session_state.client.check_health())
        active = h_data.get("engine_running", False) if h_data else False
        stats = asyncio.run(st.session_state.client.get_automation_stats())
        cached_account = stats.get("current_account_id")

        if cached_account:
            is_logged_in = True
            display_account = cached_account
        elif result and result.get("logged_in"):
            is_logged_in = True
            display_account = result.get("account_id", "Unknown")
    except Exception:
        active = False

    status_color = "#28a745" if active else "#d73a49"
    status_text = "ONLINE" if active else "OFFLINE"
    
    if not active:
        account_html = "<span style='color: #6a737d;'>Not Ready</span>"
    elif result is None and not cached_account:
        account_html = "<span style='color: #6a737d;'>Scanning...</span>"
    elif is_logged_in:
        account_html = f"<span style='color: #0366d6; font-weight: 600;'>{display_account}</span>"
    else:
        account_html = "<span style='color: #d73a49; font-weight: 600;'>GUEST / NOT LOGGED IN</span>"

    bg_color = "#ffffff" if active else "#f6f8fa"
    st.markdown(f"""
    <div style='background: {bg_color}; padding: 0 15px; height: 40px; display: flex; align-items: center; border-radius: 8px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 0.9em; border: 1px solid #ddd; color: #24292e; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 15px;'>
        <div style='flex: 1; display: flex; align-items: center; justify-content: space-between;'>
            <div><b style='color: {status_color};'>●</b> <b>BROWSER:</b> {status_text}</div>
            <div style='text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-left: 10px;'><b>Account:</b> {account_html}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

@st.fragment(run_every="5s")
def render_automation_stats():
    _trigger_rerun = False
    c, s, r, rs = 0, 0, 0, 0
    status_badge, bg_color = "<b style='color: #6b7280;'>○ STANDBY</b>", "#f6f8fa"

    try:
        stats = asyncio.run(st.session_state.client.get_automation_stats())
        if stats:
            is_active = stats.get("is_running", False)
            if st.session_state.get("last_known_auto_active", False) and not is_active:
                st.session_state.last_known_auto_active = False
                _trigger_rerun = True
            else:
                st.session_state.last_known_auto_active = is_active
            
            c, s, r, rs = stats.get("cycles", 0), stats.get("successes", 0), stats.get("refusals", 0), stats.get("resets", 0)
            
            if st.session_state.get("ui_auto_looping_active"):
                # Use real health data to detect switching
                h_data = asyncio.run(st.session_state.client.check_health())
                if h_data and not h_data.get("engine_running", False):
                    status_badge, bg_color = "<b style='color: #f39c12;'>● SWITCHING</b>", "#fff7e6"
                else:
                    status_badge, bg_color = "<b style='color: #d73a49;'>● RUNNING</b>", "#ffffff"
            elif c > 0:
                status_badge, bg_color = "<b style='color: #6a737d;'>○ IDLE / FINISHED</b>", "#f6f8fa"
    except Exception:
        status_badge, bg_color = "<b style='color: #d73a49;'>● OFFLINE</b>", "#fff5f5"

    st.markdown(f"""
    <div style='background: {bg_color}; padding: 0 15px; height: 40px; display: flex; align-items: center; border-radius: 8px; font-family: monospace; font-size: 0.9em; border: 1px solid #ddd; color: #1e1e1e; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 15px;'>
        <div>{status_badge} | Cycles: <b>{c}</b> | Images: <b>{s}</b> | Refused: <b>{r}</b> | Resets: <b>{rs}</b></div>
    </div>
    """, unsafe_allow_html=True)

    if _trigger_rerun:
        st.session_state.needs_full_rerun = True

@st.fragment(run_every="2s")
def render_live_status_bar():
    try:
        auto_stats = asyncio.run(st.session_state.client.get_automation_stats())
        is_active = auto_stats.get("is_running", False)
    except: is_active = False
    if not is_active:
        st.markdown(get_status_bar_html("SYSTEM", "Standby - Ready to start automation", "#6b7280"), unsafe_allow_html=True)
        return
    try:
        logs_resp = asyncio.run(st.session_state.client.get_engine_logs())
        new_logs = logs_resp.get("logs", [])
        if new_logs:
            for l in new_logs: st.session_state.logs.append(l)
            if len(st.session_state.logs) > 50: st.session_state.logs = st.session_state.logs[-50:]
    except: pass
    if st.session_state.logs:
        latest_log = st.session_state.logs[-1]
        status_msg = latest_log.split("] ", 1)[-1] if "] " in latest_log else latest_log
        st.markdown(get_status_bar_html("LIVE ENTRY", status_msg, "#059669"), unsafe_allow_html=True)
    else:
        st.markdown(get_status_bar_html("LIVE ENTRY", "Waiting for logs...", "#059669"), unsafe_allow_html=True)

# Top status bar row
col_account_status, col_auto_stats = st.columns(2)
with col_account_status:
    render_dash_account_status()
with col_auto_stats:
    render_automation_stats()

# Second row: live entry
render_live_status_bar()

# Put the buttons in columns
col_view, col_loop_btn, col_btn, col_chart = st.columns([1, 2, 1, 1])
with col_view:
    if st.button("📂 View Download Folder", width='stretch', help="Open the save directory in File Explorer"):
        save_dir = st.session_state.config.get("save_dir", "")
        if save_dir and os.path.isdir(save_dir):
            os.startfile(save_dir)
        else:
            st.warning("Folder not set.")
with col_loop_btn:
    render_looping_button("main")
with col_btn:
    if st.button("📊 Reject Rate Stats", width='stretch', help="View per-image download stats"):
        show_reject_rate_stats()
with col_chart:
    if st.button("📈 Stats Chart", width='stretch', help="Visualize performance trends"):
        show_reject_rate_chart()

def save_with_metadata(p_img, original_img, output_path_or_buf, original_stats=None):
    from PIL import PngImagePlugin
    save_params = {}
    if original_img.format == "PNG":
        meta = PngImagePlugin.PngInfo()
        for k, v in original_img.info.items():
            if isinstance(k, str) and k != "exif": meta.add_text(k, str(v))
        save_params["pnginfo"] = meta
    exif = original_img.info.get('exif')
    if not exif: exif = original_img.getexif().tobytes()
    if exif: save_params["exif"] = exif
    save_params["info"] = original_img.info.copy()
    if isinstance(output_path_or_buf, str):
        p_img.save(output_path_or_buf, **save_params)
        if original_stats:
            os.utime(output_path_or_buf, (original_stats.st_atime, original_stats.st_mtime))
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.windll.kernel32
                FILE_WRITE_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 0x0100, 3, 0x02000000
                def to_filetime(dt):
                    val = int((dt + 11644473600) * 10000000)
                    return wintypes.FILETIME(val & 0xFFFFFFFF, val >> 32)
                ft_creation, ft_access, ft_write = to_filetime(original_stats.st_ctime), to_filetime(original_stats.st_atime), to_filetime(original_stats.st_mtime)
                handle = kernel32.CreateFileW(output_path_or_buf, FILE_WRITE_ATTRIBUTES, 0, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, 0)
                if handle != -1:
                    kernel32.SetFileTime(handle, ctypes.byref(ft_creation), ctypes.byref(ft_access), ctypes.byref(ft_write))
                    kernel32.CloseHandle(handle)
    else: p_img.save(output_path_or_buf, format="PNG", **save_params)

import shared_state
def get_remover(): return shared_state.get_shared_remover()
def get_refiner(): return shared_state.get_shared_refiner()

@st.dialog("⚠️ Model Busy")
def show_model_busy_warning_dialog():
    st.warning("Manual edit is currently unavailable. Stop automation first.")
    if st.button("Understood", width='stretch', type="primary"): st.rerun()

@st.dialog("\u200b", width="large")
def manual_watermark_removal_dialog(file_path):
    if "manual_removal_preview_id" not in st.session_state: st.session_state.manual_removal_preview_id = 0
    if "manual_removal_preview" not in st.session_state: st.session_state.manual_removal_preview = {"hash": None, "img": None}
    filename = os.path.basename(file_path)
    save_dir = st.session_state.config.get("save_dir", "")
    processed_dir = os.path.join(save_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    try: from streamlit_drawable_canvas import st_canvas
    except: st.error("Missing library."); return
    try: 
        original_img = Image.open(file_path)
    except: st.error("Failed to load image."); return

    # --- Exhaustive Monkeypatch for Streamlit Compatibility ---
    try:
        import streamlit.elements.image as st_image
        if not hasattr(st_image, 'image_to_url'):
            found_func = None
            for path in ["streamlit.runtime.image_util", "streamlit.elements.image_utils", "streamlit.elements.lib.image_utils"]:
                try:
                    mod = __import__(path, fromlist=['image_to_url'])
                    if hasattr(mod, 'image_to_url'): found_func = mod.image_to_url; break
                except ImportError: continue
            if found_func:
                def compatible_image_to_url(data, width=-1, height=-1, *args, **kwargs):
                    if isinstance(width, int):
                        class FakeLayout:
                            def __init__(self, w, h): self.width, self.height = w, h
                        import hashlib
                        image_id = hashlib.md5(str(id(data)).encode()).hexdigest()
                        return found_func(data, FakeLayout(width, height), image_id, *args, **kwargs)
                    return found_func(data, width, height, *args, **kwargs)
                st_image.image_to_url = compatible_image_to_url
                try:
                    import streamlit.elements.lib.image_utils as lib_utils
                    lib_utils.image_to_url = compatible_image_to_url
                except ImportError: pass
    except Exception as e: pass

    brush_size = st.slider("Brush Size", 5, 100, 25)
    

    w, h = original_img.size
    max_w = 600
    scale = min(1.0, max_w / w)
    canvas_w, canvas_h = int(w * scale), int(h * scale)
    
    col_left, col_right = st.columns(2)
    with col_left:
        st.write("**Canvas (Mask Drawing)**")
        canvas_result = st_canvas(fill_color="rgba(255, 165, 0, 0.3)", stroke_width=brush_size, stroke_color="#FFFFFF", background_image=original_img, height=canvas_h, width=canvas_w, drawing_mode="freedraw", update_streamlit=True, key=f"m_c_{filename}_{st.session_state.manual_removal_preview_id}")
    with col_right:
        st.write("**AI Refined Result**")
        if canvas_result.image_data is not None:
            import numpy as np
            import hashlib
            mask_data = canvas_result.image_data[:, :, 3]
            mask_data = np.where(mask_data > 10, 255, 0).astype(np.uint8)
            mask_img = Image.fromarray(mask_data).resize(original_img.size, Image.NEAREST)
            has_paint = np.any(mask_data > 0)
            
            if has_paint:
                mask_hash = hashlib.md5(mask_data.tobytes()).hexdigest()
                if st.session_state.manual_removal_preview["hash"] != mask_hash:
                    with st.spinner("AI is thinking..."):
                        manual_refiner = get_refiner()
                        st.session_state.manual_removal_preview["img"] = manual_refiner(original_img, mask_img)
                        st.session_state.manual_removal_preview["hash"] = mask_hash
                
                result_img = st.session_state.manual_removal_preview["img"]
                st.image(result_img, width="stretch")
                
                if st.button("💾 Save", width='stretch', type="primary"):
                    save_with_metadata(result_img, original_img, os.path.join(processed_dir, filename), original_stats=os.stat(file_path))
                    st.success("Saved!")
                    st.session_state.manual_removal_preview = {"hash": None, "img": None}
                    st.session_state.manual_removal_preview_id += 1
                    time.sleep(1); st.rerun()
            else:
                st.info("Start drawing to see the AI result.")

@st.dialog("Image Metadata")
def show_dash_metadata(img_path):
    from PIL.ExifTags import TAGS
    try:
        with Image.open(img_path) as img:
            png_info, exif_data = img.info, img._getexif()
            if png_info:
                # Format all metadata textual info as individual copyable blocks
                for k, v in png_info.items():
                    if k.lower() == 'dpi': continue # Skip DPI if it exists and we don't want it, though we can print all. Let's just print all.
                    val = str(v).replace('\\n', '\n')
                    icon = "✨"
                    if k.lower() in ("prompt", "parameters", "description"):
                        icon = "📝"
                    elif k.lower() == "url":
                        icon = "🔗"
                    elif k.lower() in ("path", "save_path"):
                        icon = "📂"
                    
                    # Special display for specific keys if needed, otherwise default to Title Case
                    title = k.upper() if k.lower() == "url" else k.replace('_', ' ').title()
                    
                    st.markdown(f"**{icon} {title}**")
                    st.code(val, language="text", wrap_lines=True)
            if exif_data:
                st.markdown("**📸 Technical Metadata**")
                st.json({TAGS.get(k, k): str(v) for k, v in exif_data.items()})
    except Exception as e:
        st.error(f"Failed to read metadata: {e}")

@st.fragment(run_every="5s")
def render_image_gallery():
    save_dir = st.session_state.config.get("save_dir", "")
    if not save_dir or not os.path.isdir(save_dir): st.warning("Configure Save Directory."); return
    target_dir = os.path.join(save_dir, "processed") if st.session_state.dash_gal_check_processed else save_dir
    try:
        files = sorted([f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))], key=lambda x: os.path.getmtime(os.path.join(target_dir, x)), reverse=True)
    except: return
    if not files: st.info("No images found."); return
    p_size = st.session_state.dash_gal_page_size
    total_pages = max(1, (len(files) + p_size - 1) // p_size)
    if st.session_state.dash_gal_page > total_pages: st.session_state.dash_gal_page = total_pages
    page_files = files[(st.session_state.dash_gal_page-1)*p_size : min(st.session_state.dash_gal_page*p_size, len(files))]
    
    cols_per_row = 4
    for i in range(0, len(page_files), cols_per_row):
        cols = st.columns(cols_per_row)
        for idx, filename in enumerate(page_files[i:i+cols_per_row]):
            with cols[idx]:
                with st.container(border=True):
                    file_path = os.path.join(target_dir, filename)
                    try:
                        st.image(file_path, width="stretch")
                    except Exception:
                        st.caption("⏳ Loading...")
                    st.caption(filename)
                    bt_c1, bt_c2, bt_c3, bt_c4 = st.columns(4)
                    with bt_c1:
                        if st.button("👁️", key=f"v_{filename}", help="View image in default viewer"): os.startfile(file_path)
                    with bt_c2:
                        if st.button("📄", key=f"i_{filename}", help="View image metadata"): show_dash_metadata(file_path)
                    with bt_c3:
                        wm_help = "Manual Watermark Removal" if st.session_state.dash_gal_check_processed else "Enable 'Show AI-Cleaned Images' in the side panel to use this feature"
                        if st.button("🪄", key=f"w_{filename}", help=wm_help, disabled=not st.session_state.dash_gal_check_processed):
                            if is_auto_running and st.session_state.auto_remove_wm: show_model_busy_warning_dialog()
                            else: manual_watermark_removal_dialog(os.path.join(save_dir, filename) if os.path.exists(os.path.join(save_dir, filename)) else file_path)
                    with bt_c4:
                        if st.button("🗑️", key=f"d_{filename}", help="Delete image and generated files"):
                            for p in [os.path.join(save_dir, filename), os.path.join(save_dir, "processed", filename)]:
                                if os.path.exists(p): os.remove(p)
                            st.toast(f"Removed {filename}"); time.sleep(0.5); st.rerun()

# --- Main Gallery Call ---
render_image_gallery()