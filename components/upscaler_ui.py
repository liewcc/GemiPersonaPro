import streamlit as st
import os
import json
import time
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
from config_utils import load_config, save_config, load_login_lookup

def select_folder():
    """Opens a native Windows folder picker."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', True)
    path = filedialog.askdirectory()
    root.destroy()
    return path

def render_upscaler_tab():
    cfg = load_config()
    upscale_cfg = cfg.get("upscaler", {})

    # Init session state from config
    if "up_profile" not in st.session_state: st.session_state.up_profile = upscale_cfg.get("profile", "Profile 1")
    if "up_input" not in st.session_state: st.session_state.up_input = upscale_cfg.get("input_dir", "")
    if "up_output" not in st.session_state: st.session_state.up_output = upscale_cfg.get("output_dir", "")
    if "up_prompt" not in st.session_state: st.session_state.up_prompt = upscale_cfg.get("prompt", "Please upscale this image to 4K quality, keep it exactly as it is and do not change the content.")
    if "up_headless" not in st.session_state: st.session_state.up_headless = upscale_cfg.get("headless", True)

    col1, col2 = st.columns([1.5, 1])

    with col1:
        with st.container(border=True):
            st.markdown("#### ⚙️ Settings")
            
            # Load verified accounts from user_login_lookup
            logins = load_login_lookup()
            verified_accounts = [acc["username"] for acc in logins if "username" in acc]
            if not verified_accounts:
                verified_accounts = ["Profile 1"] # Fallback
                
            # Find index of current profile if it exists
            try:
                prof_idx = verified_accounts.index(st.session_state.up_profile)
            except ValueError:
                prof_idx = 0
                
            profile_w = st.selectbox("Paid Account Profile", options=verified_accounts, index=prof_idx, help="Select your fixed paid account. These are loaded from your verified accounts list.")
            
            input_col, in_btn = st.columns([4, 1])
            with input_col:
                input_w = st.text_input("Input Directory (Images to Upscale)", value=st.session_state.up_input)
            with in_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Browse", key="up_in_btn", width="stretch"):
                    sel = select_folder()
                    if sel:
                        input_w = sel

            output_col, out_btn = st.columns([4, 1])
            with output_col:
                output_w = st.text_input("Output Directory", value=st.session_state.up_output)
            with out_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Browse", key="up_out_btn", width="stretch"):
                    sel = select_folder()
                    if sel:
                        output_w = sel

            prompt_w = st.text_area("Upscale Prompt", value=st.session_state.up_prompt, height=100)
            
            headless_w = st.toggle("Run Headless (Hidden Browser)", value=st.session_state.up_headless, help="Turn off to see the browser window and observe what goes wrong.")

            # Save logic
            if profile_w != st.session_state.up_profile or input_w != st.session_state.up_input or output_w != st.session_state.up_output or prompt_w != st.session_state.up_prompt or headless_w != st.session_state.up_headless:
                st.session_state.up_profile = profile_w
                st.session_state.up_input = input_w
                st.session_state.up_output = output_w
                st.session_state.up_prompt = prompt_w
                st.session_state.up_headless = headless_w
                save_config({"upscaler": {
                    "profile": profile_w,
                    "input_dir": input_w,
                    "output_dir": output_w,
                    "prompt": prompt_w,
                    "headless": headless_w
                }})
                st.rerun()

            # Process state
            log_path = "upscaler.log"
            is_running = os.path.exists("upscaler.lock")

            if not is_running:
                if st.button("🚀 Start Upscaling", type="primary", width="stretch"):
                    if not input_w or not output_w:
                        st.error("Please specify Input and Output directories.")
                    elif not os.path.isdir(input_w):
                        st.error("Input directory does not exist.")
                    else:
                        try:
                            if os.path.exists(log_path):
                                os.remove(log_path)
                            with open(log_path, "w", encoding="utf-8") as f:
                                from datetime import datetime
                                ts = datetime.now().strftime("[%H:%M:%S]")
                                f.write(f"{ts} 🚀 Starting upscaler background worker...\n")
                        except: pass
                        
                        save_config({"upscaler": {
                            "profile": profile_w,
                            "input_dir": input_w,
                            "output_dir": output_w,
                            "prompt": prompt_w,
                            "headless": headless_w
                        }})
                        
                        cmd = [
                            sys.executable, "upscaler_worker.py",
                            "--profile", profile_w,
                            "--input", input_w,
                            "--output", output_w,
                            "--prompt", prompt_w
                        ]
                        if not headless_w:
                            cmd.append("--show-browser")
                        
                        try:
                            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                            proc = subprocess.Popen(cmd, creationflags=flags)
                            with open("upscaler.lock", "w") as f:
                                f.write(str(proc.pid))
                            st.toast("🚀 Upscaler background worker started!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to start worker: {e}")
            else:
                if st.button("⛔ Stop Upscaling", width="stretch"):
                    # 1. Force kill the process and its children (browser)
                    try:
                        if os.path.exists("upscaler.lock"):
                            with open("upscaler.lock", "r") as f:
                                pid = f.read().strip()
                            if pid:
                                # Use taskkill on Windows to kill the entire process tree
                                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], shell=True, capture_output=True)
                    except Exception as e:
                        st.error(f"Error killing process: {e}")
                    
                    # 2. Log stopping action
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            from datetime import datetime
                            ts = datetime.now().strftime("[%H:%M:%S]")
                            f.write(f"{ts} ⛔ Stop button clicked. Browser closed immediately.\n")
                    except: pass
                    
                    # 3. Cleanup
                    try: os.remove("upscaler.lock")
                    except: pass
                    try:
                        # Path to sandbox junction relative to this file's parent
                        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        sandbox_default = os.path.join(root, "upscaler_session_sandbox", "Default")
                        if os.path.exists(sandbox_default):
                            subprocess.run(['rmdir', sandbox_default], shell=True, capture_output=True)
                    except: pass
                    
                    st.toast("⛔ Stop signal sent and browser closed.")
                    st.rerun()

    with col2:
        with st.container(border=True):
            log_c1, log_c2, log_c3 = st.columns([2, 1, 1])
            with log_c1:
                st.markdown("#### 📋 Progress Log")
            with log_c2:
                with st.popover("📊 Status", width="stretch"):
                    @st.fragment(run_every="1s")
                    def render_status():
                        status_file = "upscaler_status.json"
                        if not os.path.exists(status_file):
                            st.info("No status data available yet.")
                            return
                        try:
                            with open(status_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                        except Exception as e:
                            st.error(f"Could not read status: {e}")
                            return
                            
                        current_file = data.get("current_file", "None")
                        history = data.get("history", {})
                        
                        st.markdown(f"**Currently Processing:** `{current_file}`")
                        
                        table_data = []
                        # Show latest files first
                        for fname in reversed(list(history.keys())):
                            info = history[fname]
                            status_icon = "🔄" if info.get("status") == "processing" else "✅"
                            table_data.append({
                                "File": f"{status_icon} {fname}",
                                "Refusals": info.get("refusals", 0)
                            })
                            
                        if table_data:
                            st.dataframe(table_data, width="stretch", hide_index=True)
                        else:
                            st.info("No files processed yet.")
                    
                    render_status()
            with log_c3:
                if st.button("🗑️ Clear Log", key="up_clear_log", width="stretch"):
                    try: os.remove(log_path)
                    except: pass
            
            @st.fragment(run_every="3s")
            def render_log_pane():
                log_text = "Waiting for background worker to start..."
                # Use a fixed height container for vertical scrolling
                with st.container(height=445):
                    if os.path.exists(log_path):
                        try:
                            with open(log_path, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                                # Load more lines and reverse so latest are at the top
                                log_text = "".join(reversed(lines[-100:]))
                        except:
                            pass
                    
                    st.code(log_text, language="text")
                    
                is_currently_running = os.path.exists("upscaler.lock")
                if is_currently_running:
                    st.session_state.up_was_running = True
                else:
                    if st.session_state.get("up_was_running", False):
                        st.session_state.up_was_running = False
                        st.rerun()
            
            render_log_pane()
