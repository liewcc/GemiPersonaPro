import streamlit as st
import asyncio
import sys
import os
import time
import threading
import json
from datetime import datetime
from streamlit.runtime.scriptrunner import add_script_run_ctx
from config_utils import load_config as load_cfg_disk, save_config as save_cfg_disk
from style_utils import apply_premium_style

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GemiPersona | API Generator (beta)",
    page_icon="sys_img/icon.png",
    layout="wide",
)
apply_premium_style()


# ── Config helpers ──────────────────────────────────────────────────────────
def load_config():
    return load_cfg_disk()


def save_config(updates):
    return save_cfg_disk(updates)


# ── Layout fix ──────────────────────────────────────────────────────────────
st.markdown("""
    <style>
    .main { overflow: hidden !important; }
    .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
    </style>
""", unsafe_allow_html=True)


# ── Session State Init ──────────────────────────────────────────────────────
def _init(key, val):
    if key not in st.session_state:
        st.session_state[key] = val

cfg = load_config()
api_cfg = cfg.get("gemini_api", {})

_init("api_key", api_cfg.get("api_key", ""))
_init("api_model", api_cfg.get("model", "gemini-2.5-flash-image"))
_init("api_client_instance", None)
_init("api_logs", [])
_init("api_running", False)
_init("api_stop_requested", False)
_init("api_last_images", [])
_init("api_generation_count", 0)

# Sync save_dir / naming from main config
_init("api_save_dir", cfg.get("save_dir", os.path.join(os.getcwd(), "gemini_outputs")))
_init("api_name_prefix", cfg.get("name_prefix", ""))
_init("api_name_padding", cfg.get("name_padding", 2))
_init("api_name_start", cfg.get("name_start", 1))
_init("api_remove_wm", cfg.get("automation", {}).get("remove_watermark", True))
_init("api_use_gpu", cfg.get("automation", {}).get("use_gpu", True))


def api_log(msg):
    ts = time.strftime("%H:%M:%S")
    st.session_state.api_logs.append(f"[{ts}] {msg}")
    if len(st.session_state.api_logs) > 100:
        st.session_state.api_logs.pop(0)


def get_api_client():
    """Returns the GeminiAPIClient singleton, creating it if needed."""
    key = st.session_state.api_key
    model = st.session_state.api_model
    if not key:
        return None
    inst = st.session_state.api_client_instance
    if inst is None or getattr(inst, "model", "") != model:
        try:
            from gemini_api_client import GeminiAPIClient
            inst = GeminiAPIClient(api_key=key, model=model)
            st.session_state.api_client_instance = inst
        except Exception as e:
            api_log(f"❌ Client init failed: {e}")
            return None
    return inst


# ── Available Models ────────────────────────────────────────────────────────
API_MODELS = {
    "gemini-2.5-flash-image": "Nano Banana (Flash · Free Tier)",
    "gemini-3.1-flash-image-preview": "Nano Banana 2 (Flash · Free Tier)",
    "gemini-3-pro-image-preview": "Nano Banana Pro (Pro · Paid)",
}


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("sys_img/logo.png", width=180)
    st.markdown("### ⚡ API Generator (beta)")
    st.caption("Direct Gemini API image generation — no browser required.")

    st.divider()

    # API Key
    new_key = st.text_input(
        "🔑 API Key",
        value=st.session_state.api_key,
        type="password",
        help="Get your key at https://aistudio.google.com/apikey",
    )
    if new_key != st.session_state.api_key:
        st.session_state.api_key = new_key
        st.session_state.api_client_instance = None  # Force re-create
        save_config({"gemini_api": {**api_cfg, "api_key": new_key}})

    # Model selector
    model_options = list(API_MODELS.keys())
    current_model_idx = model_options.index(st.session_state.api_model) if st.session_state.api_model in model_options else 0
    selected_model = st.selectbox(
        "🧠 Model",
        options=model_options,
        format_func=lambda x: API_MODELS[x],
        index=current_model_idx,
    )
    if selected_model != st.session_state.api_model:
        st.session_state.api_model = selected_model
        st.session_state.api_client_instance = None
        save_config({"gemini_api": {**api_cfg, "model": selected_model}})

    st.divider()

    # Remove watermark toggle
    wm_toggle = st.toggle("🧹 Remove Watermark", value=st.session_state.api_remove_wm, key="api_wm_toggle")
    if wm_toggle != st.session_state.api_remove_wm:
        st.session_state.api_remove_wm = wm_toggle

    gpu_toggle = st.toggle("⚡ Use GPU", value=st.session_state.api_use_gpu, key="api_gpu_toggle")
    if gpu_toggle != st.session_state.api_use_gpu:
        st.session_state.api_use_gpu = gpu_toggle

    st.divider()

    # Quick Stats
    client = get_api_client()
    if client:
        stats = client.get_stats()
        st.markdown(f"""
        **Session Stats**
        - Cycles: `{stats['cycles']}`
        - Images: `{stats['successes']}`
        - Refused: `{stats['refused']}`
        - Errors: `{stats['failures']}`
        """)
    else:
        st.info("Enter your API Key to start.")


# ── Main Panel ──────────────────────────────────────────────────────────────

# Status bar
key_ok = bool(st.session_state.api_key)
status_color = "#28a745" if key_ok else "#d73a49"
status_text = "READY" if key_ok else "NO API KEY"
model_label = API_MODELS.get(st.session_state.api_model, st.session_state.api_model)

st.markdown(f"""
<div style='background: #ffffff; padding: 0 15px; height: 40px; display: flex; align-items: center; border-radius: 8px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 0.9em; border: 1px solid #ddd; color: #24292e; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 15px;'>
    <div style='flex: 1; display: flex; align-items: center; justify-content: space-between;'>
        <div><b style='color: {status_color};'>●</b> <b>API:</b> {status_text}</div>
        <div style='text-align: right;'><b>Model:</b> <span style='color: #0366d6; font-weight: 600;'>{model_label}</span></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Two columns: Left = Controls, Right = Preview ──────────────────────────
col_ctrl, col_preview = st.columns([1.2, 1])

with col_ctrl:
    # Prompt
    prompt_text = st.text_area(
        "📝 Prompt",
        value=cfg.get("prompt", ""),
        height=180,
        key="api_prompt_widget",
        help="Describe the image you want to generate.",
    )

    # Save Directory
    import tkinter as tk
    from tkinter import filedialog

    def select_folder():
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', True)
        path = filedialog.askdirectory()
        root.destroy()
        return path

    save_dir_col, browse_col = st.columns([4, 1])
    with save_dir_col:
        save_dir = st.text_input("📁 Save Directory", value=st.session_state.api_save_dir, key="api_save_dir_widget")
        if save_dir != st.session_state.api_save_dir:
            st.session_state.api_save_dir = save_dir
    with browse_col:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Browse", key="api_browse_btn", width="stretch"):
            picked = select_folder()
            if picked:
                st.session_state.api_save_dir = picked
                st.rerun()

    # Naming Config
    nc1, nc2, nc3 = st.columns(3)
    with nc1:
        name_prefix = st.text_input("Prefix", value=st.session_state.api_name_prefix, key="api_prefix_w")
        if name_prefix != st.session_state.api_name_prefix:
            st.session_state.api_name_prefix = name_prefix
    with nc2:
        name_padding = st.number_input("Padding", value=st.session_state.api_name_padding, min_value=1, max_value=6, key="api_padding_w")
        if name_padding != st.session_state.api_name_padding:
            st.session_state.api_name_padding = name_padding
    with nc3:
        name_start = st.number_input("Start No.", value=st.session_state.api_name_start, min_value=1, key="api_start_w")
        if name_start != st.session_state.api_name_start:
            st.session_state.api_name_start = name_start

    # Goal
    goal_col1, goal_col2 = st.columns(2)
    with goal_col1:
        api_goal = st.number_input("🎯 Goal (images)", value=1, min_value=1, max_value=9999, key="api_goal_w")
    with goal_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        preview_name = f"{st.session_state.api_name_prefix}{str(st.session_state.api_name_start).zfill(st.session_state.api_name_padding)}.png"
        st.caption(f"Next file: `{preview_name}`")

    st.divider()

    # ── Action Buttons ──────────────────────────────────────────────────────

    def _run_generation_worker(client_inst, prompt, save_dir, naming, goal, remove_wm, use_gpu, extra_meta):
        """Background thread: runs the generation loop."""
        async def _loop():
            client_inst.clear_stop()
            with client_inst._lock:
                client_inst._stats["is_running"] = True
                client_inst._stats["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            current_start = naming["start"]

            for i in range(goal):
                if client_inst.is_stop_requested():
                    api_log(f"⛔ Stopped by user after {i} iterations.")
                    break

                api_log(f"🔄 Generating image {i + 1}/{goal}...")
                iter_naming = {**naming, "start": current_start}
                result = await client_inst.generate_image(
                    prompt=prompt,
                    save_dir=save_dir,
                    naming_cfg=iter_naming,
                    extra_meta=extra_meta,
                )

                status = result.get("status")
                if status == "success":
                    paths = result.get("saved_paths", [])
                    current_start = result.get("next_start", current_start)
                    api_log(f"✅ Saved: {', '.join(os.path.basename(p) for p in paths)}")

                    # Update start number on disk
                    try:
                        save_cfg_disk({"name_start": current_start})
                    except Exception:
                        pass

                    # Watermark removal
                    if remove_wm and paths:
                        try:
                            api_log("🧹 Removing watermark...")
                            from gemini_api_client import GeminiAPIClient
                            processed = GeminiAPIClient.process_watermark(paths, save_dir, use_gpu=use_gpu)
                            if processed:
                                api_log(f"✅ Processed: {', '.join(os.path.basename(p) for p in processed)}")
                        except Exception as wm_err:
                            api_log(f"⚠️ Watermark removal failed: {wm_err}")

                    # Store for preview
                    st.session_state.api_last_images = paths

                elif status == "refused":
                    reason = result.get("reason", "Unknown")
                    api_log(f"🚫 Refused: {reason[:200]}")
                else:
                    msg = result.get("message", "Unknown error")
                    api_log(f"❌ Error: {msg[:200]}")

            with client_inst._lock:
                client_inst._stats["is_running"] = False
            st.session_state.api_running = False
            api_log("🏁 Generation loop finished.")

        asyncio.run(_loop())

    is_running = st.session_state.api_running
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button(
            "🚀 Generate" if not is_running else "⏳ Running...",
            width="stretch",
            type="primary",
            disabled=is_running or not key_ok,
        ):
            client = get_api_client()
            if client:
                st.session_state.api_running = True
                naming = {
                    "prefix": st.session_state.api_name_prefix,
                    "padding": st.session_state.api_name_padding,
                    "start": st.session_state.api_name_start,
                }
                meta = {
                    "prompt": prompt_text,
                    "model": st.session_state.api_model,
                    "source": "gemini_api",
                }
                t = threading.Thread(
                    target=_run_generation_worker,
                    args=(
                        client,
                        prompt_text,
                        st.session_state.api_save_dir,
                        naming,
                        api_goal,
                        st.session_state.api_remove_wm,
                        st.session_state.api_use_gpu,
                        meta,
                    ),
                    daemon=True,
                )
                add_script_run_ctx(t)
                t.start()
                time.sleep(0.3)
                st.rerun()

    with btn_col2:
        if st.button("⛔ Stop", width="stretch", disabled=not is_running):
            client = get_api_client()
            if client:
                client.request_stop()
                st.session_state.api_stop_requested = True
                api_log("⛔ Stop requested...")
                st.rerun()

    with btn_col3:
        if st.button("🔄 Reset Stats", width="stretch", disabled=is_running):
            client = get_api_client()
            if client:
                client.reset_stats()
                st.session_state.api_last_images = []
                api_log("📊 Stats reset.")
                st.rerun()


with col_preview:
    st.markdown("#### 🖼️ Last Generated")

    # Show last generated images
    last_imgs = st.session_state.api_last_images
    if last_imgs:
        for img_path in last_imgs[-4:]:  # Show up to 4 most recent
            if os.path.exists(img_path):
                try:
                    st.image(img_path, caption=os.path.basename(img_path), width="stretch")
                except Exception:
                    st.caption(f"📄 {os.path.basename(img_path)}")
    else:
        st.info("No images generated yet. Configure your prompt and click Generate!")


# ── Logs ────────────────────────────────────────────────────────────────────
st.divider()

# Auto-refresh when running
if st.session_state.api_running:
    @st.fragment(run_every="3s")
    def _auto_refresh_logs():
        logs = st.session_state.api_logs
        if logs:
            st.code("\n".join(logs[-30:]), language="text")
        # Check if generation finished
        if not st.session_state.api_running:
            st.rerun()
    
    st.markdown("#### 📋 Live Logs")
    _auto_refresh_logs()
else:
    with st.expander("📋 Logs", expanded=bool(st.session_state.api_logs)):
        if st.session_state.api_logs:
            st.code("\n".join(st.session_state.api_logs[-30:]), language="text")
        else:
            st.caption("No logs yet.")
