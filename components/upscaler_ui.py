import streamlit as st
import os
import json
import time
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
from config_utils import load_config, save_config, load_login_lookup
from processing_utils import open_file_foreground

def select_folder():
    """Opens a native Windows folder picker."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', True)
    path = filedialog.askdirectory()
    root.update()
    root.destroy()
    time.sleep(0.1)
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

    # Delete Activity state from config
    del_act_cfg = upscale_cfg.get("delete_activity", {})
    if "up_del_enabled" not in st.session_state: st.session_state.up_del_enabled = del_act_cfg.get("enabled", False)
    if "up_del_range" not in st.session_state: st.session_state.up_del_range = del_act_cfg.get("range", "Last hour")
    if "up_del_trigger" not in st.session_state: st.session_state.up_del_trigger = del_act_cfg.get("trigger", "After Stop")

    # Max Redo state from config
    if "up_max_redo_enabled" not in st.session_state: st.session_state.up_max_redo_enabled = upscale_cfg.get("max_redo_enabled", False)
    if "up_max_redo" not in st.session_state: st.session_state.up_max_redo = upscale_cfg.get("max_redo", 3)

    # Start Index state from config
    if "up_start_index" not in st.session_state: st.session_state.up_start_index = upscale_cfg.get("start_index", 1)

    def _save_all_upscaler_settings():
        save_config({"upscaler": {
            "profile": st.session_state.up_profile,
            "input_dir": st.session_state.up_input,
            "output_dir": st.session_state.up_output,
            "prompt": st.session_state.up_prompt,
            "headless": st.session_state.up_headless,
            "delete_activity": {
                "enabled": st.session_state.up_del_enabled,
                "range": st.session_state.up_del_range,
                "trigger": st.session_state.up_del_trigger
            },
            "max_redo_enabled": st.session_state.up_max_redo_enabled,
            "max_redo": st.session_state.up_max_redo,
            "start_index": st.session_state.up_start_index
        }})

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
            
            input_col, in_btn, in_view_btn = st.columns([4, 1, 0.5])
            with input_col:
                input_w = st.text_input("Input Directory (Images to Upscale)", value=st.session_state.up_input)
            with in_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Browse", key="up_in_btn", width="stretch"):
                    sel = select_folder()
                    if sel:
                        input_w = sel
            with in_view_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📂", key="up_in_view_btn", help="Open Folder", width="stretch"):
                    if input_w and os.path.exists(input_w):
                        open_file_foreground(input_w)

            # Auto-fill output directory if input changed
            if input_w != st.session_state.up_input and input_w:
                auto_output = os.path.join(input_w, "Upscale").replace("\\", "/")
                st.session_state.up_output = auto_output

            output_col, out_btn, out_view_btn = st.columns([4, 1, 0.5])
            with output_col:
                output_w = st.text_input("Output Directory", value=st.session_state.up_output)
            with out_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Browse", key="up_out_btn", width="stretch"):
                    sel = select_folder()
                    if sel:
                        output_w = sel
            with out_view_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📂", key="up_out_view_btn", help="Open Folder", width="stretch"):
                    if output_w and os.path.exists(output_w):
                        open_file_foreground(output_w)

            prompt_w = st.text_area("Upscale Prompt", value=st.session_state.up_prompt, height=100)
            
            headless_w = st.toggle("Run Headless (Hidden Browser)", value=st.session_state.up_headless, help="Turn off to see the browser window and observe what goes wrong.")

            # Save logic
            if profile_w != st.session_state.up_profile or input_w != st.session_state.up_input or output_w != st.session_state.up_output or prompt_w != st.session_state.up_prompt or headless_w != st.session_state.up_headless:
                st.session_state.up_profile = profile_w
                st.session_state.up_input = input_w
                st.session_state.up_output = output_w
                st.session_state.up_prompt = prompt_w
                st.session_state.up_headless = headless_w
                _save_all_upscaler_settings()
                st.rerun()

            # --- Delete Activity Controls ---
            del_col_toggle, del_col_range, del_col_trigger = st.columns([1.2, 1, 1])
            with del_col_toggle:
                del_enabled_w = st.toggle("🗑️ Delete Activity", value=st.session_state.up_del_enabled, help="Automatically delete Gemini activity history at the selected trigger point.")
            
            if del_enabled_w:
                range_options = ["Last hour", "Last day", "All time"]
                trigger_options = ["After Start", "After Stop"]
                try: range_idx = range_options.index(st.session_state.up_del_range)
                except ValueError: range_idx = 0
                try: trigger_idx = trigger_options.index(st.session_state.up_del_trigger)
                except ValueError: trigger_idx = 1
                
                with del_col_range:
                    del_range_w = st.selectbox("Time Range", options=range_options, index=range_idx, key="up_del_range_select", label_visibility="collapsed")
                with del_col_trigger:
                    del_trigger_w = st.selectbox("Trigger", options=trigger_options, index=trigger_idx, key="up_del_trigger_select", label_visibility="collapsed")
            else:
                del_range_w = st.session_state.up_del_range
                del_trigger_w = st.session_state.up_del_trigger

            # Persist delete activity settings on change
            if del_enabled_w != st.session_state.up_del_enabled or del_range_w != st.session_state.up_del_range or del_trigger_w != st.session_state.up_del_trigger:
                st.session_state.up_del_enabled = del_enabled_w
                st.session_state.up_del_range = del_range_w
                st.session_state.up_del_trigger = del_trigger_w
                _save_all_upscaler_settings()
                st.rerun()

            # --- Max Redo Limit & Start Index Controls ---
            redo_col_toggle, redo_col_input, start_label_col, start_input_col = st.columns([1.2, 0.8, 0.6, 0.4])
            with redo_col_toggle:
                redo_enabled_w = st.toggle("🔄 Max Redo Limit", value=st.session_state.up_max_redo_enabled, help="Automatically skip to the next image if Gemini refuses the prompt repeatedly.")
            
            with redo_col_input:
                redo_val_w = st.number_input("Max Redos per Image", min_value=1, max_value=20, value=st.session_state.up_max_redo, step=1, label_visibility="collapsed", disabled=not redo_enabled_w)

            with start_label_col:
                st.markdown("<div style='margin-top: 4px; text-align: right;' title='Starting file number (1-based index)'>Start File No.</div>", unsafe_allow_html=True)

            with start_input_col:
                start_idx_w = st.number_input("Start File No.", min_value=1, value=st.session_state.up_start_index, step=1, help="Starting file number (1-based index)", label_visibility="collapsed")

            if redo_enabled_w != st.session_state.up_max_redo_enabled or redo_val_w != st.session_state.up_max_redo or start_idx_w != st.session_state.up_start_index:
                st.session_state.up_max_redo_enabled = redo_enabled_w
                st.session_state.up_max_redo = redo_val_w
                st.session_state.up_start_index = start_idx_w
                _save_all_upscaler_settings()
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
                        
                        _save_all_upscaler_settings()
                        
                        cmd = [
                            sys.executable, "upscaler_worker.py",
                            "--profile", profile_w,
                            "--input", input_w,
                            "--output", output_w,
                            "--prompt", prompt_w
                        ]
                        if not headless_w:
                            cmd.append("--show-browser")
                        # Pass delete activity args
                        if del_enabled_w:
                            cmd.extend(["--delete-activity", del_range_w, "--delete-trigger", del_trigger_w])
                        # Pass max redo args
                        if redo_enabled_w:
                            cmd.extend(["--max-redo", str(redo_val_w)])
                        
                        cmd.extend(["--start-index", str(start_idx_w)])
                        
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
                    
                    # 3. Cleanup lock file
                    try: os.remove("upscaler.lock")
                    except: pass

                    # 4. If delete activity After Stop is enabled, spawn a standalone delete process
                    if st.session_state.up_del_enabled and st.session_state.up_del_trigger == "After Stop":
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                from datetime import datetime
                                ts = datetime.now().strftime("[%H:%M:%S]")
                                f.write(f"{ts} 🗑️ Launching standalone delete activity ({st.session_state.up_del_range})...\n")
                        except: pass
                        try:
                            del_cmd = [
                                sys.executable, "upscaler_worker.py",
                                "--profile", st.session_state.up_profile,
                                "--delete-only",
                                "--delete-activity", st.session_state.up_del_range
                            ]
                            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                            subprocess.Popen(del_cmd, creationflags=flags)
                        except Exception as del_e:
                            st.toast(f"⚠️ Delete activity launch failed: {del_e}")
                    else:
                        # Only clean up sandbox if no delete subprocess will use it
                        try:
                            import shutil as _shutil
                            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                            sandbox_default = os.path.join(root, "upscaler_session_sandbox", "Default")
                            if os.path.exists(sandbox_default):
                                subprocess.run(['rmdir', sandbox_default], shell=True, capture_output=True)
                                if os.path.exists(sandbox_default):
                                    _shutil.rmtree(sandbox_default, ignore_errors=True)
                        except: pass
                    
                    st.toast("⛔ Stop signal sent and browser closed.")
                    st.rerun()

    with col2:
        with st.container(border=True):
            log_c1, log_c2, log_c3 = st.columns([2, 1, 1])
            with log_c1:
                st.markdown("#### 📋 Progress Log")
            with log_c2:
                with st.popover("📊 Status", key="upscaler_status_popover"):
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
                            st_val = info.get("status")
                            if st_val == "processing": status_icon = "🔄"
                            elif st_val == "skipped": status_icon = "💨"
                            elif st_val == "error": status_icon = "❌"
                            else: status_icon = "✅"
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
