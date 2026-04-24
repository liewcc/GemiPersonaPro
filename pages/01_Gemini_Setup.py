import streamlit as st
import asyncio
from streamlit.runtime.scriptrunner import add_script_run_ctx
import sys
import subprocess
import time
from api_client import EngineClient
from style_utils import apply_premium_style, render_dashboard_header

import json
import os
import threading
import psutil
import tkinter as tk
from tkinter import filedialog
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk

# Fix for Windows asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

CONFIG_PATH = "config.json"
BOOKMARKS_PATH = "Gems_bookmark.json"

def get_bookmark_title(url):
    """Returns the title of a URL if it exists in Gems_bookmark.json."""
    if not os.path.exists(BOOKMARKS_PATH):
        return None
    try:
        with open(BOOKMARKS_PATH, "r", encoding="utf-8") as f:
            bookmarks = json.load(f)
            for b in bookmarks:
                if b.get("url") == url:
                    return b.get("name")
    except:
        pass
    return None

def load_config():
    return load_cfg_disk()

def save_config(updates):
    return save_cfg_disk(updates)

def select_multiple_files():
    """Opens a native Windows file picker for multiple files."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', True)
    paths = filedialog.askopenfilenames(
        title="Select Images",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp")]
    )
    root.destroy()
    return list(paths)

# --- Page Config ---
st.set_page_config(page_title="GemiPersona | HOME", page_icon="sys_img/logo.png", layout="wide")
apply_premium_style()

def apply_layout_fix():
    st.markdown("""
        <style>
        .main { overflow: hidden !important; }
        .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar { width: 8px; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-track { background: transparent; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-thumb { background: rgba(160,160,255,0.2); border-radius: 10px; }
        [data-testid="stVerticalBlock"]::-webkit-scrollbar-thumb:hover { background: rgba(160,160,255,0.4); }
        </style>
    """, unsafe_allow_html=True)

apply_layout_fix()


# --- Initialize Session State & Sync with Disk ---
if "config" not in st.session_state:
    st.session_state.config = load_config()
if "client" not in st.session_state:
    st.session_state.client = EngineClient()
if "service_proc" not in st.session_state:
    st.session_state.service_proc = None
if "last_screenshot" not in st.session_state:
    st.session_state.last_screenshot = None
if "logs" not in st.session_state:
    st.session_state.logs = []
if "heartbeat_thread" not in st.session_state:
    st.session_state.heartbeat_thread = None
if "login_status" not in st.session_state:
    st.session_state.login_status = None
if "selected_files" not in st.session_state:
    st.session_state.selected_files = st.session_state.config.get("selected_files", [])
if "initial_login_checked" not in st.session_state:
    st.session_state.initial_login_checked = False
if "show_stop_confirmation_setup" not in st.session_state:
    st.session_state.show_stop_confirmation_setup = False
if "show_goal_reached_confirmation_setup" not in st.session_state:
    st.session_state.show_goal_reached_confirmation_setup = False
if "last_saved_paths" not in st.session_state:
    st.session_state.last_saved_paths = []
if "is_busy" not in st.session_state:
    st.session_state.is_busy = False
if "widget_rerender_key" not in st.session_state:
    st.session_state.widget_rerender_key = 0
if "needs_rerun" not in st.session_state:
    st.session_state.needs_rerun = False
if "last_known_auto_active" not in st.session_state:
    st.session_state.last_known_auto_active = False
if "headless_toggle" not in st.session_state:
    st.session_state.headless_toggle = st.session_state.config.get("headless", False)

# Automation Settings Init
auto_cfg = st.session_state.config.get("automation", {})
if "auto_looping" not in st.session_state:
    st.session_state.auto_looping = auto_cfg.get("auto_looping", False)
if "auto_mode" not in st.session_state:
    st.session_state.auto_mode = auto_cfg.get("mode", "rounds")
if "auto_goal" not in st.session_state:
    st.session_state.auto_goal = auto_cfg.get("goal", 1)
if "auto_remove_wm" not in st.session_state:
    st.session_state.auto_remove_wm = auto_cfg.get("remove_watermark", True)
if "use_gpu" not in st.session_state:
    st.session_state.use_gpu = auto_cfg.get("use_gpu", True)
if "auto_stop_requested" not in st.session_state:
    st.session_state.auto_stop_requested = False

# --- Unified Top-level Sync logic ---
config = load_config()
auto_cfg = config.get("automation", {})
current_auto_looping = auto_cfg.get("auto_looping", False)

# 1. Sync simple values & Entry Detection (Self-Sufficient)
# If the major widget keys are missing, we consider this an "Entry" run and refresh from disk.
is_entry_run = ("url_bar_widget" not in st.session_state or "prompt_input_widget" not in st.session_state)

if st.session_state.get("_load_from_config") or is_entry_run:
    config = load_config() # Refresh the config object from disk
    st.session_state["url_bar"] = config.get("browser_url", "https://gemini.google.com/app")
    st.session_state["prompt_input"] = config.get("prompt", "")
    
    # Also sync tool and model selectboxes on entry
    discovery = config.get("discovery", {})
    avail_models = discovery.get("available_models", [])
    avail_tools = discovery.get("available_tools", [])
    st.session_state["selected_model"] = config.get("selected_model", "")
    st.session_state["selected_tool"] = config.get("selected_tool", "")
    
    # Populate widget keys immediately for the first render
    st.session_state["url_bar_widget"] = st.session_state["url_bar"]
    st.session_state["prompt_input_widget"] = st.session_state["prompt_input"]
    
    if st.session_state["selected_model"] in avail_models:
        st.session_state["model_selectbox"] = st.session_state["selected_model"]
    if st.session_state["selected_tool"] in avail_tools:
        st.session_state["tool_selectbox"] = st.session_state["selected_tool"]

    # Also sync automation state immediately on entry to avoid lag
    st.session_state.auto_looping = config.get("automation", {}).get("auto_looping", False)
    st.session_state._load_from_config = False

# Unconditional widget wiping removed to fix racing conditions
# The widget keys now correctly retain frontend user input natively through Streamlit.

# 2. Sync naming settings (detect external changes)
if "save_dir" not in st.session_state:
    st.session_state.save_dir = config.get("save_dir", os.path.join(os.getcwd(), "gemini_outputs"))
    st.session_state.name_prefix = config.get("name_prefix", "")
    st.session_state.name_padding = config.get("name_padding", 2)
    st.session_state.name_start = config.get("name_start", 1)

# Detect if Start No. changed on disk (e.g. from System Config or Automation)
disk_start_no = config.get("name_start", st.session_state.name_start)
if disk_start_no != st.session_state.name_start:
    st.session_state.name_start = disk_start_no
    st.session_state.widget_rerender_key += 1

# 3. Handle 'needs_rerun' flag from background threads
if st.session_state.needs_rerun:
    st.session_state.needs_rerun = False
    st.rerun()

def on_headless_change():
    """Write headless setting immediately on toggle change."""
    st.session_state.config = save_config({"headless": st.session_state.headless_toggle})

def on_naming_change():
    k = st.session_state.widget_rerender_key
    updates = {}
    
    val_dir = st.session_state.get(f"save_dir_widget_{k}")
    if val_dir is not None and val_dir != st.session_state.save_dir:
        st.session_state.save_dir = val_dir
        updates["save_dir"] = val_dir
        
    val_prefix = st.session_state.get(f"name_prefix_widget_{k}")
    if val_prefix is not None and val_prefix != st.session_state.name_prefix:
        st.session_state.name_prefix = val_prefix
        updates["name_prefix"] = val_prefix
        
    val_padding = st.session_state.get(f"name_padding_widget_{k}")
    if val_padding is not None and val_padding != st.session_state.name_padding:
        st.session_state.name_padding = val_padding
        updates["name_padding"] = val_padding

    val_start = st.session_state.get(f"name_start_widget_{k}")
    if val_start is not None and val_start != st.session_state.name_start:
        st.session_state.name_start = val_start
        updates["name_start"] = val_start
        
    if updates:
        st.session_state.config = save_config(updates)

def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    if not msg.startswith("API>> ") and not msg.startswith("UI>> "):
        msg = f"UI>> {msg}"
    st.session_state.logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.logs) > 50:
        st.session_state.logs.pop(0)

def select_folder():
    """Opens a native Windows folder picker."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', True)
    path = filedialog.askdirectory()
    root.destroy()
    return path

# --- Heartbeat Loop ---
def heartbeat_worker(client):
    while True:
        try:
            asyncio.run(client.send_heartbeat())
        except:
            pass
        time.sleep(30) # Ping every 30 seconds

if st.session_state.heartbeat_thread is None:
    st.session_state.heartbeat_thread = threading.Thread(target=heartbeat_worker, args=(st.session_state.client,), daemon=True)
    st.session_state.heartbeat_thread.start()

# --- Real-time Status & Fragment ---
@st.fragment(run_every="5s")
def render_sidebar_status():
    # Update health data in fragment (non-blocking for rest of UI)
    h_data = asyncio.run(st.session_state.client.check_health())
    
    # Detect state changes to trigger full UI rerun (syncs buttons)
    prev_s = st.session_state.health_data is not None
    curr_s = h_data is not None
    prev_b = st.session_state.health_data.get("engine_running", False) if prev_s else False
    curr_b = h_data.get("engine_running", False) if curr_s else False

    st.session_state.health_data = h_data
    # NOTE: We do NOT trigger a full-app rerun here.
    # The sidebar already unconditionally fetches fresh health_data on every full rerun,
    # so button labels are always up-to-date after any user interaction.
    # Triggering rerun from this fragment caused 'fragment id does not exist' errors
    # during page navigation.

    def get_mem(pid):
        try:
            p = psutil.Process(pid)
            return f"{p.memory_info().rss / (1024*1024):.1f}MB"
        except: return "N/A"

    s_p = h_data.get("service_pid") if curr_s else None
    b_ps = h_data.get("browser_pids", []) if curr_b else []

    msg = f"[ SYSTEM UI ]\n >> PID: {os.getpid()} | MEM: {get_mem(os.getpid())}\n\n"
    msg += f"[ ENGINE SERVICE ]\n >> PID: {s_p if curr_s else 'OFFLINE'} | MEM: {get_mem(s_p) if s_p else 'N/A'}\n\n"
    msg += f"[ BROWSER PROCESSES ]\n"
    if b_ps:
        for pid in b_ps:
            msg += f" >> PID: {pid} | MEM: {get_mem(pid)}\n"
    else:
        msg += " >> STATUS: OFFLINE"
    
    st.code(msg, language="text")

# --- Service Lifecycle Manager ---
async def ensure_service_running():
    health = await st.session_state.client.check_health()
    if not health:
        cfg = load_config()
        show_console = cfg.get("show_engine_console", True)
        
        # Start service script as a background process
        python_exe = sys.executable
        flags = 0
        if sys.platform == 'win32':
            flags = subprocess.CREATE_NEW_CONSOLE if show_console else subprocess.CREATE_NO_WINDOW
            
        st.session_state.service_proc = subprocess.Popen(
            [python_exe, "engine_service.py"],
            creationflags=flags
        )
        # Give it a moment to boot
        time.sleep(2)
        add_log(f"Engine launched (Console: {show_console}).")
        return True
    return True

# --- UI Layout ---
with st.sidebar:
    # Always fetch fresh health data on every rerun to keep all button states in sync.
    # (Conditional caching caused stale labels after Engine/Browser Start/Stop actions.)
    st.session_state.health_data = asyncio.run(st.session_state.client.check_health())
    health_data = st.session_state.health_data
    service_active = health_data is not None
    browser_active = health_data.get("engine_running", False) if service_active else False
    
    service_pid = health_data.get("service_pid") if service_active else None
    browser_pid = health_data.get("browser_pid") if browser_active else None

    # Initial Login Check (Auto-run once if browser is already ON)
    if browser_active and not st.session_state.initial_login_checked:
        try:
            # Run in a background thread or just perform it once
            st.session_state.initial_login_checked = True
            login_resp = asyncio.run(st.session_state.client.get_account_info())
            st.session_state.login_status = login_resp
            add_log(f"Initial login check: {login_resp.get('status')} - {login_resp.get('account_id')}")
            
            # Also auto-fetch Gem Title if we are on a custom gem page
            cfg = load_config()
            startup_url = cfg.get("browser_url", "")
            if "gemini.google.com/gem/" in startup_url:
                t_resp = asyncio.run(st.session_state.client.get_gem_title())
                if t_resp.get("status") == "success":
                    st.session_state.gem_title_result = t_resp.get("title")
                    add_log(f"Auto-fetched Gem Title: {st.session_state.gem_title_result}")
        except Exception as e:
            add_log(f"Initial setup check failed: {e}")

    st.toggle(
        "Headless Mode",
        key="headless_toggle",
        on_change=on_headless_change,
        help="Toggle headless mode. Takes effect on next browser start."
    )

    auto_active = st.session_state.get("auto_looping", False)

    if st.button("Start Engine" if not service_active else "Stop Engine", width="stretch"):
        if not service_active:
            asyncio.run(ensure_service_running())
        else:
            # Graceful shutdown: Stop browser first if active
            if browser_active:
                add_log("Closing browser gracefully...")
                asyncio.run(st.session_state.client.stop_engine())
                time.sleep(1.0) # Small buffer for file locks to release
                
            # Stop the service
            if sys.platform == 'win32' and service_pid:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(service_pid)], capture_output=True)
                    add_log(f"Engine service (PID {service_pid}) terminated.")
                except Exception as e:
                    add_log(f"Error terminating engine: {e}")
            else:
                if st.session_state.service_proc:
                    st.session_state.service_proc.terminate()
                    add_log("Engine process terminated via handle.")
                else:
                    add_log("Stop requested but no PID/handle found.")
            st.session_state.service_proc = None
        st.rerun()
    
    async def toggle_browser():
        if not browser_active:
            add_log("Opening browser...")
            cfg = load_config()
            # 1. Determine target URL: prioritize UI state, fallback to config
            current_ui_url = st.session_state.get("url_bar", "").strip()
            config_url = cfg.get("browser_url", "").strip()
            
            target_url = current_ui_url if current_ui_url else config_url
            if not target_url:
                target_url = "https://gemini.google.com/app"
            
            # 2. Persist this URL before starting to ensure logic cycle is closed
            cfg = save_config({"browser_url": target_url})
            st.session_state["url_bar"] = target_url # Ensure UI state is updated too
            
            # 3. Start & Navigate
            h_val = cfg.get("headless", True)
            await st.session_state.client.start_engine(headless=h_val)
            add_log(f"Browser opened (Headless: {h_val}).")
            add_log(f"Navigating to {target_url}...")
            await st.session_state.client.navigate(target_url)
            
            # Auto-Discover tools/models after initial load if it's Gemini
            if "gemini.google.com" in current_ui_url:
                add_log("Refreshing available tools and models...")
                await st.session_state.client.discover_capabilities()
                
                # Auto-check login status
                add_log("Checking login status...")
                try:
                    login_resp = await st.session_state.client.get_account_info()
                    st.session_state.login_status = login_resp
                    add_log(f"Auto login check: {login_resp.get('status')} - {login_resp.get('account_id')}")
                except Exception as e:
                    add_log(f"Auto login check failed: {e}")
        else:
            add_log(f"Closing browser (PID {browser_pid})...")
            await st.session_state.client.stop_engine()
            add_log("Browser closed.")

    if st.button("Start Browser" if not browser_active else "Stop Browser", width="stretch", disabled=not service_active):
        if not browser_active:
            # Guard: close any lingering registration browser before starting the main one
            asyncio.run(st.session_state.client.stop_registration())
        asyncio.run(toggle_browser())
        st.rerun()

    # Browser Screen Capture
    cfg = load_config()
    is_headless = cfg.get("headless", True)
    capture_disabled = not (browser_active and is_headless)
    if st.button("📸 Browser Screen Capture", width="stretch", disabled=capture_disabled):
        async def do_shot():
            shot_resp = await st.session_state.client.get_snapshot()
            st.session_state.last_screenshot = shot_resp.get("screenshot_path")
            add_log("Screen captured.")
        asyncio.run(do_shot())
        st.rerun()

    if st.session_state.last_screenshot and os.path.exists(st.session_state.last_screenshot):
        if st.button("👁️ View Last Capture", width="stretch"):
            abs_path = os.path.abspath(st.session_state.last_screenshot)
            try:
                os.startfile(abs_path)
            except Exception as e:
                add_log(f"Error opening viewer: {e}")
    


    render_sidebar_status()

# --- Top Browser Status Bar ---
@st.fragment(run_every="10s")
def render_setup_account_status():
    """Account + browser status bar for the Setup main panel."""
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
def render_setup_automation_stats():
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
            
            # Check for switching status via health data
            h_data = asyncio.run(st.session_state.client.check_health())
            engine_on = h_data.get("engine_running", False) if h_data else False
            
            if is_active:
                if not engine_on:
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
        st.session_state.needs_rerun = True


# Top status bar row
col_account_status, col_auto_stats = st.columns(2)
with col_account_status:
    render_setup_account_status()
with col_auto_stats:
    render_setup_automation_stats()

@st.dialog("⚠️ Cannot Continue")
def show_goal_reached_dialog_setup():
    st.write("The previously configured goal has already been reached.")
    st.write("To continue, please increase the **Goal** in the settings, or click **Start Looping Process** to begin a fresh session.")
    if st.button("OK", width="stretch", key="gr_ok_setup"):
        st.rerun()

@st.dialog("Confirm Stop Automation")
def confirm_stop_automation():
    st.write("Are you sure you want to stop the looping process?")
    col_y, col_n = st.columns(2)
    if col_y.button("Yes, Stop", type="primary", width="stretch"):
        async def do_stop_auto():
            add_log("Stopping Automation Loop...")
            resp = await st.session_state.client.stop_automation()
            add_log(f"Auto Stop: {resp.get('message')}")
        asyncio.run(do_stop_auto())
        st.session_state.auto_stop_requested = True
        st.rerun()
    if col_n.button("Cancel", width="stretch"):
        st.rerun()

@st.dialog("⚠️ Confirm Session Reset")
def confirm_start_automation_setup():
    st.write("Are you sure you want to start a new looping process? This will reset your current session statistics.")
    col_y, col_n = st.columns(2)
    if col_y.button("OK", type="primary", width="stretch"):
        current_config = load_config()
        current_config["selected_files"] = st.session_state.selected_files
        current_config["prompt"] = st.session_state.get("prompt_input_widget", current_config.get("prompt", ""))
        current_config["selected_tool"] = st.session_state.get("tool_selectbox")
        current_config["selected_model"] = st.session_state.get("model_selectbox")
        current_config.setdefault("automation", {})["remove_watermark"] = st.session_state.auto_remove_wm
        
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
        time.sleep(0.5)
        st.session_state.show_start_confirmation_setup = False
        st.rerun()
    if col_n.button("Cancel", width="stretch"):
        st.session_state.show_start_confirmation_setup = False
        st.rerun()

@st.dialog("Dynamic prompt prefix", width="large")
def show_prompt_prefix_dialog():
    st.markdown("""
        <style>
            div[data-testid="stDialog"] div[role="dialog"] {
                max-width: 700px !important;
            }
        </style>
    """, unsafe_allow_html=True)
    import pandas as pd
    
    pm_enabled = config.get("prompt_matrix", {}).get("enabled", False)
    
    pm_config = config.get("prompt_matrix", {})
    pm_items = pm_config.get("items", [
        {"ratio": "16:9 (Landscape)", "target": 5, "current": 0},
        {"ratio": "9:16 (Portrait)", "target": 5, "current": 0},
        {"ratio": "1:1 (Square)", "target": 5, "current": 0},
        {"ratio": "4:3 (Landscape)", "target": 5, "current": 0},
        {"ratio": "3:4 (Portrait)", "target": 5, "current": 0},
        {"ratio": "21:9 (Ultrawide)", "target": 5, "current": 0},
        {"ratio": "3:2 (Landscape)", "target": 5, "current": 0},
        {"ratio": "2:3 (Portrait)", "target": 5, "current": 0}
    ])
    
    active_idx = -1
    if pm_enabled:
        for i, it in enumerate(pm_items):
            if it.get("current", 0) < it.get("target", 1):
                active_idx = i
                break

    pm_data = []
    for i, it in enumerate(pm_items):
        is_active = (i == active_idx)
        pm_data.append({
            "ratio": it.get("ratio", ""),
            "target": int(it.get("target", 0)),
            "current": int(it.get("current", 0)),
            "status": "▶ Executing" if is_active else ("✔ Done" if it.get("current", 0) >= it.get("target", 1) else "Pending")
        })
        
    pm_df = pd.DataFrame(pm_data)
    
    is_auto_running = False
    try:
        import requests
        r = requests.get("http://localhost:8000/health", timeout=1)
        is_auto_running = r.json().get("automation_running", False)
    except:
        pass

    edited_pm_df = st.data_editor(
        pm_df,
        column_config={
            "ratio": st.column_config.SelectboxColumn("Aspect Ratio", options=["16:9 (Landscape)", "9:16 (Portrait)", "1:1 (Square)", "4:3 (Landscape)", "3:4 (Portrait)", "21:9 (Ultrawide)", "3:2 (Landscape)", "2:3 (Portrait)", "None (Master Prompt)"], required=True, width="medium"),
            "target": st.column_config.NumberColumn("Repeat", min_value=1, step=1, required=True, width="small"),
            "current": st.column_config.NumberColumn("Count", disabled=True, width="small"),
            "status": st.column_config.TextColumn("Status", disabled=True, width="small")
        },
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        disabled=is_auto_running,
        key="pm_editor_setup"
    )
    
    btn_disabled = is_auto_running and pm_enabled
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save Setting", icon="💾", use_container_width=True, disabled=btn_disabled, key="pm_save_setup"):
            new_items = []
            for r in edited_pm_df.to_dict("records"):
                new_items.append({
                    "ratio": r.get("ratio") or "None (Master Prompt)",
                    "target": int(r.get("target") or 1),
                    "current": int(r.get("current") or 0)
                })
            
            cfg = load_config()
            if "prompt_matrix" not in cfg: cfg["prompt_matrix"] = {}
            cfg["prompt_matrix"]["items"] = new_items
            save_config({"prompt_matrix": cfg["prompt_matrix"]})
            st.success("Setting saved!")
            time.sleep(0.5)
            st.rerun()
    with c2:
        if st.button("Reset Progress", icon="🔄", use_container_width=True, disabled=btn_disabled, key="pm_reset_setup"):
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
            st.success("Progress reset!")
            time.sleep(0.5)
            st.rerun()

@st.fragment(run_every="5s")
def render_setup_logs():
    # If a background thread (Submit/Redo) finished and set needs_rerun, pick it up here.
    # NOTE: this flag is set by threads, not by fragments. Fragments handle their own rerun
    # via _trigger_rerun below, which fires OUTSIDE the try/except block.
    _trigger_rerun = False
    try:
        # 1. Get Automation Status to check for completion or progress
        auto_status = asyncio.run(st.session_state.client.get_automation_stats())
        is_running_now = auto_status.get("is_running", False)
        
        # Check for Start No. updates while running OR on finish
        current_conf = load_config()
        disk_start_no = current_conf.get("name_start", st.session_state.name_start)
        
        if disk_start_no != st.session_state.name_start:
            st.session_state.name_start = disk_start_no
            st.session_state.widget_rerender_key += 1
            st.session_state.needs_rerun = True

        # If it was running in our local state but now it's stopped, trigger full sync.
        # Use a flag — the actual rerun must happen OUTSIDE this try/except block,
        # because RerunException inherits from Exception and would be swallowed here.
        if st.session_state.get("last_known_auto_active", False) and not is_running_now:
            st.session_state.last_known_auto_active = False
            _trigger_rerun = True
        else:
            st.session_state.last_known_auto_active = is_running_now

        # 2. Get Logs
        logs_resp = asyncio.run(st.session_state.client.get_engine_logs())
        new_logs = logs_resp.get("logs", [])
        if new_logs:
            for l in new_logs:
                st.session_state.logs.append(l)
            # Keep only last 50
            if len(st.session_state.logs) > 50:
                st.session_state.logs = st.session_state.logs[-50:]
    except Exception:
        pass
    
    if not st.session_state.logs:
        st.caption("Waiting for logs...")
    else:
        log_text = "\n".join([log for log in reversed(st.session_state.logs)])
        st.code(log_text, language="text")

    # Fire rerun AFTER try/except and AFTER rendering, so RerunException is not swallowed.
    # Optimization: only rerun if state macro-changed (active -> inactive).
    if _trigger_rerun:
        st.rerun()

# --- Top-Level Dialog Triggers (Decoupled from layout) ---
if st.session_state.get("show_stop_confirmation_setup"):
    st.session_state.show_stop_confirmation_setup = False
    confirm_stop_automation()

if st.session_state.get("show_start_confirmation_setup"):
    st.session_state.show_start_confirmation_setup = False
    confirm_start_automation_setup()

if st.session_state.get("show_goal_reached_confirmation_setup"):
    st.session_state.show_goal_reached_confirmation_setup = False
    show_goal_reached_dialog_setup()

# Always reload config on each rerun to pick up discovery updates
config = load_config()

col1, col2 = st.columns([2, 1])

# Adjust these two values independently to fit your screen
LEFT_HEIGHT = 770   # Left panel (main controls) — increase/decrease as needed
RIGHT_HEIGHT = 770   # Right panel (live logs)    — increase/decrease as needed

with col1:
    with st.container(border=True, height=LEFT_HEIGHT):
        # --- Account Actions Section ---
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>ACCOUNT ACTIONS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            h_data = st.session_state.get("health_data")
            b_active = h_data.get("engine_running", False) if h_data else False

            # --- Row 1: Check Login | Add Profile ---
            r1_col1, r1_col2 = st.columns(2)
            with r1_col1:
                if st.button("🔍 Check Login Status", width="stretch", disabled=not b_active):
                    with st.spinner("Checking login status..."):
                        try:
                            result = asyncio.run(st.session_state.client.get_account_info())
                            st.session_state.login_status = result
                            add_log(f"Login check: {result.get('status')} - {result.get('account_id')}")
                        except Exception as e:
                            st.session_state.login_status = {"error": str(e)}
                            add_log(f"Login check failed: {e}")
            with r1_col2:
                if st.button(
                    "📋 Add Profile",
                    width="stretch",
                    disabled=b_active or not service_active,
                    help="Requires Engine to be STARTED and Browser to be STOPPED. Opens a headed browser window bypassing the sandbox so new Google accounts you sign into are saved permanently. Close the browser window when done, then add the new account in the 'User Login Credentials' under the System Config page."
                ):
                    with st.spinner("Opening registration browser..."):
                        try:
                            resp = asyncio.run(st.session_state.client.start_registration_mode())
                            add_log(f"Registration browser: {resp.get('message', resp)}")
                        except Exception as e:
                            add_log(f"Add Profile failed: {e}")
                    st.rerun()

            # --- Row 2: Switch Previous | Switch Next ---
            r2_col1, r2_col2 = st.columns(2)
            with r2_col1:
                if st.button("⏮️ Switch to Previous Profile", width="stretch", disabled=not b_active):
                    with st.spinner("Switching..."):
                        try:
                            result = asyncio.run(st.session_state.client.switch_profile_previous())
                            add_log(f"Profile switch (prev): {result.get('message')}")
                            st.session_state.login_status = result.get("account_info", {})
                            st.rerun()
                        except Exception as e:
                            st.error(f"Switch failed: {e}")
                            add_log(f"Switch prev failed: {e}")
            with r2_col2:
                if st.button("👤 Switch to Next Profile", width="stretch", disabled=not b_active):
                    with st.spinner("Switching..."):
                        try:
                            result = asyncio.run(st.session_state.client.switch_profile())
                            add_log(f"Profile switch (next): {result.get('message')}")
                            st.session_state.login_status = result.get("account_info", {})
                            st.rerun()
                        except Exception as e:
                            st.error(f"Switch failed: {e}")
                            add_log(f"Switch next failed: {e}")

            # --- Row 3: Profile Dropdown | Switch Profile ---
            # Load usernames from user_login_lookup.json for the dropdown
            _lookup_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_login_lookup.json")
            _profile_users = []
            try:
                if os.path.exists(_lookup_path):
                    with open(_lookup_path, "r", encoding="utf-8") as _f:
                        _profile_users = [u.get("username", "") for u in json.load(_f) if u.get("username")]
            except Exception:
                pass

            r3_col1, r3_col2 = st.columns([3, 1])
            with r3_col1:
                selected_profile = st.selectbox(
                    "Target Profile",
                    options=_profile_users,
                    label_visibility="collapsed",
                    key="direct_profile_select"
                )
            with r3_col2:
                clicked_switch = st.button("Switch Profile", width="stretch", disabled=not b_active or not selected_profile)

            if clicked_switch:
                _, spin_col, _ = st.columns([1.5, 1, 1.5])
                with spin_col:
                    with st.spinner(""):
                        try:
                            result = asyncio.run(st.session_state.client.switch_to_profile(selected_profile))
                            add_log(f"Profile switch (direct): {result.get('message')}")
                            st.session_state.login_status = result.get("account_info", {})
                        except Exception as e:
                            st.error(f"Switch failed: {e}")
                            add_log(f"Switch direct failed: {e}")
                st.rerun()

        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

        # --- Browser URL Section ---
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>BROWSER URL</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.text_input(
                "URL Input",
                key="url_bar_widget",
                label_visibility="collapsed"
            )
            # The widget automatically updates st.session_state["url_bar_widget"].
            # We sync it to our clean "url_bar" key.
            st.session_state["url_bar"] = st.session_state["url_bar_widget"]
            
            # Determine display title
            live_title = st.session_state.get("gem_title_result")
            bookmark_title = get_bookmark_title(st.session_state.get("url_bar", ""))
            
            if live_title:
                st.caption(f"**Extracted Title:** {live_title}")
            elif bookmark_title:
                st.caption(f"**Extracted Title:** {bookmark_title}")
            else:
                st.caption("**Extracted Title:** Press \"Send to Browser\" to check.")
            
            u_col1, u_col2, u_col3 = st.columns(3)
            with u_col1:
                if st.button("Load", key="url_load", width="stretch"):
                    st.session_state._load_from_config = True
                    st.session_state.gem_title_result = None
                    st.rerun()
            with u_col2:
                if st.button("Save", key="url_save", width="stretch"):
                    st.session_state["url_bar"] = st.session_state["url_bar_widget"]
                    st.session_state.config = save_config({"browser_url": st.session_state["url_bar_widget"]})
                    add_log("URL saved to config.")
            with u_col3:
                if st.button("Send to Browser", key="url_send", width="stretch", disabled=not browser_active or auto_active):
                    st.session_state.config = save_config({"browser_url": st.session_state["url_bar_widget"]})
                    async def do_nav():
                        target_url = st.session_state["url_bar_widget"]
                        add_log(f"Reloading to {target_url}...")
                        resp = await st.session_state.client.navigate(target_url)
                        add_log(f"Navigation status: {resp}")
                        
                        
                        if "gemini.google.com" in target_url:
                            add_log("Refreshing available tools and models...")
                            await st.session_state.client.discover_capabilities()
                            
                            if "gemini.google.com/gem/" in target_url:
                                add_log("Extracting Gem profile title...")
                                try:
                                    t_resp = await st.session_state.client.get_gem_title()
                                    if t_resp.get("status") == "success":
                                        st.session_state.gem_title_result = t_resp.get("title")
                                        add_log(f"Gem Title: {st.session_state.gem_title_result}")
                                except Exception as e:
                                    add_log(f"Gem Title pull failed: {e}")
                        else:
                            st.session_state.gem_title_result = None
                        
                        c = load_config()
                        if c.get("headless", True):
                            shot_resp = await st.session_state.client.get_snapshot()
                            st.session_state.last_screenshot = shot_resp.get("screenshot_path")
                    asyncio.run(do_nav())
                    st.rerun()

        # Pre-fetch status for UI locking
        is_auto_running = False
        try:
            import requests
            r = requests.get("http://localhost:8000/health", timeout=1)
            is_auto_running = r.json().get("automation_running", False)
        except:
            pass

        # --- Aspect Ratio Setting Section ---
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>ASPECT RATIO SETTING</p>", unsafe_allow_html=True)
        with st.container(border=True):
            # Load current state from config
            cfg_pm = config.get("prompt_matrix", {})
            pm_enabled = cfg_pm.get("enabled", False)
            
            mode_opts = ["Fixed Aspect Ratio", "Dynamic Prefix Loop"]
            # Sync radio index with config
            radio_idx = 1 if pm_enabled else 0
            
            ar_col1, ar_col2, ar_col3 = st.columns([1.8, 1.2, 1.2])
            with ar_col1:
                ar_mode = st.radio(
                    "Aspect Ratio Mode", 
                    options=mode_opts, 
                    index=radio_idx,
                    horizontal=True, 
                    label_visibility="collapsed",
                    key="setup_ar_mode_radio"
                )
            
            # If mode changed, update config and rerun
            if (ar_mode == "Dynamic Prefix Loop") != pm_enabled:
                cfg_pm["enabled"] = (ar_mode == "Dynamic Prefix Loop")
                if cfg_pm["enabled"]:
                    for it in cfg_pm.get("items", []): it["current"] = 0
                save_config({"prompt_matrix": cfg_pm})
                st.rerun()

            with ar_col2:
                # Fixed ratio dropdown - always visible
                ratio_list = ["16:9 (Landscape)", "9:16 (Portrait)", "1:1 (Square)", "4:3 (Landscape)", "3:4 (Portrait)", "21:9 (Ultrawide)", "3:2 (Landscape)", "2:3 (Portrait)", "None"]
                saved_fixed = config.get("fixed_aspect_ratio", "16:9 (Landscape)")
                try: f_idx = ratio_list.index(saved_fixed)
                except: f_idx = 0
                
                selected_fixed = st.selectbox("Ratio", options=ratio_list, index=f_idx, label_visibility="collapsed", key="setup_fixed_ar_select")
                if selected_fixed != saved_fixed:
                    save_config({"fixed_aspect_ratio": selected_fixed})

            with ar_col3:
                if ar_mode == "Dynamic Prefix Loop":
                    # Dynamic mode: show the config button
                    if st.button("Dynamic prompt prefix", key="btn_open_prefix_dialog", width="stretch"):
                        show_prompt_prefix_dialog()

        st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
        
        # --- Prompt Section ---
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>PROMPT</p>", unsafe_allow_html=True)
        with st.container(border=True):
            p_area_col, p_btn_col = st.columns([4, 1])
            with p_area_col:
                st.session_state["prompt_input"] = st.text_area(
                    "Prompt Input",
                    key="prompt_input_widget",
                    height=400,
                    label_visibility="collapsed"
                )
            
            with p_btn_col:
                if st.button("Load", key="prompt_load", width="stretch"):
                    st.session_state["_load_from_config"] = True
                    if auto_active:
                        asyncio.run(st.session_state.client.request_new_chat())
                        add_log("Loaded prompt from config. Will apply on next cycle.")
                    st.rerun()
                if st.button("Save", key="prompt_save", width="stretch"):
                    st.session_state.config = save_config({"prompt": st.session_state["prompt_input_widget"]})
                    st.session_state["prompt_input"] = st.session_state["prompt_input_widget"]
                    if auto_active:
                        asyncio.run(st.session_state.client.request_new_chat())
                        add_log("Prompt saved. Will apply on next cycle.")
                    else:
                        add_log("Prompt saved to config.")
                if st.button("Send to Browser", key="prompt_send", width="stretch", disabled=not browser_active or auto_active):
                    st.session_state.config = save_config({"prompt": st.session_state["prompt_input_widget"]}) 
                    async def do_prompt():
                        p_text = st.session_state["prompt_input_widget"]
                        add_log(f"Filling prompt: {p_text[:30]}...")
                        resp = await st.session_state.client.send_prompt(p_text)
                    asyncio.run(do_prompt())
                    st.rerun()


        # --- Tool & Model Selection Section ---
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>TOOL & MODEL SELECTION</p>", unsafe_allow_html=True)
        with st.container(border=True):
            # Load dynamic options from config (discovery field)
            discovery = config.get("discovery", {})
            avail_models = discovery.get("available_models", [])
            avail_tools = discovery.get("available_tools", [])
            
            # Ensure selected values are in availability list
            sel_model = config.get("selected_model", "")
            if sel_model and sel_model not in avail_models: avail_models = [sel_model] + avail_models
            
            sel_tool = config.get("selected_tool", "")
            # Filter out stale "Default" if it's not in the discovered tools
            if sel_tool == "Default": sel_tool = ""
            if sel_tool and sel_tool not in avail_tools: avail_tools = [sel_tool] + avail_tools

            t_col1, t_col2, t_col3, t_col4 = st.columns([3, 3, 1.5, 2.5])
            
            with t_col1:
                # Use first available tool as fallback if sel_tool is empty
                new_tool = st.selectbox("Tool", options=avail_tools, label_visibility="collapsed", key="tool_selectbox")
            with t_col2:
                new_model = st.selectbox("Model", options=avail_models, label_visibility="collapsed", key="model_selectbox")
            
            with t_col3:
                if st.button("💾 Save", width='stretch', help="Save to config.json"):
                    st.session_state["selected_tool"] = new_tool
                    st.session_state["selected_model"] = new_model
                    st.session_state.config = save_config({"selected_tool": new_tool, "selected_model": new_model})
                    add_log(f"Settings saved: {new_tool}, {new_model}")
                    st.rerun()
            
            with t_col4:
                btn_label = "🚀 Apply"
                if st.button(btn_label, width='stretch', disabled=not browser_active, type="primary"):
                    async def do_apply():
                        add_log(f"Applying settings to browser: {new_model} / {new_tool}...")
                        try:
                            resp = await st.session_state.client.apply_settings(model=new_model, tool=new_tool)
                            if resp.get("status") == "success":
                                add_log("Settings applied successfully.")
                            else:
                                add_log(f"Apply failed: {resp.get('message')}")
                        except Exception as e:
                            add_log(f"Apply failed: {str(e)}")
                    asyncio.run(do_apply())
                    st.rerun()

        # --- Add File Section (Isolated Container) ---
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>UPLOAD FILES TO BROWSER</p>", unsafe_allow_html=True)
        with st.container(border=True):
            if st.button("➕ Add File(s)", width="stretch"):
                paths = select_multiple_files()
                if paths:
                    for p in paths:
                        if p not in st.session_state.selected_files:
                            st.session_state.selected_files.append(p)
                    st.session_state.config = save_config({"selected_files": st.session_state.selected_files})
                    st.rerun()
            
            if st.session_state.selected_files:
                st.markdown("<hr style='margin: 10px 0; border: 1px solid #333;'>", unsafe_allow_html=True)
                
                st.markdown("<p style='font-size: 0.8em; color: #aaa; margin-bottom: 5px;'>Previews:</p>", unsafe_allow_html=True)
                
                # 5-column grid
                GRID_COLS = 5
                files_to_render = st.session_state.selected_files
                for i in range(0, len(files_to_render), GRID_COLS):
                    batch = files_to_render[i:i + GRID_COLS]
                    cols = st.columns(GRID_COLS)
                    for idx, path in enumerate(batch):
                        with cols[idx]:
                            if os.path.exists(path):
                                st.image(path, width='stretch')
                                st.caption(os.path.basename(path))
                                if st.button("🗑️", key=f"del_{i}_{idx}_{hash(path)}", help="Delete this file"):
                                    st.session_state.selected_files.remove(path)
                                    st.session_state.config = save_config({"selected_files": st.session_state.selected_files})
                                    st.rerun()
                            else:
                                st.error("LOST")

                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                
                u_col1, u_col2 = st.columns(2)
                if u_col1.button("🗑️ Delete All", width="stretch"):
                    async def do_clear():
                        add_log("Clearing all files locally and in browser...")
                        try:
                            resp = await st.session_state.client.clear_attachments()
                            add_log(f"Browser cleared: {resp.get('removed', 0)} files removed.")
                        except Exception as e:
                            add_log(f"Clear failed: {str(e)}")
                    asyncio.run(do_clear())
                    st.session_state.selected_files = []
                    st.session_state.config = save_config({"selected_files": st.session_state.selected_files})
                    st.rerun()
                
                if u_col2.button("🚀 Send to Browser", width="stretch", disabled=not browser_active):
                    async def do_upload():
                        add_log(f"Syncing {len(st.session_state.selected_files)} files with browser...")
                        try:
                            resp = await st.session_state.client.attach_files(st.session_state.selected_files)
                            msg = f"Sync: Added {resp.get('added', 0)}, Removed {resp.get('removed', 0)}"
                            add_log(msg)
                        except Exception as e:
                            add_log(f"Sync failed: {str(e)}")
                    asyncio.run(do_upload())
                    st.rerun()

        # --- Storage & Naming Section ---
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>STORAGE & NAMING</p>", unsafe_allow_html=True)
        with st.container(border=True):
            k = st.session_state.widget_rerender_key
            p_col1, p_col2 = st.columns([4, 1])
            with p_col1:
                st.text_input("Save Directory", value=st.session_state.save_dir, key=f"save_dir_widget_{k}", on_change=on_naming_change, label_visibility="collapsed")
            with p_col2:
                if st.button("📁 Browse", width="stretch"):
                    sel = select_folder()
                    if sel:
                        st.session_state.save_dir = sel
                        st.session_state.widget_rerender_key += 1
                        st.session_state.config = save_config({"save_dir": sel})
                        st.rerun()
            
            n_col1, n_col2, n_col3 = st.columns([2, 1, 1])
            with n_col1:
                st.text_input("File Prefix", value=st.session_state.name_prefix, key=f"name_prefix_widget_{k}", on_change=on_naming_change)
            with n_col2:
                st.number_input("Padding", min_value=1, max_value=10, value=st.session_state.name_padding, key=f"name_padding_widget_{k}", on_change=on_naming_change)
            with n_col3:
                st.number_input("Start No.", min_value=0, value=st.session_state.name_start, key=f"name_start_widget_{k}", on_change=on_naming_change)

        # --- Gemini Submit & Stop Section ---
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>GEMINI ACTIONS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            sub_col_nc, sub_col1, sub_col2, sub_col3 = st.columns([1, 1, 1, 1])
            
            # Disable manual buttons if browser is off, busy with manual submit, or automation is running
            is_busy = st.session_state.get("is_busy", False)
            is_auto = st.session_state.get("last_known_auto_active", False)
            btn_disabled = not browser_active or is_busy or is_auto

            with sub_col_nc:
                if st.button("➕ New Chat", width="stretch", disabled=btn_disabled):
                    async def do_new_chat():
                        add_log("Triggering New Chat...")
                        try:
                            resp = await st.session_state.client.new_chat()
                            add_log(f"New Chat status: {resp.get('message')}")
                        except Exception as e:
                            add_log(f"New Chat failed: {e}")
                    asyncio.run(do_new_chat())
                    st.rerun()

            with sub_col1:
                # --- Submit: Background Execution ---
                if st.button("🚀 Submit", width="stretch", disabled=btn_disabled, type="primary"):
                    def run_submit():
                        st.session_state.is_busy = True
                        try:
                            async def do_submit_flow():
                                p_text = st.session_state.get("prompt_input_widget", st.session_state.get("prompt_input", ""))
                                add_log("Submitting prompt (Background)...")
                                resp = await st.session_state.client.submit_response(text=p_text)
                                
                                if resp.get("status") == "success":
                                    add_log("SUCCESS: Image generated. Starting download...")
                                    naming = {"prefix": st.session_state.name_prefix, "padding": st.session_state.name_padding, "start": st.session_state.name_start}
                                    status = await st.session_state.client.get_status()
                                    meta = {"prompt": p_text, "url": status.get("url", ""), "upload_path": ", ".join(st.session_state.selected_files)}
                                    
                                    dl_resp = await st.session_state.client.download_images(st.session_state.save_dir, naming, meta)
                                    if dl_resp.get("status") == "success":
                                        st.session_state.last_saved_paths = dl_resp.get("saved_paths", [])
                                        add_log(f"DOWNLOADED: {dl_resp.get('count')} imgs. Starting processing...")
                                        st.session_state.name_start = dl_resp.get("next_start", st.session_state.name_start)
                                        st.session_state.widget_rerender_key += 1
                                        st.session_state.config = save_config({"name_start": st.session_state.name_start})
                                        proc_resp = await st.session_state.client.process_images(st.session_state.last_saved_paths, st.session_state.save_dir)
                                        if proc_resp.get("status") == "success":
                                            add_log(f"CLEANED: {proc_resp.get('processed_count')} imgs.")
                                        else:
                                            add_log(f"CLEAN FAILED: {proc_resp}")
                                    else:
                                        add_log(f"DL FAILED: {dl_resp.get('message')}")
                                else:
                                    add_log(f"FAILED: {resp.get('message', 'Unknown error')}")
                            
                            asyncio.run(do_submit_flow())
                        except Exception as e:
                            add_log(f"ERROR: {e}")
                        finally:
                            st.session_state.is_busy = False
                            st.session_state.needs_rerun = True

                    t = threading.Thread(target=run_submit, daemon=True)
                    add_script_run_ctx(t)
                    t.start()
                    st.rerun()

            with sub_col2:
                # --- Redo: Background Execution & Optimized Strategy ---
                if st.button("🔄 Redo", width="stretch", disabled=btn_disabled):
                    def run_redo():
                        st.session_state.is_busy = True
                        try:
                            async def do_redo_flow():
                                # 1. Start Redo IMMEDIATELY
                                add_log("Triggering REDO (Priority 1)...")
                                resp = await st.session_state.client.redo_response()
                                
                                if resp.get("status") == "success":
                                    # 2. Process LATEST during wait time
                                    if st.session_state.last_saved_paths:
                                        add_log("Redo active. Processing previous set during idle time...")
                                        p_resp = await st.session_state.client.process_images(st.session_state.last_saved_paths, st.session_state.save_dir)
                                        if p_resp.get("status") == "success":
                                            add_log(f"PREVIOUS SET CLEANED: {p_resp.get('processed_count')} imgs.")
                                        else:
                                            add_log(f"PREV CLEAN FAILED: {p_resp}")
                                    
                                    # 3. Monitor for NEW results
                                    wait_resp = await st.session_state.client.submit_response(text=None)
                                    
                                    if wait_resp.get("status") == "success":
                                        add_log("New images detected. Downloading...")
                                        naming = {"prefix": st.session_state.name_prefix, "padding": st.session_state.name_padding, "start": st.session_state.name_start}
                                        status = await st.session_state.client.get_status()
                                        meta = {"prompt": st.session_state.get("prompt_input_widget", ""), "url": status.get("url", ""), "upload_path": ", ".join(st.session_state.selected_files)}
                                        
                                        dl_resp = await st.session_state.client.download_images(st.session_state.save_dir, naming, meta)
                                        if dl_resp.get("status") == "success":
                                            st.session_state.last_saved_paths = dl_resp.get("saved_paths", [])
                                            add_log(f"NEW DOWNLOAD: {dl_resp.get('count')} imgs.")
                                            st.session_state.name_start = dl_resp.get("next_start", st.session_state.name_start)
                                            st.session_state.widget_rerender_key += 1
                                            st.session_state.config = save_config({"name_start": st.session_state.name_start})
                                            # Finally process the new ones
                                            p_resp = await st.session_state.client.process_images(st.session_state.last_saved_paths, st.session_state.save_dir)
                                            if p_resp.get("status") == "success":
                                                add_log(f"NEW SET CLEANED: {p_resp.get('processed_count')} imgs.")
                                            else:
                                                add_log(f"NEW CLEAN FAILED: {p_resp}")
                                    else:
                                        add_log(f"WAIT FAILED: {wait_resp.get('message')}")
                                else:
                                    add_log(f"REDO TRIGGER FAILED: {resp.get('message')}")
                            
                            asyncio.run(do_redo_flow())
                        except Exception as e:
                            add_log(f"ERROR: {e}")
                        finally:
                            st.session_state.is_busy = False
                            st.session_state.needs_rerun = True

                    t = threading.Thread(target=run_redo, daemon=True)
                    add_script_run_ctx(t)
                    t.start()
                    st.rerun()

            with sub_col3:
                # Stop Respond
                if st.button("🛑 Stop", width="stretch", disabled=not browser_active or not st.session_state.get("is_busy", False)):
                    async def do_stop():
                        add_log("Sending stop command...")
                        # Unblock UI immediately
                        st.session_state.is_busy = False
                        resp = await st.session_state.client.stop_response()
                        if resp.get("status") == "success":
                            add_log(f"STOPPED: {resp.get('message')}")
                        else:
                            add_log(f"RESULT: {resp.get('status')} - {resp.get('message')}")
                    asyncio.run(do_stop())
                    st.rerun()

        # --- Watermark Settings Section ---
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>WATERMARK SETTINGS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            wm_col1, wm_col2 = st.columns(2)
            with wm_col1:
                new_remove_wm = st.toggle("Remove Watermark", value=st.session_state.auto_remove_wm, help="Automatically clean images during loop")
            with wm_col2:
                new_use_gpu = st.toggle("Use GPU (CUDA)", value=st.session_state.use_gpu, help="Use GPU (CUDA) for significantly faster processing. Switch to CPU if encountering memory issues.")
            
            if new_remove_wm != st.session_state.auto_remove_wm or new_use_gpu != st.session_state.use_gpu:
                st.session_state.auto_remove_wm = new_remove_wm
                st.session_state.use_gpu = new_use_gpu
                
                # Update config
                auto_updates = config.get("automation", {})
                auto_updates["remove_watermark"] = new_remove_wm
                auto_updates["use_gpu"] = new_use_gpu
                st.session_state.config = save_config({"automation": auto_updates})
                
                # If GPU setting changed, clear internal model caches
                if new_use_gpu != st.session_state.get("_last_gpu_val"):
                    import shared_state
                    from processing_utils import reset_shared_processor
                    shared_state.clear_shared_refiner()
                    reset_shared_processor()
                    st.session_state._last_gpu_val = new_use_gpu
                
                st.rerun()

        # --- Gemini Automation Section ---
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>GEMINI AUTOMATION</p>", unsafe_allow_html=True)
        with st.container(border=True):
            # --- Automation Stats Fragment (Moved to top) ---

            # Disable toggle if automation is running or stopping
            auto_status_pre = asyncio.run(st.session_state.client.get_automation_stats())
            is_auto_active_pre = auto_status_pre.get("is_running", False)
            toggle_disabled = is_auto_active_pre or st.session_state.auto_stop_requested
            
            auto_enabled = st.toggle("Auto Looping", value=st.session_state.auto_looping, 
                                     help="Enable automatic repetitive generation",
                                     disabled=toggle_disabled)

            if auto_enabled != st.session_state.auto_looping:
                st.session_state.auto_looping = auto_enabled
                # Sync automation state 
                auto_updates = config.get("automation", {})
                auto_updates["auto_looping"] = auto_enabled
                st.session_state.config = save_config({"automation": auto_updates})
                # Force immediate rerun so sidebar buttons see the new state instantly
                st.rerun()

            # --- Control Button ---
            # Check status again for button rendering
            auto_status = asyncio.run(st.session_state.client.get_automation_stats())
            is_active = auto_status.get("is_running", False)

            # If server confirms stopped, clear the client-side stop flag
            if not is_active:
                st.session_state.auto_stop_requested = False

            # Determine effective state: treat as inactive if stop was already requested
            show_as_inactive = not is_active or st.session_state.auto_stop_requested

            # Final disabling logic for inputs
            # Inputs are disabled if:
            # 1. Auto Looping toggle is OFF
            # 2. Automation is already running
            # 3. Stop was requested (wait for complete stop)
            inputs_disabled = not auto_enabled or is_active or st.session_state.auto_stop_requested

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
                st.session_state.config = save_config({"automation": {"auto_looping": True, "mode": new_mode, "goal": new_goal}})

            # Calculate history and goal validation for Continue button
            REJECT_STAT_LOG_PATH = "reject_stat_log.json"
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
                if not show_as_inactive:
                    if st.button("⏹️ Stop Looping Process", width="stretch"):
                        st.session_state.show_stop_confirmation_setup = True
                        st.rerun()
                else:
                    start_disabled = not browser_active or st.session_state.get("is_busy", False) or not auto_enabled or st.session_state.auto_stop_requested
                    if st.button("▶️ Start Looping Process", width="stretch", type="primary", disabled=start_disabled):
                        if history_count > 0:
                            st.session_state.show_start_confirmation_setup = True
                            st.rerun()
                        else:
                            current_config = load_config()
                            current_config["selected_files"] = st.session_state.selected_files
                            current_config["prompt"] = st.session_state.get("prompt_input_widget", current_config.get("prompt", ""))
                            current_config["selected_tool"] = st.session_state.get("tool_selectbox")
                            current_config["selected_model"] = st.session_state.get("model_selectbox")
                            current_config.setdefault("automation", {})["remove_watermark"] = st.session_state.auto_remove_wm
                            
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
                            time.sleep(0.5)
                            st.rerun()
            
            with btn_col2:
                _continue_disabled = not show_as_inactive or history_count == 0 or not browser_active or st.session_state.get("is_busy", False) or not auto_enabled or st.session_state.auto_stop_requested
                if st.button("⏯️ Continue Session", key="continue_loop_setup", width="stretch", disabled=_continue_disabled):
                    if is_goal_reached:
                        st.session_state.show_goal_reached_confirmation_setup = True
                        st.rerun()
                    else:
                        current_config = load_config()
                        current_config["selected_files"] = st.session_state.selected_files
                        current_config["prompt"] = st.session_state.get("prompt_input_widget", current_config.get("prompt", ""))
                        current_config["selected_tool"] = st.session_state.get("tool_selectbox")
                        current_config["selected_model"] = st.session_state.get("model_selectbox")
                        current_config.setdefault("automation", {})["remove_watermark"] = st.session_state.auto_remove_wm

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
                        time.sleep(0.5)
                        st.rerun()

with col2:
    with st.container(border=True, height=RIGHT_HEIGHT):
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; color: #a0a0ff;'>ENGINE LIVE LOGS</p>", unsafe_allow_html=True)
        
        # --- Log Management Buttons ---
        cl_col1, cl_col2 = st.columns(2)
        with cl_col1:
            if st.button("🧹 Clear Console", width="stretch", help="Clears logs from the UI only."):
                st.session_state.logs = []
                st.rerun()
        with cl_col2:
            if st.button("🔥 Clear Engine Log", width="stretch", help="Strictly clears the physical engine.log file via API."):
                async def do_clear_log():
                    try:
                        resp = await st.session_state.client.clear_engine_logs()
                        if resp.get("status") == "success":
                            add_log("Engine log file cleared via API.")
                        else:
                            add_log(f"Failed to clear log: {resp.get('message')}")
                    except Exception as e:
                        add_log(f"Clear Log Error: {e}")
                asyncio.run(do_clear_log())
                st.rerun()

        render_setup_logs()
