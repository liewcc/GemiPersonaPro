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

import json
import os
import threading
import psutil

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
st.set_page_config(page_title="GemiPersona | DASHBOARD", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
apply_premium_style()

# --- Hide Custom Dash Styling ---
st.markdown("""
    <style>
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
if "selected_files" not in st.session_state:
    st.session_state.selected_files = config.get("selected_files", [])
if "name_start" not in st.session_state: 
    st.session_state.name_start = config.get("name_start", 1)

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

# --- UI Layout ---
with st.sidebar:
    st.markdown("### Album Navigation")

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

        if st.button("📂 View Download Folder", width="stretch", help="Open the save directory in File Explorer"):
            if save_dir and os.path.isdir(save_dir):
                os.startfile(save_dir)
            else:
                st.warning("Save directory is not configured or does not exist.")

    st.markdown("### Gemini Automation")
    with st.container(border=True):
        remove_wm = st.toggle("Remove Watermark", value=st.session_state.auto_remove_wm)
        auto_enabled = st.toggle("Auto Looping", value=st.session_state.auto_looping)

        if auto_enabled != st.session_state.auto_looping or remove_wm != st.session_state.auto_remove_wm:
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

        a_col1, a_col2 = st.columns([2, 1])
        with a_col1:
            mode_options = {"rounds": "Fixed Rounds", "images": "Target Images"}
            new_mode = st.radio("Stop Condition", options=list(mode_options.keys()), 
                                format_func=lambda x: mode_options[x],
                                index=list(mode_options.keys()).index(st.session_state.auto_mode),
                                horizontal=True, label_visibility="collapsed",
                                disabled=not auto_enabled)
        with a_col2:
            goal_label = "Rounds" if new_mode == "rounds" else "Images"
            new_goal = st.number_input(goal_label, min_value=1, value=st.session_state.auto_goal, label_visibility="collapsed", disabled=not auto_enabled)
        
        if auto_enabled and (new_mode != st.session_state.auto_mode or new_goal != st.session_state.auto_goal):
            st.session_state.auto_mode = new_mode
            st.session_state.auto_goal = new_goal
            save_config({"automation": {"auto_looping": True, "mode": new_mode, "goal": new_goal}})

        auto_status = asyncio.run(st.session_state.client.get_automation_stats())
        is_active = auto_status.get("is_running", False)
        is_busy = st.session_state.get("is_busy", False)

        # If server confirms stopped, clear the client-side stop flag
        if not is_active:
            st.session_state.auto_stop_requested = False

        # Determine effective state: treat as inactive if stop was already requested
        show_as_inactive = not is_active or st.session_state.auto_stop_requested

        if show_as_inactive:
            if st.button("▶️ Start Looping Process", width="stretch", type="primary", disabled=not browser_active or is_busy):
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
                time.sleep(0.5)
                st.rerun()
        else:
            if st.button("⏹️ Stop Looping Process", width="stretch"):
                async def do_stop_auto():
                    add_log("Stopping Automation Loop...")
                    resp = await st.session_state.client.stop_automation()
                    add_log(f"Auto Stop: {resp.get('message')}")
                asyncio.run(do_stop_auto())
                st.session_state.auto_stop_requested = True
                st.rerun()

def get_status_bar_html(label, msg, color):
    return f"""
        <div style='height: 46px; min-height: 46px; margin-bottom: 20px; overflow: hidden;'>
            <div style='background: #f9fafb; padding: 10px 18px; border-radius: 10px; border: 1px solid #e5e7eb; 
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                        font-size: 0.95em; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                        display: flex; align-items: center; box-shadow: 0 1px 2px rgba(0,0,0,0.03);'>
                <span style='color: {color}; margin-right: 12px; font-weight: 700; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.6px;'>{label}:</span> 
                <span style='font-weight: 500;'>{msg}</span>
            </div>
        </div>
    """

@st.fragment(run_every="10s")
def render_dash_account_status():
    """Account + browser status bar for the Dashboard main panel."""
    h_data = asyncio.run(st.session_state.client.check_health())
    active = h_data.get("engine_running", False) if h_data else False
    stats = asyncio.run(st.session_state.client.get_automation_stats())
    cached_account = stats.get("current_account_id")
    result = st.session_state.get("login_status")

    display_account = None
    is_logged_in = False
    if cached_account:
        is_logged_in = True
        display_account = cached_account
    elif result and result.get("logged_in"):
        is_logged_in = True
        display_account = result.get("account_id", "Unknown")

    status_color = "#00ff00" if active else "#ff4444"
    status_text = "ONLINE" if active else "OFFLINE"
    col_status, col_account = st.columns([1, 5])
    with col_status:
        st.markdown(f"<p style='margin: 0; font-size: 0.9em;'><span style='color:{status_color};'>\u25cf</span> <b>BROWSER:</b> {status_text}</p>", unsafe_allow_html=True)
    with col_account:
        if not active:
            st.markdown("<p style='margin: 0; font-size: 0.9em; color: #888;'>Account: Not Ready</p>", unsafe_allow_html=True)
        elif result is None and not cached_account:
            st.markdown("<p style='margin: 0; font-size: 0.9em; color: #aaa;'>Account: Scanning...</p>", unsafe_allow_html=True)
        elif is_logged_in:
            st.markdown(f"<p style='margin: 0; font-size: 0.9em;'><b>Account:</b> <span style='color:#a0a0ff;'>{display_account}</span></p>", unsafe_allow_html=True)
        else:
            st.markdown("<p style='margin: 0; font-size: 0.9em;'><b>Account:</b> <span style='color:#ff8888;'>GUEST / NOT LOGGED IN</span></p>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

@st.fragment(run_every="5s")
def render_automation_stats():
    _trigger_rerun = False
    try:
        stats = asyncio.run(st.session_state.client.get_automation_stats())
        is_active = stats.get("is_running", False)
        if st.session_state.get("last_known_auto_active", False) and not is_active:
            st.session_state.last_known_auto_active = False
            # Set flag — the actual rerun must happen OUTSIDE the try/except block,
            # because RerunException inherits from Exception and would be swallowed here.
            _trigger_rerun = True
        else:
            st.session_state.last_known_auto_active = is_active
        c, s, r, rs = stats.get("cycles", 0), stats.get("successes", 0), stats.get("refusals", 0), stats.get("resets", 0)
        if is_active:
            status_badge, bg_color = "<b style='color: #d73a49;'>● RUNNING</b>", "#ffffff"
        elif c > 0:
            status_badge, bg_color = "<b style='color: #6a737d;'>○ IDLE / FINISHED</b>", "#f6f8fa"
        else:
            st.caption("Automation Standby.")
            return
        st.markdown(f"""
        <div style='background: {bg_color}; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 0.9em; border: 1px solid #ddd; color: #1e1e1e; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 15px;'>
            {status_badge} | Cycles: <b>{c}</b> | Images: <b>{s}</b> | Refused: <b>{r}</b> | Resets: <b>{rs}</b>
        </div>
        """, unsafe_allow_html=True)
    except: pass
    # Fire the rerun AFTER try/except so RerunException is not swallowed.
    if _trigger_rerun:
        st.rerun(scope="app")

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

render_dash_account_status()
render_live_status_bar()
render_automation_stats()

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
    if st.button("Understood", width="stretch", type="primary"): st.rerun()

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
                
                if st.button("💾 Save", width="stretch", type="primary"):
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
            if png_info: st.markdown("**✨ Textual Info**"); st.json(png_info)
            if exif_data: st.markdown("**📸 Technical Metadata**"); st.json({TAGS.get(k, k): str(v) for k, v in exif_data.items()})
    except: st.error("Failed to read metadata.")

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
                    st.image(file_path, width="stretch")
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