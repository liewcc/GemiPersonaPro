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
                                break

                    record = {
                        "account": current_account,
                        "time": start_ts_str,
                        "health": f"{duration_secs}s",
                        "artifact": filename,
                        "status": "Success" if filename else "Normal",
                        "session_index": session_index
                    }
                    
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
    
    summary_list = sorted(list(summary_results.values()), key=lambda x: x['time'], reverse=True)
    detailed_list = sorted(detailed_results, key=lambda x: x['time'], reverse=True)
    
    return summary_list, detailed_list, sorted(list(found_accounts_set))

# --- Sidebar Navigation ---
with st.sidebar:
    st.markdown("<p style='font-weight: bold; color: #a0a0ff; margin-bottom: 10px;'>SYSTEM NAVIGATION</p>", unsafe_allow_html=True)
    menu_selection = st.radio("Select Section", ["Settings & Credentials", "Account Health Analysis"], label_visibility="collapsed")
    st.markdown("---")
    st.info("Configuration and monitoring tools.")

# --- Main Logic ---
config = load_config()
login_data = load_login_lookup()

st.session_state.cfg_show_console = config.get("show_engine_console", True)
st.session_state.cfg_headless = config.get("headless", False)
st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)
st.session_state.cfg_watchdog_delay = config.get("watchdog_initial_delay", 20)
st.session_state.cfg_quota_cooldown_hrs = config.get("quota_cooldown_hours", 24)

st.session_state.login_rows = list(login_data)
st.session_state._login_reload = False

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

if menu_selection == "Settings & Credentials":
    col_engine, col_watchdog = st.columns([1, 1])
    with col_engine:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>ENGINE SETTINGS</p>", unsafe_allow_html=True)
        with st.container(border=True):
            st.toggle("Show Engine Console Window", key="cfg_show_console", on_change=on_change_console)
            st.toggle("Run Browser Headless", key="cfg_headless", on_change=on_change_headless)
            st.number_input("Heartbeat Timeout (seconds)", min_value=0, max_value=86400, key="cfg_timeout", on_change=on_change_timeout)
            st.number_input("Watchdog Initial Delay (seconds)", min_value=5, max_value=120, step=5, key="cfg_watchdog_delay", on_change=on_change_watchdog_delay)
            st.number_input("Quota Cooldown (hours)", min_value=0, max_value=168, step=1, key="cfg_quota_cooldown_hrs", on_change=on_change_quota_cooldown)

    with col_watchdog:
        st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>WATCHDOG LOG</p>", unsafe_allow_html=True)
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
            else: st.text_area("Log Output", value=log_content, height=200, disabled=True, label_visibility="collapsed")

    col_quota, col_cred = st.columns([1, 3])
    with col_quota:
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

    with col_cred:
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
                    for r in rows: r["quota_full"] = ""
                    save_login_lookup(rows); st.session_state._login_reload = True; st.rerun()
            with btn_clear_stats:
                if st.button("Reset Stats", icon="🧹", width="stretch"):
                    for r in rows: r["last_switched_at"] = ""; r["session_images"] = r["session_refused"] = r["session_resets"] = ""
                    save_login_lookup(rows); st.session_state._login_reload = True; st.rerun()

elif menu_selection == "Account Health Analysis":
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

        col_sel, col_btn1, col_btn2 = st.columns([2, 0.6, 0.6])
        with col_sel:
            view_mode = st.selectbox(
                "Select View Mode",
                options=["Full Loading History (All Events)", "Detailed History: Active Account", "Latest Summary (All Accounts)"] + [f"Detailed History: {acc}" for acc in final_dropdown_accs],
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

        st.markdown("---")
        
        if is_full_history:
            st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing every recorded loading event in chronological order (latest first).</p>", unsafe_allow_html=True)
            _, all_detailed, _ = parse_account_health(target_account="ALL_EVENTS", login_data=login_data)
            if not all_detailed:
                st.info("No loading records found in engine.log.")
            else:
                if st.session_state.show_health_graph:
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>All Events</b></p>", unsafe_allow_html=True)
                    chart_df = pd.DataFrame(all_detailed)
                    chart_df["Seconds"] = chart_df["health"].str.replace("s", "").astype(float)
                    
                    # In All Events view, we use the absolute session_index to alternate colors on every account switch
                    chart_df["variant"] = chart_df["session_index"].apply(lambda x: "Base" if x % 2 == 1 else "Light")

                    # Color definitions
                    base_colors = {'Success': '#2ecc71', 'Normal': '#a0a0ff'}
                    light_colors = {'Success': '#a0e6b5', 'Normal': '#d0d0ff'}
                    legend_labels = ['Success (Base)', 'Normal (Base)', 'Success (Light)', 'Normal (Light)']
                    legend_colors = [base_colors['Success'], base_colors['Normal'],
                                     light_colors['Success'], light_colors['Normal']]

                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                    
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('time:N', title=None, axis=alt.Axis(labelOverlap='parity')),
                        y=alt.Y('Seconds:Q', title=None),
                        color=alt.Color('legend:N', 
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors), 
                                        legend=alt.Legend(title=None, orient='bottom')),
                        tooltip=['time', 'account', 'health', 'artifact', 'status']
                    ).properties(height=400)
                    
                    st.altair_chart(chart, width="stretch")
                else:
                    st.data_editor(
                        pd.DataFrame(all_detailed),
                        column_config={
                            "account": st.column_config.TextColumn("Account"),
                            "time": st.column_config.TextColumn("Time"),
                            "health": st.column_config.TextColumn("Health"),
                            "artifact": st.column_config.TextColumn("Artifact"),
                            "status": st.column_config.TextColumn("Status")
                        },
                        disabled=True,
                        width="stretch",
                        hide_index=True,
                        height=450,
                        key="health_full_history_table"
                    )
        elif is_active_account:
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
                        _chart_df = pd.DataFrame(_active_detailed)
                        _chart_df["Seconds"] = _chart_df["health"].str.replace("s", "").astype(float)
                        _chart_df["cycle"] = _chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                        _chart_df["variant"] = _chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                        _base_colors = {'Success': '#2ecc71', 'Normal': '#a0a0ff'}
                        _light_colors = {'Success': '#a0e6b5', 'Normal': '#d0d0ff'}
                        _legend_labels = ['Success (Base)', 'Normal (Base)', 'Success (Light)', 'Normal (Light)']
                        _legend_colors = [_base_colors['Success'], _base_colors['Normal'], _light_colors['Success'], _light_colors['Normal']]
                        _chart_df['legend'] = _chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                        _chart = alt.Chart(_chart_df).mark_bar().encode(
                            x=alt.X('time:N', title=None, axis=alt.Axis(labelOverlap='parity')),
                            y=alt.Y('Seconds:Q', title=None),
                            color=alt.Color('legend:N',
                                            scale=alt.Scale(domain=_legend_labels, range=_legend_colors),
                                            legend=alt.Legend(title=None, orient='bottom')),
                            tooltip=['time', 'account', 'health', 'artifact', 'status']
                        ).properties(height=400)
                        st.altair_chart(_chart, width="stretch")
                    else:
                        st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing all loading performance records for <b>{_active_user}</b> (Active Account).</p>", unsafe_allow_html=True)
                        st.data_editor(
                            pd.DataFrame(_active_detailed),
                            column_config={
                                "account": st.column_config.TextColumn("Account"),
                                "time": st.column_config.TextColumn("Time"),
                                "health": st.column_config.TextColumn("Health"),
                                "artifact": st.column_config.TextColumn("Artifact", help="Downloaded image filename"),
                                "status": st.column_config.TextColumn("Status")
                            },
                            disabled=True,
                            width="stretch",
                            hide_index=True,
                            height=450,
                            key="health_active_account_table"
                        )
        elif is_latest_summary:
            st.markdown("<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing the last recorded loading performance for each account.</p>", unsafe_allow_html=True)
            if not summary_all:
                st.info("No loading records found in engine.log.")
            else:
                st.data_editor(
                    pd.DataFrame(summary_all),
                    column_config={
                        "account": st.column_config.TextColumn("Account"),
                        "time": st.column_config.TextColumn("Time"),
                        "health": st.column_config.TextColumn("Health"),
                        "artifact": st.column_config.TextColumn("Artifact", help="Last successful image filename"),
                        "status": st.column_config.TextColumn("Status")
                    },
                    disabled=True,
                    width="stretch",
                    hide_index=True,
                    height=450,
                    key="health_summary_table"
                )
        else:
            # Detailed mode
            target_acc = view_mode.replace("Detailed History: ", "")
            _, detailed_list, _ = parse_account_health(target_account=target_acc, login_data=login_data)
            
            if not detailed_list:
                st.info(f"No detailed records found for {target_acc}.")
            else:
                if st.session_state.show_health_graph:
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Performance Graph for <b>{target_acc}</b></p>", unsafe_allow_html=True)
                    
                    # Prepare data for chart
                    chart_df = pd.DataFrame(detailed_list)
                    chart_df["Seconds"] = chart_df["health"].str.replace("s", "").astype(float)
                    
                    # Cycle is the rank of the session_index among all sessions for that account
                    chart_df["cycle"] = chart_df.groupby("account")["session_index"].rank(method="dense").astype(int)
                    chart_df["variant"] = chart_df["cycle"].apply(lambda x: "Base" if x % 2 == 1 else "Light")
                    
                    # Color definitions
                    base_colors = {'Success': '#2ecc71', 'Normal': '#a0a0ff'}
                    light_colors = {'Success': '#a0e6b5', 'Normal': '#d0d0ff'}
                    legend_labels = ['Success (Base)', 'Normal (Base)', 'Success (Light)', 'Normal (Light)']
                    legend_colors = [base_colors['Success'], base_colors['Normal'],
                                     light_colors['Success'], light_colors['Normal']]

                    chart_df['legend'] = chart_df.apply(lambda r: f"{r['status']} ({r['variant']})", axis=1)
                    
                    chart = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('time:N', title=None, axis=alt.Axis(labelOverlap='parity')),
                        y=alt.Y('Seconds:Q', title=None),
                        color=alt.Color('legend:N', 
                                        scale=alt.Scale(domain=legend_labels, range=legend_colors), 
                                        legend=alt.Legend(title=None, orient='bottom')),
                        tooltip=['time', 'account', 'health', 'artifact', 'status']
                    ).properties(height=400)
                    
                    st.altair_chart(chart, width="stretch")
                else:
                    st.markdown(f"<p style='color: #a0a0ff; font-size: 0.9em; margin-bottom: 10px;'>Showing all loading performance records for <b>{target_acc}</b>.</p>", unsafe_allow_html=True)
                    st.data_editor(
                        pd.DataFrame(detailed_list),
                        column_config={
                            "account": st.column_config.TextColumn("Account"),
                            "time": st.column_config.TextColumn("Time"),
                            "health": st.column_config.TextColumn("Health"),
                            "artifact": st.column_config.TextColumn("Artifact", help="Downloaded image filename"),
                            "status": st.column_config.TextColumn("Status")
                        },
                        disabled=True,
                        width="stretch",
                        hide_index=True,
                        height=450,
                        key=f"health_detailed_{target_acc}"
                    )
