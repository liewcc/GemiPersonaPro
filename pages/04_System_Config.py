import streamlit as st
import json
import os
import pandas as pd
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

# --- Main Logic ---

config = load_config()
login_data = load_login_lookup()

# --- Page Entry Detection & Force Reload ---
if st.session_state.get("_last_config_page") != "System_Config":
    st.session_state._last_config_page = "System_Config"
    
    # Force fresh reload from disk to ensure we have the latest data
    config = load_config()
    login_data = load_login_lookup()
    
    # Overwrite session state with latest config values
    st.session_state.cfg_show_console = config.get("show_engine_console", True)
    st.session_state.cfg_headless = config.get("headless", False)
    st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)
    
    # Force reload of login rows and clear any unsaved editor states
    st.session_state.login_rows = list(login_data)
    st.session_state._login_reload = False
    
    # Clear Streamlit data_editor widget states to discard unsaved UI edits
    if "quota_editor" in st.session_state:
        del st.session_state["quota_editor"]
    if "login_editor" in st.session_state:
        del st.session_state["login_editor"]

# Ensure keys exist if it IS the first run of the session
if "cfg_show_console" not in st.session_state:
    st.session_state.cfg_show_console = config.get("show_engine_console", True)
if "cfg_headless" not in st.session_state:
    st.session_state.cfg_headless = config.get("headless", False)
if "cfg_timeout" not in st.session_state:
    st.session_state.cfg_timeout = config.get("heartbeat_timeout", 3600)

WATCHDOG_LOG_PATH = "watchdog.log"

def get_watchdog_log():
    if not os.path.exists(WATCHDOG_LOG_PATH):
        return None
    try:
        with open(WATCHDOG_LOG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading log: {e}"

def clear_watchdog_log():
    try:
        # Open in write mode to clear contents, preventing conflict if watchdog is just appending
        with open(WATCHDOG_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        st.error(f"Failed to clear log: {e}")

# Section 1 & Watchdog Log: Split into two columns
col_engine, col_watchdog = st.columns([1, 1])

# --- Section 1: Engine Settings ---
with col_engine:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>ENGINE SETTINGS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        st.toggle(
            "Show Engine Console Window",
            key="cfg_show_console",
            on_change=on_change_console,
            help="If enabled, the background service will run in a visible console window."
        )

        st.toggle(
            "Run Browser Headless",
            key="cfg_headless",
            on_change=on_change_headless,
            help="If enabled, the browser will run in the background."
        )

        st.number_input(
            "Heartbeat Timeout (seconds)",
            min_value=0,
            max_value=86400,
            key="cfg_timeout",
            on_change=on_change_timeout,
            help="0 = Always stays alive."
        )

# --- Watchdog Log ---
with col_watchdog:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>WATCHDOG LOG</p>", unsafe_allow_html=True)
    with st.container(border=True):
        log_content = get_watchdog_log()
        
        # Display Reload and Clear Log buttons side-by-side
        btn_col1, btn_col2 = st.columns([1, 1])
        with btn_col1:
            if st.button("Reload Log", key="btn_reload_watchdog", icon="🔄", help="Reload the latest watchdog log", type="secondary", width='stretch'):
                st.rerun()
        with btn_col2:
            if st.button("Clear Log", key="btn_clear_watchdog", icon="🗑️", help="Clear the watchdog log completely", type="secondary", width='stretch'):
                clear_watchdog_log()
                st.rerun()

        st.markdown("") # Spacer
        if log_content is None:
            st.info("Watchdog log not found or no errors detected.")
        elif not log_content.strip():
            st.info("Watchdog log is empty.")
        else:
            st.text_area("Log Output", value=log_content, height=200, disabled=True, label_visibility="collapsed")


# Layout for Quota & Credentials -> 1:3 ratio
col_quota, col_cred = st.columns([1, 3])

# --- Section 2: Quota Detection Settings ---
with col_quota:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>QUOTA FULL PHRASES</p>", unsafe_allow_html=True)
    with st.container(border=True):
        quota_phrases = config.get("quota_full", [])
        quota_df = pd.DataFrame([{"phrase": p} for p in quota_phrases])

        edited_quota_df = st.data_editor(
            quota_df,
            column_config={
                "phrase": st.column_config.TextColumn("Identification Phrase", width="stretch"),
            },
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            height=415,
            key="quota_editor"
        )
        
        # Spacer padding to visually align the bottom contour of this container with the taller right container
        st.markdown("<div style='height: 85px;'></div>", unsafe_allow_html=True)

        if st.button("Save Quota Phrases", icon="📝", width='stretch'):
            new_phrases = edited_quota_df["phrase"].tolist()
            new_phrases = [p.strip() for p in new_phrases if p is not None and p.strip()]
            save_config({"quota_full": new_phrases})
            st.success("Quota phrases updated!")
            st.rerun()

# --- Section 3: Credential Management ---
with col_cred:
    st.markdown("<p style='font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase;'>USER LOGIN CREDENTIALS</p>", unsafe_allow_html=True)
    with st.container(border=True):
        # login_rows is now handled by the page entry reload logic at the top,
        # but we keep this check for manual trigger or safety.
        if "login_rows" not in st.session_state or st.session_state.get("_login_reload"):
            st.session_state.login_rows = list(login_data)
            st.session_state._login_reload = False

        rows = st.session_state.login_rows
        usernames = [r.get("username", "") for r in rows if r.get("username")]

        active_index = 0
        for i, r in enumerate(rows):
            if r.get("active"):
                active_index = i
                break

        if usernames:
            selected_active = st.selectbox(
                "Active Account",
                options=usernames,
                index=min(active_index, len(usernames) - 1),
                help="Select the account to use for the current session",
                key="active_account_select"
            )
        else:
            selected_active = None
            st.info("Add a new credential row below to get started.")

        st.markdown("")

        editor_data = [
            {
                "active": r.get("active", False),
                "bypass": r.get("bypass", False),
                "username": r.get("username", ""), 
                "auto_delete": r.get("auto_delete", False),
                "delete_range": r.get("delete_range", "Last hour"),
                "note": r.get("note", ""),
                "quota_full": r.get("quota_full", "")
            }
            for r in rows
        ]
        editor_df = pd.DataFrame(editor_data) if editor_data else pd.DataFrame(columns=["active", "bypass", "username", "auto_delete", "delete_range", "note", "quota_full"])

        # 这里的 width 设为 "content" 以确保紧凑且不报错
        edited_df = st.data_editor(
            editor_df,
            column_config={
                "active": st.column_config.CheckboxColumn(
                    "Active",
                    help="Current active account",
                    disabled=True,
                    width="small"
                ),
                "bypass": st.column_config.CheckboxColumn(
                    "Bypass",
                    help="Skip this account during automated looping",
                    width="small"
                ),
                "username": st.column_config.TextColumn("Username", width="medium"),
                "auto_delete": st.column_config.CheckboxColumn("Auto Delete", help="Auto delete history on switch", width="small"),
                "delete_range": st.column_config.SelectboxColumn("Range", options=["Last hour", "Last day", "All time"], help="Deletion time range", width="small"),
                "note": st.column_config.TextColumn("Note", width="medium"),
                "quota_full": st.column_config.TextColumn("Quota Full At", help="Date/time when quota was hit", width="stretch", disabled=True),
            },
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            height=430,
            key="login_editor"
        )

        btn_save, btn_reload, btn_clear = st.columns([1.2, 1.2, 1.6])

        with btn_save:
            if st.button("Save Credentials Table", icon="🔒", type="primary", width="stretch"):
                records = edited_df.to_dict("records")
                records = [r for r in records if r.get("username") or r.get("note")]
                
                # Map existing quota_full if not present in records 
                # (though it should be there as a column)
                final = [
                    {"active": (r.get("username") == selected_active),
                     "bypass": r.get("bypass", False),
                     "username": r.get("username", ""),
                     "auto_delete": r.get("auto_delete", False),
                     "delete_range": r.get("delete_range", "Last hour"),
                     "note": r.get("note", ""),
                     "quota_full": r.get("quota_full", "")}
                    for r in records
                ]
                save_login_lookup(final)
                st.session_state._login_reload = True
                if "active_account_select" in st.session_state:
                    del st.session_state["active_account_select"]
                st.success("Credentials saved!")
                st.rerun()

        with btn_reload:
            if st.button("Reload Credentials Table", icon="🔄", type="secondary", width="stretch"):
                st.session_state._login_reload = True
                if "active_account_select" in st.session_state:
                    del st.session_state["active_account_select"]
                st.success("Credentials reloaded!")
                st.rerun()

        with btn_clear:
            if st.button("Clear Quota Full Recorded Date", icon="🧹", help="Manually reset all quota timestamps", type="secondary", width="stretch"):
                for r in rows:
                    r["quota_full"] = ""
                save_login_lookup(rows)
                st.session_state._login_reload = True
                st.success("All quota timestamps cleared!")
                st.rerun()

# --- Technical Details ---
with st.expander("Technical Details (config.json)"):
    st.json(config)

with st.expander("Technical Details (user_login_lookup.json)"):
    st.json(load_login_lookup())