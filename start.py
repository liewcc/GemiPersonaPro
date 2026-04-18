import logging

class _SuppressFragmentWarning(logging.Filter):
    def filter(self, record):
        return "does not exist anymore" not in record.getMessage()

# The "fragment does not exist anymore" message is logged at INFO level
# from streamlit.runtime.app_session (not script_run_context as previously assumed).
logging.getLogger("streamlit.runtime.app_session").addFilter(
    _SuppressFragmentWarning()
)

import streamlit as st

import os

if "GEMI_BANNER_PRINTED" not in os.environ:
    os.environ["GEMI_BANNER_PRINTED"] = "1"

import asyncio
import sys
import subprocess   
import time
import threading
import json
import os
from streamlit.runtime.scriptrunner import add_script_run_ctx
from api_client import EngineClient
import shared_state
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk
from style_utils import apply_premium_style
from style_utils import apply_premium_style


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

CONFIG_PATH = "config.json"


# ── Config helpers ──────────────────────────────────────────────────────────

def load_config() -> dict:
    return load_cfg_disk()


def save_config(updates: dict) -> dict:
    return save_cfg_disk(updates)


# ── LaMa singleton (shared with 00_Dashboard and 04_Watermark_Removal) ─────

def get_refiner():
    return shared_state.get_shared_refiner()


# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GemiPersona | Launcher",
    page_icon="sys_img/logo.png",
    layout="centered",
    initial_sidebar_state="collapsed",
)
apply_premium_style()

# Clean launcher look – hide sidebar and top bar
st.markdown(
    """
    <style>
        [data-testid="stSidebar"]         { display: none !important; }
        [data-testid="collapsedControl"]  { display: none !important; }
        header[data-testid="stHeader"]    { display: none !important; }
        .main .block-container { padding-top: 2.5rem; max-width: 560px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session state init ───────────────────────────────────────────────────────

def _init(key, val):
    if key not in st.session_state:
        st.session_state[key] = val

_init("client",              EngineClient())
_init("step_engine_done",    False)
_init("step_engine_skip",    False)   # True = was already running
_init("step_browser_done",   False)
_init("step_browser_skip",   False)
_init("step_lama_done",      False)
_init("step_lama_skip",      False)
_init("lama_thread_started", False)
_init("lama_start_mono",     None)
_init("lama_fake_pct",       0)
_init("all_done",            False)
_init("countdown",           3)
_init("auto_redirect_done",  False)


# ── Startup logic ────────────────────────────────────────────────────────────

async def _ensure_engine() -> str:
    """Returns 'skip', 'started', or 'failed'."""
    health = await st.session_state.client.check_health()
    if health:
        return "skip"
    cfg = load_config()
    flags = (
        subprocess.CREATE_NEW_CONSOLE
        if cfg.get("show_engine_console", True)
        else subprocess.CREATE_NO_WINDOW
    )
    subprocess.Popen([sys.executable, "engine_service.py"], creationflags=flags)
    for _ in range(20):
        await asyncio.sleep(0.5)
        if await st.session_state.client.check_health():
            return "started"
    return "failed"


async def _ensure_browser() -> str:
    """Returns 'skip', 'started', or 'failed'."""
    health = await st.session_state.client.check_health()
    if not health:
        return "failed"
    if health.get("engine_running", False):
        return "skip"
    cfg = load_config()
    await st.session_state.client.start_engine(headless=cfg.get("headless", False))
    await asyncio.sleep(2.0)
    url = cfg.get("browser_url", "https://gemini.google.com/app")
    await st.session_state.client.navigate(url)
    for _ in range(20):
        await asyncio.sleep(0.5)
        h = await st.session_state.client.check_health()
        if h and h.get("engine_running", False):
            return "started"
    return "failed"


def _kick_lama_thread():
    """Spawn background thread to warm up LaMa model via @st.cache_resource."""
    if st.session_state.lama_thread_started or shared_state.lama_status["ready"]:
        return
    st.session_state.lama_thread_started = True
    st.session_state.lama_start_mono = time.monotonic()

    def _load():
        try:
            get_refiner()          # Returns immediately if already cached
            shared_state.lama_status["ready"] = True
        except Exception as exc:
            shared_state.lama_status["error"] = str(exc)

    t = threading.Thread(target=_load, daemon=True)
    add_script_run_ctx(t)
    t.start()


# ── Countdown fragment (must be at global scope – Fragment Stability Protocol) ──

@st.fragment(run_every="1s")
def render_countdown():
    if not st.session_state.all_done:
        return
    # Once the redirect has fired once, stop auto-redirecting.
    # The user may have navigated back to this page voluntarily.
    if st.session_state.auto_redirect_done:
        return
    cfg = load_config()
    page_map = {
        "gemini_setup": "pages/01_Gemini_Setup.py",
        "dashboard":    "pages/00_Dashboard.py",
    }
    target = page_map.get(cfg.get("startup_redirect", "gemini_setup"), "pages/01_Gemini_Setup.py")
    n = st.session_state.countdown
    if n > 0:
        st.caption(f"⏱️ Auto-redirecting in **{n}s** — or click a button below to navigate now")
        st.session_state.countdown -= 1
    else:
        st.session_state.auto_redirect_done = True
        st.switch_page(target)


# ── Header ───────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("sys_img/logo.png", width="stretch")

# Header title removed to save space


# ── Status widget label & state (derived from session state before the block) ─

all_done = (
    st.session_state.step_engine_done
    and st.session_state.step_browser_done
    and st.session_state.step_lama_done
)

if all_done:
    _label, _state = "System Ready ✅", "complete"
elif not st.session_state.step_engine_done:
    _label, _state = "Starting Engine Service…", "running"
elif not st.session_state.step_browser_done:
    _label, _state = "Starting Browser…", "running"
else:
    _label, _state = "Loading AI Model…", "running"


# ── Main startup st.status() block ──────────────────────────────────────────

with st.status(_label, expanded=True, state=_state) as _s:

    # Always redraw completed steps (session_state survives reruns)
    if st.session_state.step_engine_done:
        msg = "Already running" if st.session_state.step_engine_skip else "Started"
        st.write(f"✅ Engine Service: {msg}")

    if st.session_state.step_browser_done:
        msg = "Already open" if st.session_state.step_browser_skip else "Launched & navigated"
        st.write(f"✅ Browser: {msg}")

    if st.session_state.step_lama_done:
        msg = "Already in memory" if st.session_state.step_lama_skip else "Loaded successfully"
        st.write(f"✅ LaMa AI Model: {msg}")

    # Execute the next pending step (one per rerun — advance via st.rerun())
    if not st.session_state.step_engine_done:
        with st.spinner("Checking engine service…"):
            result = asyncio.run(_ensure_engine())
        if result == "failed":
            _s.update(label="❌ Engine Service failed to start", state="error")
            st.error("Could not start engine_service.py. Check console output.")
            st.stop()
        st.session_state.step_engine_done = True
        st.session_state.step_engine_skip = (result == "skip")
        st.rerun()

    elif not st.session_state.step_browser_done:
        with st.spinner("Checking browser…"):
            result = asyncio.run(_ensure_browser())
        if result == "failed":
            _s.update(label="❌ Browser failed to start", state="error")
            st.error("Could not open browser via engine. Engine may not be healthy.")
            st.stop()
        st.session_state.step_browser_done = True
        st.session_state.step_browser_skip = (result == "skip")
        st.rerun()

    elif not st.session_state.step_lama_done:
        # Kick off background thread on first visit to this step
        _kick_lama_thread()

        if shared_state.lama_status["error"]:
            _s.update(label="❌ LaMa model failed to load", state="error")
            st.error(f"LaMa load error: {shared_state.lama_status['error']}")
            st.stop()

        elif shared_state.lama_status["ready"]:
            # Thread completed — determine if it was instant (i.e. already cached)
            elapsed = time.monotonic() - (st.session_state.lama_start_mono or 0)
            st.session_state.step_lama_done = True
            st.session_state.step_lama_skip = (elapsed < 2.0)
            st.rerun()

        else:
            # Show fake progress bar while thread is working
            import torch
            gpu_hint = "(GPU)" if torch.cuda.is_available() else "(CPU — may take 10-30s)"
            pct = st.session_state.lama_fake_pct
            st.progress(pct / 100.0, f"Loading LaMa AI model… {gpu_hint}")
            # Advance fake percentage (caps at 90 — jumps to 100 when ready)
            st.session_state.lama_fake_pct = min(90, pct + 7)
            time.sleep(1)
            st.rerun()


# ── Done — redirect options ──────────────────────────────────────────────────

if all_done:
    if not st.session_state.all_done:
        st.session_state.all_done = True  # Freeze countdown start

# Divider removed to save space


    cfg = load_config()
    current_redirect = cfg.get("startup_redirect", "gemini_setup")

    left, right = st.columns(2)

    with left:
        st.markdown("**Default redirect:**")
        choice = st.radio(
            "Default redirect",
            options=["gemini_setup", "dashboard"],
            format_func=lambda x: "Gemini Setup" if x == "gemini_setup" else "Dashboard",
            index=0 if current_redirect == "gemini_setup" else 1,
            label_visibility="collapsed",
            key="redirect_radio",
        )
        if choice != current_redirect:
            save_config({"startup_redirect": choice})
            st.session_state.countdown = 3   # Reset countdown on preference change
            st.rerun()

    with right:
        st.markdown("**Navigate now:**")
        if st.button("→ Gemini Setup", width="stretch", type="primary"):
            st.switch_page("pages/01_Gemini_Setup.py")
        if st.button("→ Dashboard", width="stretch"):
            st.switch_page("pages/00_Dashboard.py")
        st.link_button("github repository", "https://github.com/liewcc/GemiPersonaPro", width="stretch")

    render_countdown()
